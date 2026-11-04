"""Temporary Windows sleep inhibition for this overnight run; no power-plan edit."""
import argparse
import ctypes
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--until',required=True)
    parser.add_argument('--status',nargs='+',default=[])
    args=parser.parse_args()
    if os.name!='nt':
        return
    deadline=datetime.fromisoformat(args.until)
    kernel=ctypes.windll.kernel32
    if not kernel.SetThreadExecutionState(0x80000001):
        raise OSError('Unable to set temporary execution state')
    print('Temporary sleep inhibition active until run completion/deadline.',flush=True)
    try:
        while datetime.now(timezone.utc)<deadline:
            statuses=[]
            for name in args.status:
                try:
                    statuses.append(json.loads(Path(name).read_text(encoding='utf-8'))['status'])
                except (FileNotFoundError,json.JSONDecodeError):
                    statuses.append('pending')
            if statuses and all(s in ['complete','failed','interrupted'] for s in statuses):
                break
            time.sleep(30)
    finally:
        kernel.SetThreadExecutionState(0x80000000)
        print('Temporary sleep inhibition released.',flush=True)


if __name__=='__main__':
    main()
