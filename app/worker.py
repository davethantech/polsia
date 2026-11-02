import argparse,time
from .core import init_db,run_once

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true');parser.add_argument('--poll-seconds',type=float,default=2)
    args=parser.parse_args();init_db()
    while True:
        result=run_once()
        if result:print(result,flush=True)
        if args.once:break
        if result is None:time.sleep(args.poll_seconds)
if __name__=='__main__':main()
