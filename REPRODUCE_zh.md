# 从零重跑 GMemory

本仓库基于官方 commit `7b581c51d993bd600df14691d101d7e601040cc6`，保留原始文件和历史。新增入口是 `python -m repro.run`。原始 `tasks/run.py` 中的 `max_trials` 实际限制单个任务的步数，不能用来限制任务数量。

## 1. 获取代码与独立环境

在 Windows PowerShell 中执行：

```powershell
git clone https://github.com/Farewellxxxx/Gmemory-Reproduction.git
cd Gmemory-Reproduction
python --version  # 本次使用 Python 3.12.7；代码需要 Python 3.12
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-repro.txt
```

这套依赖只为 PDDL + AutoGen + GMemory 路径准备。其他基准仍需要各自依赖。Windows 下旧版 `chroma-hnswlib` 需要 MSVC，本次使用提供预编译包的 `chromadb==1.0.9` 和兼容的 `langchain-chroma==0.2.4`；这是相对官方依赖的明确差异。

## 2. 准备本地模型与 tokenizer

```powershell
.\.venv\Scripts\python.exe -m repro.download_assets --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41
.\.venv\Scripts\python.exe -m nltk.downloader -d .cache/nltk_data punkt punkt_tab
```

向量模型约 90 MB，运行在本机 CPU，不消耗 ChatAnywhere token。下载脚本记录 Hugging Face revision 和每个文件的 SHA256。PDDL 题目、领域定义已经包含在官方源码中，本次没有自行编造题目。

## 3. 配置 Key

```powershell
Copy-Item .env.example .env
notepad .env
```

将 `.env` 中的占位符替换为自己的 Key。`.env` 和 `runs/` 默认不提交 Git。复现使用默认分组的 `gpt-4o-mini`，只需一把 Key；多个角色通过不同提示词共用同一模型。

## 4. 先运行不花 API 费用的检查

```powershell
$env:PYTHONHASHSEED='42'
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest
```

测试包括真实 PDDL reset/step、凭据不打印、预算持久化、请求异常和任务数量限制。网络服务在单元测试中被替代，测试结果不能作为模型能力的证据。

## 5. 小额连通性检查

```powershell
.\.venv\Scripts\python.exe -m repro.run --probe --output runs/probe --budget-file runs/budget.json
```

这一步会产生一次实际付费请求，最多输出 16 tokens。查看 `runs/probe/calls.jsonl`，核对请求型号、返回型号、usage 和估算费用。返回的型号字段只是服务端声明，不能独立证明底层模型供应链。

## 6. 两组真实实验

```powershell
.\.venv\Scripts\python.exe -m repro.run --arm g-memory --output runs/gmemory --budget-file runs/budget.json
.\.venv\Scripts\python.exe -m repro.run --arm none --output runs/no-memory --budget-file runs/budget.json
```

必须顺序运行并共用预算文件；输出目录必须是新的，避免覆盖证据。默认配置为 4 个领域各取原始索引前 6 个问题，共 24 个任务，每题最多 30 次调度循环。顺序固定为 blockworld、gripper、barman、tyreworld。原始 few-shot 示例保留 1 个，GMemory 开启角色投影。

`none` 保留当前任务的对话历史，但不保存或检索跨任务经验。这才是对照的准确含义。

本次 30 步与官方 README 的 PDDL 命令示例一致；上游 `tasks/run.py` 在省略参数时默认 50 步。任务子集等条件仍有差异，不能把这组数字直接与论文全量结果对比。额外的 90 步搬球诊断使用 `configs/diagnostic-gripper90.json`，必须使用新的输出目录、同一预算账本并分别运行两组；它与主实验分开统计。

预算文件在第一次请求前记录截止时间和 50 CA 上限，后续程序读取同一文件；重启不会清零费用或延长截止时间。网络故障造成无法核实的请求会保留预留额度。估算单价为输入 1.05 CA/百万 token、输出 4.2 CA/百万 token，平台后台账单才是实际扣费依据。

这里的单价是本次运行时使用的记录。以后重新运行前，应核对平台当前分组价格并修改新实验配置；已经开始的预算账本拒绝被静默重设单价或额度。

## 7. 查看过程

- `manifest.json`：模型、配置、任务顺序、源码/数据哈希和依赖版本。
- `calls.jsonl`：每次模型请求的用途、提示词、回答、usage、耗时和估算费用。
- `workflow.jsonl`：上游 AutoGen 输出的任务提示与行动观察。
- `episodes/000.json`：单个任务完整状态、动作和结果。
- `memory_events.jsonl`：检索、投影、写入、规则提炼与合并。
- `snapshots/`：每题完成后的记忆摘要。
- `memory/`：本地 Chroma 和图/规则持久化文件。
- `status.json`：完成、失败或中断状态。`failure.txt` 保存脱敏异常。

先按 `WALKTHROUGH_zh.md` 阅读本次真实样例，再逐条打开这些文件；不要把上游 `logs/` 内继承的历史结果当作本次运行结果。

## 8. 验证重载并生成公开结果

两组结束后执行：

```powershell
.\.venv\Scripts\python.exe -m repro.reload_check runs/gmemory
.\.venv\Scripts\python.exe -m repro.audit_evidence runs/gmemory
.\.venv\Scripts\python.exe -m repro.analyze --gmemory runs/gmemory --baseline runs/no-memory --output artifacts/my-run
```

重载检查在新进程中重新打开向量库、任务图和规则文件，并禁止调用 LLM。分析脚本先核对题目、配置、数据和实际运行源码一致性，再输出统计与压缩证据；它会保留运行状态，不把中断误写成完整实验。

证据审计逐条核对：检索时的记录数是否等于已完成任务数、成功轨迹是否与此前完成的某题完全对应、取出的规则是否已经存在于本题开始前的快照。范围仅限这些可核对内容，不能替代对记忆正确性和有效性的评价。

重载时还导出 `task_graph.json`，用可读的节点/边列表呈现实际任务图，包括相似度边权和已有的聚类标签；完整轨迹文本见 `memory_documents.json.gz`，规则及其关联见 `final_memory.json`。

压缩日志可直接用 Python 读取，例如：

```powershell
.\.venv\Scripts\python.exe -c "import gzip,json; f=gzip.open('artifacts/my-run/gmemory/calls.jsonl.gz','rt',encoding='utf-8'); print(json.loads(next(f)))"
```

准备提交自己的结果前，先明确选择需要公开的文件，再运行 `python -m repro.check_publish` 扫描跟踪文件与 Git 历史中的凭据格式。脚本也检查 gzip 内部文本；它是辅助检查，不代替对公开内容的人工确认。

## 9. 不花 API 费用，跟读一次真实记忆调用

下面是在 Python 中执行的代码，使用首次中断试跑里已完成任务的教学记录，无需配置 Key；最终配对成绩另见 `artifacts/first-run/`：

```python
import json
from pathlib import Path

trace = json.loads(Path('artifacts/interrupted-attempt/gmemory/selected_trace.json').read_text(encoding='utf-8'))
print('当前任务：', trace['retrieval']['query'])
print('原始规则：', trace['retrieval']['insights'])
for projection in trace['projections']:
    print('角色：', projection['role'])
    print('角色化规则：', projection['projected'])

# state_chain 是 JSON 字符串，还要解码一次。
states = json.loads(trace['episode']['context']['state_chain'])
print('第一步实际收到的提示词：')
print(states[0]['nodes'][0]['user_instruction'])
for index, state in enumerate(states, 1):
    step = state['graph']
    print(index, step['action'], 'step reward=', step['reward'])
print('最终结果：', trace['episode']['result']['success'])
```

若想看模型的原始回答和 token，可读取压缩调用日志并筛选同一个 `task_id`：

```python
import gzip

with gzip.open('artifacts/interrupted-attempt/gmemory/calls.jsonl.gz', 'rt', encoding='utf-8') as stream:
    calls = [json.loads(line) for line in stream]
for call in calls:
    if call['task_id'] == trace['task_id']:
        print(call['purpose'], call['answer'], call['usage'])
```

这些操作只读取已保存记录，不会重新调用模型，也不会增加费用。`step reward=-1` 需要结合动作类型理解：思考也可能得到 -1，所以不能把所有负奖励都统计成无效物理动作。
