"""Persistent, tenant-scoped execution kernel. SQLite is for single-host development."""
import hashlib, json, os, secrets, sqlite3, time, uuid
from contextlib import contextmanager

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
        db.executescript("""
        CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),role TEXT NOT NULL CHECK(role IN ('owner','viewer')));
        CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id), objective TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),mission_id TEXT NOT NULL REFERENCES missions(id),name TEXT NOT NULL,tool TEXT NOT NULL,inputs TEXT NOT NULL,outputs TEXT,depends_on TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,lease_until INTEGER,approval_required INTEGER NOT NULL DEFAULT 0,approved INTEGER NOT NULL DEFAULT 0,success_condition TEXT NOT NULL,updated_at INTEGER NOT NULL, UNIQUE(mission_id,name));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,mission_id TEXT,task_id TEXT,event_type TEXT NOT NULL,detail TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_tasks_ready ON tasks(status,lease_until);
        CREATE INDEX IF NOT EXISTS idx_events_tenant ON events(company_id,created_at);
        """)

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

ALLOWED_TOOLS={'internal.echo','internal.add'}

def create_mission(company_id,objective,task_specs):
    if not task_specs or len(task_specs)>30: raise ValueError('Provide 1–30 tasks')
    names=[s['name'] for s in task_specs]
    if len(set(names))!=len(names): raise ValueError('Duplicate task names')
    for s in task_specs:
        if s['tool'] not in ALLOWED_TOOLS: raise ValueError('Tool is unavailable: '+s['tool'])
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
            db.execute("""INSERT INTO tasks(id,company_id,mission_id,name,tool,inputs,depends_on,status,approval_required,success_condition,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(task_id,company_id,mission_id,s['name'],s['tool'],json.dumps(s.get('inputs',{})),json.dumps(s.get('depends_on',[])),'WAITING_APPROVAL' if approval else 'QUEUED',int(approval),s.get('success_condition','tool_result_valid'),now()))
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
    raise ValueError('Tool is unavailable')

def claim():
    """Atomically claim one ready task; recover expired leases within retry budget."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE tasks SET status='QUEUED',lease_until=NULL WHERE status='RUNNING' AND lease_until<? AND attempt<max_attempts",(now(),))
        db.execute("UPDATE tasks SET status='FAILED',lease_until=NULL WHERE status='RUNNING' AND lease_until<? AND attempt>=max_attempts",(now(),))
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
            db.execute("UPDATE tasks SET status='RUNNING',attempt=attempt+1,lease_until=?,updated_at=? WHERE id=?",(now()+120,now(),chosen['id']))
            log(db,chosen['company_id'],'task.started',{'attempt':chosen['attempt']+1},chosen['mission_id'],chosen['id'])
        db.commit()
        return dict(chosen) if chosen else None

def run_once():
    task=claim()
    if not task:return None
    error=None;result=None
    try:
        result=execute_tool(task['tool'],json.loads(task['inputs']))
        # Explicit verifier for current deterministic tools.
        if task['success_condition']!='tool_result_valid' or not isinstance(result,dict):raise ValueError('Unsupported verification condition')
    except Exception as ex: error=str(ex)[:300]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        status='SUCCEEDED' if error is None else ('FAILED' if task['attempt']+1>=task['max_attempts'] else 'QUEUED')
        detail={'error':error} if error else {'result':result,'verification':'tool_result_valid'}
        db.execute("UPDATE tasks SET status=?,outputs=?,lease_until=NULL,updated_at=? WHERE id=? AND status='RUNNING'",(status,json.dumps(detail),now(),task['id']))
        log(db,task['company_id'],'task.'+status.lower(),detail,task['mission_id'],task['id'])
        statuses=[x['status'] for x in db.execute('SELECT status FROM tasks WHERE mission_id=?',(task['mission_id'],))]
        if all(x=='SUCCEEDED' for x in statuses):ms='SUCCEEDED'
        elif all(x in ('SUCCEEDED','FAILED','BLOCKED') for x in statuses):ms='FAILED'
        else:ms='ACTIVE'
        db.execute('UPDATE missions SET status=? WHERE id=?',(ms,task['mission_id']))
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
