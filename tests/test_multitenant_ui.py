"""Security and tenant-scope contract for the real browser API."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app import core, identity
from app.main import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DB_PATH', str(tmp_path / 'isolation.db'))
    monkeypatch.setenv('POLSIA_SIGNUP_ENABLED','1')
    monkeypatch.delenv('BOOTSTRAP_TOKEN',raising=False)
    monkeypatch.delenv('POLSIA_ENV',raising=False)
    monkeypatch.delenv('POLSIA_SECURE_COOKIES',raising=False)
    with TestClient(app) as browser:
        yield browser


def register(browser,email='alice@example.com',company='Acme'):
    result=browser.post('/auth/register',json={'email':email,'password':'A-secret-passphrase-2026!','company_name':company})
    assert result.status_code==201, result.text
    user=browser.get('/auth/me').json()
    assert user['csrf_token']
    return user['memberships'][0]['company_id'],user['csrf_token']


def test_landing_dashboard_and_csp(client):
    root=client.get('/')
    assert root.status_code==200
    assert 'The future' in root.text
    assert "script-src 'self'" in root.headers['content-security-policy']
    assert root.headers['x-frame-options']=='DENY'
    assert client.get('/assets/styles.css').status_code==200
    assert client.get('/assets/app.js').status_code==200
    assert client.get('/assets/favicon.svg').status_code==200
    assert 'Your ambition.' in client.get('/dashboard').text
    assert client.get('/auth/me').status_code==401


def test_session_cookie_and_csrf_protection(client):
    company,csrf=register(client)
    assert client.cookies.get('polsia_sid')
    cookie_header=client.post('/auth/login',json={'email':'alice@example.com','password':'A-secret-passphrase-2026!'})
    assert cookie_header.status_code==200
    assert 'httponly' in cookie_header.headers['set-cookie'].lower()
    assert 'samesite=strict' in cookie_header.headers['set-cookie'].lower()
    # Login rotates the HttpOnly session cookie; prior CSRF proof must not survive.
    assert cookie_header.json()['csrf_token'] != csrf
    csrf = client.get('/auth/me').json()['csrf_token']
    body={'objective':'Build trust','tasks':[{'name':'first','tool':'internal.echo','inputs':{'text':'yes'}}]}
    wrong=client.post('/missions',headers={'X-Company-ID':company},json=body)
    assert wrong.status_code==403
    wrong2=client.post('/missions',headers={'X-Company-ID':company,'X-CSRF-Token':'invalid'},json=body)
    assert wrong2.status_code==403
    good=client.post('/missions',headers={'X-Company-ID':company,'X-CSRF-Token':csrf},json=body)
    assert good.status_code==201, good.text
    listed=client.get('/missions',headers={'X-Company-ID':company}).json()
    assert len(listed['missions'])==1
    assert listed['missions'][0]['objective']=='Build trust'
    assert client.get('/overview',headers={'X-Company-ID':company}).json()['missions']['ACTIVE']==1


def test_cross_company_access_denied_even_with_forged_header(client):
    company_a,csrf_a=register(client)
    with TestClient(app) as other:
        company_b,csrf_b=register(other,'bob@example.com','Belmont')
        assert company_a!=company_b
        assert client.get('/overview',headers={'X-Company-ID':company_b}).status_code==403
        assert client.get('/missions',headers={'X-Company-ID':company_b}).status_code==403
        assert client.get('/knowledge',headers={'X-Company-ID':company_b}).status_code==403
        assert client.post('/companies/invitations',json={'email':'x@example.com','role':'viewer'},headers={'X-Company-ID':company_b,'X-CSRF-Token':csrf_a}).status_code==403
        item=other.post('/knowledge',headers={'X-Company-ID':company_b,'X-CSRF-Token':csrf_b},json={'content':'Secret business beta'})
        assert item.status_code==201
        assert client.get('/knowledge',headers={'X-Company-ID':company_a}).json()==[]
        assert other.get('/knowledge',headers={'X-Company-ID':company_b}).json()[0]['content']=='Secret business beta'


def test_company_switch_requires_explicit_scope(client):
    company,csrf=register(client)
    second=client.post('/companies',json={'name':'Gamma Research'},headers={'X-CSRF-Token':csrf})
    assert second.status_code==201
    other=second.json()['company_id']
    assert other!=company
    assert client.get('/overview').status_code==403
    assert client.get('/overview',headers={'X-Company-ID':company}).status_code==200
    assert client.get('/overview',headers={'X-Company-ID':other}).status_code==200
    assert len(client.get('/companies').json()['companies'])==2


def test_invitation_single_use_tenant_role_and_existing_user(client):
    company,csrf=register(client)
    invited=client.post('/companies/invitations',headers={'X-Company-ID':company,'X-CSRF-Token':csrf},json={'email':'viewer@example.com','role':'viewer'})
    assert invited.status_code==201
    token=invited.json()['invitation_token']
    assert len(token)>24
    with TestClient(app) as reader:
        accepted=reader.post('/auth/accept-invite',json={'email':'viewer@example.com','password':'A-secret-passphrase-2026!','token':token})
        assert accepted.status_code==200
        csrf_viewer=reader.get('/auth/me').json()['csrf_token']
        assert reader.get('/overview',headers={'X-Company-ID':company}).status_code==200
        assert reader.post('/missions',headers={'X-Company-ID':company,'X-CSRF-Token':csrf_viewer},json={'objective':'Nope','tasks':[{'name':'x','tool':'internal.echo','inputs':{'text':'x'}}]}).status_code==403
        assert reader.post('/companies/invitations',headers={'X-Company-ID':company,'X-CSRF-Token':csrf_viewer},json={'email':'oops@example.com'}).status_code==403
        assert reader.get('/companies/members',headers={'X-Company-ID':company}).json()['members'][1]['role']=='viewer'
    again=client.post('/auth/accept-invite',json={'email':'viewer@example.com','password':'A-secret-passphrase-2026!','token':token})
    assert again.status_code==422


def test_signup_closed_by_default_and_bearer_cannot_switch(client,monkeypatch):
    company,csrf=register(client)
    monkeypatch.setenv('POLSIA_SIGNUP_ENABLED','0')
    blocked=client.post('/auth/register',json={'email':'x@example.com','password':'A-secret-passphrase-2026!','company_name':'X LLC'})
    assert blocked.status_code==403
    legacy=core.create_company('Legacy Company')
    with TestClient(app) as legacy_user:
        res=legacy_user.get('/overview',headers={'Authorization':'Bearer '+legacy['token'],'X-Company-ID':company})
        assert res.status_code==200
        assert res.json()['company']['id']==legacy['company_id']


def test_bad_password_never_authenticates(client):
    register(client)
    with TestClient(app) as intruder:
        for _ in range(7):
            wrong=intruder.post('/auth/login',json={'email':'alice@example.com','password':'incorrectPassword999!'})
            assert wrong.status_code==401
        assert intruder.get('/auth/me').status_code==401


def test_logout_invalidates_session(client):
    company,csrf=register(client)
    assert client.post('/auth/logout',headers={'X-CSRF-Token':'bad'}).status_code==403
    assert client.post('/auth/logout',headers={'X-CSRF-Token':csrf}).status_code==200
    assert client.get('/auth/me').status_code==401


def test_editor_can_work_but_cannot_invite(client):
    company,csrf=register(client)
    result=client.post('/companies/invitations',headers={'X-Company-ID':company,'X-CSRF-Token':csrf},json={'email':'editor@example.com','role':'editor'})
    assert result.status_code==201
    with TestClient(app) as editor:
        assert editor.post('/auth/accept-invite',json={'email':'editor@example.com','password':'A-secret-passphrase-2026!','token':result.json()['invitation_token']}).status_code==200
        proof=editor.get('/auth/me').json()['csrf_token']
        headers={'X-Company-ID':company,'X-CSRF-Token':proof}
        assert editor.post('/missions',headers=headers,json={'objective':'Work step','tasks':[{'name':'x','tool':'internal.echo','inputs':{'text':'x'}}]}).status_code==201
        assert editor.post('/companies/invitations',headers=headers,json={'email':'unknown@example.com','role':'viewer'}).status_code==403


def test_production_requires_secure_cookies_and_disabled_bootstrap(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'production.db'))
    monkeypatch.setenv('POLSIA_ENV','production')
    monkeypatch.setenv('POLSIA_SECURE_COOKIES','0')
    monkeypatch.delenv('BOOTSTRAP_TOKEN',raising=False)
    with pytest.raises(RuntimeError,match='SECURE_COOKIES'):
        with TestClient(app):pass
    monkeypatch.setenv('POLSIA_SECURE_COOKIES','1')
    monkeypatch.setenv('BOOTSTRAP_TOKEN','unsafe-legacy-bootstrap')
    with pytest.raises(RuntimeError,match='bootstrap'):
        with TestClient(app):pass
    monkeypatch.delenv('BOOTSTRAP_TOKEN',raising=False)
    with TestClient(app) as production:
        assert production.get('/').status_code==200
        assert production.get('/').headers['strict-transport-security'].startswith('max-age=')
        assert production.get('/docs').status_code==404
        existing=core.create_company('Legacy')
        assert production.get('/overview',headers={'Authorization':'Bearer '+existing['token']}).status_code==401


def test_backup_sqlite_is_consistent(tmp_path):
    from scripts.backup_sqlite import backup
    source=tmp_path/'source.db'
    db=sqlite3.connect(source)
    db.execute('CREATE TABLE data (value TEXT NOT NULL)')
    db.execute('INSERT INTO data VALUES (?)',('persisted',))
    db.commit();db.close()
    saved=backup(source,tmp_path/'copies')
    assert saved.exists()
    read=sqlite3.connect(saved)
    assert read.execute('SELECT value FROM data').fetchone()[0]=='persisted'
    assert read.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    read.close()


def test_cinematic_ui_has_unique_ids_and_no_external_assets(client):
    from html.parser import HTMLParser
    class Inspect(HTMLParser):
        def __init__(self):
            super().__init__(); self.ids=[];self.external=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if 'id' in a:self.ids.append(a['id'])
            for prop in ('src','href'):
                if prop in a and str(a[prop]).startswith(('https:','http:')):self.external.append(a[prop])
    for route in ('/','/dashboard'):
        parser=Inspect();parser.feed(client.get(route).text)
        assert len(parser.ids)==len(set(parser.ids)), route
        assert not parser.external,route
