# 怎样离线核对公开证据

这里保存最终证据核验、总用量账本与检查记录。它们检验记录是否一致，不证明模型方法有效，也不代表平台实际账单。

仓库的 `.gitattributes` 对 `artifacts/` 禁用换行转换，保留生成时的原始字节，避免 LF/CRLF 转换造成哈希不匹配。已跟踪的旧文件另通过 `git add --renormalize artifacts` 刷新索引。独立 Git 检查覆盖 LF、CRLF 两种文件及 `core.autocrlf=true/false` 两种设置，记录见 `eol_preservation.json`；实际仓库重新检出的证据也通过哈希核对。

在仓库根目录的 Python 环境运行下面的代码即可重新检查所有已导出文件哈希，无需安装模型或提供 API Key：

```python
import hashlib
import json
from pathlib import Path

count = 0
for manifest in Path('artifacts').rglob('SHA256.json'):
    hashes = json.loads(manifest.read_text(encoding='utf-8'))
    for name, expected in hashes.items():
        path = manifest.parent / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
        count += 1
print('通过哈希核对的文件数：', count)
```

也可以把全部公开模型调用与最终账本逐项对应，包括连通性检查和首次中断试跑：

```python
import gzip
import math

calls = []
for path in Path('artifacts').rglob('calls.jsonl.gz'):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        calls.extend(json.loads(line) for line in stream if line.strip())
probe = Path('artifacts/setup/probe_calls.jsonl')
calls.extend(json.loads(line) for line in probe.read_text(encoding='utf-8').splitlines())

assert len(calls) == len({call['call_id'] for call in calls})
known = [call for call in calls if 'estimated_ca' in call]
budget = json.loads(Path('artifacts/validation/final_budget.json').read_text(encoding='utf-8'))
assert budget['settled_calls'] == len(known)
assert budget['prompt_tokens'] == sum(call['usage']['prompt_tokens'] for call in known)
assert budget['completion_tokens'] == sum(call['usage']['completion_tokens'] for call in known)
assert math.isclose(budget['spent_ca'], sum(call['estimated_ca'] for call in known))
print('收到 usage 的调用数：', len(known))
print('按 token 估算费用：', budget['spent_ca'], 'CA')
print('未知费用请求的预留额：', sum(budget['pending'].values()), 'CA')
```

两个代码块可在同一个 Python 会话依次执行。`pending` 是无法从返回 usage 确认费用的请求预留额，不能当作实际扣费，也不能当作零费用。各组 `budget_at_end.json` 是共享账本在当时的累计快照，不能把多个快照再相加；分组费用应从各组调用记录或 `summary.json` 读取。
