import argparse,time,os
from .core import init_db,run_once,refresh_due_culture_subscription

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true');parser.add_argument('--poll-seconds',type=float,default=2)
    args=parser.parse_args();init_db()
    while True:
        result=run_once()
        if result is None:
            result=refresh_due_culture_subscription()
        if result:
            # Do not dump retrieved web pages or company memory into VPS logs.
            print({'task_id':result.get('task_id'),'status':result['status'],'reasons':result.get('reasons')},flush=True)
        if args.once:break
        if result is None or result.get('status')=='THROTTLED':time.sleep(max(1,args.poll_seconds))
if __name__=='__main__':main()
