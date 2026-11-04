import json
import math
import pytest
from fastapi.testclient import TestClient
from app import core, neural
from app.main import app


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'neural.db'))
    core.init_db()


def create_sources(company):
    core.store_knowledge(company,'research',
        'Scientific research market analysis with numerical experiments and economics. '
        'Detailed evidence from verified evaluations and market sizing.',
        'https://example.org/sourceA')
    core.store_knowledge(company,'research',
        'Research market analysis. Traditional history and cultural commentary.',
        'https://example.org/sourceB')
    matches=core.search_evidence(company,'research market analysis',8)
    assert len(matches)==2
    return matches


def test_genuine_gradient_update_improves_pairwise_margin():
    q='research market analysis'
    pos={'excerpt':'research market analysis rigorous methodology methods methods',
         'title':'market evidence', 'kind':'company_memory','source_url':'https://example.org',
         'evidence_class':'retrieved_unverified'}
    neg={'excerpt':'research analysis', 'title':'history','kind':'cultural_source',
         'source_url':'','evidence_class':'retrieved_unverified'}
    original=neural.initial()
    copy=json.loads(json.dumps(original))
    trained, metrics=neural.train_pair(original,q,pos,neg)
    assert metrics['loss_after']<metrics['loss_before']
    assert neural.score(trained,q,pos)-neural.score(trained,q,neg) > (
        neural.score(original,q,pos)-neural.score(original,q,neg))
    assert original==copy and trained!=original


def test_tenant_weights_stored_no_cross_company_learning():
    a=core.create_company('A')['company_id']
    b=core.create_company('B')['company_id']
    sources=create_sources(a)
    query='research market analysis'
    status=core.neural_status(a)
    assert status['version']==0
    out=core.record_neural_feedback(a,query,sources[0]['citation_id'],sources[1]['citation_id'])
    assert out['version']==1 and out['loss_after']<out['loss_before']
    assert core.neural_status(b)['version']==0
    with pytest.raises(ValueError,match='this company'):
        core.record_neural_feedback(b,query,sources[0]['citation_id'],sources[1]['citation_id'])
    with pytest.raises(ValueError,match='Duplicate'):
        core.record_neural_feedback(a,query,sources[0]['citation_id'],sources[1]['citation_id'])
    with core.connect() as db:
        record=db.execute('SELECT version,feedback_count,weights FROM neural_rankers WHERE company_id=?',(a,)).fetchone()
        assert record['feedback_count']==1 and record['version']==1
        neural.validate(json.loads(record['weights']))
        assert db.execute('SELECT COUNT(*) FROM neural_feedback WHERE company_id=?',(b,)).fetchone()[0]==0


def test_invalid_training_labels_rejected_and_no_update():
    a=core.create_company('A')['company_id'];sources=create_sources(a)
    with pytest.raises(ValueError,match='distinct'):
        core.record_neural_feedback(a,'research market analysis',sources[0]['citation_id'],sources[0]['citation_id'])
    with pytest.raises(ValueError,match='this company'):
        core.record_neural_feedback(a,'research market analysis',sources[0]['citation_id'],'memory:invented')
    with pytest.raises(ValueError):
        core.record_neural_feedback(a,'   ',sources[0]['citation_id'],sources[1]['citation_id'])
    assert core.neural_status(a)['version']==0


def test_no_unbounded_or_nan_neural_weights():
    w=neural.initial();w['w2'][0]=float('nan')
    with pytest.raises(ValueError):neural.validate(w)
    w=neural.initial();w['w1'][1][2]=100
    with pytest.raises(ValueError):neural.validate(w)
    w=neural.initial();w['w1']=[]
    with pytest.raises(ValueError):neural.validate(w)


def test_api_authorization_and_tenant_learning():
    a=core.create_company('A');b=core.create_company('B')
    sources=create_sources(a['company_id'])
    payload={'question':'research market analysis',
             'preferred_citation_id':sources[0]['citation_id'],
             'rejected_citation_id':sources[1]['citation_id']}
    with TestClient(app) as client:
        assert client.get('/intelligence/neural/status').status_code==401
        assert client.post('/intelligence/neural/feedback',json=payload).status_code==401
        r=client.post('/intelligence/neural/feedback',
            headers={'Authorization':'Bearer '+b['token']},json=payload)
        assert r.status_code==422
        ok=client.post('/intelligence/neural/feedback',
            headers={'Authorization':'Bearer '+a['token']},json=payload)
        assert ok.status_code==200 and ok.json()['version']==1
        status=client.get('/intelligence/neural/status',
            headers={'Authorization':'Bearer '+a['token']}).json()
        assert status['feedback_count']==1 and status['general_intelligence'] is False
        assert client.get('/intelligence/neural/status',
            headers={'Authorization':'Bearer '+b['token']}).json()['version']==0


def test_training_quota_enforced(monkeypatch):
    a=core.create_company('A')['company_id'];sources=create_sources(a)
    monkeypatch.setattr(neural,'MAX_FEEDBACK',0)
    # First training is allowed because no prior model exists. Next one is blocked.
    core.record_neural_feedback(a,'research market analysis',sources[0]['citation_id'],sources[1]['citation_id'])
    with pytest.raises(ValueError,match='quota'):
        core.record_neural_feedback(a,'research market analysis',sources[1]['citation_id'],sources[0]['citation_id'])


def test_bounded_parallel_worker_claims_unique_tasks(monkeypatch):
    from app import worker
    a=core.create_company('A')['company_id']
    mid=core.create_mission(a,'parallel read-only work',[
        {'name':'independent_a','tool':'internal.echo','inputs':{'text':'first'}},
        {'name':'independent_b','tool':'internal.echo','inputs':{'text':'second'}}])
    monkeypatch.setattr(core.capacity,'admit',lambda *args,**kwargs:{'admitted':True,'reasons':[]})
    monkeypatch.setattr(core.capacity,'snapshot',lambda:{})
    res=worker.process_batch(2)
    assert sorted(r['status'] for r in res)==['SUCCEEDED','SUCCEEDED']
    assert len(set(r['task_id'] for r in res))==2
    assert core.get_mission(a,mid)['mission']['status']=='SUCCEEDED'
    assert worker.process_batch(2)==[None,None]


def test_parallel_worker_rejects_unbounded_workers():
    from app import worker
    for count in (0,3,-1,100,1.3,True):
        with pytest.raises(ValueError):worker.process_batch(count)
