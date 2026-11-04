"""Local model and learning security: network traffic is stubbed, not a live model."""
import hashlib
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app import core, providers
from app.main import app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DB_PATH', str(tmp_path / 'si.db'))
    for name in ('POLSIA_AI_ENABLED','POLSIA_LOCAL_AI_URL','POLSIA_LOCAL_MODEL',
                 'POLSIA_NETWORK_ENABLED','POLSIA_LEARNING_ENABLED', 'POLSIA_AI_DAILY_CALL_LIMIT'):
        monkeypatch.delenv(name, raising=False)
    core.init_db()


def sample_source():
    return {'title':'Scientific reading','topic':'astronomy','url':'https://science.example.org/reading',
            'interval_hours':24}


class Resp:
    status = 200
    def __init__(self, value): self.value=json.dumps(value).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,length): return self.value[:length]


def test_local_model_disabled_without_config():
    cfg=providers.configuration()
    assert cfg['provider']=='local_ollama'
    assert cfg['status']=='disabled' and not cfg['live_requests']
    assert cfg['network_egress_for_inference'] is False


def test_local_model_enabled_without_internet_or_cloud_credentials(monkeypatch):
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','test:local')
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','0')
    monkeypatch.setenv('POLSIA_OPENAI_API_KEY','never-send-this')
    cfg=providers.configuration()
    assert cfg['status']=='configured_not_checked' and cfg['live_requests']
    assert cfg['model']=='test:local'
    assert cfg['network_egress_for_inference'] is False


def test_cloud_endpoint_rejected_even_if_server_env_set(monkeypatch):
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','test:local')
    for address in ('https://api.openai.com/v1','http://example.org:11434',
                    'http://127.0.0.1:5555','http://ollama:11434/redirect',
                    'http://127.0.0.1:11434@evil.com'):
        monkeypatch.setenv('POLSIA_LOCAL_AI_URL',address)
        assert providers.configuration()['status']=='invalid_local_configuration'
        with pytest.raises(providers.ProviderError): providers.require_configured()
    monkeypatch.setenv('POLSIA_LOCAL_AI_URL','http://ollama:11434')
    assert providers.require_configured()=='test:local'


def test_local_adapter_structured_result_and_no_auth_key(monkeypatch):
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','local-model:v1')
    monkeypatch.setenv('POLSIA_OPENAI_API_KEY','private-but-ignored')
    def fake(req,timeout):
        assert req.full_url=='http://127.0.0.1:11434/api/chat'
        assert timeout==providers.TIMEOUT_SECONDS
        assert not any('Authorization' in key for key in req.headers)
        body=json.loads(req.data)
        assert body['model']=='local-model:v1' and body['keep_alive']=='0'
        assert body['stream'] is False and body['format']['type']=='object'
        assert body['messages'][0]['role']=='system'
        assert 'no-external-request' in body['messages'][1]['content']
        assert 'private-but-ignored' not in repr(body)
        return Resp({'model':'local-model:v1','done':True,'done_reason':'stop',
                     'message':{'role':'assistant','content':json.dumps({
                         'answer':'Cited','citations':['memory:test'],'confidence':'low','limitations':'Unknown'})},
                     'prompt_eval_count':17,'eval_count':9})
    monkeypatch.setattr(providers,'_open',fake)
    result=providers.generate('no-external-request',[{'citation_id':'memory:test'}])
    assert result['usage']=={'input_tokens':17,'output_tokens':9}
    assert result['provider_response_id'] is None


def test_local_adapter_rejects_redirects_and_noncompleted(monkeypatch):
    req=providers.urllib.request.Request('http://127.0.0.1:11434/api/chat',data=b'{}')
    assert providers.NoRedirect().redirect_request(req,None,301,'Moved',{},
        'https://remote-api.example.org') is None
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','test')
    monkeypatch.setattr(providers,'_open',lambda *args, **kwargs: Resp({
        'model':'test','done':True,'done_reason':'length',
        'message':{'role':'assistant','content':'{}'}}))
    with pytest.raises(providers.ProviderError,match='did not complete'):
        providers.generate('question',[])


def test_local_model_catalog_does_not_install_models(monkeypatch):
    def fake(req,timeout):
        assert req.full_url=='http://127.0.0.1:11434/api/tags'
        assert req.get_method()=='GET'
        return Resp({'models':[{'name':'tiny:local'},{'name':'another:local'}]})
    monkeypatch.setattr(providers,'_open',fake)
    assert providers.installed_models()==['tiny:local','another:local']


def test_learning_is_optin_and_tenant_scoped(monkeypatch):
    a=core.create_company('A')['company_id'];b=core.create_company('B')['company_id']
    item=core.create_learning_subscription(a,sample_source())
    assert len(core.list_learning_subscriptions(a))==1
    assert not core.list_learning_subscriptions(b)
    assert not core.change_learning_subscription(b,item,'paused')
    assert core.refresh_due_learning_subscription() is None
    monkeypatch.setenv('POLSIA_LEARNING_ENABLED','1')
    assert core.refresh_due_learning_subscription() is None  # Internet still disabled.


def test_learning_validates_sources_and_rate_limit():
    c=core.create_company('A')['company_id']
    for url in ('http://example.com/page','https://127.0.0.1/test',
                'https://localhost/secret','https://company.internal/secret'):
        with pytest.raises(ValueError):
            core.create_learning_subscription(c,{**sample_source(),'url':url})
    with pytest.raises(ValueError):
        core.create_learning_subscription(c,{**sample_source(),'interval_hours':1})
    core.create_learning_subscription(c,sample_source())
    with pytest.raises(ValueError,match='Already following'):
        core.create_learning_subscription(c,sample_source())


def test_learning_stores_only_new_cited_snapshots(monkeypatch):
    c=core.create_company('A')['company_id']
    item=core.create_learning_subscription(c,sample_source())
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    monkeypatch.setenv('POLSIA_LEARNING_ENABLED','1')
    monkeypatch.setattr(core.capacity,'admit',lambda *args,**kwargs:{'admitted':True,'reasons':[]})
    monkeypatch.setattr(core.capacity,'snapshot',lambda: {})
    calls=[]
    def fake_fetch(url):
        calls.append(url)
        return {'url':url,'excerpt':'Observed stars in records.','sha256':'a'*64}
    monkeypatch.setattr(core.research,'fetch_public',fake_fetch)
    first=core.refresh_due_learning_subscription()
    assert first['status']=='RETRIEVED_UNVERIFIED'
    found=core.search_knowledge(c,'Observed stars')
    assert len(found)==1 and found[0]['evidence_status']=='retrieved_unverified'
    assert found[0]['source']=='https://science.example.org/reading'
    assert core.refresh_due_learning_subscription() is None
    with core.connect() as db:
        db.execute('UPDATE learning_subscriptions SET next_due=0 WHERE id=?',(item,))
    assert core.refresh_due_learning_subscription()['status']=='UNCHANGED'
    assert len(core.search_knowledge(c,'Observed stars'))==1
    assert len(calls)==2


def test_paused_learning_does_not_fetch(monkeypatch):
    c=core.create_company('A')['company_id']
    item=core.create_learning_subscription(c,sample_source())
    assert core.change_learning_subscription(c,item,'paused')
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    monkeypatch.setenv('POLSIA_LEARNING_ENABLED','1')
    monkeypatch.setattr(core.capacity,'admit',lambda *args,**kwargs:{'admitted':True,'reasons':[]})
    monkeypatch.setattr(core.capacity,'snapshot',lambda:{})
    monkeypatch.setattr(core.research,'fetch_public',lambda *_: pytest.fail('Paused source fetched'))
    assert core.refresh_due_learning_subscription() is None


def test_learning_throttles_before_fetch(monkeypatch):
    c=core.create_company('A')['company_id']
    core.create_learning_subscription(c,sample_source())
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    monkeypatch.setenv('POLSIA_LEARNING_ENABLED','1')
    monkeypatch.setattr(core.capacity,'admit',lambda *args,**kwargs:{'admitted':False,'reasons':['low_memory']})
    monkeypatch.setattr(core.capacity,'snapshot',lambda:{})
    monkeypatch.setattr(core.research,'fetch_public',lambda *_: pytest.fail('Unsafe source fetched'))
    assert core.refresh_due_learning_subscription()['status']=='THROTTLED'


def test_learning_api_tenant_roles_and_no_unrequested_network(monkeypatch):
    a=core.create_company('A');b=core.create_company('B')
    ha={'Authorization':'Bearer '+a['token']}
    hb={'Authorization':'Bearer '+b['token']}
    with TestClient(app) as client:
        created=client.post('/learning/sources',headers=ha,json=sample_source())
        assert created.status_code==201
        source_id=created.json()['source_id']
        assert len(client.get('/learning/sources',headers=ha).json()['sources'])==1
        assert client.get('/learning/sources',headers=hb).json()['sources']==[]
        assert client.post('/learning/sources/'+source_id+'/pause',headers=hb).status_code==404
        assert client.post('/learning/sources/'+source_id+'/pause',headers=ha).status_code==200
        assert client.get('/health').json()['knowledge_refresh']=='disabled'


def test_cloud_model_identifier_rejected(monkeypatch):
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','gemma4:cloud')
    assert providers.configuration()['status']=='invalid_local_configuration'
    with pytest.raises(providers.ProviderError):
        providers.require_configured()


def test_local_model_status_endpoint_uses_real_local_response(monkeypatch):
    a=core.create_company('A')
    headers={'Authorization':'Bearer '+a['token']}
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','installed:1b')
    def fake(req,timeout):
        assert req.full_url=='http://127.0.0.1:11434/api/tags'
        return Resp({'models':[{'name':'installed:1b'}]})
    monkeypatch.setattr(providers,'_open',fake)
    with TestClient(app) as client:
        r=client.get('/intelligence/local-models',headers=headers)
        assert r.status_code==200
        assert r.json()['selected_model_installed'] is True
        assert r.json()['external_inference'] is False
        assert client.get('/intelligence/local-models').status_code==401


def test_local_model_catalog_unavailable_is_not_reported_as_connected(monkeypatch):
    c=core.create_company('A')
    monkeypatch.setattr(providers,'_open',lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()))
    with TestClient(app) as client:
        r=client.get('/intelligence/local-models',headers={'Authorization':'Bearer '+c['token']})
        assert r.status_code==503
