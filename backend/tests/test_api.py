import concurrent.futures
import json
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from server import create_app, changed

@pytest.fixture
def env(tmp_path):
    clock=[datetime(2026,10,13,12,tzinfo=timezone.utc).timestamp()]
    app=create_app(tmp_path/'test.sqlite3',clock=lambda:clock[0])
    with TestClient(app) as client:
        yield client,app,clock

def register(env,name,birth='2009-01-01',verified=True):
    client,app,_=env
    r=client.post('/v1/auth/register',json=dict(username=name,password='test-password-123',nickname=name,birthDate=birth))
    assert r.status_code==201,r.text
    d=r.json()
    if verified:
        with app.state.database.connect(write=True) as db:
            db.execute('UPDATE users SET age_verified=1 WHERE id=?',(d['userID'],));changed(db)
    return d,{'Authorization':'Bearer '+d['token']}

def action(client,h,kind,p=None,rid=None,expected=200):
    r=client.post('/v1/actions',headers=h,json=dict(requestID=rid or str(uuid.uuid4()),kind=kind,payload=p or {}))
    assert r.status_code==expected,r.text
    return r.json()

def state(client,h):
    r=client.get('/v1/state',headers=h)
    assert r.status_code==200,r.text
    return r.json()['state']

def pair(env):
    client,_,_=env
    a,ha=register(env,'alice');b,hb=register(env,'bravo')
    iid=action(client,ha,'invitation.send',{'userID':b['userID']})['id']
    cid=action(client,hb,'invitation.accept',{'id':iid})['id']
    return a,ha,b,hb,cid

def journal(client,h,**kwargs):
    p=dict(title='PRIVATE TITLE',body='PRIVATE PREFIX. Public excerpt.',sharedText='Public excerpt.',audience='community',anonymous=False,commentsEnabled=True,support='Chỉ cần lắng nghe')
    p.update(kwargs)
    return action(client,h,'journal.save',p)['id']

def test_full_flow_and_restart(env):
    client,app,clock=env
    a,ha=register(env,'alice');b,hb=register(env,'bravo')
    jid=journal(client,ha)
    row=next(x for x in state(client,hb)['journals'] if x['id']==jid)
    assert row['body']==row['title']=='' and row['sharedText']=='Public excerpt.'
    iid=action(client,hb,'invitation.send',{'journalID':jid})['id']
    cid=action(client,ha,'invitation.accept',{'id':iid})['id']
    action(client,ha,'message.send',dict(connectionID=cid,text='Phone A'))
    assert state(client,hb)['messages'][-1]['text']=='Phone A'
    action(client,ha,'connection.checkin',dict(connectionID=cid))
    assert state(client,hb)['connections'][0]['serverTotalDays']==0
    action(client,hb,'connection.checkin',dict(connectionID=cid))
    with TestClient(create_app(app.state.database.path,clock=lambda:clock[0])) as restarted:
        assert state(restarted,hb)['connections'][0]['serverTotalDays']==1
        assert state(restarted,ha)['messages'][0]['text']=='Phone A'

def test_auth_logout_and_expiry(env):
    client,_,clock=env
    assert client.get('/v1/state').status_code==401
    _,h=register(env,'alice')
    assert client.post('/v1/auth/login',json=dict(username='alice',password='wrong-password')).status_code==401
    r=client.post('/v1/auth/login',json=dict(username='ALICE',password='test-password-123'))
    assert r.status_code==200
    fresh={'Authorization':'Bearer '+r.json()['token']}
    assert client.post('/v1/auth/logout',headers=h).status_code==200
    assert client.get('/v1/state',headers=h).status_code==401
    assert client.get('/v1/state',headers=fresh).status_code==200
    clock[0]+=31*86400
    assert client.get('/v1/state',headers=fresh).status_code==401

def test_private_and_owner_authorization(env):
    client,_,_=env
    _,ha=register(env,'alice');_,hb=register(env,'bravo')
    private=journal(client,ha,audience='privateOnly',body='SECRET ONLY',sharedText='')
    public=journal(client,ha)
    serialized=json.dumps(state(client,hb))
    assert private not in serialized and 'SECRET ONLY' not in serialized
    assert 'PRIVATE PREFIX' not in serialized and 'PRIVATE TITLE' not in serialized
    assert all(x not in serialized for x in ['birth_date','password_hash','token_hash'])
    action(client,hb,'journal.save',dict(id=public,body='Hijack'),expected=403)
    action(client,hb,'journal.delete',dict(id=public),expected=403)
    action(client,hb,'journal.comment',dict(id=private,text='Peek'),expected=404)

def test_anonymity_through_comment_invitation_and_deleted_source(env):
    client,_,_=env
    author,ha=register(env,'author');viewer,hb=register(env,'viewer')
    jid=journal(client,ha,anonymous=True)
    action(client,ha,'journal.comment',dict(id=jid,text='Anonymous reply'))
    s=state(client,hb)
    assert next(x for x in s['journals'] if x['id']==jid)['authorID']==jid
    assert s['comments'][0]['authorID']==jid
    iid=action(client,hb,'invitation.send',{'journalID':jid})['id']
    assert state(client,hb)['invitations'][0]['recipientID']==jid
    action(client,ha,'journal.delete',dict(id=jid))
    assert state(client,hb)['invitations'][0]['recipientID']==jid
    action(client,ha,'invitation.accept',dict(id=iid))
    assert set(state(client,hb)['connections'][0]['members'])=={author['userID'],viewer['userID']}

def test_withdraw_and_disabled_comments(env):
    client,_,_=env
    _,ha=register(env,'alice');_,hb=register(env,'bravo')
    jid=journal(client,ha,commentsEnabled=False)
    action(client,hb,'journal.comment',dict(id=jid,text='No'),expected=403)
    journal(client,ha,id=jid,commentsEnabled=True)
    action(client,hb,'journal.comment',dict(id=jid,text='A reply'))
    journal(client,ha,id=jid,audience='privateOnly',sharedText='')
    s=state(client,hb)
    assert not any(x['id']==jid for x in s['journals'])
    assert not any(x['journalID']==jid for x in s['comments'])

def test_consent_and_age_gates_all_routes(env):
    client,_,_=env
    a,ha=register(env,'alice');b,hb=register(env,'bravo');adult,hc=register(env,'adult','2000-01-01')
    action(client,ha,'message.send',dict(connectionID=str(uuid.uuid4()),text='No consent'),expected=409)
    action(client,ha,'invitation.send',dict(userID=adult['userID']),expected=403)
    jid=journal(client,hc)
    action(client,ha,'invitation.send',dict(journalID=jid),expected=403)
    iid=action(client,ha,'invitation.send',dict(userID=b['userID']))['id']
    action(client,ha,'invitation.accept',dict(id=iid),expected=403)
    action(client,hc,'invitation.accept',dict(id=iid),expected=404)
    action(client,hb,'invitation.accept',dict(id=iid))

def test_unverified_cannot_self_verify(env):
    client,_,_=env
    _,ha=register(env,'alice',verified=False);b,_=register(env,'bravo')
    action(client,ha,'invitation.send',dict(userID=b['userID']),expected=403)
    action(client,ha,'profile.update',dict(nickname='Alice',ageVerified=True,birthDate='2000-01-01'))
    s=state(client,ha);me=next(x for x in s['profiles'] if x['id']==s['currentUserID'])
    assert me['age']==17 and me['ageVerified'] is False

def test_birthday_rechecked_on_accept(env):
    client,_,clock=env
    _,ha=register(env,'alice','2008-10-14');b,hb=register(env,'bravo')
    iid=action(client,ha,'invitation.send',dict(userID=b['userID']))['id']
    clock[0]+=86400
    action(client,hb,'invitation.accept',dict(id=iid),expected=409)

def test_concurrent_duplicate_checkins_streak_and_gap(env):
    client,_,clock=env
    _,ha,_,hb,cid=pair(env);p=dict(connectionID=cid)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda h:action(client,h,'connection.checkin',p),[ha,hb,ha,hb]))
    assert state(client,ha)['connections'][0]['serverTotalDays']==1
    for _ in range(6):
        clock[0]+=86400
        action(client,ha,'connection.checkin',p);action(client,hb,'connection.checkin',p)
    s=state(client,hb)['connections'][0]
    assert s['serverCurrentStreak']==s['bestStreak']==s['serverTotalDays']==7
    clock[0]+=2*86400
    s=state(client,ha)['connections'][0]
    assert s['serverCurrentStreak']==0 and s['bestStreak']==7
    action(client,ha,'connection.checkin',p);action(client,hb,'connection.checkin',p)
    s=state(client,ha)['connections'][0]
    assert s['serverCurrentStreak']==1 and s['bestStreak']==7 and s['serverTotalDays']==8

def test_pause_leave_new_partner_and_history_permissions(env):
    client,_,_=env
    _,ha,_,hb,cid=pair(env);c,hc=register(env,'charlie')
    jid=journal(client,ha,audience='companion')
    assert any(x['id']==jid for x in state(client,hb)['journals'])
    action(client,ha,'connection.pause',dict(connectionID=cid,paused=True))
    action(client,hb,'connection.checkin',dict(connectionID=cid),expected=409)
    action(client,ha,'connection.leave',dict(connectionID=cid))
    action(client,hb,'message.send',dict(connectionID=cid,text='Too late'),expected=409)
    assert not any(x['id']==jid for x in state(client,hb)['journals'])
    iid=action(client,ha,'invitation.send',dict(userID=c['userID']))['id']
    action(client,hc,'invitation.accept',dict(id=iid))
    assert not any(x['id']==jid for x in state(client,hc)['journals'])
    assert client.get('/v1/messages',headers=hc,params=dict(connectionID=cid)).status_code==403

def test_anonymous_block_and_report(env):
    client,app,_=env
    a,ha,b,hb,cid=pair(env);jid=journal(client,hb,anonymous=True)
    action(client,ha,'report.create',dict(journalID=jid,reason='Harassment'))
    with app.state.database.connect() as db:
        report=db.execute('SELECT * FROM reports').fetchone()
        assert report['reported_id']==b['userID'] and report['reporter_id']==a['userID']
    assert state(client,hb)['reports']==[]
    action(client,ha,'user.block',dict(journalID=jid))
    s=state(client,ha)
    assert not any(x['id']==jid for x in s['journals']) and s['connections'][0]['endedAt'] is not None
    action(client,hb,'invitation.send',dict(userID=a['userID']),expected=403)

def test_idempotency_lost_response_retry(env):
    client,_,_=env
    _,ha,_,hb,cid=pair(env);rid=str(uuid.uuid4());p=dict(connectionID=cid,text='Only once')
    first=action(client,ha,'message.send',p,rid=rid)
    assert action(client,ha,'message.send',p,rid=rid)==first
    assert len(state(client,hb)['messages'])==1
    action(client,ha,'message.send',dict(connectionID=cid,text='Different'),rid=rid,expected=409)

def test_etag_other_device_and_midnight(env):
    client,_,clock=env
    _,ha=register(env,'alice');_,hb=register(env,'bravo')
    r=client.get('/v1/state',headers=ha);etag=r.headers['etag']
    r=client.get('/v1/state',headers={**ha,'If-None-Match':etag})
    assert r.status_code==304 and r.content==b''
    journal(client,hb)
    r=client.get('/v1/state',headers={**ha,'If-None-Match':etag})
    assert r.status_code==200 and r.headers['etag']!=etag
    clock[0]+=86400
    assert client.get('/v1/state',headers={**ha,'If-None-Match':r.headers['etag']}).status_code==200

def test_message_pagination_equal_timestamps(env):
    client,app,clock=env
    a,ha,_,_,cid=pair(env)
    with app.state.database.connect(write=True) as db:
        for i in range(130):
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?)',(str(uuid.uuid4()).upper(),cid,a['userID'],str(i),clock[0]))
        changed(db)
    ids=set();before=None
    while True:
        params=dict(connectionID=cid,limit=40)
        if before: params['before']=before
        r=client.get('/v1/messages',headers=ha,params=params)
        assert r.status_code==200,r.text
        page=r.json();new={x['id'] for x in page['items']}
        assert not ids.intersection(new);ids.update(new)
        before=page['nextCursor']
        if before is None: break
    assert len(ids)==130 and len(state(client,ha)['messages'])==100

def test_size_and_excerpt_limits(env):
    client,_,_=env
    _,h=register(env,'alice')
    action(client,h,'journal.save',dict(body='x'*20001),expected=400)
    action(client,h,'journal.save',dict(body='original',sharedText='different',audience='community'),expected=400)
    r=client.post('/v1/actions',headers={**h,'Content-Type':'application/json'},content='x'*140000)
    assert r.status_code==413

def test_concurrent_accepts_one_active_connection(env):
    client,app,_=env
    _,ha=register(env,'alice');b,hb=register(env,'bravo');_,hc=register(env,'charlie')
    ia=action(client,ha,'invitation.send',dict(userID=b['userID']))['id']
    ic=action(client,hc,'invitation.send',dict(userID=b['userID']))['id']
    def accept(iid):
        return client.post('/v1/actions',headers=hb,json=dict(requestID=str(uuid.uuid4()),kind='invitation.accept',payload={'id':iid})).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: codes=list(pool.map(accept,[ia,ic]))
    assert sorted(codes)==[200,404]
    with app.state.database.connect() as db:
        assert db.execute('SELECT count(*) FROM connections WHERE ended IS NULL').fetchone()[0]==1

def test_health_openapi_suspension(env):
    client,app,_=env
    a,h=register(env,'alice')
    assert client.get('/health').json()['dayBoundary']=='UTC'
    assert '/v1/actions' in client.get('/openapi.json').json()['paths']
    with app.state.database.connect(write=True) as db:
        db.execute('UPDATE users SET suspended=1 WHERE id=?',(a['userID'],))
    assert client.get('/v1/state',headers=h).status_code==401

def test_journal_pagination_owner_scope_and_active_suggestions(env):
    client,app,clock=env
    a,ha,b,hb,cid=pair(env)
    _,hc=register(env,'charlie')
    assert b['userID'] not in state(client,hc)['suggestedUserIDs']
    with app.state.database.connect(write=True) as db:
        for i in range(85):
            db.execute('INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()).upper(),a['userID'],'Title',f'Only Alice {i}','','privateOnly',None,0,1,'Chỉ cần lắng nghe',clock[0]))
        changed(db)
    seen=set();before=None
    while True:
        params={'limit':30}
        if before:params['before']=before
        r=client.get('/v1/journals',headers=ha,params=params)
        assert r.status_code==200,r.text
        page=r.json();ids={x['id'] for x in page['items']}
        assert not ids.intersection(seen);seen.update(ids)
        before=page['nextCursor']
        if not before:break
    assert len(seen)==85
    assert client.get('/v1/journals',headers=hb).json()['items']==[]
    assert client.get('/v1/journals',headers=hb,params={'before':next(iter(seen))}).status_code==400


def test_validation_does_not_echo_password(env):
    client,_,_=env
    r=client.post('/v1/auth/register',json={'username':'bad username','password':'secret-input'})
    assert r.status_code==422 and 'secret-input' not in r.text

def test_server_assigns_new_journal_ids(env):
    client,_,_=env
    a,h=register(env,'alice')
    action(client,h,'journal.save',dict(id=a['userID'],body='Invented ID'),expected=404)
    jid=journal(client,h,anonymous=True)
    assert jid!=a['userID']

def test_cli_age_reports_suspend_and_backup(env,tmp_path):
    import subprocess,sys,sqlite3
    from pathlib import Path
    client,app,_=env
    a,ha=register(env,'alice',verified=False);b,hb=register(env,'bravo')
    launcher=Path(__file__).resolve().parents[1]/'run.py'
    def cli(*args):
        return subprocess.run([sys.executable,str(launcher),'--db',str(app.state.database.path),*args],check=True,capture_output=True,text=True,encoding='utf-8').stdout
    cli('verify-age','--username','alice','--birth-date','2009-01-01')
    s=state(client,ha)
    assert next(p for p in s['profiles'] if p['id']==a['userID'])['ageVerified'] is True
    iid=action(client,ha,'invitation.send',dict(userID=b['userID']))['id']
    cid=action(client,hb,'invitation.accept',dict(id=iid))['id']
    # Same verified birth date is idempotent and must not end an active relationship.
    cli('verify-age','--username','alice','--birth-date','2009-01-01')
    assert state(client,ha)['connections'][0]['endedAt'] is None
    action(client,ha,'report.create',dict(userID=b['userID'],reason='CLI review'))
    reports=json.loads(cli('reports'));assert len(reports)==1
    cli('resolve-report','--id',reports[0]['id'])
    assert json.loads(cli('reports'))==[]
    cli('suspend','--username','bravo')
    assert client.get('/v1/state',headers=hb).status_code==401
    assert state(client,ha)['connections'][0]['endedAt'] is not None
    backup=tmp_path/'backup.sqlite3'
    cli('backup','--output',str(backup))
    with sqlite3.connect(backup) as copied:
        assert copied.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert copied.execute('SELECT count(*) FROM users').fetchone()[0]==2
