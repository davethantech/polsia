"""Docker-only untrusted candidate execution for a DEDICATED, rootless runner host.

Never run on the Polsia API host or give the regular worker a Docker socket.
Containers share the host kernel; this is NOT VM-level isolation.
"""
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from . import factory
from .factory_ops import check_mode

PINNED_IMAGE = re.compile(r'^[a-z0-9][a-z0-9./:_-]{1,140}@sha256:[a-f0-9]{64}$')
OUTPUT_BYTES = 12000
TIMEOUT = 45


def _image(mode):
    key='POLSIA_SANDBOX_NODE_IMAGE' if mode == 'node_test' else 'POLSIA_SANDBOX_PY_IMAGE'
    image=os.environ.get(key,'')
    if not PINNED_IMAGE.fullmatch(image):
        raise ValueError('Runner image must be an explicitly installed digest-pinned image: '+key)
    return image


def _capture(cmd, name, timeout=TIMEOUT):
    """Bound host output memory; force-remove named container on timeout or overflow."""
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':os.environ.get('PATH','/usr/bin:/bin')})
    selector=selectors.DefaultSelector()
    for pipe in (proc.stdout,proc.stderr):
        os.set_blocking(pipe.fileno(),False)
        selector.register(pipe,selectors.EVENT_READ)
    output=bytearray()
    start=time.monotonic()
    problem=None
    try:
        while selector.get_map():
            if time.monotonic()-start>=timeout:
                problem='timeout';break
            for key,_ in selector.select(timeout=min(0.25,max(.01,timeout-(time.monotonic()-start)))):
                data=os.read(key.fd,4096)
                if not data:
                    selector.unregister(key.fileobj);continue
                if len(output)+len(data)>OUTPUT_BYTES:
                    output.extend(data[:max(0,OUTPUT_BYTES-len(output))]);problem='output_limit';break
                output.extend(data)
            if problem:break
        if problem:
            proc.kill()
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
    finally:
        selector.close()
        # Delete even successful test container if daemon missed --rm.
        try:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=5,check=False)
        except (OSError,subprocess.TimeoutExpired):pass
    return {'exit_code':proc.returncode,'output':output.decode('utf-8','replace'),
            'limit_reason':problem,'elapsed_ms':int((time.monotonic()-start)*1000)}


def run(files, mode, entrypoint=None):
    check_mode(files,mode,entrypoint)
    if os.environ.get('POLSIA_FACTORY_RUNNER_ENABLED')!='1':
        raise ValueError('Isolated factory runner is disabled')
    if not shutil.which('docker'):
        raise ValueError('Docker CLI unavailable on dedicated sandbox worker')
    image=_image(mode)
    from . import capacity
    admission=capacity.admit(capacity.snapshot(),estimated_memory_mb=384,estimated_disk_mb=100)
    if not admission['admitted']:
        raise ValueError('Sandbox resource admission denied: '+','.join(admission['reasons']))
    if mode=='python_unittest' and not any(p.split('/')[-1].startswith('test_') and p.endswith('.py') for p in files):
        raise ValueError('Python unittest preset requires a test_*.py source file')
    if mode=='node_test' and not any(p.endswith(('.test.js','.spec.js')) for p in files):
        raise ValueError('Node test preset requires a *.test.js or *.spec.js file')
    executable={
      'python_syntax': ['python','-B','-c',
           'import ast,pathlib; [(ast.parse(p.read_text(),filename=str(p))) for p in pathlib.Path(".").rglob("*.py")]; print("syntax validated")'],
      'python_unittest': ['python','-B','-m','unittest','discover','-s','.','-p','test_*.py','-v'],
      'node_test': ['node','--test'],
    }
    command=['python','-B',f'/workspace/{entrypoint}'] if mode=='python_entrypoint' else executable[mode]
    # A source file is never mounted writable; output and caches stay in capped tmpfs.
    with tempfile.TemporaryDirectory(prefix='polsia-candidate-') as root:
        os.chmod(root,0o755)
        for rel,value in files.items():
            factory.checked_path(rel)
            location=Path(root)/rel
            location.parent.mkdir(parents=True,exist_ok=True)
            for parent in [location.parent,*list(location.parents)[:-1]]:
                if str(parent).startswith(root):parent.chmod(0o755)
            location.write_text(value,encoding='utf-8')
            location.chmod(0o444)
        name='polsia-sandbox-'+uuid.uuid4().hex[:20]
        args=['docker','run','--rm','--name',name,'--pull=never','--network=none',
              '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
              '--pids-limit=64','--cpus=0.50','--memory=256m','--memory-swap=256m',
              '--ulimit','nofile=64:64','--user','65534:65534','--ipc=none',
              '--tmpfs','/tmp:rw,nosuid,noexec,size=32m',
              '--mount',f'type=bind,src={root},dst=/workspace,readonly',
              '--workdir','/workspace','--env','HOME=/tmp','--env','PYTHONDONTWRITEBYTECODE=1',
              image,*command]
        outcome=_capture(args,name)
    valid=outcome['exit_code']==0 and not outcome['limit_reason']
    if mode=='python_unittest':
        match=re.search(r'Ran (\d+) tests?',outcome['output'])
        valid=valid and bool(match) and int(match.group(1))>0
    if mode=='node_test':
        # Node's built-in test runner prints a summary with a nonzero test count.
        match=re.search(r'^# tests (\d+)$',outcome['output'],re.M)
        valid=valid and bool(match) and int(match.group(1))>0
    return {'passed':bool(valid),'mode':mode,'exit_code':outcome['exit_code'],
            'output':outcome['output'][:OUTPUT_BYTES],
            'limit_reason':outcome['limit_reason'],'elapsed_ms':outcome['elapsed_ms'],
            'runtime':'docker_isolated_network_off','network_access':False,
            'image_digest':image.split('@')[-1],
            'verification':'actual_container_exit_code_and_test_count' if valid else 'candidate_not_verified'}
