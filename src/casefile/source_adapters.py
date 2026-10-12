"""Scoped source adapters and persisted dependency requests. No title judgment."""
from __future__ import annotations
import os
from datetime import datetime,timezone
from urllib.parse import urlparse

from src.casefile.storage import write_bytes
from src.casefile.training import digest


class SourceUnavailable(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def local_catalog(repo,unit_id,request):
    population=[a for a in repo.operation_artifacts(unit_id) if a['kind']=='source']
    terms=[str(t).casefold() for t in request.get('terms',[]) if str(t).strip()]
    rows=[{'artifact_id':a['id'],'name':a['metadata'].get('display_name',a['path'].replace('\\','/').split('/')[-1]),
           'sha256':a['sha256'],'path':a['path']} for a in population
          if not terms or any(t in (a['path']+' '+a['metadata'].get('display_name','')).casefold() for t in terms)]
    return {'source':'local','observed_at':_now(),'scope':'registered_file_names_only',
            'population_size':len(population),'reported_total':len(rows),'saved_total':len(rows),
            'pages':[1],'pagination_complete':True,'results':rows,
            'limitation':'Consulta do catálogo de nomes; não demonstra ausência no conteúdo ou nos índices do cartório.'}


def drive_catalog(case,request):
    import httpx
    token=os.environ.get('PLM_GOOGLE_DRIVE_ACCESS_TOKEN')
    folder=case['profile'].get('drive_folder_id')
    if not token or not folder:
        raise SourceUnavailable('drive_connection_and_case_folder_required')
    if not folder.replace('-','').replace('_','').isalnum():
        raise ValueError('invalid_drive_folder_id')
    q="'"+folder+"' in parents and trashed = false"
    terms=[str(t).replace("'","\\'") for t in request.get('terms',[])]
    if terms:
        q+=' and ('+' or '.join("name contains '"+t+"'" for t in terms)+')'
    results=[]
    token_page=None
    pages=[]
    with httpx.Client(timeout=30) as client:
        while True:
            params={'q':q,'pageSize':100,'fields':'nextPageToken,files(id,name,mimeType,webViewLink,modifiedTime,md5Checksum)'}
            if token_page:
                params['pageToken']=token_page
            response=client.get('https://www.googleapis.com/drive/v3/files',params=params,
                                headers={'Authorization':'Bearer '+token})
            if response.status_code in (401,403):
                raise SourceUnavailable('drive_login_or_folder_permission_required')
            response.raise_for_status()
            data=response.json()
            results.extend(data.get('files',[]))
            pages.append(len(pages)+1)
            token_page=data.get('nextPageToken')
            if not token_page:
                break
    return {'source':'drive','folder_id':folder,'observed_at':_now(),'scope':'direct_children_file_names_only',
            'reported_total':len(results),'saved_total':len(results),'pages':pages,
            'pagination_complete':True,'results':results,'limitation':'Catálogo de arquivos; não equivale a pesquisa registral.'}


def portal_search(repo,case,source,request,holder):
    recipe=case['profile'].get('source_recipes',{}).get(source)
    if not recipe or not recipe.get('verified_by') or not recipe.get('source_evidence'):
        raise SourceUnavailable('verified_source_recipe_required:'+source)
    if request.get('index')=='combined' and not recipe.get('combined_index_evidence'):
        raise SourceUnavailable('combined_grantor_grantee_operation_not_demonstrated')
    if not recipe.get('search_url') or not recipe.get('query_selector') or not recipe.get('results_selector'):
        raise SourceUnavailable('source_search_recipe_incomplete:'+source)
    if recipe.get('search_consumes_credit') and not recipe.get('approved_existing_views'):
        raise SourceUnavailable('portal_existing_view_limit_not_approved')
    host=urlparse(recipe['search_url']).hostname
    if host not in recipe.get('allowed_hosts',[]) or not urlparse(recipe['search_url']).scheme=='https':
        raise ValueError('source_host_not_approved')
    cdp=recipe.get('cdp_url','http://127.0.0.1:9222')
    if urlparse(cdp).hostname not in ('127.0.0.1','localhost'):
        raise ValueError('local_browser_session_required')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SourceUnavailable('browser_adapter_not_installed') from exc
    resource='portal:'+cdp
    if not repo.operation_resource(resource,holder,120):
        raise SourceUnavailable('portal_session_busy_retry_later')
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp(cdp)
            page=next((p for c in browser.contexts for p in c.pages if urlparse(p.url).hostname==host),None)
            if page is None:
                raise SourceUnavailable('authorized_browser_tab_and_login_required:'+source)
            page.goto(recipe['search_url'],wait_until='domcontentloaded')
            if recipe.get('login_selector') and page.locator(recipe['login_selector']).count():
                raise SourceUnavailable('portal_login_required:'+source)
            page.locator(recipe['query_selector']).fill(' '.join(request.get('terms',[])))
            for key in ('start_date','through_date','index'):
                if request.get(key) and recipe.get(key+'_selector'):
                    locator=page.locator(recipe[key+'_selector'])
                    if key=='index':
                        locator.select_option(request[key])
                    else:
                        locator.fill(request[key])
            page.locator(recipe['submit_selector']).click()
            results=[]
            pages=[]
            screenshots=[]
            reported=None
            page.wait_for_selector(recipe['results_selector'],timeout=30000)
            if recipe.get('total_selector'):
                import re
                total_text=page.locator(recipe['total_selector']).inner_text()
                numbers=re.findall(r'\d[\d,]*',total_text)
                reported=int(numbers[-1].replace(',','')) if numbers else None
            while True:
                if not repo.operation_resource(resource,holder,120):
                    raise SourceUnavailable('portal_lease_lost')
                pages.append(len(pages)+1)
                rows=page.locator(recipe['results_selector'])
                for index in range(rows.count()):
                    row=rows.nth(index)
                    results.append({'page':pages[-1],'row':index+1,'text':row.inner_text()})
                png=page.screenshot(full_page=True)
                path,sha=write_bytes(case['unit_id'],f"buscas/{digest(request)}/{pages[-1]}.png",png)
                screenshots.append({'path':str(path),'sha256':sha,'page':pages[-1]})
                if not recipe.get('next_selector'):
                    break
                next_button=page.locator(recipe['next_selector'])
                if not next_button.count() or next_button.is_disabled() or next_button.get_attribute('aria-disabled')=='true':
                    break
                old_text=page.locator(recipe['results_selector']).first.inner_text() if rows.count() else ''
                next_button.click()
                page.wait_for_function('(args)=>document.querySelector(args.selector)?.innerText!==args.text',
                                       arg={'selector':recipe['results_selector'],'text':old_text},timeout=30000)
            return {'source':source,'source_url':page.url,'observed_at':_now(),'query':request,
                    'reported_total':reported,'saved_total':len(results),'pages':pages,
                    'pagination_complete':True,'counts_reconciled':reported is not None and reported==len(results),
                    'results':results,'screenshots':screenshots,'index_mode':request.get('index'),
                    'combined_index_verified':bool(recipe.get('combined_index_evidence'))}
    finally:
        repo.operation_release_resource(resource,holder)


def execute(repo,task,source,request):
    if source not in ('local','drive') and len(request.get('terms',[]))>1:
        receipts=[execute(repo,task,source,{**request,'terms':[term]}) for term in request['terms']]
        return {'source':source,'variant_queries':receipts,'complete':all(not r.get('blocked') for r in receipts),
                'limitation':'Cada variante tem seu próprio recibo e intervalo; a suficiência é revisada documentalmente.'}
    case=repo.operation_case(task['unit_id'])
    if source not in case['scope'].get('sources',[]):
        raise ValueError('source_outside_approved_scope')
    request={**request,'source':source}
    for key in ('start_date','through_date'):
        if key not in request:
            request[key]=case['scope'][key]
    prior=(case['scope'].get('investigate_prior_rights') and request.get('prior_reference') and request.get('reason'))
    if (request['start_date']<case['scope']['start_date'] and not prior) or request['through_date']>case['scope']['through_date']:
        raise ValueError('search_outside_approved_temporal_scope')
    job=repo.operation_source_request(task['unit_id'],source,digest(request),request,task_id=task['id'],impact=task['title'])
    if job['status']=='complete':
        return {**job['receipt'],'job_id':job['id']}
    shared=shared_receipt(repo,case,source,digest(request)) if source!='local' else None
    if shared:
        repo.operation_source_result(job['id'],'complete',shared)
        repo.operation_event('source.reused','process:pesquisador',{'job_id':job['id'],'origin_job_id':shared['shared_origin_job_id']},unit_id=task['unit_id'],task_id=task['id'])
        return {**shared,'job_id':job['id']}
    try:
        if source=='local':
            receipt=local_catalog(repo,task['unit_id'],request)
        elif source=='drive':
            receipt=drive_catalog(case,request)
        else:
            receipt=portal_search(repo,case,source,request,'task:'+str(task['id']))
        repo.operation_source_result(job['id'],'complete',receipt)
        repo.operation_event('source.complete','process:pesquisador',{'job_id':job['id'],'source':source},unit_id=task['unit_id'],task_id=task['id'])
        return {**receipt,'job_id':job['id']}
    except SourceUnavailable as exc:
        receipt={'blocked':True,'reason':str(exc),'owner':'Renato','impact':task['title'],'source':source,'request':request}
        repo.operation_source_result(job['id'],'blocked',receipt)
        repo.operation_event('source.blocked','process:pesquisador',receipt,unit_id=task['unit_id'],task_id=task['id'])
        return {**receipt,'job_id':job['id']}


def shared_receipt(repo,case,source,key):
    if not case['scope'].get('share_research') or not case['scope'].get('pid'):
        return None
    candidates=repo.conn.execute("SELECT j.*,o.scope,o.profile FROM operation_source_jobs j JOIN operation_cases o ON o.unit_id=j.unit_id WHERE j.request_key=%s AND j.source=%s AND j.status='complete' AND j.unit_id<>%s ORDER BY j.id",(key,source,case['unit_id'])).fetchall()
    for old in candidates:
        if not old['scope'].get('share_research') or old['scope'].get('pid')!=case['scope']['pid'] or old['scope'].get('county')!=case['scope'].get('county'):
            continue
        if source=='drive' and old['profile'].get('drive_folder_id')!=case['profile'].get('drive_folder_id'):
            continue
        if source not in ('drive','local') and old['profile'].get('source_recipes',{}).get(source)!=case['profile'].get('source_recipes',{}).get(source):
            continue
        receipt=old['receipt']
        if receipt.get('blocked') or receipt.get('pagination_complete') is False:
            continue
        if receipt.get('artifact_id'):
            repo.operation_link_artifact(receipt['artifact_id'],case['unit_id'],{'status':'pending','shared_source_job':old['id']},'process:shared-source')
        return {**receipt,'shared_origin_job_id':old['id'],'shared_origin_unit_id':old['unit_id'],
                'charge_owner_unit_id':old['receipt'].get('charge_owner_unit_id',old['unit_id']),
                'territorial_application':'pending_for_this_tract'}
    return None


def capture(repo,task,source,locator):
    import io
    from PIL import Image
    case=repo.operation_case(task['unit_id'])
    recipe=case['profile'].get('source_recipes',{}).get(source)
    if source not in case['scope']['sources'] or not recipe or not recipe.get('preview_page_count_selector'):
        return {'blocked':True,'reason':'authorized_preview_capture_recipe_required','owner':'Renato'}
    if urlparse(locator).hostname not in recipe.get('allowed_hosts',[]) or urlparse(locator).scheme!='https':
        raise ValueError('capture_locator_outside_approved_source')
    if not recipe.get('approved_existing_views'):
        return {'blocked':True,'reason':'existing_portal_views_not_approved','owner':'Renato'}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'blocked':True,'reason':'browser_adapter_not_installed','owner':'Renato'}
    cdp=recipe.get('cdp_url','http://127.0.0.1:9222')
    resource='portal:'+cdp
    holder='capture:'+str(task['id'])
    if urlparse(cdp).hostname not in ('localhost','127.0.0.1') or not repo.operation_resource(resource,holder,120):
        return {'blocked':True,'reason':'portal_session_busy_or_unavailable','owner':'Renato'}
    request={'source':source,'locator':locator,'operation':'preview_capture'}
    job=repo.operation_source_request(task['unit_id'],source,digest(request),request,task_id=task['id'],impact=task['title'])
    if job['status']=='complete':
        repo.operation_release_resource(resource,holder)
        return job['receipt']
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp(cdp)
            host=urlparse(locator).hostname
            page=next((p for c in browser.contexts for p in c.pages if urlparse(p.url).hostname==host),None)
            if page is None:
                raise SourceUnavailable('authorized_browser_tab_and_login_required')
            before=None
            if recipe.get('view_balance_selector'):
                before=page.locator(recipe['view_balance_selector']).inner_text()
            page.goto(locator,wait_until='domcontentloaded')
            if recipe.get('login_selector') and page.locator(recipe['login_selector']).count():
                raise SourceUnavailable('portal_login_required')
            import re
            count_text=page.locator(recipe['preview_page_count_selector']).inner_text()
            numbers=re.findall(r'\d+',count_text)
            if not numbers:
                raise SourceUnavailable('preview_page_count_not_demonstrated')
            total=int(numbers[-1])
            if total<1 or total>500:
                raise ValueError('invalid_preview_page_count')
            images=[]
            proofs=[]
            for n in range(1,total+1):
                if not repo.operation_resource(resource,holder,120):
                    raise SourceUnavailable('portal_capture_lease_lost')
                if recipe.get('page_number_selector'):
                    selector=page.locator(recipe['page_number_selector'])
                    selector.fill(str(n))
                    selector.press('Enter')
                elif n>1:
                    if not recipe.get('preview_next_selector'):
                        raise SourceUnavailable('preview_pagination_recipe_missing')
                    page.locator(recipe['preview_next_selector']).click()
                page.wait_for_selector(recipe['preview_image_selector'],timeout=30000)
                image=page.locator(recipe['preview_image_selector'])
                png=image.screenshot()
                path,sha=write_bytes(task['unit_id'],f"capturas/{digest(request)}/pagina_{n}.png",png)
                proofs.append({'source_page':n,'path':str(path),'sha256':sha})
                images.append(Image.open(io.BytesIO(png)).convert('RGB'))
            buffer=io.BytesIO()
            images[0].save(buffer,format='PDF',save_all=True,append_images=images[1:])
            data=buffer.getvalue()
            path,sha=write_bytes(task['unit_id'],f"capturas/{digest(request)}/documento.pdf",data)
            metadata={'source_url':locator,'source':source,'preview_page_count':total,'captured_pages':list(range(1,total+1)),
                      'images':proofs,'capture_status':'captured_pending_visual_review','view_balance_before':before,
                      'view_balance_after':page.locator(recipe['view_balance_selector']).inner_text() if recipe.get('view_balance_selector') else None,
                      'observed_at':_now(),'allocation':'pending','independent_review':'pending'}
            artifact=repo.operation_add_artifact(task['unit_id'],'source',path,sha,len(data),metadata,task['id'])
            repo.registrar_source_file(sha,len(data))
            receipt={**metadata,'artifact_id':artifact['id'],'path':str(path),'sha256':sha}
            repo.operation_source_result(job['id'],'complete',receipt)
            return receipt
    except SourceUnavailable as exc:
        receipt={'blocked':True,'reason':str(exc),'owner':'Renato','source':source,'locator':locator}
        repo.operation_source_result(job['id'],'blocked',receipt)
        return receipt
    finally:
        repo.operation_release_resource(resource,holder)
