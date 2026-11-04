"""Business departments produce persisted drafts, not simulated completed actions."""
import json
import pytest
from fastapi.testclient import TestClient
from app import business,core,providers
from app.main import app


@pytest.fixture(autouse=True)
def environment(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'business.sqlite'))
    monkeypatch.setenv('POLSIA_AI_ENABLED','1')
    monkeypatch.setenv('POLSIA_LOCAL_MODEL','test:local')
    monkeypatch.setenv('POLSIA_AI_DAILY_CALL_LIMIT','10')
    core.init_db()


def stub_business(monkeypatch, fail=None):
    recorded=[]
    def generate(role,brief,context,schema):
        recorded.append((role,brief,context))
        assert schema['required']==['title','summary','deliverables','assumptions','next_actions','limitations']
        if role==fail:return {'model':'test:local','content':{'invalid':'bad'},'usage':{'input_tokens':12,'output_tokens':14}}
        doc={'title':role.capitalize()+' action plan',
             'summary':'A scoped, testable draft business deliverable from the local model.',
             'deliverables':[{'name':'Work package','content':'Prepare draft work and verify actual results against measured records.'}],
             'assumptions':['The market is not verified yet'],
             'next_actions':['Validate hypotheses with sourced research'],
             'limitations':'No external API action, email, payment, or deployment occurred.'}
        return {'model':'test:local','content':doc,'usage':{'input_tokens':12,'output_tokens':14}}
    monkeypatch.setattr(providers,'generate_business',generate)
    return recorded


def test_launch_produces_real_persistent_nine_department_mission(monkeypatch):
    seen=stub_business(monkeypatch)
    a=core.create_company('Alto')['company_id']; b=core.create_company('Beta')['company_id']
    result=business.launch(core,a,'Create a healthcare platform for independent clinics','Healthcare','India')
    assert result['agent_count']==9
    assert len(core.get_mission(a,result['mission_id'])['tasks'])==9
    for _ in range(9):
        state=core.run_once()
        assert state is not None and state['status']=='SUCCEEDED',state
        assert state['result']['verification']=='schema_checked_no_external_actions'
    assert core.run_once() is None
    assert core.get_mission(a,result['mission_id'])['mission']['status']=='SUCCEEDED'
    docs=business.get_artifacts(core,a,result['mission_id'])
    assert set(d['role'] for d in docs)==set(business.ROLES)
    assert all(d['evidence_status']=='local_model_draft_unverified' for d in docs)
    assert all(d['content']['deliverables'] for d in docs)
    assert len(seen)==9 and seen[0][0]=='executive'
    assert seen[1][0]=='research' and seen[1][2][0]['role']=='executive'
    assert business.get_programs(core,b)==[]
    assert business.get_artifacts(core,b,result['mission_id']) is None
    assert core.get_usage(a)['ai_calls']==9
    assert all('Prepare draft work' not in e['detail'] for e in core.get_events(a,result['mission_id']))


def test_model_fails_closed_once_and_blocks_dependent_agents(monkeypatch):
    stub_business(monkeypatch,fail='executive')
    company=core.create_company('A')['company_id']
    created=business.launch(core,company,'A fully specified medical scheduling SaaS')
    assert core.run_once()['status']=='FAILED'
    assert core.run_once() is None
    mission=core.get_mission(company,created['mission_id'])
    assert mission['mission']['status']=='FAILED'
    assert mission['tasks'][0]['attempt']==1
    assert not business.get_artifacts(core,company,created['mission_id'])
    assert core.get_usage(company)['ai_calls']==1


def test_no_fake_model_connection(monkeypatch):
    monkeypatch.setenv('POLSIA_AI_ENABLED','0')
    a=core.create_company('A')['company_id']
    with pytest.raises(ValueError,match='disabled or unconfigured'):
        business.launch(core,a,'Design a healthcare analytics product')
    assert business.get_programs(core,a)==[]
    assert business.capabilities()['external_actions']['stripe_payments']=='NOT_CONNECTED'


def test_business_document_requires_bounded_actual_content():
    valid={'title':'Support program','summary':'A concrete set of support workflows for a proposed business.',
           'deliverables':[{'name':'FAQ','content':'Customer onboarding answers drafted for company review.'}],
           'assumptions':['Customers will ask onboarding questions'],
           'next_actions':['Verify terminology with company staff'],
           'limitations':'Not sent'}
    assert business.validate_document('support',valid) is valid
    for bad in ({**valid,'deliverables':[]},{**valid,'secret':'x'},
                {**valid,'summary':''},{**valid,'next_actions':[1]}):
        with pytest.raises(ValueError):business.validate_document('support',bad)
    with pytest.raises(ValueError):business.validate_document('ceo-superpowers',valid)


def test_crm_and_support_tenant_scope_and_status():
    a=core.create_company('A')['company_id'];b=core.create_company('B')['company_id']
    lead=business.add_lead(core,a,'Dr Jane',organization='Clinic 1',email='jane@clinic.example',notes='Introduced at expo')
    ticket=business.add_ticket(core,a,'Cannot sign in','Customer says the password reset link fails')
    assert not business.leads(core,b) and not business.tickets(core,b)
    assert business.update_lead(core,b,lead['id'],'contacted') is False
    assert business.update_ticket(core,b,ticket['id'],'closed') is False
    assert business.update_lead(core,a,lead['id'],'qualified')
    assert business.update_ticket(core,a,ticket['id'],'needs_follow_up')
    assert business.leads(core,a)[0]['stage']=='qualified'
    assert business.tickets(core,a)[0]['status']=='needs_follow_up'
    with pytest.raises(ValueError):business.add_lead(core,a,'X',email='no-at-symbol')
    with pytest.raises(ValueError):business.update_ticket(core,a,ticket['id'],'replied_by_ai')
    with pytest.raises(ValueError):business.update_lead(core,a,lead['id'],'money_collected')
    assert all('jane@clinic.example' not in e['detail'] for e in core.get_events(a,None))


def test_business_http_apis_are_company_scoped_and_role_checked(monkeypatch):
    stub_business(monkeypatch)
    a=core.create_company('A');b=core.create_company('B')
    ha={'Authorization':'Bearer '+a['token']};hb={'Authorization':'Bearer '+b['token']}
    with TestClient(app) as client:
        assert client.get('/business/capabilities',headers=ha).status_code==200
        launch=client.post('/business/programs',headers=ha,json={
            'idea':'Build a useful healthcare appointment SaaS','industry':'Healthcare','market':'India'})
        assert launch.status_code==201,launch.text
        item=launch.json()
        assert client.get('/business/programs',headers=hb).json()['programs']==[]
        assert client.get('/business/programs/'+item['program_id'],headers=hb).status_code==404
        assert client.get('/business/programs/'+item['program_id'],headers=ha).status_code==200
        lead=client.post('/business/leads',headers=ha,json={'name':'Clinic One','email':'lead@example.org'})
        assert lead.status_code==201
        assert client.get('/business/leads',headers=hb).json()['leads']==[]
        assert client.patch('/business/leads/'+lead.json()['id'],headers=hb,json={'stage':'contacted'}).status_code==404
        ticket=client.post('/business/tickets',headers=ha,json={'subject':'Setup question','message':'How can I activate the product?'})
        assert ticket.status_code==201
        assert client.get('/business/tickets',headers=hb).json()['tickets']==[]
        assert client.patch('/business/tickets/'+ticket.json()['id'],headers=hb,json={'status':'closed'}).status_code==404
        assert client.patch('/business/leads/'+lead.json()['id'],headers=ha,json={'stage':'qualified'}).status_code==200


def test_program_creation_is_atomic_even_if_registration_fails(monkeypatch):
    a=core.create_company('A')['company_id']
    monkeypatch.setattr(business,'MAX_PROGRAMS',0)
    with pytest.raises(ValueError,match='limit'):
        business.launch(core,a,'Build a global commerce platform')
    assert business.get_programs(core,a)==[]
    with core.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM missions WHERE company_id=?',(a,)).fetchone()[0]==0


def test_browser_session_csrf_viewer_and_company_switch(tmp_path,monkeypatch):
    from app import identity
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'browser_business.db'))
    monkeypatch.setenv('POLSIA_SIGNUP_ENABLED','1')
    monkeypatch.delenv('BOOTSTRAP_TOKEN',raising=False)
    with TestClient(app) as client:
        response=client.post('/auth/register',json={
            'email':'studio@example.com','password':'A-secret-passphrase-2026!',
            'company_name':'Studio A'})
        assert response.status_code==201
        me=client.get('/auth/me').json()
        company=me['memberships'][0]['company_id'];csrf=me['csrf_token']
        headers={'X-Company-ID':company,'X-CSRF-Token':csrf}
        assert client.post('/business/leads',headers={'X-Company-ID':company},json={'name':'Clinic lead'}).status_code==403
        lead=client.post('/business/leads',headers=headers,json={'name':'Clinic lead'})
        assert lead.status_code==201
        assert client.get('/business/leads',headers={'X-Company-ID':company}).json()['leads'][0]['name']=='Clinic lead'
        second=client.post('/companies',headers={'X-CSRF-Token':csrf},json={'name':'Studio B'})
        assert second.status_code==201
        b=second.json()['company_id']
        assert client.get('/business/leads',headers={'X-Company-ID':b}).json()['leads']==[]
        assert client.get('/business/programs').status_code==403
        invite=client.post('/companies/invitations',headers=headers,json={'email':'viewer@example.com','role':'viewer'})
        assert invite.status_code==201
        with TestClient(app) as viewer:
            accepted=viewer.post('/auth/accept-invite',json={'email':'viewer@example.com',
                'password':'A-secret-passphrase-2026!','token':invite.json()['invitation_token']})
            assert accepted.status_code==200
            viewer_csrf=viewer.get('/auth/me').json()['csrf_token']
            viewer_headers={'X-Company-ID':company,'X-CSRF-Token':viewer_csrf}
            assert viewer.get('/business/leads',headers={'X-Company-ID':company}).status_code==200
            assert viewer.post('/business/leads',headers=viewer_headers,json={'name':'Cannot edit'}).status_code==403
            assert viewer.post('/business/programs',headers=viewer_headers,json={'idea':'Create healthcare scheduling software'}).status_code==403


def test_factory_jobs_do_not_auto_execute_or_auto_publish(tmp_path,monkeypatch):
    from app import factory, factory_ops, factory_runner, factory_sandbox
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'factory_gates.db'))
    core.init_db()
    a=core.create_company('Company')['company_id']
    files={'hello.py':'print("hi")\n'}
    monkeypatch.setattr(providers,'generate_code',lambda goal,snapshot:{
        'model':'test:local','content':{'summary':'Update hello world',
        'files':[{'path':'hello.py','content':'print("hello again")\n'}],
        'limitations':'Not tested or deployed'},'usage':{'input_tokens':10,'output_tokens':20}})
    mid=core.create_mission(a,'Change local program',[{'name':'patch','tool':'software.propose',
        'inputs':{'goal':'Improve hello world message','files':files}}])
    assert core.run_once()['status']=='SUCCEEDED'
    prop=core.list_factory_proposals(a)[0]['id']
    queued=factory_ops.queue_test(core,a,prop,'python_syntax')
    assert factory_ops.get_job(core,a,queued)['status']=='QUEUED'
    monkeypatch.delenv('POLSIA_FACTORY_RUNNER_ENABLED',raising=False)
    with pytest.raises(ValueError,match='disabled'):factory_runner.process_one('test')
    with pytest.raises(ValueError,match='disabled'):factory_sandbox.run(files,'python_syntax')
    with pytest.raises(ValueError):factory_ops.queue_publish(core,a,prop,'thirdparty/repository')
    assert factory_ops.list_jobs(core,a)[0]['status']=='QUEUED'
