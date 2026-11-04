"""Persistent, tenant-scoped execution kernel. SQLite is for single-host development."""
import hashlib, json, os, secrets, sqlite3, time, uuid
from contextlib import contextmanager
from . import capacity, mathematics, research, cosmos, culture, evidence, providers, intelligence, learning, neural

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
        CREATE TABLE IF NOT EXISTS culture_records (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            title TEXT NOT NULL, tradition TEXT NOT NULL, topic TEXT NOT NULL,
            language TEXT NOT NULL, work TEXT NOT NULL, passage TEXT NOT NULL,
            content TEXT NOT NULL, source_url TEXT NOT NULL,
            evidence_class TEXT NOT NULL, review_status TEXT NOT NULL,
            source_sha256 TEXT, subscription_id TEXT, retrieved_at INTEGER, created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_culture_records_tenant ON culture_records(company_id, created_at);
        CREATE TABLE IF NOT EXISTS culture_subscriptions (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            title TEXT NOT NULL, tradition TEXT NOT NULL, url TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL, next_due INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','paused')),
            last_checked INTEGER, last_sha256 TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            UNIQUE(company_id,url)
        );
        CREATE INDEX IF NOT EXISTS idx_culture_subscriptions_due ON culture_subscriptions(status,next_due);
        CREATE TABLE IF NOT EXISTS learning_subscriptions (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            title TEXT NOT NULL, topic TEXT NOT NULL, url TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL, next_due INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','paused')),
            last_checked INTEGER, last_sha256 TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            UNIQUE(company_id,url)
        );
        CREATE INDEX IF NOT EXISTS idx_learning_due ON learning_subscriptions(status,next_due);
        CREATE TABLE IF NOT EXISTS ai_calls (
            task_id TEXT PRIMARY KEY REFERENCES tasks(id),
            company_id TEXT NOT NULL REFERENCES companies(id),
            model TEXT NOT NULL, attempted_at INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('reserved','completed','failed')),
            input_tokens INTEGER, output_tokens INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_ai_calls_company_day ON ai_calls(company_id,attempted_at);
        CREATE TABLE IF NOT EXISTS neural_rankers (
            company_id TEXT PRIMARY KEY REFERENCES companies(id),
            weights TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
            feedback_count INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS neural_feedback (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            question TEXT NOT NULL, preferred_id TEXT NOT NULL, rejected_id TEXT NOT NULL,
            loss_before REAL NOT NULL, loss_after REAL NOT NULL, created_at INTEGER NOT NULL,
            UNIQUE(company_id,question,preferred_id,rejected_id)
        );
        CREATE INDEX IF NOT EXISTS idx_neural_feedback_tenant ON neural_feedback(company_id,created_at);

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

ALLOWED_TOOLS={'internal.echo','internal.add','math.evaluate','research.fetch','knowledge.store',
               'astronomy.horizons','astrology.zodiac','culture.record','intelligence.answer'}
TOOL_ESTIMATES={'internal.echo':(16,1),'internal.add':(16,1),'math.evaluate':(32,1),
                'research.fetch':(64,2),'knowledge.store':(24,2),
                'astronomy.horizons':(64,2),'astrology.zodiac':(16,1),'culture.record':(32,2),
                'intelligence.answer':(128,3)}

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
        ai=db.execute('''SELECT COUNT(*) AS provider_calls,
            SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
            SUM(CASE WHEN input_tokens IS NULL OR output_tokens IS NULL THEN 1 ELSE 0 END) AS unknown_usage
            FROM ai_calls WHERE company_id=?''',(company_id,)).fetchone()
        return {**dict(r),'ai_calls':ai['provider_calls'],
                'model_input_tokens':ai['input_tokens'],'model_output_tokens':ai['output_tokens'],
                'model_tokens':(ai['input_tokens']+ai['output_tokens']
                    if ai['unknown_usage']==0 and ai['input_tokens'] is not None
                    and ai['output_tokens'] is not None else None),
                'provider_cost_usd':None,
                'note':'Model token usage is local-runtime-reported when available; hosting/electricity costs are not measured.'}

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

def search_evidence(company_id, query, limit=5):
    with connect() as db:
        return evidence.search(db, company_id, query, limit)


def daily_ai_call_limit():
    raw=os.environ.get('POLSIA_AI_DAILY_CALL_LIMIT','10')
    try: value=int(raw)
    except ValueError as exc: raise ValueError('Invalid AI daily call limit') from exc
    if not 1<=value<=100:raise ValueError('AI daily call limit must be 1–100')
    return value


def reserve_ai_call(company_id, task_id, model):
    '''Atomic daily tenant call budget and at-most-once attempt per task.

    Local inference consumes VPS capacity; no silent retry is attempted.
    '''
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM ai_calls WHERE task_id=?',(task_id,)).fetchone():
            raise ValueError('AI request already attempted; automatic replay prohibited')
        limit=daily_ai_call_limit()
        count=db.execute('SELECT COUNT(*) FROM ai_calls WHERE company_id=? AND attempted_at>=?',
                        (company_id,now()//86400*86400)).fetchone()[0]
        if count>=limit:raise ValueError('Company daily AI call limit reached')
        db.execute('INSERT INTO ai_calls(task_id,company_id,model,attempted_at,status) VALUES(?,?,?,?,?)',
                   (task_id,company_id,model,now(),'reserved'))
        log(db,company_id,'ai.request_reserved',{'task_id':task_id,'model':model})
        db.commit()


def record_ai_call(company_id, task_id, status, usage):
    if status not in ('completed','failed'):raise ValueError('Invalid provider call status')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''UPDATE ai_calls SET status=?,input_tokens=?,output_tokens=?
            WHERE task_id=? AND company_id=?''',
            (status,usage.get('input_tokens'),usage.get('output_tokens'),task_id,company_id))
        log(db,company_id,'ai.request_'+status,{'task_id':task_id,
            'input_tokens':usage.get('input_tokens'), 'output_tokens':usage.get('output_tokens')})
        db.commit()


def create_mission(company_id,objective,task_specs):
    if not task_specs or len(task_specs)>30: raise ValueError('Provide 1–30 tasks')
    names=[s['name'] for s in task_specs]
    if len(set(names))!=len(names): raise ValueError('Duplicate task names')
    for s in task_specs:
        if s['tool'] not in ALLOWED_TOOLS: raise ValueError('Tool is unavailable: '+s['tool'])
        if s['tool']=='intelligence.answer':
            question=s.get('inputs',{}).get('question')
            if not isinstance(question,str) or not 3<=len(question.strip())<=1200:
                raise ValueError('Invalid research question')
            sources=s.get('inputs',{}).get('min_sources',1)
            if type(sources) is not int or not 1<=sources<=4:
                raise ValueError('Invalid minimum source count')
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
            if s['tool']=='intelligence.answer':
                db.execute('UPDATE tasks SET max_attempts=1 WHERE id=?',(task_id,))
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

def execute_tool(tool,inputs,company_id=None,task_id=None):
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
    if tool=='astronomy.horizons':
        return cosmos.jpl_ephemeris(inputs.get('body'), inputs.get('date_utc'))
    if tool=='astrology.zodiac':
        return cosmos.zodiac(inputs.get('longitude_deg'),
                            ayanamsha_deg=inputs.get('ayanamsha_deg'),
                            frame=inputs.get('frame','ecliptic_of_date'))
    if tool=='culture.record':
        return culture.validate_record(inputs)
    if tool=='intelligence.answer':
        if not company_id or not task_id:
            raise ValueError('Missing execution context')
        return intelligence.answer(connect, company_id, inputs,
            reserve_call=lambda model:reserve_ai_call(company_id,task_id,model),
            record_call=lambda status,usage:record_ai_call(company_id,task_id,status,usage))
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

        if task['tool']=='intelligence.answer':
            result=execute_tool(task['tool'],json.loads(task['inputs']),company_id=task['company_id'],task_id=task['id'])
        else:
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
        event_detail=detail
        if task['tool']=='intelligence.answer' and not error:
            event_detail={'provider_response_id':result.get('provider_response_id'),
                'citation_count':len(result.get('citations',[])),
                'verification':result.get('verification')}
        log(db,task['company_id'],'task.'+status.lower(),event_detail,task['mission_id'],task['id'])
        if status=='SUCCEEDED' and task['tool']=='research.fetch':
            store_knowledge(task['company_id'],'research',result['excerpt'],result['url'],
                            'retrieved_unverified',db=db)
        if status=='SUCCEEDED' and task['tool']=='knowledge.store':
            store_knowledge(task['company_id'],result['layer'],result['content'],result['source'],
                            'user_supplied_unverified',db=db)
        if status=='SUCCEEDED' and task['tool']=='culture.record':
            _insert_culture_record(db,task['company_id'],result)
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


def _insert_culture_record(db, company_id, fields, *, subscription_id=None,
                           source_sha256=None, retrieved_at=None):
    """Insert only normalized, provenance-labeled records in a tenant transaction."""
    item_id=uid()
    db.execute("""INSERT INTO culture_records
        (id,company_id,title,tradition,topic,language,work,passage,content,
         source_url,evidence_class,review_status,source_sha256,subscription_id,retrieved_at,created_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (item_id,company_id,fields['title'],fields['tradition'],fields['topic'],
         fields['language'],fields['work'],fields['passage'],fields['content'],
         fields['source_url'],fields['evidence_class'],fields['review_status'],
         source_sha256,subscription_id,retrieved_at,now()))
    log(db,company_id,'culture.record_stored',
        {'record_id':item_id,'source_url':fields['source_url'],
         'evidence_class':fields['evidence_class'],'review_status':fields['review_status']})
    return item_id


def add_culture_record(company_id,fields):
    value=culture.validate_record(fields)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        record_id=_insert_culture_record(db,company_id,value)
        db.commit()
    return record_id


def get_culture_records(company_id,query='',limit=20):
    if not isinstance(query,str):raise ValueError('Invalid query')
    q='%'+query[:120].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    with connect() as db:
        return [dict(r) for r in db.execute("""SELECT * FROM culture_records
            WHERE company_id=? AND (content LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
            OR tradition LIKE ? ESCAPE '\\' OR work LIKE ? ESCAPE '\\'
            OR topic LIKE ? ESCAPE '\\') ORDER BY created_at DESC,rowid DESC LIMIT ?""",
            (company_id,q,q,q,q,q,min(50,max(1,limit))))]


def create_culture_subscription(company_id,fields):
    settings=culture.validate_subscription(fields)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        count=db.execute('SELECT COUNT(*) FROM culture_subscriptions WHERE company_id=?',
                         (company_id,)).fetchone()[0]
        if count>=10:raise ValueError('Maximum 10 subscriptions per company')
        item_id=uid()
        try:
            db.execute("""INSERT INTO culture_subscriptions
                (id,company_id,title,tradition,url,interval_seconds,next_due,status)
                VALUES(?,?,?,?,?,?,?,'active')""",
                (item_id,company_id,settings['title'],settings['tradition'],
                 settings['url'],settings['interval_seconds'],now()))
        except sqlite3.IntegrityError as e:
            raise ValueError('Already subscribed to this URL') from e
        log(db,company_id,'culture.subscription_created',{'subscription_id':item_id,'url':settings['url']})
        db.commit()
    return item_id


def list_culture_subscriptions(company_id):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM culture_subscriptions WHERE company_id=? ORDER BY rowid', (company_id,))]


def change_culture_subscription(company_id, item_id, status):
    if status not in ('active','paused'):raise ValueError('Invalid subscription status')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # Resuming schedules a new check, with no automatic high-frequency loop.
        row=db.execute('SELECT id FROM culture_subscriptions WHERE id=? AND company_id=?',
                       (item_id,company_id)).fetchone()
        if row is None:
            db.rollback();return False
        db.execute('UPDATE culture_subscriptions SET status=?,next_due=? WHERE id=?',
                   (status,now(),item_id))
        log(db,company_id,'culture.subscription_status',{'subscription_id':item_id,'status':status})
        db.commit();return True


def refresh_due_culture_subscription():
    """At most one due, preauthorized public-source fetch per call.

    Requires separate opt-ins for network access and automatic updates. Reserve
    next_due before doing I/O so worker failures cannot cause a request storm.
    """
    if os.environ.get('POLSIA_NETWORK_ENABLED')!='1' or        os.environ.get('POLSIA_CULTURE_REFRESH_ENABLED')!='1':
        return None
    admission=capacity.admit(capacity.snapshot(),estimated_memory_mb=64,estimated_disk_mb=2)
    if not admission['admitted']:
        return {'status':'THROTTLED','reasons':admission['reasons']}
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        item=db.execute("""SELECT * FROM culture_subscriptions
           WHERE status='active' AND next_due<=? ORDER BY next_due,id LIMIT 1""",
           (now(),)).fetchone()
        if item is None:
            db.rollback();return None
        entry=dict(item)
        db.execute('UPDATE culture_subscriptions SET next_due=?,attempts=attempts+1 WHERE id=?',
                   (now()+entry['interval_seconds'],entry['id']))
        db.commit()
    try:
        result=research.fetch_public(entry['url'])
        new_hash=result['sha256']
        # Every webpage remains unverified: it may be outdated or misleading.
        if not result['excerpt'].strip():raise ValueError('Empty source text')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            fresh=db.execute('SELECT status,last_sha256 FROM culture_subscriptions WHERE id=?',
                             (entry['id'],)).fetchone()
            if fresh is None or fresh['status']!='active':
                db.rollback();return {'status':'CANCELLED','subscription_id':entry['id']}
            changed=new_hash!=fresh['last_sha256']
            if changed:
                record={'title':entry['title'],'tradition':entry['tradition'],
                        'topic':'automated_source_snapshot','language':'unspecified',
                        'work':'unspecified','passage':'unspecified',
                        'content':result['excerpt'],'source_url':result['url'],
                        'evidence_class':'unverified_claim',
                        'review_status':'retrieved_unverified'}
                _insert_culture_record(db,entry['company_id'],record,
                    subscription_id=entry['id'],source_sha256=new_hash,
                    retrieved_at=result['retrieved_at'])
            db.execute("""UPDATE culture_subscriptions SET last_checked=?,last_sha256=? WHERE id=?""",
                       (now(),new_hash,entry['id']))
            log(db,entry['company_id'],'culture.subscription_checked',
                {'subscription_id':entry['id'],'changed':changed,'sha256':new_hash})
            db.commit()
        return {'status':'RETRIEVED_UNVERIFIED' if changed else 'UNCHANGED',
                'subscription_id':entry['id'],'sha256':new_hash}
    except Exception as exc:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            log(db,entry['company_id'],'culture.subscription_failed',
                {'subscription_id':entry['id'],'error_type':type(exc).__name__})
            db.commit()
        return {'status':'FAILED','subscription_id':entry['id'],'error_type':type(exc).__name__}


def list_missions(company_id, limit=50):
    """Read-only tenant-scoped mission summaries; never leak other workspaces."""
    with connect() as db:
        results=[dict(r) for r in db.execute('''SELECT m.id,m.objective,m.status,m.created_at,
          COUNT(t.id) AS task_count,
          SUM(CASE WHEN t.status='SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_tasks,
          SUM(CASE WHEN t.status='WAITING_APPROVAL' THEN 1 ELSE 0 END) AS pending_approvals
          FROM missions m LEFT JOIN tasks t ON m.id=t.mission_id AND m.company_id=t.company_id
          WHERE m.company_id=? GROUP BY m.id ORDER BY m.created_at DESC,m.rowid DESC LIMIT ?''',
          (company_id,min(100,max(1,limit))))]
    return results


def workspace_overview(company_id):
    with connect() as db:
        companies=db.execute('SELECT name FROM companies WHERE id=?',(company_id,)).fetchone()
        if companies is None:return None
        statuses={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) AS n FROM tasks WHERE company_id=? GROUP BY status',(company_id,))}
        mission_statuses={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) AS n FROM missions WHERE company_id=? GROUP BY status',(company_id,))}
        memories=db.execute('SELECT COUNT(*) AS n FROM knowledge WHERE company_id=?',(company_id,)).fetchone()['n']
        culture_count=db.execute('SELECT COUNT(*) AS n FROM culture_records WHERE company_id=?',(company_id,)).fetchone()['n']
        active_agents=0 # This project has no implemented specialist-agent registry.
        recent=[dict(r) for r in db.execute('''SELECT id,event_type,detail,mission_id,task_id,created_at FROM events
          WHERE company_id=? ORDER BY created_at DESC,rowid DESC LIMIT 12''',(company_id,))]
        approvals=[dict(r) for r in db.execute('''SELECT t.id,t.name,t.mission_id,m.objective
          FROM tasks t JOIN missions m ON m.id=t.mission_id AND m.company_id=t.company_id
          WHERE t.company_id=? AND t.status='WAITING_APPROVAL' ORDER BY t.updated_at DESC LIMIT 20''',(company_id,))]
    return {'company':{'id':company_id,'name':companies['name']},'tasks':statuses,
            'missions':mission_statuses,'knowledge_records':memories,
            'culture_records':culture_count,'active_ai_agents':active_agents,
            'recent_events':recent,'approvals':approvals,'usage':get_usage(company_id)}


def create_learning_subscription(company_id, fields):
    """Owner/editor authorizes a particular source; worker won't discover random URLs."""
    item = learning.validate_source(fields)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute('SELECT COUNT(*) FROM learning_subscriptions WHERE company_id=?',
                           (company_id,)).fetchone()[0]
        if count >= 10:
            raise ValueError('Maximum 10 learning sources per company')
        source_id = uid()
        try:
            db.execute('''INSERT INTO learning_subscriptions
                (id,company_id,title,topic,url,interval_seconds,next_due,status)
                VALUES(?,?,?,?,?,?,?,'active')''',
                (source_id, company_id, item['title'], item['topic'], item['url'],
                 item['interval_seconds'], now()))
        except sqlite3.IntegrityError as exc:
            raise ValueError('Already following this learning source') from exc
        log(db,company_id,'learning.source_created',{'source_id':source_id,'url':item['url']})
        db.commit()
    return source_id


def list_learning_subscriptions(company_id):
    with connect() as db:
        return [dict(r) for r in db.execute('''SELECT * FROM learning_subscriptions
            WHERE company_id=? ORDER BY rowid''',(company_id,))]


def change_learning_subscription(company_id, source_id, status):
    if status not in ('active','paused'):
        raise ValueError('Invalid learning source status')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        cur=db.execute('''UPDATE learning_subscriptions SET status=?,next_due=?
            WHERE id=? AND company_id=?''',(status,now(),source_id,company_id))
        if cur.rowcount != 1:
            db.rollback();return False
        log(db,company_id,'learning.source_status',{'source_id':source_id,'status':status})
        db.commit()
    return True


def refresh_due_learning_subscription():
    """Poll at most one subscribed page, and only while capacity is safe.

    Source snapshots remain UNVERIFIED and cannot give instructions to agents.
    Reserve next poll before I/O to prevent request storms on worker restart.
    """
    if (os.environ.get('POLSIA_NETWORK_ENABLED')!='1' or
            os.environ.get('POLSIA_LEARNING_ENABLED')!='1'):
        return None
    admit=capacity.admit(capacity.snapshot(),estimated_memory_mb=64,estimated_disk_mb=2)
    if not admit['admitted']:
        return {'status':'THROTTLED','reasons':admit['reasons']}
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('''SELECT * FROM learning_subscriptions
            WHERE status='active' AND next_due<=? ORDER BY next_due,id LIMIT 1''',(now(),)).fetchone()
        if not row:
            db.rollback();return None
        entry=dict(row)
        db.execute('''UPDATE learning_subscriptions
            SET next_due=?,attempts=attempts+1 WHERE id=?''',
            (now()+entry['interval_seconds'],entry['id']))
        db.commit()
    try:
        fetched=research.fetch_public(entry['url'])
        if not fetched['excerpt'].strip():
            raise ValueError('Empty source')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT status,last_sha256 FROM learning_subscriptions WHERE id=? AND company_id=?',
                               (entry['id'],entry['company_id'])).fetchone()
            if not current or current['status']!='active':
                db.rollback()
                return {'status':'CANCELLED','source_id':entry['id']}
            changed = fetched['sha256'] != current['last_sha256']
            if changed:
                store_knowledge(entry['company_id'],'research',
                                'Topic: '+entry['topic']+'\n'+fetched['excerpt'][:11800],
                                fetched['url'],'retrieved_unverified',db=db)
            db.execute('''UPDATE learning_subscriptions SET last_checked=?,last_sha256=? WHERE id=?''',
                       (now(),fetched['sha256'],entry['id']))
            log(db,entry['company_id'],'learning.source_checked',
                {'source_id':entry['id'],'changed':changed,'sha256':fetched['sha256']})
            db.commit()
        return {'status':'RETRIEVED_UNVERIFIED' if changed else 'UNCHANGED',
                'source_id':entry['id']}
    except Exception as exc:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            log(db,entry['company_id'],'learning.source_failed',
                {'source_id':entry['id'],'error_type':type(exc).__name__})
            db.commit()
        return {'status':'FAILED','source_id':entry['id'],'error_type':type(exc).__name__}


def neural_status(company_id):
    """Only company-scoped model information; no company-to-company weight sharing."""
    with connect() as db:
        row=db.execute('SELECT version,feedback_count,updated_at FROM neural_rankers WHERE company_id=?',(company_id,)).fetchone()
    return {'type':'local_two_layer_neural_reranker','version':row['version'] if row else 0,
            'feedback_count':row['feedback_count'] if row else 0,
            'learns_from':'explicit_evaluated_source_preferences',
            'general_intelligence':False, 'trained_foundation_model':False}


def record_neural_feedback(company_id, question, preferred_id, rejected_id):
    """Atomic versioned update after validating that both evidence IDs belong to tenant."""
    if not isinstance(preferred_id,str) or not isinstance(rejected_id,str) or preferred_id==rejected_id:
        raise ValueError('Two distinct citation identifiers are required')
    if len(preferred_id)>120 or len(rejected_id)>120:
        raise ValueError('Citation identifier too long')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        sources=evidence.search(db,company_id,question,limit=8)
        by_id={r['citation_id']:r for r in sources}
        if preferred_id not in by_id or rejected_id not in by_id:
            raise ValueError('Both sources must be retrieved from this company for that question')
        prior=db.execute('SELECT weights,version,feedback_count FROM neural_rankers WHERE company_id=?',(company_id,)).fetchone()
        if prior and prior['feedback_count']>=neural.MAX_FEEDBACK:
            raise ValueError('Learning feedback quota reached')
        if db.execute('''SELECT 1 FROM neural_feedback WHERE company_id=? AND question=?
                         AND preferred_id=? AND rejected_id=?''',
                      (company_id,question,preferred_id,rejected_id)).fetchone():
            raise ValueError('Duplicate training feedback')
        weights=json.loads(prior['weights']) if prior else neural.initial()
        updated,metrics=neural.train_pair(weights,question,by_id[preferred_id],by_id[rejected_id])
        ver=prior['version']+1 if prior else 1
        count=prior['feedback_count']+1 if prior else 1
        db.execute('''INSERT INTO neural_rankers(company_id,weights,version,feedback_count,updated_at)
                      VALUES(?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET
                      weights=excluded.weights,version=excluded.version,
                      feedback_count=excluded.feedback_count,updated_at=excluded.updated_at''',
                   (company_id,json.dumps(updated),ver,count,now()))
        db.execute('INSERT INTO neural_feedback VALUES(?,?,?,?,?,?,?,?)',
                   (uid(),company_id,question,preferred_id,rejected_id,
                    metrics['loss_before'],metrics['loss_after'],now()))
        log(db,company_id,'neural.ranker_updated',{'version':ver, 'loss_delta':
                                                  round(metrics['loss_before']-metrics['loss_after'],8)})
        db.commit()
    return {'version':ver,'feedback_count':count,**metrics}
