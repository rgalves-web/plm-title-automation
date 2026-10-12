"""Receipt per request; known usage survives dispatch errors and process death."""
from src.casefile.operations import require_running
from src.casefile.repo import _json


class UnknownProviderUsage(RuntimeError):
    pass


class ProviderUnavailable(RuntimeError):
    def __init__(self, reason, status_code, request_id='', detail=''):
        self.reason, self.status_code, self.request_id, self.detail = reason, status_code, request_id, detail
        super().__init__(reason)


def rejected_request(exc):
    """Whitelist diagnostic facts; do not persist credentials or raw SDK errors."""
    import re
    code=getattr(exc,'status_code',None)
    body=getattr(exc,'body',{}) or {}
    error=body.get('error',body) if isinstance(body,dict) else {}
    message=str(error.get('message','') if isinstance(error,dict) else '').lower()
    reason={400:'provider_request_invalid',401:'provider_credentials_invalid',
            403:'provider_access_denied',404:'provider_model_unavailable',
            409:'provider_request_conflict',422:'provider_request_invalid',
            429:'provider_rate_limited',529:'provider_overloaded'}.get(code,'provider_request_rejected')
    if code in (400,403) and ('credit balance' in message or 'insufficient credit' in message):
        reason='provider_credit_balance_insufficient'
    request_id=str(getattr(exc,'request_id','') or (body.get('request_id','') if isinstance(body,dict) else ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',request_id): request_id=''
    detail=''
    if code in (400,404,422,500,502,503,504) and reason!='provider_credit_balance_insufficient':
        original=str(error.get('message','') if isinstance(error,dict) else '') or str(exc)
        original=re.sub(r'data:[^\s]+','[image-data]',original)
        original=re.sub(r'sk-[A-Za-z0-9_-]+','[redacted]',original)
        original=re.sub(r'([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@',r'\1[redacted]@',original)
        detail=original[:500]
    return ProviderUnavailable(reason,code,request_id,detail)


class RunAccounting:
    def __init__(self,repo,task,run):
        self.repo,self.task,self.run=repo,task,run
        self.ordinal=0
        self.request_id=None

    def before(self,estimate=None):
        require_running(self.repo,self.task['unit_id'])
        from src.casefile.spending import reserve,installed
        with self.repo.transacao():
            limit_id,amount=reserve(self.repo,self.task['unit_id'],estimate)
            self.ordinal+=1
            if installed(self.repo):
                row=self.repo.conn.execute('INSERT INTO operation_requests(run_id,ordinal,spend_limit_id,reserved_usd) VALUES (%s,%s,%s,%s) RETURNING id',
                    (self.run['id'],self.ordinal,limit_id,amount)).fetchone()
            else:
                row=self.repo.conn.execute('INSERT INTO operation_requests(run_id,ordinal) VALUES (%s,%s) RETURNING id',(self.run['id'],self.ordinal)).fetchone()
            self.request_id=row['id']
            self.repo.conn.execute("UPDATE task_runs SET usage_state='inflight' WHERE id=%s",(self.run['id'],))

    def response(self,msg,usage,cost):
        if msg.usage is None:
            self.failure(UnknownProviderUsage('usage_not_returned'))
            raise UnknownProviderUsage('provider_usage_requires_reconciliation')
        with self.repo.transacao():
            old=self.repo.conn.execute('SELECT * FROM operation_requests WHERE id=%s FOR UPDATE',(self.request_id,)).fetchone()
            if old['status']=='confirmed':
                # A late response must not charge again after a receipt was
                # reconciled by the operator or the same response was saved.
                return
            self.repo.conn.execute(
                "UPDATE operation_requests SET status='confirmed',provider_request_id=%s,usage=%s,cost_usd=%s,finished_at=now() WHERE id=%s",
                (getattr(msg,'request_id',None) or getattr(msg,'_request_id',None) or getattr(msg,'id',''),_json(usage),cost,self.request_id))
            self.repo.registrar_custo(self.task['unit_id'],'tarefa',cost,
                                      {'run_id':self.run['id'],'task_id':self.task['id'],'request_id':self.request_id,'confirmed_response':True})
            self.repo.conn.execute("UPDATE task_runs SET usage_state='confirmed',reserved_usd=greatest(0,reserved_usd-%s),cost_usd=(SELECT coalesce(sum(cost_usd),0) FROM operation_requests WHERE run_id=%s AND status='confirmed') WHERE id=%s",
                                   (cost,self.run['id'],self.run['id']))
            self.repo.operation_event('model.response','process:worker',{'run_id':self.run['id'],'cost_usd':cost,'ordinal':self.ordinal},
                                      unit_id=self.task['unit_id'],task_id=self.task['id'])

    def failure(self,exc):
        nonbillable=getattr(exc,'status_code',None) in (400,401,403,404,409,422,429,529)
        status='nonbillable' if nonbillable else 'unknown'
        with self.repo.transacao():
            rejection=rejected_request(exc)
            self.repo.conn.execute("UPDATE operation_requests SET status=%s,provider_request_id=%s,finished_at=now() WHERE id=%s",(status,rejection.request_id,self.request_id))
            self.repo.conn.execute("UPDATE task_runs SET usage_state=%s WHERE id=%s",('confirmed' if nonbillable else 'unknown',self.run['id']))
            if nonbillable:
                self.repo.conn.execute('UPDATE operation_requests SET provider_request_id=%s WHERE id=%s',
                                       (rejection.request_id,self.request_id))
                self.repo.operation_event('model.rejected','process:worker',
                    {'run_id':self.run['id'],'reason':rejection.reason,'status_code':rejection.status_code,
                     'request_id':rejection.request_id,'billable':False,'error_detail':rejection.detail},
                    unit_id=self.task['unit_id'],task_id=self.task['id'])
            if not nonbillable:
                row=self.repo.conn.execute('SELECT reserved_usd FROM operation_requests WHERE id=%s',(self.request_id,)).fetchone()
                if not row or float(row['reserved_usd'])<=0:
                    self.repo.operation_update(self.task['unit_id'],execution_state='waiting')
                self.repo.operation_event('model.usage_unknown','process:worker',{'run_id':self.run['id'],'error':type(exc).__name__,
                                          'status_code':rejection.status_code,'request_id':rejection.request_id,'error_detail':rejection.detail},
                                          unit_id=self.task['unit_id'],task_id=self.task['id'])
        if not nonbillable:
            raise UnknownProviderUsage('provider_usage_requires_reconciliation') from exc
        return rejection
