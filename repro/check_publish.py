"""Check tracked files and reachable Git blob history without printing matches."""
import gzip
import json
from pathlib import Path
import re
import subprocess

PATTERN=re.compile(rb'sk-[A-Za-z0-9_-]{16,}')
TEST_DUMMY=b'sk-secret-that-must-never-be-published'


def contains_secret(data):
    if data.startswith(b'\x1f\x8b'):
        data=gzip.decompress(data)
    return any(value!=TEST_DUMMY for value in PATTERN.findall(data))


def main():
    hits=[]
    paths=subprocess.check_output(['git','ls-files','-z']).split(b'\0')
    count=0
    for raw in paths:
        if not raw:
            continue
        path=Path(raw.decode('utf-8'))
        if path.is_file():
            count+=1
            if contains_secret(path.read_bytes()):
                hits.append({'scope':'working-tree','path':str(path)})
    objects=subprocess.check_output(['git','rev-list','--objects','--all'],text=True).splitlines()
    process=subprocess.Popen(['git','cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    blobs=0
    try:
        for row in objects:
            identifier=row.split(' ',1)[0]
            process.stdin.write((identifier+'\n').encode())
            process.stdin.flush()
            header=process.stdout.readline().decode().split()
            if len(header)!=3:
                raise RuntimeError('Unexpected git object header')
            content=process.stdout.read(int(header[2]))
            process.stdout.read(1)
            if header[1]=='blob':
                blobs+=1
                if contains_secret(content):
                    hits.append({'scope':'git-history','object':identifier,'path_hint':row.split(' ',1)[1] if ' ' in row else ''})
    finally:
        process.stdin.close()
        process.wait(timeout=10)
    result=dict(tracked_files_checked=count,history_blobs_checked=blobs,
                credential_like_matches=hits,
                scope='sk-prefixed credentials, gzip contents included; one explicit synthetic test dummy excluded')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return bool(hits)


if __name__=='__main__':
    raise SystemExit(main())
