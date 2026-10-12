"""One local entry point for the visual workbench and background workers."""
from __future__ import annotations
import argparse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','prepare'])
    parser.add_argument('--port',type=int,default=8788)
    args=parser.parse_args()
    if args.command=='prepare':
        from src.casefile.bootstrap import prepare
        print(prepare())
        return
    from src.casefile.supervisor import Supervisor
    from src.casefile.api import app
    import uvicorn
    supervisor=Supervisor().start()
    try:
        uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')
    finally:
        supervisor.close()


if __name__=='__main__':
    main()
