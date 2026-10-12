"""Local command API and replayable SSE. All visible state comes from Postgres."""
from __future__ import annotations
import asyncio
import json
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import FileResponse,Response,StreamingResponse

from src.casefile import operations
from src.casefile.storage import checked_artifact

TOKEN=secrets.token_urlsafe(32)


def event_batch(repo,cursor):
    if not repo.operations_installed():
        return {'installed':False,'last_event_id':0},[]
    maximum=repo.operation_last_event()
    if cursor<=0 or cursor>maximum:
        return operations.snapshot(repo),[]
    return None,operations.serializable(repo.operation_events(cursor,limit=250))


def attach(app,get_repo):
    router=APIRouter(prefix='/api/operations')

    @router.get('/session')
    def session():
        return {'command_token':TOKEN}

    @router.get('')
    def overview(repo=Depends(get_repo)):
        return operations.snapshot(repo)

    @router.get('/cases/{unit_id}')
    def case(unit_id:int,repo=Depends(get_repo)):
        try:
            return operations.detail(repo,unit_id)
        except ValueError as exc:
            raise HTTPException(404,str(exc)) from exc

    @router.get('/tasks/{task_id}')
    def task(task_id:int,repo=Depends(get_repo)):
        try:
            return operations.task_detail(repo,task_id)
        except ValueError as exc:
            raise HTTPException(404,str(exc)) from exc

    @router.post('/commands')
    async def command(request:Request,repo=Depends(get_repo)):
        if not secrets.compare_digest(request.headers.get('x-plm-token',''),TOKEN):
            raise HTTPException(403,'Abra o painel local para registrar decisões.')
        origin=request.headers.get('origin')
        if origin:
            parsed=urlparse(origin)
            target=urlparse(str(request.base_url))
            if parsed.hostname not in ('localhost','127.0.0.1') or parsed.port!=target.port:
                raise HTTPException(403,'Origem da decisão não autorizada.')
        try:
            body=await request.json()
            return await asyncio.to_thread(operations.command,repo,body)
        except operations.OperationConflict as exc:
            raise HTTPException(409,str(exc)) from exc
        except (ValueError,KeyError,TypeError) as exc:
            raise HTTPException(422,str(exc)) from exc

    @router.get('/artifacts/{artifact_id}')
    def artifact(artifact_id:int,repo=Depends(get_repo)):
        row=repo.operation_artifact(artifact_id)
        if not row:
            raise HTTPException(404,'Arquivo não registrado.')
        try:
            path=checked_artifact(row)
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc
        # Untrusted HTML and other documents are downloads, never executed here.
        return FileResponse(path,filename=row['metadata'].get('display_name',path.name))

    @router.get('/artifacts/{artifact_id}/page/{page}')
    def artifact_page(artifact_id:int,page:int,repo=Depends(get_repo)):
        row=repo.operation_artifact(artifact_id)
        if not row:
            raise HTTPException(404,'Arquivo não registrado.')
        try:
            path=checked_artifact(row)
            import fitz
            if path.suffix.lower()=='.pdf':
                with fitz.open(path) as doc:
                    if not 1<=page<=len(doc):
                        raise ValueError('Página inexistente')
                    png=doc[page-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).tobytes('png')
                return Response(png,media_type='image/png')
            if page==1 and path.suffix.lower() in ('.png','.jpg','.jpeg','.tif','.tiff'):
                from PIL import Image
                import io
                with Image.open(path) as img:
                    buf=io.BytesIO()
                    img.convert('RGB').save(buf,format='PNG')
                return Response(buf.getvalue(),media_type='image/png')
            raise ValueError('Visualização de páginas indisponível para este formato')
        except (ValueError,OSError) as exc:
            raise HTTPException(409,str(exc)) from exc

    @router.get('/events')
    async def events(request:Request,after:int=0):
        try:
            cursor=int(request.headers.get('last-event-id',str(after)))
        except ValueError:
            raise HTTPException(422,'invalid_event_cursor')
        def fetch(cursor):
            from src.casefile.db import connect
            from src.casefile.repo import Repo
            with connect() as conn:
                repo=Repo(conn)
                return event_batch(repo,cursor)
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                snap,rows=await asyncio.to_thread(fetch,cursor)
                if snap is not None:
                    cursor=snap['last_event_id']
                    yield f"id: {cursor}\nevent: snapshot\ndata: {json.dumps(snap,ensure_ascii=False)}\n\n"
                for event in rows:
                    cursor=event['id']
                    yield f"id: {cursor}\nevent: change\ndata: {json.dumps(event,ensure_ascii=False)}\n\n"
                if not rows and snap is None:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    app.include_router(router)
