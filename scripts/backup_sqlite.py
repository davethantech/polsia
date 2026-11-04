"""Consistent online backup for a single-host SQLite deployment.

Example: POLSIADB=/srv/data/polsia.db python scripts/backup_sqlite.py /backups
Store encrypted copies off-host; running this script alone is not a DR plan.
"""
import argparse
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def backup(database, directory):
    database = Path(database)
    directory = Path(directory)
    if not database.is_file():
        raise FileNotFoundError('No application database found')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = directory / f'polsia-{stamp}.sqlite3'
    if target.exists():
        raise FileExistsError('Backup filename already exists; retry with a new UTC second')
    src = sqlite3.connect(f'file:{database.resolve()}?mode=ro', uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst,pages=200,sleep=0.1)
        status = dst.execute('PRAGMA quick_check').fetchone()[0]
        if status != 'ok':
            raise RuntimeError('Backup failed SQLite integrity check')
    except Exception:
        dst.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        src.close()
        dst.close()
    os.chmod(target,0o600)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Atomic SQLite online backup; do not expose backups publicly')
    parser.add_argument('output_dir')
    parser.add_argument('--database',default=os.environ.get('POLSIADB','polsia.db'))
    args=parser.parse_args()
    print(backup(args.database,args.output_dir))
