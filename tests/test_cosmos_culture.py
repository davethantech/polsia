"""Unit/integration tests use stubbed external APIs; not live connectivity claims."""
import hashlib
import json
import pytest
from urllib.parse import parse_qs, urlsplit
from app import core, culture, cosmos

@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',str(tmp_path/'test.db'))
    monkeypatch.delenv('POLSIA_CULTURE_REFRESH_ENABLED',raising=False)
    monkeypatch.delenv('POLSIA_NETWORK_ENABLED',raising=False)
    core.init_db()


def record(**overrides):
    data={'title':'Text commentary','tradition':'Vedic','topic':'cosmology',
          'work':'Rigveda','passage':'1.1','language':'Sanskrit',
          'source_url':'https://gretil.sub.uni-goettingen.de/',
          'evidence_class':'historical_primary_text','content':'A historical claim with a precise edition and passage.'}
    return {**data,**overrides}


def subscribe(**overrides):
    return {'title':'Public source','tradition':'Vedic','url':'https://gretil.sub.uni-goettingen.de/',
            'interval_hours':24,**overrides}


def test_horizons_fixed_parameters_and_hard_limits():
    url=cosmos.horizons_url('mars','2026-11-02')
    q=parse_qs(urlsplit(url).query)
    assert urlsplit(url).hostname=='ssd.jpl.nasa.gov'
    assert q['COMMAND']==["'499'"]
    assert q['REF_PLANE']==['ECLIPTIC']
    assert q['CENTER']==["'500@399'"]
    assert q['TIME_TYPE']==['UT']
    assert q['VEC_LABELS']==['NO']
    assert q['VEC_CORR']==['NONE']
    assert q['TLIST_TYPE']==['CAL']
    assert q['TLIST']==["'2026-11-02 00:00'"]
    assert 'START_TIME' not in q
    for body,date in [('unknown','2026-11-02'),('mars','1600-01-01'),
                      ('mars',"2026-11-02'&COMMAND='10"),('mars','no')]:
        with pytest.raises(ValueError):cosmos.horizons_url(body,date)


def test_parse_single_jpl_vector_and_reject_incomplete_or_multiple():
    excerpt="""Target body name: Mars (499)\n$$SOE
2461346.500000000, A.D. 2026-Nov-02 00:00:00.0000 TDB, 1.0E+06, 0.0, -5.0,
 0.0, 1.0E-1, 0.0,
$$EOE"""
    with pytest.raises(ValueError,match='Malformed|exactly one'):
        cosmos.parse_vectors(excerpt)  # Multiline data row is not accepted.
    one="$$SOE\n2461346.500000000, A.D. 2026-Nov-02 TDB, 0.0, 1.0E+06, -5, 0, 0.1, 0,\n$$EOE"
    out=cosmos.parse_vectors(one)
    assert out['geocentric_ecliptic_J2000_longitude_degrees']==90
    assert out['position_km']['z']==-5
    for malformed in ('no ephemeris',one.replace('$$EOE',''),
                      one.replace('1.0E+06','banana'),
                      one.replace('$$EOE','2461347, date, 0, 0, 0, 0, 0, 0,\n$$EOE')):
        with pytest.raises(ValueError):cosmos.parse_vectors(malformed)


def test_jpl_workflow_persists_remote_provenance(monkeypatch):
    sample='$$SOE\n2461346.5, A.D. 2026-Nov-02 00:00:00 TDB, 1000, 0, 0, 0, 2, 0,\n$$EOE'
    def fake(url):
        assert "horizons.api" in url
        return {'url':url,'sha256':hashlib.sha256(sample.encode()).hexdigest(),
                'retrieved_at':1000,'excerpt':sample}
    monkeypatch.setattr(cosmos.research,'fetch_public',fake)
    company=core.create_company('Astronomy')['company_id']
    mid=core.create_mission(company,'NASA JPL lookup',[
        {'name':'planet','tool':'astronomy.horizons','inputs':{'body':'mars','date_utc':'2026-11-02'}}])
    r=core.run_once()
    assert r['status']=='SUCCEEDED'
    assert r['result']['evidence_class']=='remote_scientific_ephemeris_unverified_locally'
    assert 'J2000' in r['result']['reference_frame']
    assert core.get_mission(company,mid)['tasks'][0]['status']=='SUCCEEDED'


def test_remote_ephemeris_does_not_invent_data_if_offline():
    company=core.create_company('Offline')['company_id']
    mid=core.create_mission(company,'NASA JPL lookup',[
        {'name':'planet','tool':'astronomy.horizons','inputs':{'body':'mars','date_utc':'2026-11-02'}}])
    assert core.run_once()['status']=='QUEUED'
    assert core.run_once()['status']=='QUEUED'
    assert core.run_once()['status']=='FAILED'
    assert core.get_mission(company,mid)['mission']['status']=='FAILED'


def test_zodiac_signs_nakshatras_and_ayanamsha_no_default():
    a=cosmos.zodiac('0')
    assert a['tropical_sign']=='Aries'
    assert a['sidereal_status'].startswith('ayanamsha_required')
    b=cosmos.zodiac('24',ayanamsha_deg='24')
    assert b['sidereal_sign']=='Aries' and b['nakshatra']=='Ashwini'
    assert cosmos.zodiac('360',ayanamsha_deg='0')['nakshatra']=='Ashwini'
    assert cosmos.zodiac('-1',ayanamsha_deg='0')['tropical_sign']=='Pisces'
    assert cosmos.zodiac('359.9999999999',ayanamsha_deg='0')['nakshatra']=='Revati'
    for v in ('NaN','Infinity',float('inf'),None):
        with pytest.raises(ValueError):cosmos.zodiac(v)
    with pytest.raises(ValueError):cosmos.zodiac(35,ayanamsha_deg=70)
    with pytest.raises(ValueError):cosmos.zodiac(35,frame='J2000')


def test_cultural_evidence_never_marked_verified_by_user_claim():
    company=core.create_company('Cultures')['company_id']
    item_id=core.add_culture_record(company,record())
    rows=core.get_culture_records(company,'Rigveda')
    assert len(rows)==1 and rows[0]['id']==item_id
    assert rows[0]['evidence_class']=='historical_primary_text'
    assert rows[0]['review_status']=='user_supplied_unverified'
    assert rows[0]['passage']=='1.1'


def test_culture_record_mission_persistence():
    company=core.create_company('History')['company_id']
    mission=core.create_mission(company,'Document ancient text',[
        {'name':'record','tool':'culture.record','inputs':record()}])
    assert core.run_once()['status']=='SUCCEEDED'
    rows=core.get_culture_records(company,'cosmology')
    assert len(rows)==1  # Searches topic and work, too.
    assert len(core.get_culture_records(company,'Vedic'))==1
    assert core.get_mission(company,mission)['mission']['status']=='SUCCEEDED'


def test_cross_company_records_and_subscriptions_not_readable():
    a=core.create_company('A')['company_id'];b=core.create_company('B')['company_id']
    core.add_culture_record(a,record())
    sid=core.create_culture_subscription(a,subscribe())
    assert core.get_culture_records(b)==[]
    assert core.list_culture_subscriptions(b)==[]
    assert not core.change_culture_subscription(b,sid,'paused')
    assert core.change_culture_subscription(a,sid,'paused')
    assert core.list_culture_subscriptions(a)[0]['status']=='paused'


def test_source_validation_and_restricted_subscription_interval():
    for v in [record(source_url='http://example.com'),
              record(evidence_class='scientifically_proven'),
              record(content=''), record(title='')]:
        with pytest.raises(ValueError):culture.validate_record(v)
    for v in [subscribe(url='http://example.org'),subscribe(url='https://localhost/path'),subscribe(url='https://127.0.0.1/'),
              subscribe(interval_hours=1),subscribe(interval_hours=True)]:
        with pytest.raises(ValueError):culture.validate_subscription(v)


def test_scheduled_refresh_requires_both_opt_ins(monkeypatch):
    company=core.create_company('Schedule')['company_id']
    core.create_culture_subscription(company,subscribe())
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    assert core.refresh_due_culture_subscription() is None
    monkeypatch.delenv('POLSIA_NETWORK_ENABLED')
    monkeypatch.setenv('POLSIA_CULTURE_REFRESH_ENABLED','1')
    assert core.refresh_due_culture_subscription() is None


def test_scheduled_refresh_persists_once_then_deduplicates(monkeypatch):
    company=core.create_company('Scheduled')['company_id']
    sid=core.create_culture_subscription(company,subscribe())
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    monkeypatch.setenv('POLSIA_CULTURE_REFRESH_ENABLED','1')
    called=[]
    def fake(url):
        called.append(url)
        text='Public-source excerpt still requiring verification'
        return {'url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),
                'retrieved_at':core.now(),'excerpt':text}
    monkeypatch.setattr(core.research,'fetch_public',fake)
    assert core.refresh_due_culture_subscription()['status']=='RETRIEVED_UNVERIFIED'
    assert core.refresh_due_culture_subscription() is None
    assert len(called)==1
    rows=core.get_culture_records(company)
    assert len(rows)==1 and rows[0]['review_status']=='retrieved_unverified'
    assert rows[0]['subscription_id']==sid
    with core.connect() as db:
        db.execute('UPDATE culture_subscriptions SET next_due=0 WHERE id=?',(sid,))
    assert core.refresh_due_culture_subscription()['status']=='UNCHANGED'
    assert len(core.get_culture_records(company))==1


def test_scheduled_refresh_failure_never_claims_success(monkeypatch):
    company=core.create_company('Failure')['company_id']
    core.create_culture_subscription(company,subscribe())
    monkeypatch.setenv('POLSIA_NETWORK_ENABLED','1')
    monkeypatch.setenv('POLSIA_CULTURE_REFRESH_ENABLED','1')
    def bad(_url):raise ValueError('HTTP 503')
    monkeypatch.setattr(core.research,'fetch_public',bad)
    result=core.refresh_due_culture_subscription()
    assert result['status']=='FAILED' and result['error_type']=='ValueError'
    assert core.get_culture_records(company)==[]
    assert core.refresh_due_culture_subscription() is None


def test_subscription_limit_and_pause(monkeypatch):
    c=core.create_company('Limited')['company_id']
    for i in range(10):
        core.create_culture_subscription(c,subscribe(url=f'https://example.org/{i}'))
    with pytest.raises(ValueError,match='Maximum'):
        core.create_culture_subscription(c,subscribe(url='https://example.org/11'))
    sid=core.list_culture_subscriptions(c)[0]['id']
    core.change_culture_subscription(c,sid,'paused')
    assert core.list_culture_subscriptions(c)[0]['status']=='paused'


def test_api_auth_enforcement_and_subscriptions():
    from fastapi.testclient import TestClient
    from app.main import app
    a=core.create_company('Tenant A'); b=core.create_company('Tenant B')
    owner={'Authorization':'Bearer '+a['token']}
    other={'Authorization':'Bearer '+b['token']}
    with TestClient(app) as client:
        assert client.get('/cosmos/catalog').status_code==401
        assert client.get('/culture/catalog',headers=owner).status_code==200
        assert client.post('/cosmos/zodiac',headers=owner,json={'longitude_deg':10}).json()['tropical_sign']=='Aries'
        r=client.post('/culture/records',headers=owner,json=record())
        assert r.status_code==201
        assert len(client.get('/culture/records',headers=owner).json())==1
        assert client.get('/culture/records',headers=other).json()==[]
        r=client.post('/culture/subscriptions',headers=owner,json=subscribe())
        assert r.status_code==201
        sid=r.json()['subscription_id']
        assert client.post(f'/culture/subscriptions/{sid}/pause',headers=other).status_code==404
        assert client.post(f'/culture/subscriptions/{sid}/pause',headers=owner).status_code==200
        assert client.post(f'/culture/subscriptions/{sid}/resume',headers=owner).status_code==200
        assert client.post('/culture/records',json=record()).status_code==401
