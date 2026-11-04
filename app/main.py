"""Small operational API. No AI provider or external integration is claimed."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI,Header,HTTPException,Depends
from pydantic import BaseModel,Field
from . import core,capacity,cosmos,culture,providers

@asynccontextmanager
async def lifespan(_app):
    core.init_db()
    yield

app=FastAPI(title='Autonomous Company Execution Core',version='0.4.0',lifespan=lifespan)

class Bootstrap(BaseModel):
    name:str=Field(min_length=1,max_length=120)
class TaskSpec(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    tool:str
    inputs:dict=Field(default_factory=dict)
    depends_on:list[str]=Field(default_factory=list)
    approval_required:bool=False
    success_condition:str='tool_result_valid'
class MissionSpec(BaseModel):
    objective:str=Field(min_length=1,max_length=2000)
    tasks:list[TaskSpec]=Field(min_length=1,max_length=30)

def principal(authorization:str=Header(default='')):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Bearer token required')
    p=core.authenticate(authorization[7:])
    if not p:raise HTTPException(401,'Invalid token')
    return p

def owner(p=Depends(principal)):
    if p['role']!='owner':raise HTTPException(403,'Owner role required')
    return p

@app.get('/health')
def health():return {'status':'ok','ai_provider':providers.configuration()['status'],'internet_research':'enabled' if os.environ.get('POLSIA_NETWORK_ENABLED')=='1' else 'disabled','external_integrations':'unconfigured','cultural_source_refresh':'enabled' if os.environ.get('POLSIA_CULTURE_REFRESH_ENABLED')=='1' and os.environ.get('POLSIA_NETWORK_ENABLED')=='1' else 'disabled'}

@app.get('/capacity')
def get_capacity(p=Depends(principal)):
    return capacity.capacity()

@app.get('/knowledge')
def knowledge(query:str='',limit:int=20,p=Depends(principal)):
    return core.search_knowledge(p['company_id'],query,limit)

class MemoryInput(BaseModel):
    layer:str='company'
    content:str=Field(min_length=1,max_length=12000)
    source:str=Field(default='',max_length=2048)

@app.post('/knowledge',status_code=201)
def add_knowledge(data:MemoryInput,p=Depends(owner)):
    try: memory_id=core.store_knowledge(p['company_id'],data.layer,data.content,data.source)
    except ValueError as e:raise HTTPException(422,str(e))
    return {'memory_id':memory_id,'evidence_status':'user_supplied_unverified'}

@app.get('/usage')
def usage(p=Depends(principal)):
    return core.get_usage(p['company_id'])

@app.post('/bootstrap',status_code=201)
def bootstrap(body:Bootstrap,x_bootstrap_token:str=Header(default='')):
    configured=os.environ.get('BOOTSTRAP_TOKEN','')
    if not configured or x_bootstrap_token!=configured:raise HTTPException(403,'Bootstrap disabled or denied')
    return core.create_company(body.name)

@app.post('/missions/estimate')
def estimate(body:MissionSpec,p=Depends(owner)):
    try:
        result=core.estimate_mission([t.model_dump() for t in body.tasks])
    except ValueError as e:raise HTTPException(422,str(e))
    return {**result,'capacity':capacity.capacity()}

@app.post('/missions',status_code=201)
def create_mission(body:MissionSpec,p=Depends(owner)):
    try:mission_id=core.create_mission(p['company_id'],body.objective,[t.model_dump() for t in body.tasks])
    except ValueError as e:raise HTTPException(422,str(e))
    return {'mission_id':mission_id,'status':'ACTIVE'}

@app.get('/missions/{mission_id}')
def mission(mission_id:str,p=Depends(principal)):
    value=core.get_mission(p['company_id'],mission_id)
    if value is None:raise HTTPException(404,'Mission not found')
    return value

@app.post('/tasks/{task_id}/approve')
def approve(task_id:str,p=Depends(owner)):
    if not core.approve(p['company_id'],task_id):raise HTTPException(404,'Pending approval not found')
    return {'approved':True}

@app.get('/missions/{mission_id}/events')
def events(mission_id:str,p=Depends(principal)):
    if core.get_mission(p['company_id'],mission_id) is None:raise HTTPException(404,'Mission not found')
    return core.get_events(p['company_id'],mission_id)


# Knowledge and astronomy require evidence labeling. These endpoints are
# authenticated, but they are NOT an AI general-reasoning or prediction service.
@app.get('/cosmos/catalog')
def cosmos_catalog(p=Depends(principal)):
    return {'bodies':list(cosmos.BODIES),'provider':'NASA/JPL Horizons',
            'live_availability':'not_checked','network_enabled':os.environ.get('POLSIA_NETWORK_ENABLED')=='1',
            'limitations':'JPL ephemeris requires live access; astrology is cultural interpretation.'}

class ZodiacInput(BaseModel):
    longitude_deg:float
    ayanamsha_deg:float|None=None
    frame:str='ecliptic_of_date'

@app.post('/cosmos/zodiac')
def zodiac(data:ZodiacInput,p=Depends(principal)):
    try:return cosmos.zodiac(data.longitude_deg,ayanamsha_deg=data.ayanamsha_deg,frame=data.frame)
    except ValueError as e:raise HTTPException(422,str(e))

@app.get('/culture/catalog')
def culture_catalog(p=Depends(principal)):
    return {'sources':culture.SOURCE_CATALOG,
            'coverage':'seed_catalog_only_not_a_complete_world_knowledge_base',
            'interpretations':'traditional_beliefs_are_not_empirical_predictions'}

class CultureRecordInput(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    tradition:str=Field(min_length=1,max_length=100)
    topic:str=Field(min_length=1,max_length=120)
    language:str=Field(default='',max_length=80)
    work:str=Field(default='',max_length=200)
    passage:str=Field(default='',max_length=200)
    source_url:str=Field(min_length=1,max_length=2048)
    evidence_class:str
    content:str=Field(min_length=1,max_length=12000)

@app.get('/culture/records')
def culture_records(query:str='',limit:int=20,p=Depends(principal)):
    return core.get_culture_records(p['company_id'],query,limit)

@app.post('/culture/records',status_code=201)
def culture_record(data:CultureRecordInput,p=Depends(owner)):
    try:record_id=core.add_culture_record(p['company_id'],data.model_dump())
    except ValueError as e:raise HTTPException(422,str(e))
    return {'record_id':record_id,'review_status':'user_supplied_unverified'}

class CultureSubscriptionInput(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    tradition:str=Field(min_length=1,max_length=100)
    url:str=Field(min_length=1,max_length=2048)
    interval_hours:int=Field(default=24,ge=24,le=2160)

@app.get('/culture/subscriptions')
def culture_subscriptions(p=Depends(principal)):
    return core.list_culture_subscriptions(p['company_id'])

@app.post('/culture/subscriptions',status_code=201)
def subscribe_culture(data:CultureSubscriptionInput,p=Depends(owner)):
    try:subscription_id=core.create_culture_subscription(p['company_id'],data.model_dump())
    except ValueError as e:raise HTTPException(422,str(e))
    return {'subscription_id':subscription_id,'automatic_checks':
        'enabled' if os.environ.get('POLSIA_CULTURE_REFRESH_ENABLED')=='1' and os.environ.get('POLSIA_NETWORK_ENABLED')=='1' else 'disabled'}

@app.post('/culture/subscriptions/{subscription_id}/pause')
def pause_culture(subscription_id:str,p=Depends(owner)):
    if not core.change_culture_subscription(p['company_id'],subscription_id,'paused'):
        raise HTTPException(404,'Subscription not found')
    return {'status':'paused'}

@app.post('/culture/subscriptions/{subscription_id}/resume')
def resume_culture(subscription_id:str,p=Depends(owner)):
    if not core.change_culture_subscription(p['company_id'],subscription_id,'active'):
        raise HTTPException(404,'Subscription not found')
    return {'status':'active'}


# Research questions are queued as durable missions; no model call is made in
# an API request. Retrieval also works without an AI provider configuration.
@app.get('/intelligence/provider')
def ai_provider(p=Depends(principal)):
    return {**providers.configuration(), 'daily_call_limit':core.daily_ai_call_limit()}

@app.get('/intelligence/evidence')
def retrieved_evidence(query:str,limit:int=5,p=Depends(principal)):
    try:return {'query':query,'retrieval_method':'tenant_scoped_keyword_matching',
                'sources':core.search_evidence(p['company_id'],query,limit)}
    except ValueError as e:raise HTTPException(422,str(e))

class IntelligenceQuestion(BaseModel):
    question:str=Field(min_length=3,max_length=1200)
    min_sources:int=Field(default=1,ge=1,le=4)

@app.post('/intelligence/questions',status_code=202)
def queue_question(data:IntelligenceQuestion,p=Depends(owner)):
    config=providers.configuration()
    if not config['live_requests']:
        raise HTTPException(503,'AI provider is '+config['status'])
    try:
        mission_id=core.create_mission(p['company_id'],'Evidence-grounded research question',[
            {'name':'grounded_answer','tool':'intelligence.answer',
             'inputs':data.model_dump()}])
    except ValueError as e:raise HTTPException(422,str(e))
    return {'mission_id':mission_id,'status':'ACTIVE',
            'message':'Queued for single-attempt provider execution; no outcome claimed yet'}
