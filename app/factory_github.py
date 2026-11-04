"""Optional GitHub REST publishing and deployment workflow adapter.

Owner actions and deployment approvals are persisted by factory_ops. Tokens are
available only to the separate integration worker. Never pass tokens to models,
source files, test containers, API responses or audit events.
"""
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from . import factory_ops

BASE='https://api.github.com'

class GitHubError(ValueError):pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None


def request(method,path,data=None,allow_missing=False):
    if not isinstance(path,str) or not path.startswith('/repos/') or '://' in path:
        raise GitHubError('Invalid GitHub endpoint')
    token=os.environ.get('POLSIA_GITHUB_TOKEN','').strip()
    if not token or len(token)<12:raise GitHubError('GitHub service credential is unconfigured')
    blob=None if data is None else json.dumps(data,separators=(',',':')).encode('utf-8')
    req=urllib.request.Request(BASE+path,data=blob,method=method,headers={
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','User-Agent':'Polsia-Factory/0.8',
        'Content-Type':'application/json'})
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(req,timeout=12) as res:
            status=res.status
            raw=res.read(180001)
            if len(raw)>180000:raise GitHubError('GitHub response limit exceeded')
    except urllib.error.HTTPError as exc:
        if allow_missing and exc.code==404:return None
        raise GitHubError('GitHub HTTP '+str(exc.code)) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise GitHubError('GitHub unavailable or timed out') from None
    if status not in (200,201,202,204):raise GitHubError('GitHub returned unsuccessful response')
    if not raw:return {'accepted':True,'http_status':status}
    try:return json.loads(raw)
    except ValueError:raise GitHubError('GitHub response was not JSON') from None


def repo_path(repo):
    if not factory_ops.GITHUB_REPO.fullmatch(repo):raise GitHubError('Invalid repository')
    return '/repos/'+repo


def _sha(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def publish(company, proposal_id, repo, source_hashes, changes, test_job_id):
    """Check GitHub baseline against the persisted source, commit a branch and open a PR.

    If an external write times out, caller must reconcile, never blindly replay.
    """
    factory_ops._authorized_repo(company,repo)
    root=repo_path(repo)
    base=request('GET',root+'/git/ref/heads/main')
    base_sha=base['object']['sha']
    if not factory_ops.SHA.fullmatch(base_sha):raise GitHubError('Invalid base commit')
    for change in changes:
        path=change['path']
        # Encode paths once and compare actual file contents at the immutable base commit.
        encoded=urllib.parse.quote(path,safe='/')
        current=request('GET',root+'/contents/'+encoded+'?ref='+base_sha,allow_missing=True)
        old=source_hashes.get(path)
        if current is None:
            if old is not None:raise GitHubError('Source file missing on GitHub; source has diverged')
        else:
            if old is None or current.get('type')!='file' or current.get('encoding')!='base64':
                raise GitHubError('GitHub file not included in original snapshot')
            try:content=base64.b64decode(current['content'],validate=False).decode('utf-8')
            except (ValueError,KeyError,UnicodeDecodeError):raise GitHubError('Invalid GitHub file data') from None
            if _sha(content)!=old:raise GitHubError('GitHub source does not match reviewed snapshot')
    branch='polsia/proposal-'+proposal_id.replace('-','')[:20]
    request('POST',root+'/git/refs',{'ref':'refs/heads/'+branch,'sha':base_sha})
    commits=[]
    for change in changes:
        path=urllib.parse.quote(change['path'],safe='/')
        entry=request('GET',root+'/contents/'+path+'?ref='+urllib.parse.quote(branch,safe=''),allow_missing=True)
        payload={'message':'feat: Polsia candidate '+proposal_id[:8]+' '+change['path'],
                 'content':base64.b64encode(change['content'].encode('utf-8')).decode('ascii'),
                 'branch':branch}
        if entry is not None:payload['sha']=entry['sha']
        response=request('PUT',root+'/contents/'+path,payload)
        sha=response.get('commit',{}).get('sha')
        if not isinstance(sha,str) or not factory_ops.SHA.fullmatch(sha):
            raise GitHubError('GitHub failed to confirm file commit')
        commits.append(sha)
    pull=request('POST',root+'/pulls',{
        'title':'Polsia candidate '+proposal_id[:8],
        'body':'Automated candidate with verified sandbox job '+test_job_id+'. Review before merging. No deployment was performed.',
        'head':branch,'base':'main','draft':True})
    number=pull.get('number')
    if type(number) is not int or number<1:raise GitHubError('GitHub did not return a PR number')
    fetched=request('GET',root+'/pulls/'+str(number))
    if fetched.get('number')!=number or fetched.get('head',{}).get('ref')!=branch:
        raise GitHubError('GitHub PR verification failed')
    url=fetched.get('html_url','')
    if url!=f'https://github.com/{repo}/pull/{number}':
        raise GitHubError('GitHub PR URL validation failed')
    return {'repo':repo,'branch':branch,'pr_number':number,'pr_url':url,
            'base_sha':base_sha,'last_commit':commits[-1],
            'verification':'confirmed_from_github_pull_request_readback',
            'deployment':False}


def dispatch_deployment(company, repo, pr_number, workflow, environment, job_id):
    """Trigger preinstalled deploy workflow ONLY for a merged PR.

    A dispatch receipt is never a claim that deployment succeeded.
    """
    factory_ops._deploy_config(company,repo,environment)
    root=repo_path(repo)
    pr=request('GET',root+'/pulls/'+str(pr_number))
    if pr.get('merged') is not True or pr.get('base',{}).get('ref')!='main':
        raise GitHubError('Pull request must be merged into main before deployment')
    head=request('GET',root+'/git/ref/heads/main')
    sha=head['object']['sha']
    if not factory_ops.SHA.fullmatch(sha):raise GitHubError('Invalid deployment head')
    uri=root+'/actions/workflows/'+urllib.parse.quote(workflow,safe='')+'/dispatches'
    result=request('POST',uri,{'ref':'main','inputs':{'environment':environment,
        'expected_sha':sha,'polsia_job_id':job_id}})
    if not result.get('accepted'):
        # Newer API variants may return a workflow-run object; require evidence.
        if not result.get('id'):raise GitHubError('Workflow dispatch was not confirmed')
    return {'repo':repo,'workflow':workflow,'environment':environment,'expected_sha':sha,
        'pr_number':pr_number,'job_id':job_id,'requested_at':factory_ops.now(),
        'status':'DISPATCHED_UNVERIFIED','note':'Workflow accepted, application NOT verified deployed'}


def poll_deployment(result, health_url=None):
    """Require correlated workflow run + exact-commit /health before verified."""
    root=repo_path(result['repo'])
    wf=urllib.parse.quote(result['workflow'],safe='')
    info=request('GET',root+'/actions/workflows/'+wf+'/runs?event=workflow_dispatch&per_page=30')
    matches=[r for r in info.get('workflow_runs',[]) if
        result['job_id'] in str(r.get('display_title','')) and r.get('head_sha')==result['expected_sha']]
    if len(matches)!=1:return {'status':'DISPATCHED_UNVERIFIED','reason':'matching_run_not_confirmed'}
    run=matches[0]
    if run.get('status')!='completed':return {'status':'DISPATCHED_UNVERIFIED','reason':'workflow_not_complete'}
    if run.get('conclusion')!='success':return {'status':'FAILED','reason':'workflow_failed','run_id':run['id']}
    if not health_url:
        return {'status':'WORKFLOW_SUCCESS_UNVERIFIED','reason':'health_endpoint_not_configured','run_id':run['id']}
    # Health URL is fixed by the server operator, checked for public HTTPS/SSRF.
    from . import research
    data=research.fetch_public(health_url)
    try:health=json.loads(data['excerpt'])
    except (ValueError,TypeError):
        return {'status':'WORKFLOW_SUCCESS_UNVERIFIED','reason':'health_response_not_json','run_id':run['id']}
    if health.get('status')!='ok' or health.get('commit_sha')!=result['expected_sha']:
        return {'status':'WORKFLOW_SUCCESS_UNVERIFIED','reason':'health_commit_mismatch','run_id':run['id']}
    return {'status':'DEPLOYED_VERIFIED','run_id':run['id'],'commit_sha':result['expected_sha'],
            'verification':'github_workflow_success_and_public_health_commit_match'}
