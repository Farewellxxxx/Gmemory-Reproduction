# GMemory 复现与学习记录

这是 [G-Memory 官方实现](https://github.com/bingreeky/GMemory) 的独立复现仓库，用于学习 **多智能体系统怎样写入、检索和演化跨任务记忆**。

本次路径：**PDDL → 仓库自带 AutoGen 工作流 → GPT-4o mini（ChatAnywhere 默认分组）→ GMemory / 无记忆对照**。本地向量模型是 `all-MiniLM-L6-v2`。上游固定在 `7b581c51d993bd600df14691d101d7e601040cc6`，保留 Git 历史，原始说明见 [README_UPSTREAM.md](README_UPSTREAM.md)。

## 建议阅读顺序

1. [REPORT_zh.md](REPORT_zh.md)：先看本次到底跑成了什么、哪些没有完成、花费多少。
2. [WALKTHROUGH_zh.md](WALKTHROUGH_zh.md)：沿一条真实轨迹，看旧经验如何进入下一题提示词。
3. [PAPER_TO_CODE_zh.md](PAPER_TO_CODE_zh.md)：把论文中的三层记忆、W/P/R 与实际函数对应起来。
4. [REPRODUCE_zh.md](REPRODUCE_zh.md)：从安装、配置 Key 到运行两组实验，自己重跑。
5. [KNOWN_UPSTREAM_BEHAVIOR_zh.md](KNOWN_UPSTREAM_BEHAVIOR_zh.md)：了解原始实现中已经核实、但本次保留的行为与局限。
6. [RUNBOOK.md](RUNBOOK.md)：遇到中断时怎么定位问题、保留证据并恢复工作。
7. [PROCESS_LOG_zh.md](PROCESS_LOG_zh.md)：查看这次具体怎样执行、遇到什么问题、各项取舍的依据。

执行授权与方案记录在 [EXECUTION_PROMPT_zh.md](EXECUTION_PROMPT_zh.md)。实验配置在 [configs/reproduction.json](configs/reproduction.json)。

## 本次怎样评价？

两组使用同一份预先固定的 24 题清单（四个领域各 6 题）、相同题目顺序、模型和每题 30 步预算。GMemory 在题目结束后累积记忆，后续题目才能读取它；无记忆组保留当前题历史，但不复用过去题目。

同时记录平均进度率（论文的 PDDL 指标）、完整成功率、环境步数、模型调用量、输入/输出 token、时间和费用估算，并单独统计记忆处理的开销。本次 30 步与官方 README 的 PDDL 示例一致；上游 CLI 在省略参数时默认 50 步。

这是**单次、有序、在线积累的小规模诊断实验**。它用于核实代码、理解机制、定位问题，不能替代论文全量结果、多随机种子或消融实验。未来的论文级研究仍需要更完整的验证。

## 证据放在哪里？

- `artifacts/first-run/`：公开的结果、模型调用、记忆事件和完整 episode 记录；较大的文本使用 gzip 压缩。
- `artifacts/diagnostic-gripper90/`：事后追加的 90 步搬球诊断，两组各 6 题，与主实验分开统计。
- `artifacts/audits/`：独立离线诊断证据，明确与真实模型实验区分。
- `artifacts/interrupted-attempt/`：HTTP 525 中断的首次试跑；19 个已完成任务可用于教学，不计入最终配对成绩。
- `artifacts/setup/`：模型连通性、可用型号及本地 embedding 文件哈希。
- `tests/`：环境、存储、预算、统计与发布检查。
- `repro/`：运行、下载、统计、重载验证和敏感信息扫描脚本。
- `runs/`：你本机的新实验目录，默认忽略，不会随 Git 自动提交。
- `mas/`、`tasks/`、`data/`：保留官方代码和数据；少量必要补丁在 Git diff 中可查。
- `logs/`：继承的上游历史日志，不代表本次实验。

## 引用与归属

原方法、官方实现与数据的归属以其上游来源为准。本仓库新增的是复现适配、运行保护、测试、中文解释和本次实验记录。

```bibtex
@article{zhang2025g-memory,
  title={G-Memory: Tracing Hierarchical Memory for Multi-Agent Systems},
  author={Zhang, Guibin and Fu, Muxin and Wan, Guancheng and Yu, Miao and Wang, Kun and Yan, Shuicheng},
  journal={arXiv preprint arXiv:2506.07398},
  year={2025}
}
```
