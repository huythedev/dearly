"""Small real-HTTP smoke/latency measurement; not a concurrent load test."""
import json
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
import httpx
from server import Database,changed


def main():
    with tempfile.TemporaryDirectory() as directory:
        dbpath=Path(directory)/'benchmark.sqlite3'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        pidfile=Path(directory)/'server.pid'
        bootstrap=Path(directory)/'bootstrap.py'
        launcher=Path(__file__).resolve().with_name('run.py')
        bootstrap.write_text('import os, runpy, sys\nfrom pathlib import Path\n'
            +f'sys.path.insert(0, {str(launcher.parent)!r})\n'
            +f'Path({str(pidfile)!r}).write_text(str(os.getpid()))\n'
            +f'sys.argv = {[str(launcher),'--db',str(dbpath),'serve','--port',str(port)]!r}\n'
            +f'runpy.run_path({str(launcher)!r},run_name="__main__")\n',encoding='utf-8')
        process=subprocess.Popen([sys.executable,str(bootstrap)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=15,trust_env=False) as client:
                for attempt in range(100):
                    try:
                        if client.get('/health').status_code==200:break
                    except httpx.ConnectError:pass
                    time.sleep(0.05)
                else:raise RuntimeError('Server did not start')
                users=[]
                for name in ['bench_writer','bench_reader']:
                    r=client.post('/v1/auth/register',json=dict(username=name,password='benchmark-password-123',nickname=name,birthDate='2000-01-01'))
                    assert r.status_code==201,r.text
                    users.append((r.json(),{'Authorization':'Bearer '+r.json()['token']}))
                database=Database(dbpath)
                now=time.time()
                with database.connect(write=True) as db:
                    db.execute('UPDATE users SET age_verified=1')
                    for i in range(300):
                        content=f'Fixture {i}. '+('A journal sentence. '*50)
                        db.execute('INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()).upper(),users[0][0]['userID'],'Private title',content,content,'community',None,0,1,'listen',now+i/1000))
                    changed(db)
                def action(h,kind,p):
                    r=client.post('/v1/actions',headers=h,json=dict(requestID=str(uuid.uuid4()),kind=kind,payload=p));assert r.status_code==200,r.text;return r.json()
                iid=action(users[0][1],'invitation.send',dict(userID=users[1][0]['userID']))['id']
                cid=action(users[1][1],'invitation.accept',dict(id=iid))['id']
                action(users[0][1],'message.send',dict(connectionID=cid,text='Real HTTP smoke test'))
                peer=client.get('/v1/state',headers=users[1][1])
                assert peer.json()['state']['messages'][-1]['text']=='Real HTTP smoke test'
                for _,h in users:action(h,'connection.checkin',dict(connectionID=cid))
                assert client.get('/v1/state',headers=users[0][1]).json()['state']['connections'][0]['serverTotalDays']==1
                timings={};payload_size=0;etag=None
                for cached in [False,True]:
                    values=[]
                    for _ in range(20):
                        headers=dict(users[1][1])
                        if cached:headers['If-None-Match']=etag
                        start=time.perf_counter();r=client.get('/v1/state',headers=headers);values.append((time.perf_counter()-start)*1000)
                        assert r.status_code==(304 if cached else 200),r.text
                        if not cached:etag=r.headers['etag'];payload_size=len(r.content)
                        else:assert not r.content
                    timings['conditional_304' if cached else 'snapshot_200']={'p50_ms':round(statistics.median(values),2),'p95_ms':round(sorted(values)[18],2)}
                rss=None
                pid=int(pidfile.read_text()) if pidfile.exists() else process.pid
                status=Path(f'/proc/{pid}/status')
                if status.exists():
                    for line in status.read_text().splitlines():
                        if line.startswith('VmRSS:'):rss=round(int(line.split()[1])/1024,1)
                # Some hosted runtimes expose a launcher PID rather than interpreter memory.
                # Do not report that implausibly small value as the server footprint.
                if rss is not None and rss<10: rss=None
                result=dict(transport='real HTTP on localhost, sequential requests',sampleCount=20,fixtures={'users':2,'publicJournals':300,'windowJournals':60},snapshotBytes=payload_size,serverRSSMiB=rss,rssNote="RSS not measurable on this host" if rss is None else "Current process RSS on Linux",timings=timings)
                print(json.dumps(result,indent=2))
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
