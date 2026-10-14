"""Portable launcher and offline administration. Run `python run.py --help`."""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from server import Database, changed, create_app, validate_birth


def main():
    parser=argparse.ArgumentParser(description='Dearly server and local administration')
    parser.add_argument('--db',default=os.environ.get('DEARLY_DB','data/dearly.sqlite3'))
    sub=parser.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve')
    serve.add_argument('--host',default='127.0.0.1')
    serve.add_argument('--port',type=int,default=8000)
    serve.add_argument('--proxy-ips',default='',help='Trusted reverse-proxy IPs only (e.g. 127.0.0.1). Empty disables forwarded headers.')
    serve.add_argument('--cert',help='TLS certificate PEM (optional behind an HTTPS reverse proxy)')
    serve.add_argument('--key',help='TLS private key PEM')
    verify=sub.add_parser('verify-age',help='Mark date of birth reviewed by an operator')
    verify.add_argument('--username',required=True); verify.add_argument('--birth-date',required=True)
    sub.add_parser('reports')
    resolve=sub.add_parser('resolve-report');resolve.add_argument('--id',required=True)
    suspend=sub.add_parser('suspend');suspend.add_argument('--username',required=True)
    backup=sub.add_parser('backup');backup.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='serve':
        if bool(args.cert)!=bool(args.key): parser.error('--cert and --key must be used together')
        import uvicorn
        uvicorn.run(create_app(args.db),host=args.host,port=args.port,workers=1,loop='asyncio',http='h11',
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
            cursor=db.execute("UPDATE reports SET status='reviewed' WHERE id=?",(args.id.upper(),))
            if cursor.rowcount==0: parser.error('Report not found.')
        else:
            user=db.execute('SELECT * FROM users WHERE username=?',(args.username.lower(),)).fetchone()
            if user is None: parser.error('User not found.')
            uid=user['id']
            if args.command=='verify-age':
                birth=validate_birth(args.birth_date,time.time())
                db.execute('UPDATE users SET birth_date=?,age_verified=1 WHERE id=?',(birth,uid))
                # End old edges after a correction; a new invitation will re-check the new age.
                if user['birth_date'] != birth:
                    db.execute('UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)',(time.time(),uid,uid))
                    db.execute('DELETE FROM invitations WHERE sender_id=? OR recipient_id=?',(uid,uid))
            if args.command=='suspend':
                db.execute('UPDATE users SET suspended=1 WHERE id=?',(uid,))
                db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
                db.execute('DELETE FROM invitations WHERE sender_id=? OR recipient_id=?',(uid,uid))
                db.execute('UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)',(time.time(),uid,uid))
        changed(db)
    print('Done.')


if __name__=='__main__':
    main()
