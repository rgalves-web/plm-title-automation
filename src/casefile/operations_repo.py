"""Durable operation primitives. Stores observations and explicit decisions."""
from __future__ import annotations

from typing import Any


def _json(value):
    from psycopg.types.json import Json
    return Json(value)


class OperationsRepo:
    def operations_installed(self):
        return bool(self.conn.execute(
            "SELECT to_regclass('operation_cases') IS NOT NULL AS ok").fetchone()['ok'])

    def operation_case(self, unit_id, *, lock=False):
        return self.conn.execute("SELECT * FROM operation_cases WHERE unit_id=%s" +
                                 (" FOR UPDATE" if lock else ""), (unit_id,)).fetchone()

    def operation_cases(self):
        return self.conn.execute(
            "SELECT o.*,u.canonical_name,u.folder_path,u.state,p.name AS project "
            "FROM operation_cases o JOIN units u ON u.id=o.unit_id "
            "JOIN projects p ON p.id=u.project_id ORDER BY o.unit_id").fetchall()

    def operation_register(self, unit_id, scope, profile=None):
        self.conn.execute(
            "INSERT INTO operation_cases(unit_id,scope,profile) VALUES (%s,%s,%s) "
            "ON CONFLICT(unit_id) DO NOTHING", (unit_id,_json(scope),_json(profile or {})))
        return self.operation_case(unit_id)

    def operation_update(self, unit_id, **fields):
        allowed = {'execution_state','approved_budget_usd','approval','scope','profile','last_dispatched_at'}
        if not fields or set(fields)-allowed:
            raise ValueError('invalid_operation_fields')
        values = [_json(v) if k in ('approval','scope','profile') else v for k,v in fields.items()]
        return self.conn.execute("UPDATE operation_cases SET " +
                                 ','.join(k+'=%s' for k in fields) +
                                 " WHERE unit_id=%s RETURNING *", (*values,unit_id)).fetchone()

    def operation_event(self, kind, actor, detail=None, *, unit_id=None, task_id=None):
        with self.conn.transaction():
            if unit_id is not None:
                self.conn.execute("UPDATE operation_cases SET revision=revision+1 WHERE unit_id=%s",(unit_id,))
            # Allocate IDs in commit order so an SSE cursor cannot skip an
            # earlier, still-uncommitted event from another executor.
            self.conn.execute('SELECT pg_advisory_xact_lock(781876,5)')
            return self.conn.execute(
                "INSERT INTO operation_events(unit_id,task_id,kind,actor,detail) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING *",
                (unit_id,task_id,kind,actor,_json(detail or {}))).fetchone()

    def operation_events(self, after=0, unit_id=None, limit=250, *, task_id=None, kind=None, latest=False):
        rows=self.conn.execute(
            "SELECT * FROM operation_events WHERE id>%s AND (%s::bigint IS NULL OR unit_id=%s) "
            "AND (%s::bigint IS NULL OR task_id=%s) AND (%s::text IS NULL OR kind=%s) "
            "ORDER BY id " + ('DESC' if latest else 'ASC') + " LIMIT %s",
            (after,unit_id,unit_id,task_id,task_id,kind,kind,min(max(int(limit),1),1000))).fetchall()
        return list(reversed(rows)) if latest else rows

    def operation_last_event(self):
        return self.conn.execute("SELECT coalesce(max(id),0) AS id FROM operation_events").fetchone()['id']

    def operation_command(self, command_id):
        return self.conn.execute("SELECT * FROM operation_commands WHERE command_id=%s",(command_id,)).fetchone()

    def operation_save_command(self, command_id, body_sha256, unit_id, response):
        self.conn.execute("INSERT INTO operation_commands(command_id,body_sha256,unit_id,response) "
                          "VALUES (%s,%s,%s,%s)",(command_id,body_sha256,unit_id,_json(response)))

    def operation_artifact(self, artifact_id):
        return self.conn.execute("SELECT * FROM operation_artifacts WHERE id=%s",(artifact_id,)).fetchone()

    def operation_artifacts(self, unit_id, kind=None):
        return self.conn.execute(
            "SELECT a.* FROM operation_artifacts a WHERE (a.unit_id=%s OR EXISTS "
            "(SELECT 1 FROM operation_artifact_links l WHERE l.artifact_id=a.id AND l.unit_id=%s)) "
            "AND (%s::text IS NULL OR a.kind=%s) ORDER BY a.id",(unit_id,unit_id,kind,kind)).fetchall()

    def operation_add_artifact(self, unit_id, kind, path, sha256, size_bytes, metadata=None, task_id=None):
        return self.conn.execute(
            "INSERT INTO operation_artifacts(unit_id,task_id,kind,path,sha256,size_bytes,metadata) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(unit_id,path,sha256) DO UPDATE "
            "SET metadata=operation_artifacts.metadata RETURNING *",
            (unit_id,task_id,kind,str(path),sha256,size_bytes,_json(metadata or {}))).fetchone()

    # --- Function files (issues 02/03): index of write-once Case files ------
    def function_file_add(self, unit_id, task_id, run_id, direction, ordinal,
                          relative, sha256, size_bytes, status, reason=None,
                          artifact_id=None):
        return self.conn.execute(
            "INSERT INTO function_files(unit_id,task_id,run_id,direction,ordinal,"
            "relative,sha256,size_bytes,status,reason,artifact_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (unit_id,task_id,run_id,direction,ordinal,relative,sha256,
             size_bytes,status,_json(list(reason or [])),artifact_id)).fetchone()

    def function_file(self, file_id):
        return self.conn.execute("SELECT * FROM function_files WHERE id=%s",
                                 (file_id,)).fetchone()

    def function_files(self, *, task_id=None, run_id=None, direction=None,
                       unit_id=None, sha256=None):
        return self.conn.execute(
            "SELECT * FROM function_files WHERE (%s::bigint IS NULL OR task_id=%s) "
            "AND (%s::bigint IS NULL OR run_id=%s) AND (%s::text IS NULL OR direction=%s) "
            "AND (%s::bigint IS NULL OR unit_id=%s) AND (%s::text IS NULL OR sha256=%s) "
            "ORDER BY id",(task_id,task_id,run_id,run_id,direction,direction,
                           unit_id,unit_id,sha256,sha256)).fetchall()

    def function_file_applied(self, file_id):
        got = self.conn.execute(
            "UPDATE function_files SET applied_at=now() WHERE id=%s AND direction='output' "
            "AND status='accepted' AND applied_at IS NULL RETURNING *",(file_id,)).fetchone()
        if got is None:
            raise ValueError('function_output_not_applicable')
        return got

    def operation_link_artifact(self, artifact_id, unit_id, allocation, actor):
        self.conn.execute(
            "INSERT INTO operation_artifact_links(artifact_id,unit_id,allocation,linked_by) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (artifact_id,unit_id,_json(allocation),actor))

    def operation_source_request(self, unit_id, source, request_key, request, *, task_id=None, impact=''):
        return self.conn.execute(
            "INSERT INTO operation_source_jobs(unit_id,task_id,source,request_key,request,impact) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(unit_id,request_key) DO UPDATE "
            "SET request=operation_source_jobs.request RETURNING *",
            (unit_id,task_id,source,request_key,_json(request),impact)).fetchone()

    def operation_sources(self, unit_id):
        return self.conn.execute("SELECT * FROM operation_source_jobs WHERE unit_id=%s ORDER BY id",(unit_id,)).fetchall()

    def operation_source_result(self, job_id, status, receipt):
        return self.conn.execute("UPDATE operation_source_jobs SET status=%s,receipt=%s WHERE id=%s RETURNING *",
                                 (status,_json(receipt),job_id)).fetchone()

    def operation_resource(self, resource, holder, seconds=120):
        row = self.conn.execute(
            "INSERT INTO operation_resources(resource,holder,lease_until) VALUES (%s,%s,now()+%s*interval '1 second') "
            "ON CONFLICT(resource) DO UPDATE SET holder=EXCLUDED.holder,lease_until=EXCLUDED.lease_until "
            "WHERE operation_resources.lease_until<now() OR operation_resources.holder=EXCLUDED.holder RETURNING resource",
            (resource,holder,seconds)).fetchone()
        return row is not None

    def operation_release_resource(self, resource, holder):
        self.conn.execute("DELETE FROM operation_resources WHERE resource=%s AND holder=%s",(resource,holder))

    def operation_requirements(self, unit_id, sha256=None):
        return self.conn.execute(
            "SELECT * FROM operation_requirements WHERE unit_id=%s AND (%s::text IS NULL OR report_sha256=%s) "
            "ORDER BY report_sha256,criterion",(unit_id,sha256,sha256)).fetchall()

    def operation_report_requirements(self, unit_id, sha256):
        self.conn.execute("UPDATE operation_requirements SET status='invalidated',updated_at=now() "
                          "WHERE unit_id=%s AND report_sha256<>%s AND status IN ('observed','verified')",(unit_id,sha256))
        for n in range(1,7):
            self.conn.execute("INSERT INTO operation_requirements(unit_id,report_sha256,criterion) VALUES (%s,%s,%s) "
                              "ON CONFLICT DO NOTHING",(unit_id,sha256,'Q'+str(n)))

    def operation_requirement_record(self, unit_id, sha256, criterion, status, evidence, actor):
        self.operation_report_requirements(unit_id,sha256)
        self.conn.execute("UPDATE operation_requirements SET status=%s,evidence=%s,reviewed_by=%s,updated_at=now() "
                          "WHERE unit_id=%s AND report_sha256=%s AND criterion=%s",
                          (status,_json(evidence),actor,unit_id,sha256,criterion))

    def operation_add_lesson(self, unit_id, task_id, version, card):
        return self.conn.execute("INSERT INTO operation_lessons(unit_id,task_id,version,card) VALUES (%s,%s,%s,%s) "
                                 "ON CONFLICT(version) DO UPDATE SET card=operation_lessons.card RETURNING *",
                                 (unit_id,task_id,version,_json(card))).fetchone()

    def operation_lessons(self, unit_id=None):
        return self.conn.execute("SELECT * FROM operation_lessons WHERE %s::bigint IS NULL OR unit_id=%s ORDER BY id",
                                 (unit_id,unit_id)).fetchall()

    def operation_update_lesson(self, lesson_id, status, *, verification=None, decision=None, release_id=None):
        self.conn.execute("UPDATE operation_lessons SET status=%s,verification=coalesce(%s::jsonb,verification),"
                          "decision=coalesce(%s::jsonb,decision),release_id=coalesce(%s,release_id) WHERE id=%s",
                          (status,_json(verification) if verification is not None else None,
                           _json(decision) if decision is not None else None,release_id,lesson_id))

    def operation_heartbeat(self, name, detail):
        self.conn.execute("INSERT INTO operation_services(name,detail) VALUES (%s,%s) ON CONFLICT(name) "
                          "DO UPDATE SET heartbeat_at=now(),detail=EXCLUDED.detail",(name,_json(detail)))

    def operation_services(self):
        return self.conn.execute("SELECT *,heartbeat_at>now()-interval '30 seconds' AS online FROM operation_services").fetchall()

    def operation_dispatch_cases(self):
        return self.conn.execute("SELECT * FROM operation_cases WHERE execution_state='running' "
                                 "ORDER BY last_dispatched_at NULLS FIRST,unit_id").fetchall()

    def operation_enqueue(self,uid,ref,role,title,data,schema,budget,parent_task_id=None):
        self.conn.execute('INSERT INTO operation_followups(unit_id,ref,role,title,input_json,output_schema,budget_usd,parent_task_id) '
                           'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(unit_id,ref) DO NOTHING',
                           (uid,ref,role,title,_json(data),schema,budget,parent_task_id))

    def operation_followups(self,uid):
        return self.conn.execute('SELECT * FROM operation_followups WHERE unit_id=%s AND task_id IS NULL ORDER BY id',(uid,)).fetchall()

    def operation_allocate(self,uid):
        with self.conn.transaction():
            case=self.operation_case(uid,lock=True)
            committed=sum(t['budget_usd'] for t in self.tarefas(uid) if t['status'] in ('planejada','pronta','em_execucao'))
            available=float(case['approved_budget_usd'])-self.custo_acumulado(uid)-committed
            created=[]
            for item in self.operation_followups(uid):
                if float(item['budget_usd'])>available:
                    break
                old=self.tarefa_por_ref(uid,item['ref'])
                if old is None:
                    old=self.criar_tarefas(uid,[{'ref':item['ref'],'role':item['role'],'pack':'title-texas-surface',
                        'title':item['title'],'input_json':item['input_json'],'output_schema':item['output_schema'],
                        'acceptance':'Saída rastreável; julgamento pela função e revisão independente.',
                        'depends_on_refs':[],'budget_usd':float(item['budget_usd']),'priority':-1,
                        'verificacao':'nenhuma' if item['role']=='verificador' or item['output_schema']=='comparacao_independente' else 'operador'}],
                        'process:operacao')[0]
                    if item.get('parent_task_id') is not None:
                        # Issue 10: the follow-up keeps the task it came from.
                        old=self.conn.execute('UPDATE tasks SET parent_task_id=%s WHERE id=%s RETURNING *',
                                              (item['parent_task_id'],old['id'])).fetchone()
                    available-=float(item['budget_usd'])
                self.conn.execute('UPDATE operation_followups SET task_id=%s WHERE id=%s',(old['id'],item['id']))
                created.append(old['id'])
            self.promover_prontas(uid,'process:operacao')
            return created
