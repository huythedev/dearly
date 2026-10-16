"""Portable launcher and offline administration. Run `python run.py --help`."""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from fastapi import HTTPException
from server import Database, changed, create_app, identifier, review_report, set_role, set_suspended, verify_age


def main():
    parser=argparse.ArgumentParser(description='Dearly server and local administration')
    parser.add_argument('--db',default=os.environ.get('DEARLY_DB','data/dearly.sqlite3'))
    sub=parser.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve')
    serve.add_argument('--host',default='127.0.0.1')
    serve.add_argument('--port',type=int,default=8000)
    serve.add_argument('--body-idle-timeout',type=float,default=5.0,help='Maximum seconds between request body chunks')
    serve.add_argument('--body-total-timeout',type=float,default=15.0,help='Maximum total seconds to read a request body')
    serve.add_argument('--proxy-ips',default='',help='Trusted reverse-proxy IPs only (e.g. 127.0.0.1). Empty disables forwarded headers.')
    serve.add_argument('--cert',help='TLS certificate PEM (optional behind an HTTPS reverse proxy)')
    serve.add_argument('--key',help='TLS private key PEM')
    verify=sub.add_parser('verify-age',help='Mark date of birth reviewed by an operator')
    verify.add_argument('--username',required=True); verify.add_argument('--birth-date',required=True)
    verify.add_argument('--reason',default='Birth date reviewed by server operator')
    sub.add_parser('reports')
    resolve=sub.add_parser('resolve-report');resolve.add_argument('--id',required=True)
    resolve.add_argument('--reason',default='Reviewed by server operator')
    suspend=sub.add_parser('suspend');suspend.add_argument('--username',required=True)
    suspend.add_argument('--reason',default='Suspended by server operator')
    restore=sub.add_parser('restore',help='Restore a suspended account (requires a new login)')
    restore.add_argument('--username',required=True);restore.add_argument('--reason',default='Restored by server operator')
    role=sub.add_parser('set-role',help='Grant or revoke user/moderator/admin access on an existing account')
    role.add_argument('--username',required=True)
    role.add_argument('--role',choices=['user','moderator','admin'],required=True)
    role.add_argument('--reason',required=True,help='Reason recorded in the audit log')
    backup=sub.add_parser('backup');backup.add_argument('--output',required=True)
    args=parser.parse_args()
    if hasattr(args, 'reason'):
        args.reason=args.reason.strip()
        if not 1 <= len(args.reason) <= 1000: parser.error('--reason must contain 1–1000 characters')
    if args.command=='serve':
        if bool(args.cert)!=bool(args.key): parser.error('--cert and --key must be used together')
        if args.body_idle_timeout <= 0 or args.body_total_timeout <= 0:
            parser.error('Request body timeouts must be positive.')
        import uvicorn
        uvicorn.run(create_app(args.db,body_idle_timeout=args.body_idle_timeout,body_total_timeout=args.body_total_timeout),
                    host=args.host,port=args.port,workers=1,loop='asyncio',http='h11',
                    limit_concurrency=64,timeout_keep_alive=5,proxy_headers=bool(args.proxy_ips),forwarded_allow_ips=args.proxy_ips,
                    ssl_certfile=args.cert,ssl_keyfile=args.key)
        return
    database=Database(args.db)
    if args.command=='backup':
        destination=Path(args.output)
        if destination.exists(): parser.error('Backup output already exists; choose a new filename.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        # SQLite backup API copies a consistent live WAL database. Do not copy only the .db file.
        with sqlite3.connect(str(database.path)) as source, sqlite3.connect(str(destination)) as target:
            source.backup(target)
        print('Backup created:',destination);return
    with database.connect(write=args.command!='reports') as db:
        if args.command=='reports':
            rows=db.execute('SELECT * FROM reports WHERE status=? ORDER BY created LIMIT 100',('open',)).fetchall()
            print(json.dumps([dict(r) for r in rows],ensure_ascii=False,indent=2));return
        if args.command=='resolve-report':
            review_report(db,identifier(args.id),'reviewed',args.reason,'server-cli',time.time())
        else:
            user=db.execute('SELECT * FROM users WHERE username=?',(args.username.lower(),)).fetchone()
            if user is None: parser.error('User not found.')
            if args.command=='verify-age':
                verify_age(db,user,args.birth_date,'server-cli',args.reason,time.time())
            if args.command in ('suspend','restore'):
                set_suspended(db,user,args.command=='suspend','server-cli',args.reason,time.time())
            if args.command=='set-role':
                set_role(db,user,args.role,'server-cli',args.reason,time.time())
        changed(db)
    print('Done.')


if __name__=='__main__':
    try:
        main()
    except HTTPException as error:
        print(error.detail,file=sys.stderr)
        sys.exit(1)
