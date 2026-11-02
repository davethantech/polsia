"""Persistent, tenant-scoped execution kernel. SQLite is for single-host development."""
import hashlib, json, os, secrets, sqlite3, time, uuid
from contextlib import contextmanager
from . import capacity, mathematics, research

DB_PATH = os.environ.get('POLSIADB', 'polsia.db')

def uid(): return str(uuid.uuid4())
def now(): return int(time.time())
def digest(token): return hashlib.sha256(token.encode()).hexdigest()

@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    try: yield db
    finally: db.close()

def init_db():
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),role TEXT NOT NULL CHECK(role IN ('owner','viewer')));
        CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id), objective TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),mission_id TEXT NOT NULL REFERENCES missions(id),name TEXT NOT NULL,tool TEXT NOT NULL,inputs TEXT NOT NULL,outputs TEXT,depends_on TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,lease_until INTEGER,approval_required INTEGER NOT NULL DEFAULT 0,approved INTEGER NOT NULL DEFAULT 0,success_condition TEXT NOT NULL,updated_at INTEGER NOT NULL, UNIQUE(mission_id,name));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,mission_id TEXT,task_id TEXT,event_type TEXT NOT NULL,detail TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_tasks_ready ON tasks(status,lease_until);
        CREATE INDEX IF NOT EXISTS idx_events_tenant ON events(company_id,created_at);
        CREATE TABLE IF NOT EXISTS knowledge(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),layer TEXT NOT NULL,content TEXT NOT NULL,source TEXT NOT NULL,evidence_status TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_knowledge_tenant ON knowledge(company_id,created_at);
        CREATE TABLE IF NOT EXISTS usage_records(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),mission_id TEXT NOT NULL,task_id TEXT NOT NULL,tool TEXT NOT NULL,elapsed_ms INTEGER NOT NULL,input_bytes INTEGER NOT NULL,output_bytes INTEGER NOT NULL,created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_records(company_id,created_at);
        ''')
        # Add the lease-fencing token without deleting preexisting user data.
        if 'lease_token' not in {r['name'] for r in db.execute('PRAGMA table_info(tasks)')}: 
            db.execute('ALTER TABLE tasks ADD COLUMN lease_token TEXT')

def log(db, company_id, kind, detail, mission_id=None, task_id=None):
    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',(uid(),company_id,mission_id,task_id,kind,json.dumps(detail,sort_keys=True),now()))

def create_company(name):
    token=secrets.token_urlsafe(32); company_id=uid()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO companies VALUES(?,?,?)',(company_id,name,now()))
        db.execute('INSERT INTO tokens VALUES(?,?,?)',(digest(token),company_id,'owner'))
        log(db,company_id,'company.created',{'name':name})
        db.commit()
    return {'company_id':company_id,'token':token}

def authenticate(token):
    with connect() as db:
        row=db.execute('SELECT company_id,role FROM tokens WHERE hash=?',(digest(token),)).fetchone()
    return dict(row) if row else None

ALLOWED_TOOLS={'internal.echo','internal.add','math.evaluate','research.fetch','knowledge.store'}
TOOL_ESTIMATES={'internal.echo':(16,1),'internal.add':(16,1),'math.evaluate':(32,1),
                'research.fetch':(64,2),'knowledge.store':(24,2)}

def store_knowledge(company_id,layer,content,source,evidence_status='user_supplied_unverified',db=None):
    if layer not in ('company','research','math','strategy','project','episodic'):
        raise ValueError('Unknown memory layer')
    if not isinstance(content,str) or not 1<=len(content)<=12000 or not isinstance(source,str) or len(source)>2048:
        raise ValueError('Invalid memory content or source')
    item={'id':uid(),'company_id':company_id,'layer':layer,'content':content,'source':source,
          'evidence_status':evidence_status,'created_at':now()}
    if db is None:
        with connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO knowledge VALUES(?,?,?,?,?,?,?)',tuple(item.values()))
            log(conn,company_id,'knowledge.stored',{'memory_id':item['id'],'layer':layer,'evidence_status':evidence_status})
            conn.commit()
    else:
        db.execute('INSERT INTO knowledge VALUES(?,?,?,?,?,?,?)',tuple(item.values()))
        log(db,company_id,'knowledge.stored',{'memory_id':item['id'],'layer':layer,'evidence_status':evidence_status})
    return item['id']

def search_knowledge(company_id,query='',limit=20):
    with connect() as db:
        return [dict(x) for x in db.execute("SELECT * FROM knowledge WHERE company_id=? AND content LIKE ? ESCAPE '\\' ORDER BY created_at DESC,rowid DESC LIMIT ?",
                     (company_id,'%'+query[:120].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',min(50,max(1,limit))))]

def get_usage(company_id):
    with connect() as db:
        r=db.execute('SELECT COUNT(*) AS total_tasks,COALESCE(SUM(elapsed_ms),0) AS elapsed_ms,COALESCE(SUM(input_bytes),0) AS input_bytes,COALESCE(SUM(output_bytes),0) AS output_bytes FROM usage_records WHERE company_id=?',(company_id,)).fetchone()
        return {**dict(r),'model_tokens':None,'provider_cost_usd':None,'note':'No model-provider accounting configured; resource usage only.'}

def estimate_mission(task_specs):
    """Planning estimates, not guaranteed capacity or billable charges."""
    rows=[]
    for task in task_specs:
        tool=task['tool']
        if tool not in TOOL_ESTIMATES:raise ValueError('Tool is unavailable: '+str(tool))
        mem,disk=TOOL_ESTIMATES[tool]
        rows.append({'name':task['name'],'tool':tool,'estimated_peak_memory_mb':mem,
                     'estimated_disk_mb':disk,'input_bytes':len(json.dumps(task.get('inputs',{})).encode())})
    return {'tasks':rows,'estimated_peak_tool_memory_mb':max((x['estimated_peak_memory_mb'] for x in rows),default=0),
            'estimated_cumulative_disk_mb':sum(x['estimated_disk_mb'] for x in rows),
            'model_tokens':None,'provider_cost_usd':None,'confidence':'assumed_tool_budgets_not_measured',
            'execution_parallelism':1,'note':'Capacity snapshots are not reservations. Host/container quotas are enforced separately.'}

def create_mission(company_id,objective,task_specs):
    if not task_specs or len(task_specs)>30: raise ValueError('Provide 1–30 tasks')
    names=[s['name'] for s in task_specs]
    if len(set(names))!=len(names): raise ValueError('Duplicate task names')
    for s in task_specs:
        if s['tool'] not in ALLOWED_TOOLS: raise ValueError('Tool is unavailable: '+s['tool'])
        if s.get('success_condition','tool_result_valid')!='tool_result_valid': raise ValueError('Unknown verification condition')
        if s.get('depends_on',[]) and not set(s['depends_on']).issubset(names): raise ValueError('Unknown task dependency')
        if s['name'] in s.get('depends_on',[]): raise ValueError('Self dependency')
    edges={s['name']:s.get('depends_on',[]) for s in task_specs}
    def visit(n,stack,done):
        if n in stack: raise ValueError('Dependency cycle')
        if n in done: return
        stack.add(n)
        for d in edges[n]: visit(d,stack,done)
        stack.remove(n);done.add(n)
    done=set()
    for n in names: visit(n,set(),done)
    mission_id=uid()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO missions VALUES(?,?,?,?,?)',(mission_id,company_id,objective,'ACTIVE',now()))
        for s in task_specs:
            task_id=uid(); approval=bool(s.get('approval_required',False))
            db.execute('''INSERT INTO tasks(id,company_id,mission_id,name,tool,inputs,depends_on,status,approval_required,success_condition,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(task_id,company_id,mission_id,s['name'],s['tool'],json.dumps(s.get('inputs',{})),json.dumps(s.get('depends_on',[])),'WAITING_APPROVAL' if approval else 'QUEUED',int(approval),s.get('success_condition','tool_result_valid'),now()))
            log(db,company_id,'task.created',{'name':s['name'],'tool':s['tool']},mission_id,task_id)
        log(db,company_id,'mission.created',{'objective':objective},mission_id)
        db.commit()
    return mission_id

def approve(company_id,task_id):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM tasks WHERE id=? AND company_id=?',(task_id,company_id)).fetchone()
        if not row or row['status']!='WAITING_APPROVAL':
            db.rollback();return False
        db.execute("UPDATE tasks SET status='QUEUED',approved=1,updated_at=? WHERE id=?",(now(),task_id))
        log(db,company_id,'task.approved',{},row['mission_id'],task_id)
        db.commit();return True

def execute_tool(tool,inputs):
    if tool=='internal.echo':
        if not isinstance(inputs.get('text'),str): raise ValueError('text must be string')
        return {'text':inputs['text']}
    if tool=='internal.add':
        values=inputs.get('values')
        if not isinstance(values,list) or len(values)>100 or not all(type(x) in (int,float) for x in values): raise ValueError('values must be numeric list of at most 100')
        return {'sum':sum(values)}
    if tool=='math.evaluate':
        return mathematics.evaluate(inputs.get('expression'))
    if tool=='research.fetch':
        return research.fetch_public(inputs.get('url'))
    if tool=='knowledge.store':
        content=inputs.get('content');source=inputs.get('source','');layer=inputs.get('layer','company')
        if layer not in ('company','research','math','strategy','project','episodic') or not isinstance(content,str) or not (1<=len(content)<=12000) or not isinstance(source,str) or len(source)>2048:
            raise ValueError('Invalid knowledge record')
        return {'content':content,'source':source,'layer':layer,'evidence_status':'user_supplied_unverified'}
    raise ValueError('Tool is unavailable')

def refresh_mission_status(db, mission_id):
    statuses=[r['status'] for r in db.execute('SELECT status FROM tasks WHERE mission_id=?',(mission_id,))]
    if not statuses:return
    if all(state=='SUCCEEDED' for state in statuses):state='SUCCEEDED'
    elif all(state in ('SUCCEEDED','FAILED','BLOCKED') for state in statuses):state='FAILED'
    else:state='ACTIVE'
    db.execute('UPDATE missions SET status=? WHERE id=?',(state,mission_id))

def claim():
    """Atomically claim one ready task; recover expired leases within retry budget."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE tasks SET status='QUEUED',lease_until=NULL,lease_token=NULL WHERE status='RUNNING' AND lease_until<? AND attempt<max_attempts",(now(),))
        db.execute("UPDATE tasks SET status='FAILED',lease_until=NULL,lease_token=NULL WHERE status='RUNNING' AND lease_until<? AND attempt>=max_attempts",(now(),))
        # Propagate terminal dependency failures, including into approval-pending tasks.
        active=db.execute("SELECT * FROM tasks WHERE status IN ('QUEUED','WAITING_APPROVAL')").fetchall()
        affected=set()
        for candidate in active:
            deps=json.loads(candidate['depends_on'])
            if not deps:continue
            statuses={x['name']:x['status'] for x in db.execute('SELECT name,status FROM tasks WHERE mission_id=? AND company_id=?',(candidate['mission_id'],candidate['company_id']))}
            if any(statuses.get(dep) in ('FAILED','BLOCKED') for dep in deps):
                db.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),candidate['id']))
                log(db,candidate['company_id'],'task.blocked',{'reason':'failed dependency'},candidate['mission_id'],candidate['id'])
                affected.add(candidate['mission_id'])
        for mission in db.execute("SELECT id FROM missions WHERE status='ACTIVE'"):
            refresh_mission_status(db,mission['id'])
        rows=db.execute("SELECT * FROM tasks WHERE status='QUEUED' ORDER BY updated_at,id").fetchall()
        chosen=None
        for r in rows:
            deps=json.loads(r['depends_on'])
            if deps:
                statuses={x['name']:x['status'] for x in db.execute('SELECT name,status FROM tasks WHERE mission_id=? AND company_id=?',(r['mission_id'],r['company_id']))}
                if any(statuses[d] in ('FAILED','BLOCKED') for d in deps):
                    db.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),r['id']))
                    log(db,r['company_id'],'task.blocked',{'reason':'failed dependency'},r['mission_id'],r['id'])
                    continue
                if not all(statuses[d]=='SUCCEEDED' for d in deps):continue
            chosen=r;break
        if chosen:
            lease_token=secrets.token_urlsafe(24)
            db.execute("UPDATE tasks SET status='RUNNING',attempt=attempt+1,lease_until=?,lease_token=?,updated_at=? WHERE id=?",(now()+120,lease_token,now(),chosen['id']))
            log(db,chosen['company_id'],'task.started',{'attempt':chosen['attempt']+1},chosen['mission_id'],chosen['id'])
        db.commit()
        return {**dict(chosen), 'lease_token':lease_token} if chosen else None

def run_once():
    # Gate the worker before even claiming a new task. Docker quotas enforce harder limits.
    admission=capacity.admit(capacity.snapshot())
    if not admission['admitted']:
        return {'status':'THROTTLED','reasons':admission['reasons']}
    task=claim()
    if not task:return None
    error=None;result=None
    started=time.monotonic()
    try:
        memory_mb,disk_mb=TOOL_ESTIMATES[task['tool']]
        check=capacity.admit(capacity.snapshot(),memory_mb,disk_mb)
        if not check['admitted']:
            # Capacity may have changed between queue claim and execution.
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("UPDATE tasks SET status='QUEUED',attempt=attempt-1,lease_until=NULL,lease_token=NULL WHERE id=? AND status='RUNNING' AND lease_token=?",(task['id'],task['lease_token']))
                log(db,task['company_id'],'task.throttled',{'reasons':check['reasons']},task['mission_id'],task['id'])
                db.commit()
            return {'status':'THROTTLED','reasons':check['reasons']}

        result=execute_tool(task['tool'],json.loads(task['inputs']))
        # Explicit verifier for current deterministic tools.
        if task['success_condition']!='tool_result_valid' or not isinstance(result,dict):raise ValueError('Unsupported verification condition')
    except Exception as ex: error=str(ex)[:300]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # A stale worker must never overwrite a result after lease recovery.
        current=db.execute('SELECT lease_token,status FROM tasks WHERE id=? AND company_id=?',(task['id'],task['company_id'])).fetchone()
        if current is None or current['status']!='RUNNING' or current['lease_token']!=task['lease_token']:
            db.rollback()
            return {'task_id':task['id'],'status':'STALE_LEASE','result':None,'error':'Lease ownership changed'}
        status='SUCCEEDED' if error is None else ('FAILED' if task['attempt']+1>=task['max_attempts'] else 'QUEUED')
        detail={'error':error} if error else {'result':result,'verification':'tool_result_valid'}
        db.execute('UPDATE tasks SET status=?,outputs=?,lease_until=NULL,lease_token=NULL,updated_at=? WHERE id=? AND status=\'RUNNING\' AND lease_token=?',(status,json.dumps(detail),now(),task['id'],task['lease_token']))
        log(db,task['company_id'],'task.'+status.lower(),detail,task['mission_id'],task['id'])
        if status=='SUCCEEDED' and task['tool']=='research.fetch':
            store_knowledge(task['company_id'],'research',result['excerpt'],result['url'],
                            'retrieved_unverified',db=db)
        if status=='SUCCEEDED' and task['tool']=='knowledge.store':
            store_knowledge(task['company_id'],result['layer'],result['content'],result['source'],
                            'user_supplied_unverified',db=db)
        db.execute('INSERT INTO usage_records VALUES(?,?,?,?,?,?,?,?,?)',(uid(),task['company_id'],task['mission_id'],task['id'],task['tool'],int((time.monotonic()-started)*1000),len(task['inputs'].encode()),len(json.dumps(detail).encode()),now()))
        refresh_mission_status(db,task['mission_id'])
        db.commit()
    return {'task_id':task['id'],'status':status,'result':result,'error':error}

def get_mission(company_id,mission_id):
    with connect() as db:
        m=db.execute('SELECT * FROM missions WHERE id=? AND company_id=?',(mission_id,company_id)).fetchone()
        if not m:return None
        tasks=db.execute('SELECT id,name,tool,status,attempt,outputs,approval_required,approved,success_condition FROM tasks WHERE mission_id=? AND company_id=? ORDER BY rowid',(mission_id,company_id)).fetchall()
    return {'mission':dict(m),'tasks':[dict(t) for t in tasks]}

def get_events(company_id,mission_id):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM events WHERE company_id=? AND mission_id=? ORDER BY created_at,rowid',(company_id,mission_id))]
