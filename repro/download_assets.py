"""Download only the files used by all-MiniLM-L6-v2; record exact revision."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

FILES = ['config.json','config_sentence_transformers.json','modules.json',
         'sentence_bert_config.json','special_tokens_map.json','tokenizer_config.json',
         'tokenizer.json','vocab.txt','1_Pooling/config.json','model.safetensors']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--endpoint',default='https://huggingface.co')
    parser.add_argument('--output',default='.cache/all-MiniLM-L6-v2')
    parser.add_argument('--revision',default='main')
    args=parser.parse_args()
    repo='sentence-transformers/all-MiniLM-L6-v2'
    with urllib.request.urlopen(f'{args.endpoint}/api/models/{repo}/revision/{args.revision}',timeout=60) as response:
        metadata=json.load(response)
    revision=metadata['sha']
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    def download(name):
        target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        # Complete file set is pinned to one revision on every invocation.
        with urllib.request.urlopen(f'{args.endpoint}/{repo}/resolve/{revision}/{name}',timeout=120) as response:
            temporary=target.with_suffix(target.suffix+'.download')
            with temporary.open('wb') as stream:
                while chunk:=response.read(1024*1024):
                    stream.write(chunk)
        temporary.replace(target)
        return name,hashlib.sha256(target.read_bytes()).hexdigest()
    with ThreadPoolExecutor(max_workers=3) as executor:
        hashes=dict(executor.map(download,FILES))
    manifest=dict(repo=repo,revision=revision,endpoint=args.endpoint,sha256=hashes)
    (output/'download-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(output),revision=revision,files=len(hashes))))


if __name__=='__main__':
    main()
