"""Conservative Linux VPS capacity probe and admission control.

These are snapshots, not resource reservations. Docker/cgroup limits remain essential.
"""
import os
import shutil
from pathlib import Path


def read_int(path):
    try:
        v=Path(path).read_text().strip()
        return None if v=='max' else int(v)
    except (OSError, ValueError):
        return None


def meminfo():
    try:
        lines=Path('/proc/meminfo').read_text().splitlines()
        return {k: int(v.split()[0])*1024 for k, v in (line.split(':',1) for line in lines)}
    except (OSError, ValueError):
        return {}


def thermal_c():
    values=[]
    for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        t=read_int(path)
        if t is not None and -10000 < t < 150000: values.append(t/1000)
    return max(values) if values else None


def effective_cores():
    physical=max(1,os.cpu_count() or 1)
    try:
        quota,period=Path('/sys/fs/cgroup/cpu.max').read_text().split()[:2]
        if quota != 'max':return min(physical,max(0.1,int(quota)/int(period)))
    except (OSError,ValueError,ZeroDivisionError):pass
    return physical


def snapshot(work_path='.'):
    memory=meminfo()
    m_available=memory.get('MemAvailable')
    cg_limit=read_int('/sys/fs/cgroup/memory.max')
    cg_used=read_int('/sys/fs/cgroup/memory.current')
    cg_free= max(0,cg_limit-cg_used) if cg_limit is not None and cg_used is not None else None
    if cg_free is not None:m_available=min(m_available,cg_free) if m_available is not None else cg_free
    # Unknown measurements must be visible: do not invent available RAM.
    disk=shutil.disk_usage(work_path)
    cores=effective_cores()
    try: load=os.getloadavg()[0]
    except OSError:load=None
    # loadavg is host-wide, not a per-cgroup measurement; dividing by the
    # container CPU quota would incorrectly throttle idle containers on busy VPS hosts.
    host_cores=max(1,os.cpu_count() or 1)
    try:
        pressure_line=Path('/sys/fs/cgroup/cpu.pressure').read_text().splitlines()[0]
        pressure=float(next(x for x in pressure_line.split() if x.startswith('avg10=')).split('=')[1])/100.0
    except (OSError,ValueError,IndexError,StopIteration): pressure=None
    return {'effective_cores':round(cores,2),'load_1m':load,
            'load_per_core':round(load/host_cores,3) if load is not None else None,
            'cpu_cgroup_pressure_fraction':pressure,
            'memory_available_bytes':m_available,'cgroup_memory_limit_bytes':cg_limit,
            'disk_free_bytes':disk.free,'disk_total_bytes':disk.total,
            'swap_free_bytes':memory.get('SwapFree'),'max_temperature_c':thermal_c()}


def admit(metrics, estimated_memory_mb=32, estimated_disk_mb=4):
    """Deny if limits uncertain/unsafe; no operation overrides a host limit."""
    reasons=[]
    mem=metrics.get('memory_available_bytes');disk=metrics.get('disk_free_bytes')
    if mem is None:reasons.append('memory_unknown')
    elif mem < (256 + estimated_memory_mb)*1024**2:reasons.append('low_memory')
    if disk is None:reasons.append('disk_unknown')
    elif disk < (1024 + estimated_disk_mb)*1024**2:reasons.append('low_disk')
    load=metrics.get('load_per_core')
    if load is None:reasons.append('cpu_load_unknown')
    elif load > 0.85:reasons.append('high_cpu_load')
    pressure=metrics.get('cpu_cgroup_pressure_fraction')
    if pressure is not None and pressure > 0.30:reasons.append('cpu_cgroup_pressure')
    temp=metrics.get('max_temperature_c')
    if temp is not None and temp>=80:reasons.append('high_temperature')
    return {'admitted':not reasons,'reasons':reasons,'estimated_memory_mb':estimated_memory_mb,
            'estimated_disk_mb':estimated_disk_mb,'estimates_are_assumptions':True,
            'temperature_monitored':temp is not None}


def capacity(work_path='.'):
    m=snapshot(work_path)
    return {'measurements':m,'decision':admit(m)}
