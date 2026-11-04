"""Dedicated factory worker. Separate sandbox executor and GitHub publisher hosts.

Launch --kind test ONLY on an isolated rootless Docker worker; --kind publish/deploy
ONLY on a separate integration worker with tenant-scoped GitHub credentials.
"""
import argparse
import json
import os
import time
from . import core, factory_ops, factory_sandbox, factory_github


def process_one(kind):
    if kind=='test' and os.environ.get('POLSIA_FACTORY_RUNNER_ENABLED')!='1':
        raise ValueError('Factory test worker disabled')
    if kind in ('publish','deploy') and os.environ.get('POLSIA_FACTORY_GITHUB_ENABLED')!='1':
        raise ValueError('Factory integration worker disabled')
    job=factory_ops.claim(core,{kind})
    if job is None:return None
    params=json.loads(job['parameters'])
    try:
        with core.connect() as db:
            proposal=factory_ops._proposal(db,job['company_id'],job['proposal_id'])
            if not proposal:raise ValueError('Proposal disappeared')
            files,changes=factory_ops.candidate(db,job['company_id'],job['proposal_id'])
        if kind=='test':
            result=factory_sandbox.run(files,params['mode'],params.get('entrypoint'))
            status='PASSED' if result['passed'] else 'TEST_FAILED'
        elif kind=='publish':
            with core.connect() as db:
                prior=db.execute('''SELECT id FROM factory_jobs WHERE id=? AND company_id=?
                    AND proposal_id=? AND kind='test' AND status='PASSED' ''',
                    (params['test_job_id'],job['company_id'],job['proposal_id'])).fetchone()
                if not prior:raise ValueError('Sandbox verification was revoked or is missing')
            result=factory_github.publish(job['company_id'],job['proposal_id'],params['repo'],
                json.loads(proposal['source_sha256']),changes,params['test_job_id'])
            status='PUBLISHED'
        elif kind=='deploy':
            with core.connect() as db:
                prior=db.execute('''SELECT result FROM factory_jobs WHERE id=? AND company_id=?
                    AND proposal_id=? AND kind='publish' AND status='PUBLISHED' ''',
                    (params['publish_job_id'],job['company_id'],job['proposal_id'])).fetchone()
                if not prior:raise ValueError('Published PR does not exist')
                published=json.loads(prior['result'])
            factory_ops._deploy_config(job['company_id'],params['repo'],params['environment'])
            result=factory_github.dispatch_deployment(job['company_id'],params['repo'],
                published['pr_number'],params['workflow'],params['environment'],job['id'])
            status='DISPATCHED_UNVERIFIED'
    except Exception as exc:
        # Never expose provider payloads, tokens, source bytes or detailed internals.
        result={'error_type':type(exc).__name__,'error':str(exc)[:190]}
        status='FAILED'
    accepted=factory_ops.finish(core,job,status,result)
    return {'job_id':job['id'],'kind':kind,'status':status if accepted else 'STALE_LEASE'}


def poll_one():
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('''SELECT * FROM factory_jobs WHERE kind='deploy' AND status='DISPATCHED_UNVERIFIED'
            AND next_check<=? AND checks<40 ORDER BY next_check LIMIT 1''',(factory_ops.now(),)).fetchone()
        if not row:
            db.rollback();return None
        # Reserve next poll before calling GitHub, so restarts cannot spin.
        db.execute('UPDATE factory_jobs SET checks=checks+1,next_check=? WHERE id=?',
                   (factory_ops.now()+60,row['id']))
        db.commit()
    job=dict(row);params=json.loads(job['parameters'])
    try:
        result=factory_github.poll_deployment(json.loads(job['result']),params.get('health_url'))
    except Exception as exc:
        return {'job_id':job['id'],'status':'DISPATCHED_UNVERIFIED', 'reason':type(exc).__name__}
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        state=result['status']
        if state in ('DEPLOYED_VERIFIED','WORKFLOW_SUCCESS_UNVERIFIED','FAILED'):
            db.execute('''UPDATE factory_jobs SET status=?,result=?,updated_at=?
                WHERE id=? AND company_id=? AND status='DISPATCHED_UNVERIFIED' ''',
                (state,json.dumps(result),factory_ops.now(),job['id'],job['company_id']))
            core.log(db,job['company_id'],'factory.deployment_checked',
                     {'job_id':job['id'],'status':state})
        db.commit()
    return {'job_id':job['id'],'status':result['status']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',required=True,choices=('test','publish','deploy','integrations'))
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-seconds',type=float,default=8)
    args=parser.parse_args()
    if not 1<=args.poll_seconds<=300:parser.error('Invalid polling cadence')
    core.init_db()
    while True:
        kinds=('publish','deploy') if args.kind=='integrations' else (args.kind,)
        result=None
        for kind in kinds:
            result=process_one(kind)
            if result:break
        if args.kind in ('deploy','integrations') and not result:
            result=poll_one()
        if result:print(result,flush=True)
        elif not args.once:time.sleep(args.poll_seconds)
        if args.once:break

if __name__=='__main__':main()
