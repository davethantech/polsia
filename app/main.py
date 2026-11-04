"""Small operational API. No AI provider or external integration is claimed."""
import os
import hashlib
import hmac
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,Header,HTTPException,Depends,Request,Response
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from . import core,capacity,cosmos,culture,providers,identity

@asynccontextmanager
async def lifespan(_app):
    core.init_db()
    identity.install()
    if os.environ.get('POLSIA_ENV') == 'production':
        if os.environ.get('POLSIA_SECURE_COOKIES') != '1':
            raise RuntimeError('Production requires POLSIA_SECURE_COOKIES=1 (TLS reverse proxy)')
        if os.environ.get('BOOTSTRAP_TOKEN'):
            raise RuntimeError('Disable legacy bootstrap token in production')
    yield

app=FastAPI(title='Polsia — Autonomous Company OS',version='0.5.0',lifespan=lifespan,
            docs_url=None if os.environ.get('POLSIA_ENV')=='production' else '/docs',
            redoc_url=None if os.environ.get('POLSIA_ENV')=='production' else '/redoc')
ASSETS = Path(__file__).parent / 'static'
app.mount('/assets',StaticFiles(directory=str(ASSETS)),name='assets')

@app.middleware('http')
async def secure_headers(request:Request,call_next):
    if os.environ.get('POLSIA_ENV')=='production' and request.url.path in ('/docs','/redoc','/openapi.json'):
        return JSONResponse({'detail':'Not found'},status_code=404)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    if os.environ.get('POLSIA_ENV') == 'production':
        response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy']=("default-src 'self'; script-src 'self'; "
      "style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
      "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
    if request.url.path.startswith(('/auth','/missions','/overview','/companies','/knowledge','/usage','/capacity')):
        response.headers['Cache-Control']='no-store'
    return response

@app.get('/',include_in_schema=False)
def landing():return FileResponse(ASSETS / 'index.html')

@app.get('/dashboard',include_in_schema=False)
def dashboard_page():return FileResponse(ASSETS / 'dashboard.html')


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

def csrf_for(token):
    return hmac.new(token.encode(),b'polsia-csrf-v1',hashlib.sha256).hexdigest()


def principal(request:Request,authorization:str=Header(default=''),x_company_id:str=Header(default=''),x_csrf_token:str=Header(default='')):
    # Preserve legacy owner tokens for backwards compatibility; these cannot
    # switch tenant using a forged X-Company-ID header.
    if authorization.startswith('Bearer '):
        if os.environ.get('POLSIA_ENV')=='production' and os.environ.get('POLSIA_ALLOW_LEGACY_TOKENS')!='1':
            raise HTTPException(401,'Legacy tokens disabled in production')
        p=core.authenticate(authorization[7:])
        if not p:raise HTTPException(401,'Invalid bearer token')
        return {**p,'auth_type':'legacy'}
    sid=request.cookies.get('polsia_sid')
    user=identity.session_info(sid)
    if not user:raise HTTPException(401,'Sign in to continue')
    if request.method not in ('GET','HEAD','OPTIONS'):
        if not hmac.compare_digest(x_csrf_token,csrf_for(sid)):
            raise HTTPException(403,'CSRF token missing or invalid')
    membership=None
    if x_company_id:
        membership=next((m for m in user['memberships'] if m['company_id']==x_company_id),None)
    elif len(user['memberships'])==1:
        membership=user['memberships'][0]
    if membership is None:raise HTTPException(403,'Select an authorized company')
    return {'company_id':membership['company_id'],'role':membership['role'],
            'user_id':user['id'],'auth_type':'session'}


def owner(p=Depends(principal)):
    if p['role']!='owner':raise HTTPException(403,'Owner role required')
    return p


def operator(p=Depends(principal)):
    if p['role'] not in ('owner','editor'):raise HTTPException(403,'Editor or owner role required')
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
def add_knowledge(data:MemoryInput,p=Depends(operator)):
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
def estimate(body:MissionSpec,p=Depends(operator)):
    try:
        result=core.estimate_mission([t.model_dump() for t in body.tasks])
    except ValueError as e:raise HTTPException(422,str(e))
    return {**result,'capacity':capacity.capacity()}

@app.post('/missions',status_code=201)
def create_mission(body:MissionSpec,p=Depends(operator)):
    try:mission_id=core.create_mission(p['company_id'],body.objective,[t.model_dump() for t in body.tasks])
    except ValueError as e:raise HTTPException(422,str(e))
    return {'mission_id':mission_id,'status':'ACTIVE'}

@app.get('/missions/{mission_id}')
def mission(mission_id:str,p=Depends(principal)):
    value=core.get_mission(p['company_id'],mission_id)
    if value is None:raise HTTPException(404,'Mission not found')
    return value

@app.post('/tasks/{task_id}/approve')
def approve(task_id:str,p=Depends(operator)):
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
def culture_record(data:CultureRecordInput,p=Depends(operator)):
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
def subscribe_culture(data:CultureSubscriptionInput,p=Depends(operator)):
    try:subscription_id=core.create_culture_subscription(p['company_id'],data.model_dump())
    except ValueError as e:raise HTTPException(422,str(e))
    return {'subscription_id':subscription_id,'automatic_checks':
        'enabled' if os.environ.get('POLSIA_CULTURE_REFRESH_ENABLED')=='1' and os.environ.get('POLSIA_NETWORK_ENABLED')=='1' else 'disabled'}

@app.post('/culture/subscriptions/{subscription_id}/pause')
def pause_culture(subscription_id:str,p=Depends(operator)):
    if not core.change_culture_subscription(p['company_id'],subscription_id,'paused'):
        raise HTTPException(404,'Subscription not found')
    return {'status':'paused'}

@app.post('/culture/subscriptions/{subscription_id}/resume')
def resume_culture(subscription_id:str,p=Depends(operator)):
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
def queue_question(data:IntelligenceQuestion,p=Depends(operator)):
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


# Auth and management routes. A browser session is a user identity, not a
# company identity. Each tenant request must resolve an explicit membership.
class Credentials(BaseModel):
    email:str=Field(min_length=5,max_length=254)
    password:str=Field(min_length=12,max_length=128)

class Registration(Credentials):
    company_name:str=Field(min_length=2,max_length=120)

class CompanyInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)

class InviteInput(BaseModel):
    email:str=Field(min_length=5,max_length=254)
    role:str='viewer'

class AcceptInvitation(Credentials):
    token:str=Field(min_length=10,max_length=200)


def _cookie(response,token):
    response.set_cookie('polsia_sid',token,httponly=True,
       secure=os.environ.get('POLSIA_SECURE_COOKIES')=='1',
       samesite='strict',max_age=identity.SESSION_SECONDS,path='/')

@app.get('/auth/config')
def auth_config():
    return {'signup_enabled':os.environ.get('POLSIA_SIGNUP_ENABLED')=='1',
            'secure_cookies':os.environ.get('POLSIA_SECURE_COOKIES')=='1'}

@app.post('/auth/register',status_code=201)
def register(body:Registration,response:Response):
    if os.environ.get('POLSIA_SIGNUP_ENABLED')!='1':
        raise HTTPException(403,'Public registration disabled; use an invitation')
    try: sid=identity.create_user_company(body.email,body.password,body.company_name)
    except ValueError as exc:raise HTTPException(422,str(exc))
    _cookie(response,sid)
    return {'authenticated':True,'csrf_token':csrf_for(sid)}

@app.post('/auth/login')
def auth_login(body:Credentials,request:Request,response:Response):
    try:sid=identity.login(body.email,body.password,request.client.host if request.client else 'unknown')
    except ValueError:sid=None
    if not sid:raise HTTPException(401,'Invalid credentials or too many attempts')
    _cookie(response,sid)
    return {'authenticated':True,'csrf_token':csrf_for(sid)}

@app.get('/auth/me')
def me(request:Request):
    sid=request.cookies.get('polsia_sid')
    user=identity.session_info(sid)
    if not user:raise HTTPException(401,'Not signed in')
    return {'id':user['id'],'email':user['email'],'memberships':user['memberships'],
            'csrf_token':csrf_for(sid)}

@app.post('/auth/logout')
def logout(request:Request,response:Response,x_csrf_token:str=Header(default='')):
    sid=request.cookies.get('polsia_sid')
    if sid and not hmac.compare_digest(x_csrf_token,csrf_for(sid)):
        raise HTTPException(403,'CSRF token missing or invalid')
    if sid:identity.revoke_session(sid)
    response.delete_cookie('polsia_sid',path='/')
    return {'signed_out':True}

@app.get('/companies')
def companies(request:Request):
    sid=request.cookies.get('polsia_sid')
    user=identity.session_info(sid)
    if not user:raise HTTPException(401,'Not signed in')
    return {'companies':user['memberships']}

@app.post('/companies',status_code=201)
def company_create(body:CompanyInput,request:Request,x_csrf_token:str=Header(default='')):
    sid=request.cookies.get('polsia_sid')
    user=identity.session_info(sid)
    if not user:raise HTTPException(401,'Not signed in')
    if not hmac.compare_digest(x_csrf_token,csrf_for(sid)):
        raise HTTPException(403,'CSRF token missing or invalid')
    try:company_id=identity.create_company(user['id'],body.name)
    except ValueError as exc:raise HTTPException(422,str(exc))
    return {'company_id':company_id,'name':body.name}

@app.post('/companies/invitations',status_code=201)
def invite_member(body:InviteInput,p=Depends(owner)):
    try:token=identity.invite(p['company_id'],body.email,body.role)
    except ValueError as exc:raise HTTPException(422,str(exc))
    return {'invitation_token':token,'expires_in_seconds':identity.INVITE_SECONDS,
            'note':'Give this token securely to the intended recipient; no email was sent.'}

@app.post('/auth/accept-invite')
def accept_invitation(body:AcceptInvitation,response:Response):
    try:sid=identity.accept_invite(body.token,body.email,body.password)
    except ValueError as exc:raise HTTPException(422,str(exc))
    _cookie(response,sid)
    return {'authenticated':True,'csrf_token':csrf_for(sid)}

@app.get('/overview')
def overview(p=Depends(principal)):
    return core.workspace_overview(p['company_id'])

@app.get('/missions')
def missions(limit:int=50,p=Depends(principal)):
    return {'missions':core.list_missions(p['company_id'],limit)}

@app.get('/companies/members')
def members(p=Depends(principal)):
    return {'members':identity.list_members(p['company_id'])}
