"""Durable, tenant-scoped software-factory test, PR and deployment jobs.

Generated content remains untrusted. Only a separate, explicitly enabled worker
may execute tests or use service credentials. No test or deployment happens in
HTTP request handlers, model processes or the normal mission worker.
"""
import base64
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from . import factory, capacity

TEST_MODES = frozenset({'python_unittest', 'python_entrypoint', 'python_syntax', 'node_test'})
GITHUB_REPO = re.compile(r'^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}$')
SHA = re.compile(r'^[a-f0-9]{40}$')
WORKFLOW = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.ya?ml$')
JOB_TIMEOUT = 120  # Actual test process capped at 45 s. 120 s claim is conservative.
RUN_OUTPUT_LIMIT = 24000


def job_id(): return str(uuid.uuid4())
def now(): return int(time.time())
def _json(obj): return json.dumps(obj, sort_keys=True, ensure_ascii=False)
def _sha(txt): return hashlib.sha256(txt.encode('utf-8')).hexdigest()


def init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS factory_jobs (
        id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL REFERENCES companies(id),
        proposal_id TEXT NOT NULL REFERENCES factory_proposals(id),
        kind TEXT NOT NULL CHECK(kind IN ('test','publish','deploy')),
        status TEXT NOT NULL,
        parameters TEXT NOT NULL,
        result TEXT,
        lease_token TEXT,
        lease_until INTEGER,
        checks INTEGER NOT NULL DEFAULT 0,
        next_check INTEGER,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_factory_jobs_company ON factory_jobs(company_id,created_at);
    CREATE INDEX IF NOT EXISTS idx_factory_jobs_queue ON factory_jobs(kind,status,created_at);
    ''')


def _proposal(db, company_id, proposal_id):
    row = db.execute('''SELECT p.*, t.inputs AS original_inputs
        FROM factory_proposals p JOIN tasks t ON t.id=p.task_id AND t.company_id=p.company_id
        WHERE p.id=? AND p.company_id=?''',(proposal_id,company_id)).fetchone()
    return dict(row) if row else None


def candidate(db,company_id,proposal_id):
    """Recover the original bounded source snapshot from the persisted task.

    Validate source hashes even if the database was edited between proposal and run.
    """
    item=_proposal(db,company_id,proposal_id)
    if item is None: raise ValueError('Proposal not found')
    source=factory.validate_snapshot(json.loads(item['original_inputs'])['files'])
    hashes=json.loads(item['source_sha256'])
    if set(hashes)!=set(source) or any(_sha(text)!=hashes[path] for path,text in source.items()):
        raise ValueError('Source snapshot integrity verification failed')
    changes=json.loads(item['changes'])
    if not (1 <= len(changes) <= factory.MAX_CHANGED_FILES):raise ValueError('Invalid stored changes')
    for change in changes:
        path=factory.checked_path(change['path'])
        if _sha(change['content'])!=change['new_sha256']:
            raise ValueError('Generated file hash mismatch')
        if change.get('old_sha256') != (_sha(source[path]) if path in source else None):
            raise ValueError('Generated file based on wrong source revision')
        source[path]=change['content']
    if len(source)>20 or sum(len(value.encode('utf-8')) for value in source.values())>40000:
        raise ValueError('Candidate exceeds sandbox limits')
    return source, changes


def check_mode(files,mode,entrypoint):
    if mode not in TEST_MODES:raise ValueError('Unsupported test preset')
    if mode.startswith('python') and not any(p.endswith('.py') for p in files):
        raise ValueError('No Python sources to run')
    if mode == 'node_test' and not any(p.endswith('.js') for p in files):
        raise ValueError('No JavaScript sources to test')
    if mode=='python_entrypoint':
        if factory.checked_path(entrypoint)!=entrypoint or not entrypoint.endswith('.py') or entrypoint not in files:
            raise ValueError('Entrypoint must be a candidate Python file')
    elif entrypoint not in (None,''):
        raise ValueError('Entrypoint is only valid for python_entrypoint')


def _insert(db, company, proposal, kind, status, params):
    previous=db.execute('''SELECT 1 FROM factory_jobs WHERE company_id=? AND proposal_id=? AND kind=?
        AND status IN ('QUEUED','RUNNING','WAITING_APPROVAL','DISPATCHED_UNVERIFIED')''',
        (company,proposal,kind)).fetchone()
    if previous:raise ValueError('This proposal already has an active operation of that type')
    if db.execute('SELECT COUNT(*) FROM factory_jobs WHERE company_id=?',(company,)).fetchone()[0]>=200:
        raise ValueError('Company factory job quota reached')
    ident=job_id()
    db.execute('''INSERT INTO factory_jobs
        (id,company_id,proposal_id,kind,status,parameters,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)''',(ident,company,proposal,kind,status,_json(params),now(),now()))
    return ident


def queue_test(core, company, proposal, mode, entrypoint=None):
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        files,_=candidate(db,company,proposal)
        check_mode(files,mode,entrypoint)
        ident=_insert(db,company,proposal,'test','QUEUED',{'mode':mode,'entrypoint':entrypoint})
        core.log(db,company,'factory.test_requested',{'job_id':ident,'mode':mode})
        db.commit()
    return ident


def _tenant_repos(company):
    """Operator-controlled authorization map, not an agent-selected repo."""
    try: values=json.loads(os.environ.get('POLSIA_GITHUB_TENANT_REPOS','{}'))
    except ValueError:raise ValueError('Invalid GitHub tenant mapping')
    if not isinstance(values,dict) or not isinstance(values.get(company,[]),list):
        raise ValueError('Invalid GitHub tenant mapping')
    return set(values.get(company,[]))


def _authorized_repo(company,repo):
    if not isinstance(repo,str) or not GITHUB_REPO.fullmatch(repo) or '..' in repo or repo not in _tenant_repos(company):
        raise ValueError('Repository is not explicitly authorized for this company')
    return repo


def queue_publish(core,company,proposal,repo,base='main'):
    _authorized_repo(company,repo)
    if base != 'main':raise ValueError('Only the configured main branch is publishable')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        candidate(db,company,proposal)
        passed=db.execute('''SELECT id,parameters FROM factory_jobs WHERE company_id=? AND proposal_id=?
            AND kind='test' AND status='PASSED' ORDER BY created_at DESC,rowid DESC LIMIT 1''',
            (company,proposal)).fetchone()
        if not passed or json.loads(passed['parameters']).get('mode') not in ('python_unittest','node_test'):
            raise ValueError('A passing sandbox unit-test suite is required before publication')
        ident=_insert(db,company,proposal,'publish','QUEUED',{'repo':repo,'base':base,'test_job_id':passed['id']})
        core.log(db,company,'factory.publish_requested',{'job_id':ident,'repo':repo})
        db.commit()
    return ident


def _deploy_config(company,repo,environment):
    if environment not in ('staging','production'):raise ValueError('Unsupported deployment environment')
    _authorized_repo(company,repo)
    try: mapping=json.loads(os.environ.get('POLSIA_DEPLOY_TARGETS','{}'))
    except ValueError:raise ValueError('Invalid deployment target configuration')
    if not isinstance(mapping,dict):raise ValueError('Invalid deployment target configuration')
    spec=mapping.get(company,{}).get(repo,{}).get(environment) if isinstance(mapping.get(company,{}),dict) else None
    if not isinstance(spec,dict) or not isinstance(spec.get('workflow'),str) or not WORKFLOW.fullmatch(spec['workflow']):
        raise ValueError('No approved deployment workflow for this tenant and environment')
    url=spec.get('health_url')
    if url is not None and (not isinstance(url,str) or not url.startswith('https://') or len(url)>500):
        raise ValueError('Invalid configured health URL')
    return {'workflow':spec['workflow'],'health_url':url}


def queue_deploy(core,company,proposal,publish_job_id,environment):
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('''SELECT * FROM factory_jobs WHERE id=? AND company_id=? AND proposal_id=?
            AND kind='publish' AND status='PUBLISHED' ''',(publish_job_id,company,proposal)).fetchone()
        if not row:raise ValueError('Verified published pull request required')
        result=json.loads(row['result'])
        repo=result['repo']
        target=_deploy_config(company,repo,environment)
        ident=_insert(db,company,proposal,'deploy','WAITING_APPROVAL',{'publish_job_id':publish_job_id,
            'repo':repo,'environment':environment,'workflow':target['workflow'],'health_url':target['health_url']})
        core.log(db,company,'factory.deployment_requested',{'job_id':ident,'environment':environment})
        db.commit()
    return ident


def approve_deploy(core,company,job_id):
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        job=db.execute("SELECT * FROM factory_jobs WHERE id=? AND company_id=? AND kind='deploy' AND status='WAITING_APPROVAL'",(job_id,company)).fetchone()
        if not job:return False
        # Recheck operator configuration at approval, never trust persisted permissions alone.
        params=json.loads(job['parameters'])
        _deploy_config(company,params['repo'],params['environment'])
        db.execute("UPDATE factory_jobs SET status='QUEUED',updated_at=? WHERE id=?",(now(),job_id))
        core.log(db,company,'factory.deployment_approved',{'job_id':job_id})
        db.commit()
    return True


def get_job(core,company,job_id):
    with core.connect() as db:
        row=db.execute('''SELECT id,proposal_id,kind,status,result,created_at,updated_at,checks
            FROM factory_jobs WHERE company_id=? AND id=?''',(company,job_id)).fetchone()
    if not row:return None
    item=dict(row)
    item['result']=json.loads(item['result']) if item['result'] else None
    return item


def list_jobs(core,company,proposal=None):
    with core.connect() as db:
        if proposal:
            rows=db.execute('''SELECT id,proposal_id,kind,status,created_at,updated_at FROM factory_jobs
                WHERE company_id=? AND proposal_id=? ORDER BY created_at DESC,rowid DESC LIMIT 40''',(company,proposal)).fetchall()
        else:
            rows=db.execute('''SELECT id,proposal_id,kind,status,created_at,updated_at FROM factory_jobs
                WHERE company_id=? ORDER BY created_at DESC,rowid DESC LIMIT 60''',(company,)).fetchall()
    return [dict(row) for row in rows]


def claim(core, kinds):
    if not kinds or not set(kinds).issubset({'test','publish','deploy'}):raise ValueError('Invalid runner specialization')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # External side effects must never retry after a worker crash: reconciliation required.
        db.execute('''UPDATE factory_jobs SET status='NEEDS_RECONCILIATION',lease_token=NULL,lease_until=NULL
            WHERE status='RUNNING' AND lease_until<?''',(now(),))
        placeholders=','.join('?'*len(kinds))
        item=db.execute(f'''SELECT * FROM factory_jobs WHERE status='QUEUED' AND kind IN ({placeholders})
             ORDER BY created_at,rowid LIMIT 1''',tuple(kinds)).fetchone()
        if not item:
            db.rollback();return None
        token=job_id()
        db.execute('''UPDATE factory_jobs SET status='RUNNING',lease_token=?,lease_until=?,updated_at=?
            WHERE id=?''',(token,now()+300,now(),item['id']))
        core.log(db,item['company_id'],'factory.job_started',{'job_id':item['id'],'kind':item['kind']})
        db.commit()
    return {**dict(item),'lease_token':token}


def finish(core,item,status,result):
    if status not in ('PASSED','TEST_FAILED','PUBLISHED','FAILED','DISPATCHED_UNVERIFIED'):
        raise ValueError('Invalid factory terminal state')
    raw=_json(result)
    if len(raw)>RUN_OUTPUT_LIMIT:raise ValueError('Result exceeds storage limit')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        changed=db.execute('''UPDATE factory_jobs SET status=?,result=?,lease_until=NULL,lease_token=NULL,updated_at=?,next_check=?
           WHERE id=? AND company_id=? AND status='RUNNING' AND lease_token=?''',
           (status,raw,now(),now()+30 if status=='DISPATCHED_UNVERIFIED' else None,
            item['id'],item['company_id'],item['lease_token']))
        if changed.rowcount!=1:
            db.rollback();return False
        core.log(db,item['company_id'],'factory.job_'+status.lower(),
                 {'job_id':item['id'],'kind':item['kind'],'status':status})
        db.commit()
    return True
