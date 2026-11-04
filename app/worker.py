"""Resource-bounded mission worker and low-frequency knowledge refresh worker.

Independent tasks may run concurrently in one process, but there is no
unbounded spawning or speculative auto-agent generation.
"""
import argparse
import concurrent.futures
import time
from .core import init_db,run_once,refresh_due_culture_subscription,refresh_due_learning_subscription

MAX_WORKERS=2  # Conservative VPS cap; each has independent SQLite connections.


def process_batch(workers=1):
    if type(workers) is not int or not 1<=workers<=MAX_WORKERS:
        raise ValueError('Worker concurrency must be 1 or 2')
    if workers==1:
        return [run_once()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers,thread_name_prefix='polsia') as pool:
        return list(pool.map(lambda _:run_once(),range(workers)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-seconds',type=float,default=5)
    parser.add_argument('--workers',type=int,choices=range(1,MAX_WORKERS+1),default=1,
                        help='Bounded concurrent task slots (default 1, maximum 2)')
    args=parser.parse_args()
    if not (1 <= args.poll_seconds <= 600):parser.error('poll-seconds must be 1–600')
    init_db()
    while True:
        results=process_batch(args.workers)
        for result in results:
            if result:
                # Do not dump retrieved webpages, private company data, or model answers.
                print({'task_id':result.get('task_id'),'status':result['status'],
                       'reasons':result.get('reasons')},flush=True)
        # Source polling is single-flight and only when mission workers idle.
        if all(x is None for x in results):
            refresh=refresh_due_culture_subscription() or refresh_due_learning_subscription()
            if refresh:
                print({'status':refresh['status'],'reasons':refresh.get('reasons')},flush=True)
            else:
                time.sleep(args.poll_seconds)
        elif all(x is None or x.get('status')=='THROTTLED' for x in results):
            time.sleep(args.poll_seconds)
        if args.once:break


if __name__=='__main__':main()
