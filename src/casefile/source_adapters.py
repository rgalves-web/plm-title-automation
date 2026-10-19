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


# --- issue 17: public Job sources the Researcher reaches with no operator ------------

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/130.0 Safari/537.36'}
GLO_SEARCH = 'https://www.glo.texas.gov/archives-heritage/search-our-collections/land-grant-search'
GLO_AJAX = 'https://www.glo.texas.gov/glo-custom/landgrant-ajax'
GLO_HOSTS = ('www.glo.texas.gov', 'cdn.glo.texas.gov')
GLO_FIELDS = {'abstract': 'abstractnumber', 'grantee': 'originalgrantee', 'patentee': 'patentee',
              'file': 'filenumber', 'certificate': 'certificate'}
TOPICS_SEARCH = 'https://topics.txcourts.gov/CitationsPublic/GetAllCitationNoticeDocs'
CAD_VIEW = 'https://esearch.terrellcad.org/property/view/'


def _http():
    import httpx
    return httpx.Client(headers=UA, timeout=httpx.Timeout(30, read=120), follow_redirects=True)


def _network(source, exc):
    raise SourceUnavailable(f'network_unreachable:{source}:{type(exc).__name__}') from exc


def _text(html):
    import re
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def glo_search(case, request):
    """Texas GLO land grants by county, one field at a time. The search form's
    antibot key is read from the page's own settings, as a browser would."""
    import json, re
    from urllib.parse import urljoin
    field = GLO_FIELDS.get(request.get('index') or 'grantee')
    if not field:
        raise ValueError('glo_index_must_be_abstract_grantee_patentee_file_or_certificate')
    term = ' '.join(request.get('terms', [])).strip()
    county = str(case['scope'].get('county') or '').upper()
    if not term or not county:
        raise ValueError('glo_search_requires_term_and_case_county')
    try:
        with _http() as client:
            page = client.get(GLO_SEARCH).text
            settings = json.loads(re.search(r'data-drupal-selector="drupal-settings-json">(.*?)</script>', page, re.S).group(1))
            key = settings['antibot']['forms']['glo-custom-land-grant-search']['key'][::-1]
            antibot = ''.join(key[i:i + 2][::-1] for i in range(0, len(key), 2))
            build = re.search(r'name="form_build_id" value="([^"]+)"', page).group(1)
            params = {name: '' for name in ('abstractnumber', 'originalgrantee', 'patentee', 'classtype', 'filenumber',
                                            'certificate', 'titledate', 'patentdate', 'patentnumber', 'patentvolume',
                                            'partsection', 'surveyblocktownship')}
            params.update({'county': county, field: term, 'pageSize': '25', 'form_build_id': build,
                           'form_id': 'glo_custom_land_grant_search', 'antibot_key': antibot})
            results, pages, reported = [], [], None
            for number in range(1, 21):
                html = client.get(GLO_AJAX, params={**params, 'page': str(number)}).text
                pages.append(number)
                found = re.search(r'out of\s+(\d+)\s+results', _text(html))
                reported = int(found.group(1)) if found else (0 if 'No results were found' in html else reported)
                for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S):
                    cells = [_text(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
                    if len(cells) < 6:
                        continue
                    links = [urljoin(GLO_SEARCH, h) for h in re.findall(r'href="([^"]+)"', row)]
                    # Columns: County, Abstract, District/Class, File Number, Grantee, Patentee, PDF.
                    results.append({'county': cells[0], 'abstract': cells[1], 'district_class': cells[2],
                                    'file_number': cells[3], 'grantee': cells[4], 'patentee': cells[5],
                                    'pdf_status': cells[6] if len(cells) > 6 else '',
                                    'pdf': next((l for l in links if l.lower().endswith('.pdf')), None),
                                    'detail': next((l for l in links if '/land-grant/' in l), None)})
                if reported is None or len(results) >= reported:
                    break
    except SourceUnavailable:
        raise
    except Exception as exc:
        if type(exc).__module__.startswith(('httpx', 'httpcore', 'ssl', 'socket')):
            _network('glo', exc)
        raise SourceUnavailable(f'source_response_not_understood:glo:{type(exc).__name__}') from exc
    return {'source': 'glo', 'source_url': GLO_SEARCH, 'observed_at': _now(), 'query': request,
            'index_field': field, 'county': county, 'reported_total': reported, 'saved_total': len(results),
            'pages': pages, 'pagination_complete': reported is not None and len(results) >= reported,
            'counts_reconciled': reported == len(results), 'results': results,
            'limitation': 'Índice de land grants do GLO por campo; não é índice de deeds do condado.'}


def topics_search(request):
    term = ' '.join(request.get('terms', [])).strip()
    if not term:
        raise ValueError('topics_search_requires_term')
    try:
        with _http() as client:
            response = client.get(TOPICS_SEARCH, params={'searchData': term},
                                  headers={'X-Requested-With': 'XMLHttpRequest'})
            response.raise_for_status()
            rows = response.json().get('data', [])
    except Exception as exc:
        if type(exc).__module__.startswith(('httpx', 'httpcore', 'ssl', 'socket')):
            _network('topics', exc)
        raise SourceUnavailable(f'source_response_not_understood:topics:{type(exc).__name__}') from exc
    results = [{'style': r[0], 'cause': r[1], 'court': r[2], 'status': r[3], 'id': r[4]}
               for r in rows if isinstance(r, list) and len(r) >= 5]
    return {'source': 'topics', 'source_url': TOPICS_SEARCH, 'observed_at': _now(), 'query': request,
            'reported_total': len(rows), 'saved_total': len(results), 'pages': [1],
            'pagination_complete': True, 'results': results,
            'limitation': 'Busca textual nas citações e notices publicados no TOPICs; não cobre todos os processos.'}


def cad_view(case, request):
    """Terrell CAD property card by PID (the case's PID unless the terms name one)."""
    import re
    pid = next((t for t in request.get('terms', []) if re.fullmatch(r'\d{1,9}', str(t).strip())), None) \
        or str(case['scope'].get('pid') or '')
    if not re.fullmatch(r'\d{1,9}', pid):
        raise ValueError('terrell_cad_requires_numeric_pid')
    try:
        with _http() as client:
            response = client.get(CAD_VIEW + pid)
            response.raise_for_status()
            text = _text(response.text)
    except Exception as exc:
        if type(exc).__module__.startswith(('httpx', 'httpcore', 'ssl', 'socket')):
            _network('terrell_cad', exc)
        raise SourceUnavailable(f'source_response_not_understood:terrell_cad:{type(exc).__name__}') from exc
    return {'source': 'terrell_cad', 'source_url': CAD_VIEW + pid, 'observed_at': _now(), 'query': request,
            'reported_total': 1, 'saved_total': 1, 'pages': [1], 'pagination_complete': True,
            'results': [{'pid': pid, 'text': text[:20000]}],
            'limitation': 'Cartão fiscal do CAD; não prova titularidade nem cadeia.'}


def glo_capture(repo, task, locator):
    """A public GLO land-grant PDF becomes a source document of the Case."""
    import httpx
    url = urlparse(locator)
    if url.scheme != 'https' or url.hostname not in GLO_HOSTS or not url.path.lower().endswith('.pdf'):
        raise ValueError('capture_locator_outside_approved_source')
    request = {'source': 'glo', 'locator': locator, 'operation': 'public_pdf'}
    job = repo.operation_source_request(task['unit_id'], 'glo', digest(request), request,
                                        task_id=task['id'], impact=task['title'])
    if job['status'] == 'complete':
        return job['receipt']
    try:
        with _http() as client:
            response = client.get(locator)
            response.raise_for_status()
            data = response.content
    except Exception as exc:
        receipt = {'blocked': True, 'reason': f'network_unreachable:glo:{type(exc).__name__}',
                   'access': 'network', 'owner': 'Renato', 'source': 'glo', 'locator': locator}
        repo.operation_source_result(job['id'], 'blocked', receipt)
        return receipt
    if not data.startswith(b'%PDF') or len(data) > 60_000_000:
        raise ValueError('glo_capture_not_a_pdf_or_too_large')
    path, sha = write_bytes(task['unit_id'], f"capturas/glo/{digest(request)}.pdf", data)
    metadata = {'source_url': locator, 'source': 'glo', 'public_document': True, 'cost_usd': 0,
                'observed_at': _now(), 'display_name': 'GLO ' + url.path.rsplit('/', 1)[-1],
                'capture_status': 'captured_pending_visual_review'}
    artifact = repo.operation_add_artifact(task['unit_id'], 'source', path, sha, len(data), metadata, task['id'])
    repo.registrar_source_file(sha, len(data))
    receipt = {**metadata, 'artifact_id': artifact['id'], 'path': str(path), 'sha256': sha}
    repo.operation_source_result(job['id'], 'complete', receipt)
    return receipt


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
    from src.casefile import routines
    try:
        if source=='local':
            receipt=local_catalog(repo,task['unit_id'],request)
        elif source=='drive':
            receipt=drive_catalog(case,request)
        elif source=='glo':
            receipt=glo_search(case,request)
        elif source=='topics':
            receipt=topics_search(request)
        elif source=='terrell_cad':
            receipt=cad_view(case,request)
        elif routines.access(source)=='paid':
            # Issue 17: a paid source is never searched automatically.
            raise SourceUnavailable('paid_source:'+source)
        else:
            receipt=portal_search(repo,case,source,request,'task:'+str(task['id']))
        repo.operation_source_result(job['id'],'complete',receipt)
        repo.operation_event('source.complete','process:pesquisador',{'job_id':job['id'],'source':source},unit_id=task['unit_id'],task_id=task['id'])
        return {**receipt,'job_id':job['id']}
    except SourceUnavailable as exc:
        receipt={'blocked':True,'reason':str(exc),'owner':'Renato','impact':task['title'],'source':source,'request':request,
                 'access':blocked_access(source,str(exc))}
        repo.operation_source_result(job['id'],'blocked',receipt)
        repo.operation_event('source.blocked','process:pesquisador',receipt,unit_id=task['unit_id'],task_id=task['id'])
        return {**receipt,'job_id':job['id']}


def blocked_access(source,reason):
    """Issue 17: what an operator must provide for a blocked source."""
    from src.casefile import routines
    if reason.startswith('paid_source') or routines.access(source)=='paid':
        return 'paid'
    if reason.startswith('network_unreachable'):
        return 'network'
    if reason.startswith('source_response_not_understood'):
        return 'adapter'
    return 'login'


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
    if source=='glo' and source in case['scope']['sources']:
        return glo_capture(repo,task,locator)
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
