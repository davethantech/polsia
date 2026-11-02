import socket
import pytest
from app import core,capacity,mathematics,research

@pytest.fixture(autouse=True)
def db(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'test.db'))
    core.init_db()


def test_decimal_math_exact():
    c=core.create_company('Math Co')
    mid=core.create_mission(c['company_id'],'calculate',[{'name':'calc','tool':'math.evaluate','inputs':{'expression':'0.1+0.2'}}])
    result=core.run_once()
    assert result['status']=='SUCCEEDED'
    assert result['result']['value']=='0.3'
    assert core.get_mission(c['company_id'],mid)['mission']['status']=='SUCCEEDED'
    assert core.get_usage(c['company_id'])['total_tasks']==1
    assert core.get_usage(c['company_id'])['provider_cost_usd'] is None

@pytest.mark.parametrize('expression',['2**10000','__import__("os")','2/0','9'*120,'1 if True else 2','1<<30'])
def test_math_disallows_unsafe_or_unbounded(expression):
    with pytest.raises(ValueError):mathematics.evaluate(expression)

def test_memory_tenant_isolation_and_provenance():
    a=core.create_company('A')['company_id']; b=core.create_company('B')['company_id']
    mid=core.store_knowledge(a,'research','Market X is growing','https://example.com')
    rows=core.search_knowledge(a,'Market')
    assert len(rows)==1 and rows[0]['id']==mid
    assert rows[0]['evidence_status']=='user_supplied_unverified'
    assert core.search_knowledge(b,'Market')==[]
    assert len(core.search_knowledge(a,'%'))==0

def test_memory_tool_persists():
    c=core.create_company('Memory')['company_id']
    core.create_mission(c,'record',[{'name':'store','tool':'knowledge.store','inputs':{'layer':'strategy','content':'Focus on qualified demand','source':'user instruction'}}])
    assert core.run_once()['status']=='SUCCEEDED'
    assert core.search_knowledge(c,'qualified')[0]['layer']=='strategy'

def test_capacity_blocks_overload_without_dequeuing(monkeypatch):
    c=core.create_company('Capacity')['company_id']
    mid=core.create_mission(c,'will wait',[{'name':'echo','tool':'internal.echo','inputs':{'text':'x'}}])
    monkeypatch.setattr(capacity,'snapshot',lambda: {'memory_available_bytes':128*1024**2,'disk_free_bytes':4*1024**3,'load_per_core':0.2,'max_temperature_c':None})
    response=core.run_once()
    assert response['status']=='THROTTLED'
    assert 'low_memory' in response['reasons']
    assert core.get_mission(c,mid)['tasks'][0]['status']=='QUEUED'

def test_capacity_rejects_overheat():
    metrics={'memory_available_bytes':8*1024**3,'disk_free_bytes':100*1024**3,'load_per_core':0.01,'max_temperature_c':83}
    assert capacity.admit(metrics)['reasons']==['high_temperature']
    metrics['max_temperature_c']=None
    assert capacity.admit(metrics)['temperature_monitored'] is False

@pytest.mark.parametrize('host,ip', [('localhost','127.0.0.1'),('internal.example','10.0.0.2'),('cloud.example','169.254.169.254'),('host.example','::1')])
def test_private_network_rejected(monkeypatch,host,ip):
    def dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]
    monkeypatch.setattr(socket,'getaddrinfo',dns)
    with pytest.raises(ValueError):research.validated_destination('https://'+host+'/test')

def test_http_and_credentials_rejected():
    with pytest.raises(ValueError):research.validated_destination('http://example.com')
    with pytest.raises(ValueError):research.validated_destination('https://alice:pass@example.com')


def test_network_disabled_fails_closed(monkeypatch):
    monkeypatch.delenv('POLSIA_NETWORK_ENABLED',raising=False)
    with pytest.raises(ValueError,match='not enabled'):research.fetch_public('https://example.com')

def test_research_workflow_persists_unverified_source(monkeypatch):
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    class FakeResponse:
        status=200
        def getheader(self,k,default=None):return {'Content-Type':'text/plain'}.get(k,default)
        def read(self,n):return b'Research claim requiring verification'
    class FakeConnection:
        def __init__(self,*args): pass
        def request(self,*args,**kwargs):pass
        def getresponse(self):return FakeResponse()
        def close(self):pass
    monkeypatch.setattr(research,'validated_destination',lambda url: ('example.com','93.184.215.14',__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url)))
    monkeypatch.setattr(research,'PinnedHTTPSConnection',FakeConnection)
    c=core.create_company('Research')['company_id']
    core.create_mission(c,'fetch',[{'name':'fetch','tool':'research.fetch','inputs':{'url':'https://example.com/article'}}])
    r=core.run_once()
    assert r['status']=='SUCCEEDED'
    assert r['result']['evidence_status']=='retrieved_unverified'
    assert core.search_knowledge(c,'Research claim')[0]['source']=='https://example.com/article'


def test_api_auth_and_tenant_scope(monkeypatch):
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except ImportError:pytest.skip('FastAPI test client not installed')
    a=core.create_company('A');b=core.create_company('B')
    core.store_knowledge(a['company_id'],'company','A business secret','user')
    with TestClient(app) as client:
        assert client.get('/knowledge').status_code==401
        ra=client.get('/knowledge',headers={'Authorization':'Bearer '+a['token']})
        rb=client.get('/knowledge',headers={'Authorization':'Bearer '+b['token']})
        assert ra.status_code==200 and len(ra.json())==1
        assert rb.status_code==200 and rb.json()==[]
        assert client.get('/capacity',headers={'Authorization':'Bearer '+b['token']}).status_code==200


def test_resource_estimate_explicitly_is_not_cost():
    specs=[{'name':'r','tool':'research.fetch','inputs':{'url':'https://example.com'}},
           {'name':'m','tool':'math.evaluate','inputs':{'expression':'2+3'}}]
    est=core.estimate_mission(specs)
    assert est['estimated_peak_tool_memory_mb']==64
    assert est['estimated_cumulative_disk_mb']==3
    assert est['model_tokens'] is None
    assert est['provider_cost_usd'] is None
    assert est['confidence']=='assumed_tool_budgets_not_measured'


def test_lost_lease_prevents_old_worker_from_clobbering(monkeypatch):
    cid=core.create_company('Fence')['company_id']
    mid=core.create_mission(cid,'lease',[{'name':'job','tool':'internal.echo','inputs':{'text':'x'}}])
    original=core.execute_tool
    def stolen(tool,inputs):
        with core.connect() as db:
            db.execute("UPDATE tasks SET lease_token=? WHERE mission_id=?",('new-worker-owns-it',mid))
        return original(tool,inputs)
    monkeypatch.setattr(core,'execute_tool',stolen)
    result=core.run_once()
    assert result['status']=='STALE_LEASE'
    row=core.get_mission(cid,mid)['tasks'][0]
    assert row['status']=='RUNNING'
    assert row['outputs'] is None


def test_migration_preserves_existing_records():
    c=core.create_company('Existing')
    with core.connect() as db:
        db.execute('ALTER TABLE tasks RENAME TO tasks_backup')
        db.execute('CREATE TABLE tasks (id TEXT PRIMARY KEY,company_id TEXT NOT NULL,mission_id TEXT NOT NULL,name TEXT NOT NULL,tool TEXT NOT NULL,inputs TEXT NOT NULL,outputs TEXT,depends_on TEXT NOT NULL DEFAULT "[]",status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,lease_until INTEGER,approval_required INTEGER NOT NULL DEFAULT 0,approved INTEGER NOT NULL DEFAULT 0,success_condition TEXT NOT NULL,updated_at INTEGER NOT NULL,UNIQUE(mission_id,name))')
        db.execute('DROP TABLE tasks_backup')
    core.init_db()
    with core.connect() as db:
        assert 'lease_token' in {x['name'] for x in db.execute('PRAGMA table_info(tasks)')}
        assert db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]==1


def test_mission_estimate_endpoint_is_authenticated():
    from fastapi.testclient import TestClient
    from app.main import app
    c=core.create_company('Estimate')
    with TestClient(app) as client:
        body={'objective':'estimate','tasks':[{'name':'calc','tool':'math.evaluate','inputs':{'expression':'1+1'}}]}
        assert client.post('/missions/estimate',json=body).status_code==401
        response=client.post('/missions/estimate',json=body,headers={'Authorization':'Bearer '+c['token']})
        assert response.status_code==200
        assert response.json()['provider_cost_usd'] is None


def test_failed_dependency_blocks_unapproved_task_and_closes_mission():
    cid=core.create_company('Blocked')['company_id']
    mid=core.create_mission(cid,'blocked',[
        {'name':'bad','tool':'internal.add','inputs':{'values':['not a number']}},
        {'name':'approval','tool':'internal.echo','inputs':{'text':'x'},'depends_on':['bad'],'approval_required':True}])
    assert core.run_once()['status']=='QUEUED'
    assert core.run_once()['status']=='QUEUED'
    assert core.run_once()['status']=='FAILED'
    assert core.run_once() is None
    mission=core.get_mission(cid,mid)
    assert mission['mission']['status']=='FAILED'
    assert [t['status'] for t in mission['tasks']]==['FAILED','BLOCKED']
