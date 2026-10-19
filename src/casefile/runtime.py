"""Tools and result handlers for the operational roles. Models judge content."""
from __future__ import annotations
import json
import re
from pathlib import Path

from src.casefile import agentes,case_records,function_files,orquestracao,worker
from src.casefile.operations import PACK,require_running,serializable
from src.casefile.storage import checked_artifact,digest_file,write_bytes
from src.casefile.training import digest


class PageOutOfRange(ValueError):
    """Issue 16: a page that is not in the document, with its page count."""


class CorpusSearchError(ValueError):
    """Issue 16: the local corpus search failed; named, never internal."""


def tool(name,description,properties=None,required=None):
    return {'name':name,'description':description,'input_schema':{'type':'object','properties':properties or {},'required':required or []}}


def cited_pages(locator):
    """Expand physical page locators only; never infer a missing citation."""
    pages=[]
    for part in str(locator).split(','):
        match=re.fullmatch(r'\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*',part)
        if not match:return []
        first=int(match[1]);last=int(match[2] or first)
        if first<1 or last<first or last-first>100:return []
        pages.extend(str(n) for n in range(first,last+1))
    return list(dict.fromkeys(pages))


def reader(repo,task):
    from src.casefile.acervo import Acervo,AcervoIndex,Entrada
    allowed=[a for a in repo.operation_artifacts(task['unit_id']) if a['kind']=='source']
    profile=repo.operation_case(task['unit_id'])['profile']
    references={profile.get(k) for k in ('template_artifact_id','lead_example_artifact_id') if profile.get(k)}
    allowed=[a for a in allowed if a['id'] not in references]
    if task['role']=='verificador':
        allowed=[a for a in allowed if a['sha256']==task['input_json'].get('source_sha256')]
    entries=[Entrada('sha256:'+a['sha256']+Path(a['path']).suffix.lower(),Path(a['path']),'','unit_files') for a in allowed]
    return Acervo(AcervoIndex(entries)),{a['sha256']:a for a in allowed}


def tools(repo,task):
    acervo,artifacts=reader(repo,task)
    def read_page(documento,pagina=1,modo='texto',**_):
        sha=str(documento).removeprefix('sha256:').split('.',1)[0]
        artifact=artifacts.get(sha)
        if not artifact:
            raise ValueError('source_outside_task_evidence')
        checked_artifact(artifact)
        if task['role']=='verificador' and str(pagina) not in cited_pages(task['input_json'].get('pagina')):
            raise ValueError('blind_verifier_page_mismatch')
        name='sha256:'+sha+Path(artifact['path']).suffix.lower()
        from src.infra.corpus import XLSX_SUFFIXES
        if Path(artifact['path']).suffix.lower() not in XLSX_SUFFIXES and re.fullmatch(r'\s*-?\d+\s*',str(pagina)):
            # Issue 16: a page past the end is named, with the page count,
            # in every mode; never empty text or an off-by-one IndexError.
            total=acervo.page_count(name)
            if not 1<=int(str(pagina))<=total:
                raise PageOutOfRange(f'page_out_of_range: o documento sha256:{sha} tem {total} '
                                     f'página(s); a página {str(pagina).strip()} não existe')
        result=acervo.read_page(name,pagina,modo)
        if result.get('kind') in ('text','image'):
            import hashlib
            payload=result.get('png') or result.get('text','').encode('utf-8')
            repo.operation_event('source.page_read','process:'+task['role'],
                                  {'run_id':task.get('_operation_run_id'),'source_sha256':sha,'page':str(pagina),
                                   'payload_sha256':hashlib.sha256(payload).hexdigest()},
                                  unit_id=task['unit_id'],task_id=task['id'])
        return result
    read_spec=tool('read_page','Leia uma página da fonte identificada por sha256; nunca outro caso.',
                   {'documento':{'type':'string'},'pagina':{'type':['string','integer']},'modo':{'enum':['texto','imagem','ocr']}},['documento','pagina','modo'])
    if task['role']=='verificador':
        return {'ler_pagina_confirmada':(dict(read_spec,name='ler_pagina_confirmada'),read_page)}
    def bounded(value):
        if isinstance(value,list):return [bounded(v) for v in value]
        if not isinstance(value,dict):return value
        return {**{k:bounded(v) for k,v in value.items() if k!='results'},**({'results':value['results'][:25],
                'next_result_offset':25 if len(value['results'])>25 else None,'result_population':len(value['results'])} if isinstance(value.get('results'),list) else {})}
    def case_file(secao='pesquisas',offset=0,limite=25,registro_id=None,text_offset=0,text_limite=6000,filtro=None):
        uid=task['unit_id']
        sections={'pesquisas':lambda:repo.pesquisas(uid),'claims':lambda:repo.claims_da_unit(uid),
                  'documentos':lambda:[{'id':a['id'],'documento':'sha256:'+a['sha256'],'nome':Path(a['path']).name,
                                        'metadata':a['metadata']} for a in repo.operation_artifacts(uid) if a['kind']=='source'],
                  'tarefas':lambda:repo.tarefas(uid),'escalonamentos':lambda:repo.escalonamentos(uid,abertos=True),
                  'decisoes':lambda:repo.decisoes_da_unit(uid),'fontes':lambda:repo.operation_sources(uid),
                  'qa':lambda:repo.operation_requirements(uid),'licoes':lambda:repo.operation_lessons(uid)}
        sections['eventos']=lambda:repo.operation_events(unit_id=uid,limit=1000,latest=True)
        sections['controles']=lambda:[a for a in repo.operation_artifacts(uid) if a['kind']=='control_record']
        sections['registros_execucao']=lambda:[a for a in repo.operation_artifacts(uid) if a['kind'] in ('run_record','output_attempt','function_output','provider_rejection','qa_observation','research_observation','retrospective_observation','claim_checkpoint')]
        sections['resultados']=lambda:[{'id':t['id'],'task_id':t['id'],'role':t['role'],'runs':repo.runs_da_tarefa(t['id'])}
                                        for t in repo.tarefas(uid) if t['id']!=task['id'] and t['status']!='em_execucao']
        if secao not in sections:
            raise ValueError('unknown_case_section')
        rows=sections[secao]()
        if registro_id is not None:
            row=next((r for r in rows if r.get('id')==int(registro_id)),None)
            if row is None:raise ValueError('case_section_record_not_found')
            full=json.dumps(serializable(row),ensure_ascii=False)
            start=max(0,int(text_offset));length=min(max(1,int(text_limite)),6000)
            return {'section':secao,'record_id':registro_id,'text':full[start:start+length],
                    'total_characters':len(full),'next_text_offset':start+length if start+length<len(full) else None,
                    'historical_record_is_not_current_approval':secao=='decisoes'}
        if secao=='fontes':rows=bounded(rows)
        if filtro:
            needle=str(filtro).casefold()
            rows=[r for r in rows if needle in ' '.join(str(r.get(k,'')) for k in ('title','question','path','nome')).casefold() or needle in str(r.get('metadata',{}).get('display_name','')).casefold()]
        size=min(max(int(limite),1),100)
        offset=max(int(offset),0)
        selected=[];characters=0
        for row in rows[offset:offset+size]:
            full=json.dumps(serializable(row),ensure_ascii=False)
            shown=serializable(row)
            if len(full)>5000:
                shown={k:row[k] for k in ('id','kind','question','title','role','status','task_id') if k in row}
                shown={**serializable(shown),'preview':full[:1800],'total_characters':len(full),
                       'read_full_with':{'secao':secao,'registro_id':row.get('id'),'text_offset':0}}
            length=len(json.dumps(shown,ensure_ascii=False))
            if selected and characters+length>24000:break
            selected.append(shown);characters+=length
        end=offset+len(selected)
        return {'total':len(rows),'rows':selected,'next_offset':end if len(rows)>end else None,
                'response_characters':characters,'historical_record_is_not_current_approval':secao=='decisoes'}
    def search_source(fonte,terms,index=None,start_date=None,through_date=None,prior_reference=None,reason=None):
        from src.casefile.source_adapters import execute
        request={'terms':terms}
        for key,value in [('index',index),('start_date',start_date),('through_date',through_date),('prior_reference',prior_reference),('reason',reason)]:
            if value:
                request[key]=value
        return bounded(execute(repo,task,fonte,request))
    def read_search_results(job_id,offset=0,limite=25):
        job=next((j for j in repo.operation_sources(task['unit_id']) if j['id']==job_id),None)
        if not job:raise ValueError('search_receipt_outside_case')
        receipt=job['receipt'];rows=receipt.get('results',[])
        offset=max(0,int(offset));limit=min(max(1,int(limite)),50)
        return serializable({'job_id':job_id,'request':job['request'],'metadata':{k:v for k,v in receipt.items() if k!='results'},
            'results':rows[offset:offset+limit],'saved_total':len(rows),'next_offset':offset+limit if len(rows)>offset+limit else None})
    def capture_source(fonte,localizador):
        from src.casefile.source_adapters import capture
        return capture(repo,task,fonte,localizador)
    def inspect_template(offset=0,limite=100):
        from src.casefile.report_writer import inspected
        profile=repo.operation_case(task['unit_id'])['profile']
        identifier=profile.get('template_artifact_id')
        artifact=repo.operation_artifact(identifier) if identifier else None
        if not artifact:
            return {'blocked':True,'reason':'template_and_lead_example_not_selected','owner':'Renato'}
        result=inspected(checked_artifact(artifact),offset,limite)
        return {'artifact_id':identifier,'sha256':artifact['sha256'],**result}
    def read_trace(offset=0,limite=25):
        trace={'events':case_file('eventos',offset,limite),
                'escalations':case_file('escalonamentos',0,15),
                'execution_results':case_file('resultados',0,15),
                'execution_artifacts':case_file('registros_execucao',0,15)}
        raw=json.dumps(trace,ensure_ascii=False,indent=2).encode()
        path,sha=write_bytes(task['unit_id'],f"execucoes/trilha_tarefa_{task['id']}_{digest(trace)[:12]}.json",raw)
        source=repo.operation_add_artifact(task['unit_id'],'run_record',path,sha,len(raw),
            {'display_name':'Trilha citável · tarefa '+str(task['id']),'title_acceptance':False},task['id'])
        lines=['Registro factual de execução; não aprova title nem aprendizado.']
        for row in repo.tarefas(task['unit_id']):
            for run in repo.runs_da_tarefa(row['id']):
                if run['finished_at'] is None:continue
                lines.append(f"Tarefa {row['id']}; execução {run['id']}; função {row['role']}; modelo {run['model']}; tokens de entrada {run['tokens_in']}; tokens de saída {run['tokens_out']}; custo conhecido USD {run['cost_usd']}; parada {run['stop_reason']}; erros {', '.join(run['validation_errors'])}.")
        text='\n'.join(lines[-51:])
        data=text.encode('utf-8')
        path,sha=write_bytes(task['unit_id'],f"execucoes/trilha_literal_{task['id']}_{digest(text)[:12]}.txt",data)
        literal=repo.operation_add_artifact(task['unit_id'],'run_record',path,sha,len(data),
            {'display_name':'Registro literal citável · tarefa '+str(task['id']),'source_trace_artifact_id':source['id'],'title_acceptance':False},task['id'])
        return {'artifact_id':literal['id'],'sha256':sha,'citation_source_text':text,'structured_trace_artifact_id':source['id'],'trace':trace,
            'citation_instruction':'Copie quote literalmente de citation_source_text e use o artifact_id fornecido. Não invente ID de artefato a partir de evento ou tarefa, nem compacte espaços/quebras de um JSON para produzir uma citação.'}
    def inspect_document(artifact_id):
        artifact=next((a for a in repo.operation_artifacts(task['unit_id']) if a['id']==artifact_id),None)
        if not artifact:
            raise ValueError('artifact_outside_case')
        path=checked_artifact(artifact)
        result={'artifact_id':artifact_id,'path':str(path),'sha256':artifact['sha256'],'metadata':artifact['metadata']}
        if path.suffix.lower()=='.pdf':
            import fitz
            with fitz.open(path) as document:
                result['pages']=len(document)
        return result
    def read_control(artifact_id,offset=0,limite=6000):
        from src.casefile.training import text_parts
        artifact=next((a for a in repo.operation_artifacts(task['unit_id']) if a['id']==artifact_id and a['kind'] in ('control_record','run_record','qa_observation','operator_evidence','knowledge_source','output_attempt','function_output','provider_rejection','research_observation','retrospective_observation','claim_checkpoint')),None)
        if not artifact: raise ValueError('case_control_required')
        path=checked_artifact(artifact)
        if path.suffix.lower() not in ('.md','.txt','.json','.csv','.html','.docx','.xlsx'):
            raise ValueError('control_text_format_not_supported')
        text='\n'.join(locator+'\n'+part for locator,part in text_parts(path))
        offset=max(0,int(offset));limit=min(max(1,int(limite)),6000)
        return {'artifact_id':artifact_id,'sha256':artifact['sha256'],'historical_acceptance':False,
                'text':text[offset:offset+limit],'total_characters':len(text),'next_offset':offset+limit if offset+limit<len(text) else None}
    def update_task(task_id,motivo,budget_usd=None,priority=None,cancelar=False):
        import math
        if task['role']!='coordenador' or not motivo.strip():
            raise ValueError('coordinator_and_reason_required')
        with repo.transacao():
            case=repo.operation_case(task['unit_id'],lock=True)
            target=repo.tarefa(task_id)
            if not target or target['unit_id']!=task['unit_id'] or target['id']==task['id'] or target['status'] not in ('planejada','pronta','bloqueada'):
                raise ValueError('unstarted_or_blocked_case_task_required')
            if cancelar:
                repo.transicionar_tarefa(task_id,(target['status'],),'cancelada','process:coordenador',motivo)
            else:
                amount=float(budget_usd if budget_usd is not None else target['budget_usd'])
                spent=sum(float(r['cost_usd']) for r in repo.runs_da_tarefa(task_id))
                committed=sum(float(t['budget_usd']) for t in repo.tarefas(task['unit_id']) if t['id'] not in (task_id,task['id']) and t['status'] in ('planejada','pronta','em_execucao'))
                if not math.isfinite(amount) or amount<spent or repo.custo_acumulado(task['unit_id'])+committed+amount>float(case['approved_budget_usd']):
                    raise ValueError('task_reallocation_exceeds_approved_budget')
                repo.conn.execute('UPDATE tasks SET budget_usd=%s,priority=%s,updated_at=now() WHERE id=%s',
                    (amount,int(priority if priority is not None else target['priority']),task_id))
                if target['status']=='bloqueada':
                    if repo.task_attempts(task_id)>=3:raise ValueError('two_new_attempts_exhausted')
                    repo.transicionar_tarefa(task_id,('bloqueada',),'planejada','process:coordenador',motivo)
                repo.promover_prontas(task['unit_id'],'process:coordenador')
            repo.operation_event('task.reallocated','process:coordenador',{'target_task_id':task_id,'budget_usd':budget_usd,'cancelled':cancelar,'reason':motivo},unit_id=task['unit_id'],task_id=task['id'])
            return serializable(repo.tarefa(task_id))
    def escalate(motivo,pergunta,opcoes,artifact_id=None,pagina=None,trecho=None,tipo=None):
        evidence={}
        if artifact_id is not None:
            artifact=next((a for a in repo.operation_artifacts(task['unit_id']) if a['id']==artifact_id),None)
            if not artifact:raise ValueError('escalation_evidence_outside_case')
            checked_artifact(artifact)
            evidence={'artifact_id':artifact_id,'sha256':artifact['sha256'],'page':pagina,'quote':trecho}
        if orquestracao._in_open_lot(repo,task['unit_id']):
            from src.casefile import autonomy
            identifier=autonomy.lot_escalation(repo,task,str(tipo or ''),motivo,pergunta,evidence)
            return {'escalation_id':identifier,'owner':'Renato','external_message_sent':False}
        question=pergunta+(('\nEvidência: '+json.dumps(evidence,ensure_ascii=False)) if evidence else '')
        existing=next((e for e in repo.escalonamentos(task['unit_id'],abertos=True) if e['motivo']==motivo and e['pergunta']==question),None)
        if existing:return {'escalation_id':existing['id'],'owner':'Renato','external_message_sent':False}
        identifier=repo.abrir_escalonamento(task['unit_id'],task['id'],motivo,question,opcoes)
        repo.operation_event('decision.requested','process:'+task['role'],{'escalation_id':identifier,'owner':'Renato','evidence':evidence},unit_id=task['unit_id'],task_id=task['id'])
        return {'escalation_id':identifier,'owner':'Renato','external_message_sent':False}
    def list_docs():
        return case_file('documentos',0,100)
    def checkpoint_claims(claims):
        if task['role'] not in ('examinador','arbitro') or task['input_json'].get('independent_comparison'):
            raise ValueError('primary_examination_checkpoint_required')
        output={'claims':claims}
        errors=agentes.validar_saida('claims',output)
        if not errors:errors=check_source_claims(repo,task,output)
        if errors:raise ValueError(';'.join(errors[:10]))
        run=repo.run(task.get('_operation_run_id'))
        if not run or run['finished_at'] or run['task_id']!=task['id']:
            raise ValueError('active_task_run_required')
        with repo.transacao():
            ids=persist_claims(repo,task,output,run['operation_session_id'])
            for cid in ids:
                queue_claim_review(repo,task['unit_id'],repo.claim(cid),parent=task['id'])
            repo.operation_event('claims.checkpointed','process:examinador',
                {'run_id':run['id'],'claim_ids':ids,'task_completed':False},unit_id=task['unit_id'],task_id=task['id'])
        return {'claim_ids':ids,'task_completed':False,'independent_review_queued':True}
    def search_corpus(termo):
        # Issue 16: results or a named error; an internal failure is never
        # passed through as if it were the search's answer.
        try:
            return _search_corpus(termo)
        except Exception as exc:
            raise CorpusSearchError(f'corpus_search_failed: {type(exc).__name__}; a busca no acervo '
                                    'local não foi feita e nada foi concluído sobre presença ou '
                                    'ausência') from exc
    def _search_corpus(termo):
        key=digest({'kind':'local_corpus_text','term':termo,'artifacts':sorted(artifacts)})
        job=repo.operation_source_request(task['unit_id'],'local',key,{'kind':'local_corpus_text','terms':[termo]},task_id=task['id'])
        if job['status']=='complete':
            receipt=job['receipt']
            return {'job_id':job['id'],'cached':True,'results':receipt['results'][:25],
                    'next_result_offset':25 if len(receipt['results'])>25 else None,'populations':receipt['populations'],
                    'registry_search':False,'hint':'Use ler_resultados_busca para recuperar todos os resultados; controles e logs são consultados em ler_case_file(secao=controles,filtro=termo).'}
        result=acervo.search(termo)
        hits=[]
        needle=termo.casefold()
        for sha,a in artifacts.items():
            if needle in a['metadata'].get('display_name',Path(a['path']).name).casefold():
                hits.append({'documento':'sha256:'+sha,'nome':a['metadata'].get('display_name',Path(a['path']).name)})
        result['no_nome']=hits
        counts={k:len(v) for k,v in result.items() if isinstance(v,list)}
        saved=[]
        for key in ('no_nome','no_texto','nao_pesquisavel_sem_ocr'):
            for value in result.get(key,[]):
                saved.append({'kind':key,**(value if isinstance(value,dict) else {'documento':value})})
        repo.operation_source_result(job['id'],'complete',{'results':saved,'populations':counts,'registry_search':False})
        return {**{k:v[:25] if isinstance(v,list) else v for k,v in result.items()},'job_id':job['id'],
                'populations':counts,'limited_reply':True,'next_result_offset':25 if len(saved)>25 else None,
                'file_name_matches_are_not_document_findings':True,
                'hint':'Para nomes de controles e logs, consulte ler_case_file(secao=controles,filtro=termo), depois ler_controle por ID. Nomes e texto local não substituem busca registral.'}
    items={
        'read_page':(read_spec,read_page),
        'registrar_claims':(tool('registrar_claims','Persista imediatamente um pequeno lote de claims no esquema da tarefa. Cada um recebe revisão independente; esta gravação não conclui a tarefa.',{'claims':{'type':'array','items':{'type':'object'}}},['claims']),checkpoint_claims),
        'ler_case_file':(tool('ler_case_file','Consulte o registro deste caso com paginação e IDs.',
                            {'secao':{'type':'string'},'offset':{'type':'integer'},'limite':{'type':'integer'},
                             'registro_id':{'type':'integer','description':'Leia um registro completo em trechos de JSON; use o ID da listagem.'},
                             'text_offset':{'type':'integer'},'text_limite':{'type':'integer'},'filtro':{'type':'string','description':'Filtre o título, nome ou caminho do registro; seleção textual não é julgamento de relevância.'}}),case_file),
        'list_documents':(tool('list_documents','Liste fontes registradas deste caso.'),list_docs),
        'search_corpus':(tool('search_corpus','Busque texto no acervo registrado; nomes não comprovam relevância.',{'termo':{'type':'string'}},['termo']),search_corpus),
        'pesquisar_fonte':(tool('pesquisar_fonte','Execute pesquisa na fonte aprovada e registre recibo ou dependência.',
                              {'fonte':{'type':'string'},'terms':{'type':'array','items':{'type':'string'}},
                               'index':{'enum':['grantor','grantee','combined']},'start_date':{'type':'string'},'through_date':{'type':'string'},'prior_reference':{'type':'string'},'reason':{'type':'string'}},['fonte','terms']),search_source),
        'ler_resultados_busca':(tool('ler_resultados_busca','Leia uma janela dos resultados completos salvos, mantendo total e próxima página.',{'job_id':{'type':'integer'},'offset':{'type':'integer'},'limite':{'type':'integer'}},['job_id']),read_search_results),
        'capturar_preview':(tool('capturar_preview','Capture todas as páginas de um preview autorizado; compra e download não são permitidos.',
                                {'fonte':{'type':'string'},'localizador':{'type':'string'}},['fonte','localizador']),capture_source),
        'inspecionar_template':(tool('inspecionar_template','Leia campos, estilos, fórmulas e identidade do template selecionado com paginação.',{'offset':{'type':'integer'},'limite':{'type':'integer'}}),inspect_template),
        'inspecionar_documento':(tool('inspecionar_documento','Confira arquivo, hash e número real de páginas.',{'artifact_id':{'type':'integer'}},['artifact_id']),inspect_document),
        'ler_controle':(tool('ler_controle','Leia registros históricos com paginação; observações não provam aprovação.',{'artifact_id':{'type':'integer'},'offset':{'type':'integer'},'limite':{'type':'integer'}},['artifact_id']),read_control),
        'atualizar_tarefa':(tool('atualizar_tarefa','Redistribua orçamento/prioridade ou cancele tarefa sem execução, dentro dos limites aprovados.',{'task_id':{'type':'integer'},'motivo':{'type':'string'},'budget_usd':{'type':'number'},'priority':{'type':'integer'},'cancelar':{'type':'boolean'}},['task_id','motivo']),update_task),
        'abrir_escalonamento':(tool('abrir_escalonamento','Prepare decisão ou consulta ao SME, com evidência e responsável; nenhum envio externo. Dentro de um lote, só credencial, documento pago ou comunicação externa (tipo); o resto se pesquisa nas fontes do job ou vira lacuna declarada.',{'motivo':{'type':'string'},'pergunta':{'type':'string'},'opcoes':{'type':'array','items':{'type':'string'}},'artifact_id':{'type':'integer'},'pagina':{'type':'string'},'trecho':{'type':'string'},'tipo':{'enum':['credencial','documento_pago','comunicacao_externa']}},['motivo','pergunta','opcoes']),escalate),
        'ler_trilha_da_unit':(tool('ler_trilha_da_unit','Leia registros reais de execução, correções e artefatos de origem, com paginação.',{'offset':{'type':'integer'},'limite':{'type':'integer'}}),read_trace),
        'ler_escalonamentos':(tool('ler_escalonamentos','Leia questões abertas deste caso.'),lambda:case_file('escalonamentos'))}
    # Preserve the reading name used by the role cards. Both names share the
    # same evidence boundary and page receipt; no second execution path.
    items['ler_pagina'] = (dict(read_spec, name='ler_pagina'), read_page)
    return items


def context(repo,task):
    case=repo.operation_case(task['unit_id'])
    if task['role']=='verificador':
        if task['output_schema']=='revisao_licao':
            lesson=next(l for l in repo.operation_lessons(task['unit_id']) if l['id']==task['input_json']['lesson_id'])
            sources=[]
            for source in lesson['card']['sources']:
                from src.casefile.training import text_parts
                if digest_file(source['path'])!=source['sha256']:
                    raise ValueError('lesson_source_changed')
                text='\n'.join(t for _,t in text_parts(Path(source['path'])))
                at=text.find(source['quote'])
                if at<0:raise ValueError('lesson_literal_quote_missing')
                start=max(0,at-2000);end=min(len(text),max(start+12000,at+len(source['quote'])+2000))
                sources.append({**source,'text':text[start:end],'text_offset':start,'source_characters':len(text)})
            return '\nVerifique esta candidata contra as fontes e a interpretação, sem aprovar publicação. Tokens por execução são agregados de várias chamadas: não representam uma única chamada. Não confirmar interpretação que a fonte não sustenta; explicar a correção necessária no reason e devolver source_quotes_confirmed=false nesse caso.\n'+json.dumps({'candidate':lesson['card'],'sources':sources},ensure_ascii=False)
        # No scope decisions, training, earlier conclusions or original value.
        return '\nExtração independente: leia TODAS as páginas físicas identificadas, uma por chamada ler_pagina_confirmada, e responda à pergunta neutra.\n'+json.dumps({**task['input_json'],'paginas_fisicas':cited_pages(task['input_json'].get('pagina'))},ensure_ascii=False)
    return '\nOPERAÇÃO — escopo e limites aprovados:\n'+json.dumps(serializable({
        'scope':case['scope'],'budget_usd':float(case['approved_budget_usd']),
        'approval':case['approval'],
        'task_budget_usd':float(task['budget_usd']),
        'claim_types':repo.tipos_de_claim() if task['role'] in ('examinador','arbitro') else {},
        'current_template':{k:case['profile'].get(k) for k in ('template_artifact_id','lead_example_artifact_id','sample_data_clearance','configuration_note')},
        'open_research_ids':['pesquisa:'+str(r['id']) for r in repo.pesquisas(task['unit_id']) if r['status']=='aberta'],
        'rules':['Toda parte da cadeia deve ter pesquisa grantor e grantee com cobertura e reconciliação.',
                 'A fonte e a aplicação territorial precisam ser examinadas por tract.',
                 'Consultas locais de nomes não são buscas registrais nem provam ausência.',
                 'Qualidade exige Q1–Q6 com evidências da versão; fonte indisponível é dependência.',
                 'Consulte o Case File para documentos, claims, fontes, tarefas e decisões.',
                 'Registros históricos em decisoes são observações; a aprovação, o escopo e o template vigentes são os fixados acima.',
                 'Avance com o acervo local disponível; mantenha fontes externas como dependências agrupadas sem ampliar o escopo.',
                 'Nunca crie instrumentos, resultados de buscas, recibos ou aprovações inexistentes.'],
        'automatic_replanning':True}),ensure_ascii=False)


def check_plan(repo,task,output,*,teto,raiz=None,**_):
    errors=orquestracao.checar_plano(repo,task['unit_id'],output,teto=teto,pacote=task['pack'],raiz=raiz,excluir_tarefa=task['id'])
    requested={p for t in output.get('tarefas',[]) for p in t.get('pendencias',[])}
    required={'pesquisa:'+str(r['id']) for r in repo.pesquisas(task['unit_id']) if r['status']=='aberta'}
    if required-requested:
        errors.append('open_research_not_covered:'+','.join(sorted(required-requested)))
    case=repo.operation_case(task['unit_id'])
    permitted={a['id'] for a in repo.operation_artifacts(task['unit_id'])}
    for item in output.get('tarefas',[]):
        data=item.get('input_json',{})
        if data.get('unit_id',task['unit_id'])!=task['unit_id']:
            errors.append('task_outside_case')
        if data.get('source') and data['source'] not in case['scope']['sources']:
            errors.append('task_source_outside_scope')
        if set(data.get('artifact_ids',[]))-permitted:
            errors.append('task_artifacts_outside_case')
        if item['role']=='verificador' and not all(data.get(k) for k in ('claim_id','source_sha256','pagina')):
            errors.append('independent_review_requires_registered_claim_and_source; executor_queues_this_after_examination')
        clean=lambda value:{k:v for k,v in value.items() if k!='operation'}
        repeated=[t for t in repo.tarefas(task['unit_id']) if t['role']==item['role'] and t['status'] not in ('recusada','cancelada') and clean(t['input_json'])==clean(data)]
        if repeated:
            errors.append('repeated_task_without_new_input:'+item['ref'])
    return errors


def persist_plan(repo,task,output,session_id,*,run_id=None,**_):
    targets={'open_research_ids':['pesquisa:'+str(r['id']) for r in repo.pesquisas(task['unit_id']) if r['status']=='aberta']}
    pid=repo.registrar_proposta(task['unit_id'],task['id'],run_id,task['pack'],output,targets,{'covered':targets['open_research_ids']})
    stop=output.get('parada',{})
    if orquestracao._in_open_lot(repo,task['unit_id']):
        # Issue 17: inside a Lot the plan's stops are researched in the Job's
        # sources or shipped as declared gaps; they stay in the proposal.
        return [pid]
    for category in ('dependencias_externas','decisoes_do_operador'):
        for question in stop.get(category,[]):
            if not any(e['motivo']==category and e['pergunta']==question for e in repo.escalonamentos(task['unit_id'],abertos=True)):
                repo.abrir_escalonamento(task['unit_id'],task['id'],category,question,['fornecer evidência ou acesso','registrar decisão'])
    return [pid]


def decide_plan(repo,task,accept,actor,note):
    proposals=[p for p in repo.propostas(task['unit_id']) if p['task_id']==task['id'] and p['status']=='proposta']
    if not proposals:
        raise ValueError('coordinator_proposal_not_available')
    proposal=proposals[-1]
    if not accept:
        repo.recusar_proposta(proposal['id'],actor,note)
        return orquestracao.decidir(repo,task['id'],aceitar=False,ator=actor,nota=note)
    ceiling=float(repo.operation_case(task['unit_id'])['approved_budget_usd'])
    errors=check_plan(repo,task,proposal['plan'],teto=ceiling)
    if errors:
        raise ValueError(';'.join(errors))
    rows=orquestracao.linhas_do_plano(repo,task['unit_id'],proposal['plan'],teto=ceiling,pacote=PACK,excluir_tarefa=task['id'])
    for row in rows:
        if row['role']=='verificador':
            row['output_schema']='extracao_cega'
            row['verificacao']='nenhuma'
        elif row['role'] in ('pesquisador','arquivista','classificador'):
            # These outputs are observations. They do not approve claims or Q2.
            row['verificacao']='nenhuma'
        row['input_json']={**row['input_json'],'operation':True} if row['role']!='verificador' else row['input_json']
    repo.aprovar_proposta(proposal['id'],rows,'process:coordenador',actor,note)
    repo.transicionar_tarefa(task['id'],('aguardando_operador',),'aceita',actor,note)
    repo.promover_prontas(task['unit_id'],'process:operacao')


def check_source_claims(repo,task,output,**kw):
    errors=worker._checar_claims(repo,task,output,**kw)
    allowed={a['sha256'] for a in repo.operation_artifacts(task['unit_id']) if a['kind']=='source'}
    profile=repo.operation_case(task['unit_id'])['profile']
    protected=[repo.operation_artifact(profile[k]) for k in ('template_artifact_id','lead_example_artifact_id') if profile.get(k)]
    allowed-={a['sha256'] for a in protected if a}
    for claim in output.get('claims',[]):
        if claim.get('documento','').removeprefix('sha256:') not in allowed:
            errors.append('claim_source_outside_case')
    return errors


def persist_research(repo,task,output,session_id,**_):
    ids=[]
    raw=json.dumps({'observation':output,'session_id':session_id,'status':'unreviewed_research_observation'},ensure_ascii=False,indent=2).encode()
    path,sha=write_bytes(task['unit_id'],f"pesquisas/resultado_{task['id']}_{digest(output)[:12]}.json",raw)
    observation=repo.operation_add_artifact(task['unit_id'],'research_observation',path,sha,len(raw),{'title_acceptance':False,'source':output['fonte']},task['id'])
    ids.append(observation['id'])
    for found in output['encontrados']:
        ids.append(repo.criar_collection_item(task['unit_id'],found['referencia_registro'],'research_lead',
            {'source':output['fonte'],'research_observation_artifact_id':observation['id'],'found':found,'territorial_application':'pending'}))
    for search in output['busca_negativa']:
        ids.append(repo.registrar_busca(task['unit_id'],search['target'],search['terms'],json.dumps(search,ensure_ascii=False),
                                        search.get('names_scanned',0),search.get('hits',[])))
    for target in output['pedidos_de_captura']:
        ids.append(repo.criar_collection_item(task['unit_id'],target['referencia_registro'],'authorized_preview',target))
    return ids


def check_document(repo,task,output,**_):
    if output['estado']=='rejeitado':
        return []
    candidates=[a for a in repo.operation_artifacts(task['unit_id']) if a['sha256']==output.get('sha256') and a['path']==output.get('caminho_staging')]
    if not candidates:
        return ['captured_document_not_registered_in_case']
    path=checked_artifact(candidates[0])
    metadata=candidates[0]['metadata']
    if metadata.get('preview_page_count') and (metadata['preview_page_count']!=output['paginas'] or metadata.get('captured_pages')!=list(range(1,output['paginas']+1))):
        return ['captured_document_incomplete_against_source_page_count']
    if path.suffix.lower()=='.pdf':
        import fitz
        with fitz.open(path) as document:
            if len(document)!=output['paginas']:
                return ['captured_page_count_mismatch']
    return []


def persist_document(repo,task,output,session_id,**_):
    if output['estado']=='rejeitado':
        repo.abrir_escalonamento(task['unit_id'],task['id'],'capture',output['motivo'],['recapturar','fornecer cópia completa'])
        return []
    source=next(a for a in repo.operation_artifacts(task['unit_id']) if a['sha256']==output['sha256'])
    repo.registrar_source_file(source['sha256'],source['size_bytes'])
    item=repo.criar_collection_item(task['unit_id'],output['nome_canonico'],'authorized_preview',{'artifact_id':source['id']})
    repo.atualizar_collection_item(item,status='staged',staged_path=source['path'],sha256=source['sha256'],
                                   provenance={'capture_observation':output,'independent_review':'pending'},cost_usd=0,note='WORKING DRAFT; capture observation')
    return [item]


def persist_label(repo,task,output,session_id,**_):
    allowed={a['sha256'] for a in repo.operation_artifacts(task['unit_id']) if a['kind']=='source'}
    if output['sha256'] not in allowed:
        raise ValueError('classification_source_outside_case')
    fid=repo.source_file_id_por_sha(output['sha256'])
    repo.gravar_rotulo(fid,task['unit_id'],output['categoria'],output.get('resumo',output['trecho']),output['confianca'],session_id)
    return [fid]


def persist_claims(repo,task,output,session_id,**kwargs):
    ids=[]
    with repo.transacao():
        repo.operation_case(task['unit_id'],lock=True)
        cached={f:cid for a in repo.operation_artifacts(task['unit_id']) if a['kind']=='claim_checkpoint' and a['task_id']==task['id'] for f,cid in a['metadata'].get('claim_fingerprints',{}).items()}
        for claim in output['claims']:
            fingerprint=digest(claim)
            cid=cached.get(fingerprint)
            if cid is None:
                cid=worker._gravar_claims(repo,task,{'claims':[claim]},session_id,**kwargs)[0]
                cached[fingerprint]=cid
            ids.append(cid)
        raw=json.dumps({'claims':output['claims'],'claim_ids':ids,'task_completed':False},ensure_ascii=False,indent=2).encode()
        path,sha=write_bytes(task['unit_id'],f"exame/claims_tarefa_{task['id']}_{digest({'claim_ids':ids,'output':output})[:12]}.json",raw)
        repo.operation_add_artifact(task['unit_id'],'claim_checkpoint',path,sha,len(raw),
            {'claim_fingerprints':{digest(c):cid for c,cid in zip(output['claims'],ids)},'independent_acceptance':'pending'},task['id'])
        # Issue 05: each Claim of the applied output gets its own Case file.
        case_records.write_claim_files(repo,task,ids,function_files.current_output(repo,task['unit_id']))
    if any(c.get('materialidade')=='alta' for c in output['claims']):
        repo.conn.execute("UPDATE tasks SET verificacao='obrigatoria_e_operador' WHERE id=%s",(task['id'],))
    return ids


def queue_claim_review(repo,uid,claim,parent=None):
    add_followup(repo,uid,'verificador','Revisão independente da afirmação '+str(claim['id']),
        {'claim_id':claim['id'],'claim_type':claim['claim_type'],'source_sha256':claim['source_sha256'],
         'pagina':claim['page'],'pergunta':'Transcreva os fatos e cláusulas legíveis desta página em um objeto valor, com trecho literal. Inclua partes, datas, identificação de registro, descrição territorial e restrições quando presentes. Não complete campos por suposição; declare se a evidência é insuficiente.'},
        'extracao_cega',.6,ref='review-claim-'+str(claim['id']),parent=parent)
    if not cited_pages(claim['page']):
        review=repo.tarefa_por_ref(uid,'review-claim-'+str(claim['id']))
        if review and review['status'] in ('planejada','pronta'):
            repo.transicionar_tarefa(review['id'],(review['status'],),'bloqueada','process:source-identity','physical_source_page_required_before_paid_review')
        question='Afirmação '+str(claim['id'])+' sem página física verificável. Corrigir a referência ou fornecer a evidência de pesquisa; não inferir ausência de documento.'
        if not any(e['pergunta']==question for e in repo.escalonamentos(uid,abertos=True)):
            repo.abrir_escalonamento(uid,review['id'] if review else None,'document_evidence',question,['corrigir referência','fornecer pesquisa completa'])


def persist_verification(repo,task,output,session_id,*,run_id=None,**_):
    if task['output_schema']=='revisao_licao':
        from src.casefile.learning import verify
        verify(repo,task['input_json']['lesson_id'],output,actor='process:verificador',model_family='B')
        return [task['input_json']['lesson_id']]
    data=task['input_json']
    claim=repo.claim(data['claim_id'])
    # Same document; the review covers the Claim's cited pages, and may read
    # further ones (a re-read of another page, issue 13).
    covered=set(cited_pages(claim['page'])) if claim else set()
    if not claim or claim['unit_id']!=task['unit_id'] or claim['source_sha256']!=data['source_sha256'] or not (
            claim['page']==str(data['pagina']) or (covered and covered<=set(cited_pages(data['pagina'])))):
        raise ValueError('blind_verification_identity_mismatch')
    # Preserve the independent extraction before any comparison. A second AI
    # review judges agreement; Python never compares title values.
    verdict='evidencia_insuficiente' if not output['evidencia_suficiente'] else 'nao_verificavel'
    run=repo.run(run_id)
    request=repo.conn.execute("SELECT provider_request_id FROM operation_requests WHERE run_id=%s ORDER BY id DESC LIMIT 1",(run_id,)).fetchone()
    vid=repo.registrar_verificacao(claim['id'],data['pergunta'],verdict,run['model'],output,{'stage':'blind_extraction'},0,session_id,
         rastreio={'source_sha256':claim['source_sha256'],'page':str(data['pagina']),
                  'prompt_sha256':run['prompt_sha256'],'raw_response':json.dumps(output,ensure_ascii=False),
                  'request_id':request['provider_request_id'] if request else '',
                  'model_params':{'model':run['model'],'blind':True}})
    # Issue 05: the review is a Case file; its invalidation is a new file.
    applied=function_files.current_output(repo,task['unit_id'])
    case_records.write_review_file(repo,task,vid,applied)
    case_records.invalidate_review(repo,task,vid,'blind_extraction_awaiting_ai_comparison',applied)
    return [vid]


def check_verification(repo,task,output,**_):
    if task['output_schema']=='revisao_licao':
        return []
    data=task['input_json']
    receipts=[e for e in repo.operation_events(unit_id=task['unit_id'],limit=1000,task_id=task['id'],kind='source.page_read')
              if e['kind']=='source.page_read' and e['task_id']==task['id']
              and e['detail'].get('run_id')==task.get('_operation_run_id')
              and e['detail'].get('source_sha256')==data.get('source_sha256')
              and e['detail'].get('page') in cited_pages(data.get('pagina'))]
    expected=set(cited_pages(data.get('pagina')))
    observed={e['detail']['page'] for e in receipts}
    return [] if expected and expected<=observed else ['blind_source_page_not_read_in_this_run']


def check_comparison(repo,task,output,**_):
    if output['claim_id']!=task['input_json']['claim']['id']:
        return ['comparison_claim_different_from_requested_claim']
    claim=repo.claim(output['claim_id'])
    if not claim or claim['unit_id']!=task['unit_id']:
        return ['comparison_claim_outside_case']
    if output['source_sha256']!=claim['source_sha256'] or output['page']!=claim['page']:
        return ['comparison_evidence_identity_mismatch']
    data={'source_sha256':claim['source_sha256'],'pagina':claim['page']}
    receipts=[e for e in repo.operation_events(unit_id=task['unit_id'],limit=1000,task_id=task['id'],kind='source.page_read')
              if e['detail'].get('run_id')==task.get('_operation_run_id') and e['detail'].get('source_sha256')==data['source_sha256']
              and e['detail'].get('page') in cited_pages(data['pagina'])]
    expected=set(cited_pages(data['pagina']))
    if not expected or not expected<={e['detail']['page'] for e in receipts}:
        return ['comparison_source_page_not_read_in_this_run']
    if output['verdict']=='concordancia' and not output['quote'].strip():
        return ['comparison_requires_literal_quote']
    return []


def persist_comparison(repo,task,output,session_id,*,run_id=None,**_):
    run=repo.run(run_id)
    if run['model_family']!='B':
        raise ValueError('independent_family_required_for_comparison')
    claim=repo.claim(output['claim_id'])
    request=repo.conn.execute('SELECT provider_request_id FROM operation_requests WHERE run_id=%s ORDER BY id DESC LIMIT 1',(run_id,)).fetchone()
    vid=repo.registrar_verificacao(claim['id'],'Revisão por IA da afirmação e da extração independente',
        output['verdict'],run['model'],output,{'ai_judgment':True,'blind_verification_id':task['input_json']['blind_verification_id']},0,session_id,
        rastreio={'source_sha256':claim['source_sha256'],'page':claim['page'],'prompt_sha256':run['prompt_sha256'],
                 'raw_response':json.dumps(output,ensure_ascii=False),'request_id':request['provider_request_id'] if request else '',
                 'model_params':{'model':run['model'],'stage':'independent_ai_comparison'}})
    case_records.write_review_file(repo,task,vid,function_files.current_output(repo,task['unit_id']))
    if output['material_divergence'] and not orquestracao._in_open_lot(repo,task['unit_id']):
        repo.abrir_escalonamento(task['unit_id'],task['id'],'material_title',output['reason'],['consultar SME','fornecer evidência complementar'])
    return [vid]


def check_arbitration(repo,task,output,**kw):
    data=task['input_json']
    if output['claim_id']!=data['claim']['id'] or output['verificacao_id']!=data['verification']['id']:
        return ['arbitration_requested_identity_mismatch']
    if output['desfecho']=='escalado':
        return []  # An access failure may be escalated without pretending to read.
    sha=output['documento'].removeprefix('sha256:')
    pages=set(cited_pages(output['pagina']))
    receipts=repo.operation_events(unit_id=task['unit_id'],task_id=task['id'],
                                   kind='source.page_read',limit=1000)
    observed={e['detail']['page'] for e in receipts
              if e['detail'].get('run_id')==task.get('_operation_run_id')
              and e['detail'].get('source_sha256')==sha}
    if not pages or not pages<=observed:
        return ['arbitration_source_page_not_read_in_this_run']
    if output['desfecho']=='corrigido':
        return check_source_claims(repo,task,{'claims':[output['novo_claim']]},**kw)
    return []


def persist_arbitration(repo,task,output,session_id,**_):
    claim=repo.claim(output['claim_id'])
    if not claim or claim['unit_id']!=task['unit_id']:
        raise ValueError('arbitration_claim_outside_case')
    if (output['desfecho']=='escalado' or output['material_conclusao_titulo']) and orquestracao._in_open_lot(repo,task['unit_id']):
        pass    # issue 17: the Coordinator researches the Claim or declares the gap
    elif output['desfecho']=='escalado' or output['material_conclusao_titulo']:
        escalation=output.get('escalonamento',{})
        repo.abrir_escalonamento(task['unit_id'],task['id'],'material_title',
                                 escalation.get('pergunta',output['justificativa']),escalation.get('opcoes',['consultar SME','fornecer evidência']))
    elif output['desfecho']=='corrigido':
        ids=worker._gravar_claims(repo,task,{'claims':[output['novo_claim']]},session_id)
        # Issue 05: the new Claim's file supersedes the old one's, with the reason.
        case_records.replace_claim(repo,task,claim['id'],ids[0],output['justificativa'],
                                   function_files.current_output(repo,task['unit_id']))
        repo.conn.execute("UPDATE tasks SET verificacao='obrigatoria_e_operador' WHERE id=%s",(task['id'],))
        current=repo.tarefa(task['id'])
        if current['status']!='aguardando_verificacao':
            repo.transicionar_tarefa(task['id'],(current['status'],),'aguardando_verificacao','process:arbitro','Correção exige nova leitura independente antes da decisão humana.')
        return ids
    return []


def persist_qa(repo,task,output,session_id,**_):
    # A model QA report is an observation. It cannot certify PREP/SME/human acceptance.
    raw=json.dumps({'observation':output,'status':'WORKING DRAFT','session_id':session_id},ensure_ascii=False,indent=2).encode()
    path,sha=write_bytes(task['unit_id'],f"revisoes/qa_{task['id']}_{digest(output)[:12]}.json",raw)
    artifact=repo.operation_add_artifact(task['unit_id'],'qa_observation',path,sha,len(raw),{'independent':False,'protocol_acceptance':False},task['id'])
    return [artifact['id']]


def handlers():
    from src.casefile import report_writer,learning
    return {'plano_tarefas':(check_plan,persist_plan),'claims':(check_source_claims,persist_claims),
            'resultado_pesquisa':(lambda *a,**k:[],persist_research),'documento_registrado':(check_document,persist_document),
            'rotulo':(lambda *a,**k:[],persist_label),'extracao_cega':(check_verification,persist_verification),
            'revisao_licao':(lambda *a,**k:[],persist_verification),'adjudicacao':(check_arbitration,persist_arbitration),
            'comparacao_independente':(check_comparison,persist_comparison),
            'projecao_celulas':(lambda repo,task,output,**kw:report_writer.validate(repo,task,output),report_writer.persist),
            'relatorio_qa':(lambda *a,**k:[],persist_qa),'fichas_candidatas':(learning.validate,learning.persist)}


def finalize(repo,task,result):
    uid=task['unit_id']
    record={'task_id':task['id'],'result':serializable(result),'status':'execution_record_not_title_approval'}
    raw=json.dumps(record,ensure_ascii=False,indent=2).encode()
    if result['erros']:
        path,sha=write_bytes(uid,f"execucoes/tarefa_{task['id']}_run_{result['run_id']}_{digest(record)[:12]}.json",raw)
        repo.operation_add_artifact(uid,'run_record',path,sha,len(raw),{},task['id'])
        repo.operation_event('task.incomplete','process:worker',{'run_id':result['run_id'],'errors':result['erros']},unit_id=uid,task_id=task['id'])
        return
    current=repo.tarefa(task['id'])
    if task['role']=='coordenador':
        # Approval of the scope authorizes task redistribution inside its limits.
        decide_plan(repo,current,True,'process:coordenador','Reorganização dentro do escopo e orçamento aprovados.')
    if task['role'] in ('examinador','arbitro'):
        claims=[repo.claim(i) for i in repo.claims_da_tarefa(task['id'])]
        for claim in claims:
            queue_claim_review(repo,uid,claim,parent=task['id'])
        if repo.tarefa(task['id'])['status']=='aguardando_verificacao' and claims:
            orquestracao.aceitar_por_verificacao(repo,task['id'])
    if task['role']=='verificador' and task['output_schema']=='extracao_cega':
        cid=task['input_json']['claim_id']
        reviews=repo.verificacoes_do_claim(cid)
        # Even a partial extraction is judged against the particular claim by
        # the independent AI. A missing unrelated field must not become a
        # Python decision about the sufficiency of a title assertion.
        add_followup(repo,uid,'arbitro','Comparar as duas leituras da afirmação '+str(cid),
                     {'claim':repo.claim(cid),'blind_extraction':reviews[-1]['verifier_value'],
                      'blind_verification_id':reviews[-1]['id'],'independent_comparison':True},
                     'comparacao_independente',0.6,
                     # A re-read (review-claim-N-rK) gets its own comparison.
                     ref='compare-'+task['ref'].removeprefix('review-') if task['ref'].startswith('review-') else 'compare-claim-'+str(cid),
                     parent=task['id'])
    if task['output_schema']=='comparacao_independente':
        cid=task['input_json']['claim']['id']
        for parent in repo.tarefas(uid,'aguardando_verificacao'):
            if cid in repo.claims_da_tarefa(parent['id']):
                result_review=orquestracao.aceitar_por_verificacao(repo,parent['id'])
                if result_review['nao_concordantes']:
                    claim=repo.claim(cid)
                    reviews=repo.verificacoes_do_claim(cid)
                    add_followup(repo,uid,'arbitro','Examinar divergência da afirmação '+str(cid),
                                 {'claim':claim,'verification':reviews[-1]},'adjudicacao',1.0,ref='arbitrate-claim-'+str(cid),parent=task['id'])
    if task['role']=='retrospectivo':
        for lesson in repo.operation_lessons(uid):
            if lesson['task_id']==task['id'] and lesson['status']=='candidate':
                add_followup(repo,uid,'verificador','Verificar lição candidata '+str(lesson['id']),
                             {'lesson_id':lesson['id']},'revisao_licao',0.6,ref='review-lesson-'+str(lesson['id']),parent=task['id'])
    repo.promover_prontas(uid,'process:operacao')
    path,sha=write_bytes(uid,f"execucoes/tarefa_{task['id']}_run_{result['run_id']}_{digest(record)[:12]}.json",raw)
    repo.operation_add_artifact(uid,'run_record',path,sha,len(raw),{},task['id'])
    repo.operation_event('task.persisted','process:worker',{'run_id':result['run_id'],'role':task['role']},unit_id=uid,task_id=task['id'])


def add_followup(repo,uid,role,title,input_json,schema,budget,ref,parent=None):
    """Queue a follow-up task; `parent` is the task whose result produced it
    (issue 10: a focused Round runs its focus task and these descendants)."""
    if repo.tarefa_por_ref(uid,ref):
        return
    repo.operation_enqueue(uid,ref,role,title,serializable(input_json),schema,budget,parent)
    repo.operation_allocate(uid)


def reapply_learning(repo,uid,run_id,actor,note):
    """Apply the already-paid output atomically; original failed run stays intact."""
    run=repo.run(run_id)
    task=repo.tarefa(run['task_id']) if run else None
    if not task or task['unit_id']!=uid or task['output_schema']!='fichas_candidatas':
        raise ValueError('preserved_learning_result_required')
    previous=[e for e in repo.operation_events(unit_id=uid,task_id=task['id'],kind='result.reapplied') if e['detail'].get('run_id')==run_id]
    if previous:return previous[-1]['detail']['saved_ids']
    if not run['finished_at'] or run['stop_reason']!='result_not_persisted' or run['usage_state']!='confirmed' or task['status']!='aguardando_operador':
        raise ValueError('closed_confirmed_unapplied_result_required')
    if repo.runs_da_tarefa(task['id'])[-1]['id']!=run_id:raise ValueError('latest_preserved_result_required')
    errors=agentes.validar_saida(task['output_schema'],run['output_json'])
    current={**task,'_operation_run_id':run_id}
    check,persist=handlers()[task['output_schema']]
    errors+=check(repo,current,run['output_json'])
    if errors:raise ValueError(';'.join(errors))
    from src.casefile import function_files
    outputs=repo.function_files(run_id=run_id,direction='output')
    with repo.transacao():
        # Issue 03: a run with output files applies only its accepted one,
        # and the rows it creates cite that file. Runs from before output
        # files existed (no files at all) are applied as before.
        arquivo=function_files.begin_apply(repo,function_files.accepted_output(repo,run_id)) if outputs else None
        ids=persist(repo,current,run['output_json'],run['operation_session_id'],run_id=run_id)
        next_state=orquestracao.DESTINO_SAIDA_VALIDA[task['verificacao']]
        if next_state!=task['status']:
            repo.transicionar_tarefa(task['id'],(task['status'],),next_state,actor,note)
        finalize(repo,current,{'run_id':run_id,'erros':[],'gravados':ids,'custo_usd':run['cost_usd'],
            'modelo':run['model'],'parada':'preserved_result_applied_without_new_inference','tarefa':repo.tarefa(task['id'])})
        repo.operation_event('result.reapplied',actor,{'run_id':run_id,'saved_ids':ids,'additional_cost_usd':0,'original_failed_run_preserved':True,'note':note},unit_id=uid,task_id=task['id'])
        if arquivo:
            function_files.finish_apply(repo,arquivo)
    return ids
