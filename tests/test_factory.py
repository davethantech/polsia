"""Software factory tests: no real model or code execution takes place."""
import json
import pytest
from fastapi.testclient import TestClient
from app import core, factory, providers, workforce
from app.main import app

@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'factory.db'))
    for name in ('POLSIA_AI_ENABLED','POLSIA_LOCAL_MODEL','POLSIA_LOCAL_AI_URL'):
        monkeypatch.delenv(name,raising=False)
    core.init_db()


def example():
    return {'pkg/hello.py':'def hello():\n    return "hello"\n',
            'metadata.json':'{"status":"draft"}'}


def fake_local_model(monkeypatch, *, changes=None, usage=None):
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','test:local')
    if changes is None:changes=[{'path':'pkg/hello.py','content':'def hello():\n    return "hello world"\n'}]
    output={'summary':'Updated greeting code','files':changes,'limitations':'Syntax only; no tests run'}
    if usage is None:usage=(90,50)
    def reply(req,timeout):
        assert req.full_url=='http://127.0.0.1:11434/api/chat'
        data=json.loads(req.data)
        assert data['model']=='test:local'
        assert data['keep_alive']=='0' and data['stream'] is False
        assert data['messages'][0]['role']=='system'
        assert 'source_files' in data['messages'][1]['content']
        assert not any(k.lower() == 'authorization' for k in req.headers)
        return Stub({'model':'test:local','done':True,'done_reason':'stop',
            'message':{'role':'assistant','content':json.dumps(output)},
            'prompt_eval_count':usage[0],'eval_count':usage[1]})
    monkeypatch.setattr(providers,'_open',reply)


class Stub:
    status=200
    def __init__(self,value):self.payload=json.dumps(value).encode()
    def __enter__(self):return self
    def __exit__(self,*exc):return False
    def read(self,size):return self.payload[:size]


def test_inspection_is_read_only_and_returns_hashes():
    result=factory.inspect(example())
    assert len(result['files'])==2
    assert result['syntax_failures']==0
    assert all(v['syntax']['valid'] is True for v in result['files'])
    assert len(result['files'][0]['sha256'])==64
    assert 'return \"hello\"' not in repr(result)


@pytest.mark.parametrize('bad',[
    '../secrets.py', '/absolute.py', 'sub/../other.py', 'sub//file.py',
    'sub\\other.py', '.github/workflows/tests.yml', '.env', '.env.local',
    'secrets/secret.py','keys/api_token.json','id_rsa','app/code.sh',
    'folder/.hidden.py', 'package.py/../other.py',
])
def test_unsafe_source_paths_are_blocked(bad):
    with pytest.raises(ValueError):factory.inspect({bad:'safe'})


def test_snapshots_reject_limits_and_binary():
    with pytest.raises(ValueError):factory.inspect({})
    with pytest.raises(ValueError):factory.inspect({'a.py':'a'*8001})
    with pytest.raises(ValueError):factory.inspect({'a.py':'x\x00y'})
    with pytest.raises(ValueError):factory.inspect({f'f{i}.py':'ok' for i in range(11)})


def test_static_validation_reports_invalid_syntax_not_success():
    result=factory.inspect({'x.py':'def broken(:\n pass','x.json':'{broken'})
    assert result['syntax_failures']==2
    assert all(row['syntax']['valid'] is False for row in result['files'])


def test_proposal_checks_changes_and_marks_untrusted():
    val=factory.validate_proposal({'summary':'Fix greeting','files':[{'path':'pkg/hello.py',
        'content':'def hello():\n    return "hi"\n'}], 'limitations':'Tests not run'},example())
    assert val['executed'] is False and val['deployed'] is False
    assert len(val['changes'])==1 and val['changes'][0]['old_sha256']!=val['changes'][0]['new_sha256']
    assert val['verification'].startswith('python_json_syntax_checked')


@pytest.mark.parametrize('changes',[
    [{'path':'pkg/hello.py','content':'def broken(:'}],
    [{'path':'pkg/hello.py','content':'def hello():\n    return "hello"\n'}],
    [{'path':'other.json','content':'{bad}'}],
    [{'path':'pkg/hello.py','content':'def hello():\n    return 7\n'},
     {'path':'pkg/hello.py','content':'def hello():\n    return 8\n'}],
    [{'path':'.env','content':'bad'}],
])
def test_bad_code_proposals_rejected(changes):
    with pytest.raises(ValueError):factory.validate_proposal({'summary':'Fix greeting',
        'files':changes,'limitations':'None'},example())


def test_factory_mission_never_fakes_model_availability(monkeypatch):
    c=core.create_company('A')['company_id']
    mission=core.create_mission(c,'Factory mission',[
        {'name':'inspect','tool':'software.inspect','inputs':{'files':example()}},
        {'name':'propose','tool':'software.propose',
         'inputs':{'files':example(),'goal':'Improve greeting code'},'depends_on':['inspect']}])
    assert core.run_once()['status']=='SUCCEEDED'
    assert core.run_once()['status']=='FAILED'
    assert core.get_mission(c,mission)['mission']['status']=='FAILED'
    assert core.get_usage(c)['ai_calls']==0
    assert not core.list_factory_proposals(c)


def test_factory_mission_persists_tenant_scoped_proposal_and_usage(monkeypatch):
    fake_local_model(monkeypatch)
    a=core.create_company('A')['company_id'];b=core.create_company('B')['company_id']
    mission=core.create_mission(a,'Engineering',[
        {'name':'inspect','tool':'software.inspect','inputs':{'files':example()}},
        {'name':'propose','tool':'software.propose','inputs':{'goal':'Improve greeting code','files':example()},
         'depends_on':['inspect']}])
    assert core.run_once()['status']=='SUCCEEDED'
    finished=core.run_once()
    assert finished['status']=='SUCCEEDED'
    artifact_id=finished['result']['proposal_id']
    proposal=core.get_factory_proposal(a,artifact_id)
    assert proposal['model']=='test:local'
    assert proposal['changes'][0]['path']=='pkg/hello.py'
    assert proposal['deployed'] is False and proposal['status']=='UNTRUSTED_CANDIDATE'
    assert not core.list_factory_proposals(b) and core.get_factory_proposal(b,artifact_id) is None
    assert core.get_mission(a,mission)['mission']['status']=='SUCCEEDED'
    events=core.get_events(a,mission)
    assert all('hello world' not in e['detail'] for e in events)
    assert core.get_usage(a)['ai_calls']==1
    assert core.get_usage(a)['model_output_tokens']==50
    assert core.run_once() is None


def test_invalid_generated_code_records_failed_call_once(monkeypatch):
    fake_local_model(monkeypatch,changes=[{'path':'new.py','content':'def invalid(:'}])
    a=core.create_company('A')['company_id']
    mid=core.create_mission(a,'proposal',[
        {'name':'propose','tool':'software.propose','inputs':{'goal':'Change the greeting','files':example()}}])
    result=core.run_once()
    assert result['status']=='FAILED'
    assert not core.list_factory_proposals(a)
    assert core.get_usage(a)['ai_calls']==1
    assert core.get_mission(a,mid)['tasks'][0]['attempt']==1
    assert core.run_once() is None


def test_factory_api_role_scoping_and_workforce(monkeypatch):
    fake_local_model(monkeypatch)
    a=core.create_company('A');b=core.create_company('B')
    ha={'Authorization':'Bearer '+a['token']};hb={'Authorization':'Bearer '+b['token']}
    with TestClient(app) as client:
        cat=client.get('/workforce/capabilities',headers=ha)
        assert cat.status_code==200
        tools={x['tool']:x['available'] for x in cat.json()['agents']}
        assert tools['software.propose'] and tools['software.inspect']
        spec={'goal':'Improve the greeting code','files':example()}
        created=client.post('/factory/missions',headers=ha,json=spec)
        assert created.status_code==201
        assert created.json()['deployment'] is False
        assert client.post('/factory/inspect',headers=ha,json={'files':example()}).status_code==200
        assert core.run_once()['status']=='SUCCEEDED'
        assert core.run_once()['status']=='SUCCEEDED'
        proposal_id=client.get('/factory/proposals',headers=ha).json()[0]['id']
        assert client.get('/factory/proposals/'+proposal_id,headers=hb).status_code==404
        assert client.get('/factory/proposals',headers=hb).json()==[]
        assert client.get('/factory/proposals/'+proposal_id,headers=ha).json()['changes'][0]['path']=='pkg/hello.py'
        assert client.post('/factory/missions',headers=ha,json={**spec,'files':{'../secret.py':'bad'}}).status_code==422


def test_schema_rejects_unexpected_model_and_no_network_escalation(monkeypatch):
    fake_local_model(monkeypatch)
    monkeypatch.setenv('POLSIA_LOCAL_AI_URL','https://models.example.com')
    with pytest.raises(providers.ProviderError):providers.generate_code('Improve greeting code',example())


def test_cinematic_dashboard_exposes_safe_factory_workflow():
    with TestClient(app) as client:
        page=client.get('/dashboard')
        assert page.status_code==200
        assert 'id="view-factory"' in page.text
        assert 'id="factoryForm"' in page.text
        assert 'id="factoryPreviewBody"' in page.text
        script=client.get('/assets/app.js').text
        assert "'/factory/missions'" in script
        assert 'element(\'pre\',\'factory-code\',change.content)' in script
