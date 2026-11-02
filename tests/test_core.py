import pytest
from app import core

@pytest.fixture(autouse=True)
def db(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'test.db'))
    core.init_db()

def test_durable_execution_and_dependencies():
    c=core.create_company('Acme'); cid=c['company_id']
    assert core.authenticate(c['token'])['company_id']==cid
    mid=core.create_mission(cid,'execute',[{'name':'first','tool':'internal.add','inputs':{'values':[2,3]}},{'name':'second','tool':'internal.echo','inputs':{'text':'done'},'depends_on':['first']}])
    assert core.run_once()['status']=='SUCCEEDED'
    assert core.run_once()['status']=='SUCCEEDED'
    assert core.get_mission(cid,mid)['mission']['status']=='SUCCEEDED'
    assert core.run_once() is None
    assert len(core.get_events(cid,mid))>=6

def test_approvals_and_tenant_boundary():
    a=core.create_company('A');b=core.create_company('B')
    mid=core.create_mission(a['company_id'],'approval',[{'name':'x','tool':'internal.echo','inputs':{'text':'x'},'approval_required':True}])
    task=core.get_mission(a['company_id'],mid)['tasks'][0]
    assert core.get_mission(b['company_id'],mid) is None
    assert not core.approve(b['company_id'],task['id'])
    assert core.run_once() is None
    assert core.approve(a['company_id'],task['id'])
    assert core.run_once()['status']=='SUCCEEDED'

def test_invalid_cycle():
    cid=core.create_company('X')['company_id']
    with pytest.raises(ValueError,match='cycle'):
        core.create_mission(cid,'bad',[{'name':'a','tool':'internal.echo','depends_on':['b']},{'name':'b','tool':'internal.echo','depends_on':['a']}])

def test_error_not_reported_success():
    cid=core.create_company('X')['company_id']
    mid=core.create_mission(cid,'bad',[{'name':'bad','tool':'internal.add','inputs':{'values':['oops']}}])
    assert core.run_once()['status']=='QUEUED'
    assert core.run_once()['status']=='QUEUED'
    assert core.run_once()['status']=='FAILED'
    assert core.get_mission(cid,mid)['mission']['status']=='FAILED'
