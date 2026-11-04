"""Bounded autonomous business planning workforce with persisted, unverified drafts.

No external publishing, payment, email, advertisement, repository or deployment action
is performed by these agents. Agents share one local model and a tenant-filtered
artifact ledger; an agent role is NOT a separate trained neural model.
"""
import json
import re
from . import providers

ROLES = {
    'executive': ('CEO / Strategy', 'business model, measurable objectives, risk register, and a 30-day operating roadmap'),
    'research': ('Market researcher', 'market hypotheses, competitor research questions, source needs, and customer segments'),
    'product': ('Product manager', 'product requirements, user journeys, success metrics and release plan'),
    'engineering': ('Engineering lead', 'application architecture, milestones, database plan and test criteria'),
    'marketing': ('Marketing manager', 'positioning, campaign briefs, SEO hypotheses and measurable experiments'),
    'sales': ('Sales agent', 'ideal customer profiles, qualification, CRM stages and outreach drafts only'),
    'support': ('Customer support', 'support playbook, response drafts, escalation policy and service metrics'),
    'social': ('Social media manager', 'channel-specific draft posts and an editorial schedule only'),
    'operations': ('Operations manager', 'department handoffs, budget assumptions, checkpoints and operating procedures'),
}

# Real DAG: independent departments work concurrently once their prerequisites finish.
STEPS = (
    ('executive', ()),
    ('research', ('executive',)),
    ('product', ('executive', 'research')),
    ('engineering', ('product',)),
    ('marketing', ('research', 'product')),
    ('sales', ('research', 'marketing')),
    ('support', ('product',)),
    ('social', ('marketing',)),
    ('operations', ('engineering', 'sales', 'support', 'social')),
)
MAX_PROGRAMS = 10

DOC_SCHEMA = {
    'type':'object','additionalProperties':False,
    'properties':{
        'title':{'type':'string'},
        'summary':{'type':'string'},
        'deliverables':{'type':'array','items':{'type':'object','additionalProperties':False,
            'properties':{'name':{'type':'string'},'content':{'type':'string'}},
            'required':['name','content']}},
        'assumptions':{'type':'array','items':{'type':'string'}},
        'next_actions':{'type':'array','items':{'type':'string'}},
        'limitations':{'type':'string'},
    },
    'required':['title','summary','deliverables','assumptions','next_actions','limitations'],
}


def clean_brief(idea, industry='',market=''):
    if not isinstance(idea,str) or not 12 <= len(idea.strip()) <= 1200:
        raise ValueError('Business idea must be 12–1200 characters')
    for name,value,limit in (('industry',industry,120),('market',market,120)):
        if not isinstance(value,str) or len(value)>limit:
            raise ValueError('Invalid '+name)
    return {'idea':idea.strip(),'industry':industry.strip(),'market':market.strip()}


def validate_document(role,doc):
    if role not in ROLES:raise ValueError('Unsupported business agent role')
    if not isinstance(doc,dict) or set(doc)!=set(DOC_SCHEMA['properties']):
        raise ValueError('Agent output does not match business document schema')
    for key,lower,upper in (('title',4,120),('summary',20,1200),('limitations',1,1200)):
        if not isinstance(doc[key],str) or not lower <= len(doc[key]) <= upper:
            raise ValueError('Invalid agent '+key)
    if not isinstance(doc['deliverables'],list) or not 1 <= len(doc['deliverables']) <= 5:
        raise ValueError('Agent must supply 1–5 deliverables')
    for item in doc['deliverables']:
        if not isinstance(item,dict) or set(item)!={'name','content'} or not isinstance(item['name'],str) or not 3 <= len(item['name']) <= 120 or not isinstance(item['content'],str) or not 20 <= len(item['content']) <= 3500:
            raise ValueError('Invalid agent deliverable')
    for key in ('assumptions','next_actions'):
        values=doc[key]
        if not isinstance(values,list) or not 1 <= len(values) <= 6 or any(not isinstance(x,str) or not 3 <= len(x) <= 350 for x in values):
            raise ValueError('Invalid agent '+key)
    if len(json.dumps(doc,ensure_ascii=False).encode())>19000:
        raise ValueError('Agent document too large')
    return doc


def init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS business_programs (
        id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
        mission_id TEXT NOT NULL UNIQUE REFERENCES missions(id),
        idea TEXT NOT NULL,industry TEXT NOT NULL, market TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_business_programs_tenant ON business_programs(company_id,created_at);
    CREATE TABLE IF NOT EXISTS business_artifacts (
        id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),
        mission_id TEXT NOT NULL REFERENCES missions(id),
        task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
        role TEXT NOT NULL,content TEXT NOT NULL,model TEXT NOT NULL,
        evidence_status TEXT NOT NULL,created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_business_artifacts_tenant ON business_artifacts(company_id,mission_id);
    CREATE TABLE IF NOT EXISTS business_leads (
        id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
        name TEXT NOT NULL, organization TEXT NOT NULL, email TEXT NOT NULL,
        stage TEXT NOT NULL CHECK(stage IN ('new','qualified','contacted','converted','lost')),
        source TEXT NOT NULL, notes TEXT NOT NULL, created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_business_leads_tenant ON business_leads(company_id,created_at);
    CREATE TABLE IF NOT EXISTS business_tickets (
        id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
        subject TEXT NOT NULL, message TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('open','needs_follow_up','closed')),
        source TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_business_tickets_tenant ON business_tickets(company_id,created_at);
    ''')


def launch(core,company_id,idea,industry='',market=''):
    brief=clean_brief(idea,industry,market)
    if not providers.configuration().get('live_requests'):
        raise ValueError('Local AI is disabled or unconfigured; install a local model first')
    with core.connect() as db:
        if db.execute('SELECT COUNT(*) FROM business_programs WHERE company_id=?',(company_id,)).fetchone()[0]>=MAX_PROGRAMS:
            raise ValueError('Company program limit reached')
    tasks=[{'name':role,'tool':'business.draft','inputs':{'role':role,'brief':brief},
            'depends_on':list(deps)} for role,deps in STEPS]
    ident=core.uid()
    def register(db,mission_id):
        if db.execute('SELECT COUNT(*) FROM business_programs WHERE company_id=?',(company_id,)).fetchone()[0]>=MAX_PROGRAMS:
            raise ValueError('Company program limit reached')
        db.execute('INSERT INTO business_programs VALUES(?,?,?,?,?,?,?)',
            (ident,company_id,mission_id,brief['idea'],brief['industry'],brief['market'],core.now()))
        core.log(db,company_id,'business.program_created',{'program_id':ident,'agent_count':len(STEPS)},mission_id)
    mission_id=core.create_mission(company_id,'Launch plan: '+brief['idea'][:150],tasks,on_create=register)
    return {'program_id':ident,'mission_id':mission_id,'status':'ACTIVE','agent_count':len(STEPS)}


def execute(core,company_id,task_id,inputs):
    role=inputs.get('role')
    if role not in ROLES:raise ValueError('Unsupported business role')
    with core.connect() as db:
        task=db.execute('''SELECT t.mission_id,p.idea,p.industry,p.market
            FROM tasks t JOIN business_programs p ON p.mission_id=t.mission_id AND p.company_id=t.company_id
            WHERE t.id=? AND t.company_id=? AND t.tool='business.draft' ''',(task_id,company_id)).fetchone()
        if task is None:raise ValueError('No authorized business program for task')
        earlier=db.execute('''SELECT role,content FROM business_artifacts
            WHERE company_id=? AND mission_id=? ORDER BY created_at,rowid LIMIT 9''',
            (company_id,task['mission_id'])).fetchall()
    context=[]
    for a in earlier:
        try:summary=json.loads(a['content'])['summary']
        except (TypeError,ValueError,KeyError):continue
        context.append({'role':a['role'],'summary':summary[:550]})
    model=providers.require_configured()
    core.reserve_ai_call(company_id,task_id,model)
    try:
        result=providers.generate_business(role,{'idea':task['idea'],'industry':task['industry'],'market':task['market']},context,DOC_SCHEMA)
        doc=validate_document(role,result['content'])
        core.record_ai_call(company_id,task_id,'completed',result['usage'])
    except Exception:
        core.record_ai_call(company_id,task_id,'failed',{'input_tokens':None,'output_tokens':None})
        raise
    return {'role':role,'document':doc,'model':result['model'],
            'evidence_status':'local_model_draft_unverified',
            'verification':'schema_validated_only_no_external_actions'}


def get_programs(core,company_id):
    with core.connect() as db:
        rows=db.execute('''SELECT p.id,p.mission_id,p.idea,p.industry,p.market,p.created_at,m.status,
            (SELECT COUNT(*) FROM business_artifacts a WHERE a.mission_id=p.mission_id AND a.company_id=p.company_id) AS drafts
            FROM business_programs p JOIN missions m ON m.id=p.mission_id AND m.company_id=p.company_id
            WHERE p.company_id=? ORDER BY p.created_at DESC LIMIT 10''',(company_id,)).fetchall()
    return [dict(r) for r in rows]


def get_artifacts(core,company_id,mission_id):
    with core.connect() as db:
        program=db.execute('SELECT 1 FROM business_programs WHERE company_id=? AND mission_id=?',(company_id,mission_id)).fetchone()
        if not program:return None
        rows=db.execute('''SELECT id,role,content,model,evidence_status,created_at FROM business_artifacts
            WHERE company_id=? AND mission_id=? ORDER BY created_at,rowid''',(company_id,mission_id)).fetchall()
    return [{**dict(r),'content':json.loads(r['content'])} for r in rows]


def capabilities():
    enabled=providers.configuration().get('live_requests',False)
    return {'model_configured_unverified':bool(enabled),'roles':[
        {'id':id,'name':name,'scope':scope,'execution':'local_model_draft',
         'status':'configured_unverified' if enabled else 'unconfigured'} for id,(name,scope) in ROLES.items()],
        'external_actions':{'stripe_payments':'NOT_CONNECTED','meta_ads':'NOT_CONNECTED',
        'email_send':'NOT_CONNECTED','social_publishing':'NOT_CONNECTED',
        'automatic_customer_discovery':'NOT_IMPLEMENTED',
        'github_pr_and_deployment':'SEPARATE_CONTROLLED_FACTORY'},
        'disclaimer':'Drafts are NOT websites, deployed applications, contacted customers, paid ads or finished business operations'}


# Functional company ledgers: users or external integrations supply records; no
# invented customers, contacts, deals, support replies, payments or sent emails.
STAGES=frozenset({'new','qualified','contacted','converted','lost'})
TICKET_STATUSES=frozenset({'open','needs_follow_up','closed'})


def add_lead(core,company_id,name,organization='',email='',notes=''):
    if not isinstance(name,str) or not 2 <= len(name.strip()) <= 120:
        raise ValueError('Lead name must be 2–120 characters')
    if not isinstance(organization,str) or len(organization)>150 or not isinstance(notes,str) or len(notes)>1800:
        raise ValueError('Lead organization or notes too long')
    if not isinstance(email,str) or len(email)>254 or (email and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]{2,}',email) is None):
        raise ValueError('Invalid lead email')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM business_leads WHERE company_id=?',(company_id,)).fetchone()[0]>=2000:
            raise ValueError('Company lead quota reached')
        ident=core.uid();tick=core.now()
        db.execute('INSERT INTO business_leads VALUES(?,?,?,?,?,?,?,?,?,?)',
            (ident,company_id,name.strip(),organization.strip(),email.lower().strip(),
             'new','user_supplied_unverified',notes,tick,tick))
        core.log(db,company_id,'crm.lead_created',{'lead_id':ident})
        db.commit()
    return {'id':ident,'stage':'new','source':'user_supplied_unverified'}


def leads(core,company_id):
    with core.connect() as db:
        return [dict(r) for r in db.execute('''SELECT id,name,organization,email,stage,source,notes,created_at,updated_at
             FROM business_leads WHERE company_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100''',(company_id,))]


def update_lead(core,company_id,lead_id,stage):
    if stage not in STAGES:raise ValueError('Unknown CRM stage')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT id FROM business_leads WHERE company_id=? AND id=?',(company_id,lead_id)).fetchone()
        if row is None:
            db.rollback();return False
        db.execute('UPDATE business_leads SET stage=?,updated_at=? WHERE id=? AND company_id=?',
            (stage,core.now(),lead_id,company_id))
        core.log(db,company_id,'crm.stage_changed',{'lead_id':lead_id,'stage':stage})
        db.commit()
    return True


def add_ticket(core,company_id,subject,message):
    if not isinstance(subject,str) or not 3 <= len(subject.strip()) <= 180 or not isinstance(message,str) or not 3 <= len(message.strip()) <= 5000:
        raise ValueError('Ticket subject or message invalid')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM business_tickets WHERE company_id=?',(company_id,)).fetchone()[0]>=2000:
            raise ValueError('Company ticket quota reached')
        ident=core.uid();tick=core.now()
        db.execute('INSERT INTO business_tickets VALUES(?,?,?,?,?,?,?,?)',
            (ident,company_id,subject.strip(),message.strip(),'open','user_supplied',tick,tick))
        core.log(db,company_id,'support.ticket_created',{'ticket_id':ident})
        db.commit()
    return {'id':ident,'status':'open','source':'user_supplied'}


def tickets(core,company_id):
    with core.connect() as db:
        return [dict(r) for r in db.execute('''SELECT id,subject,message,status,source,created_at,updated_at
             FROM business_tickets WHERE company_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100''',(company_id,))]


def update_ticket(core,company_id,ticket_id,status):
    if status not in TICKET_STATUSES:raise ValueError('Unknown ticket status')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT id FROM business_tickets WHERE company_id=? AND id=?',(company_id,ticket_id)).fetchone()
        if not row:
            db.rollback();return False
        db.execute('UPDATE business_tickets SET status=?,updated_at=? WHERE id=? AND company_id=?',
            (status,core.now(),ticket_id,company_id))
        core.log(db,company_id,'support.ticket_updated',{'ticket_id':ticket_id,'status':status})
        db.commit()
    return True
