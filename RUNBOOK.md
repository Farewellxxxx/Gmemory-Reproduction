# 运行与恢复记录

执行方案见 `EXECUTION_PROMPT_zh.md`，细化计划见 `docs/superpowers/plans/2026-11-05-gmemory-reproduction.md`。

## 当前本地布局

- 项目：`E:\study documents\FYP\gmemory-reproduction`。
- Python：`.venv\Scripts\python.exe`。
- 凭据在项目外的本地私密配置中；仓库只提供 `.env.example`。
- 安装日志在父工作区 `tmp/gmemory-install-*.log`；模型下载日志为 `tmp/gmemory-download-embedding.log`。
- 首轮实验共用 `runs/budget.json`，截至北京时间 2026-11-05 08:13:04。
- 首次中断试跑为 `runs/gmemory`；最终配对重新从空记忆开始，目录为 `runs/primary-gmemory`、`runs/primary-no-memory`。两次之间不拼接成绩。
- `repro.keep_awake` 临时请求 Windows 保持系统唤醒，实验结束或截止时释放；不修改电源计划。

## 异常处理

1. 先看对应运行目录的 `status.json`、`failure.txt`、最后一条 `calls.jsonl`。
2. 临时网络、429、5xx 错误最多尝试三次，每次单独预留额度并记录；耗尽尝试会中止任务。usage 缺失、空回答和其他 4xx 立即停止，不能把这些情况归类为模型解题失败。
3. 保留原目录和预算文件；不要删掉账本重新尝试来绕过上限。
4. 当前入口拒绝覆盖已存在目录。修复后可以用新目录继续诊断，并记录所用任务、记忆来源和费用；不要把中断前后不同条件的数据直接拼成一组完整实验。
5. 结果中的已完成 episode 和记忆快照可用于离线教学。重跑整组时必须重新使用空记忆，并为两组选择相同任务。

## 已遇到的安装问题

- 受限执行环境中的 Git DNS 线程、Conda 进程及 venv ensurepip 子进程启动失败。正常权限下 Git clone 和 Python 3.12 venv 成功。
- 原 `langchain-chroma==0.2.3` 要求 `chromadb<0.7`。Windows 安装其 `chroma-hnswlib` 时缺少 MSVC。已通过 PyPI 元数据核实 `langchain-chroma==0.2.4` 支持 `chromadb>=1.0.9`，后者提供 Windows wheel。
- ChatAnywhere 文档中的 `/v1/query/usage_details` 查询返回 404。已成功查询 `/v1/models`，白名单仅返回 `gpt-4o-mini`；尚无可用的后台实际扣费查询证据。
