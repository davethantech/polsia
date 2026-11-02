"""Small operational API. No AI provider or external integration is claimed."""
import os
from fastapi import FastAPI,Header,HTTPException,Depends
from pydantic import BaseModel,Field
from . import core

app=FastAPI(title='Autonomous Company Execution Core',version='0.1.0')

@app.on_event('startup')
def startup(): core.init_db()

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
def health():return {'status':'ok','ai_provider':'unconfigured','external_integrations':'unconfigured'}

@app.post('/bootstrap',status_code=201)
def bootstrap(body:Bootstrap,x_bootstrap_token:str=Header(default='')):
    configured=os.environ.get('BOOTSTRAP_TOKEN','')
    if not configured or x_bootstrap_token!=configured:raise HTTPException(403,'Bootstrap disabled or denied')
    return core.create_company(body.name)

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
