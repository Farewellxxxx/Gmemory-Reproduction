# 跟着一题成功记录看完整执行

这是一道 **PDDL 虚拟规划题**，不是现实汽车维修教程。证据来自正式主实验 `task_id=18`，即 tyreworld 的 `problem_index=0`；不是人工补写的成功演示。

## 1. 先看题目，而不是先看模型

题目规定三个最终条件：新轮胎 `r1` 已充气、`r1` 安装在 `the-hub1`、旧轮胎 `w1` 放在后备箱 `boot`。初始时后备箱关闭，工具和新轮胎在里面，旧轮胎在轮毂上。成功只按这个符号环境定义的目标判断。

`repro/run.py` 选择官方题目文件，把目标和初始观察传给仓库自带 AutoGen 工作流。AutoGen 创建两个角色，但通常先让 solver 提议一步；只有重复相同行动卡住时，另一个 LLM 角色才接替。环境根据 PDDL 规则执行并返回观察，模型不能自行宣布成功。

## 2. 此时有哪些记忆？

本题开始前已经完成 18 题，数据库有 18 条记录，但它们都失败了；本轮还没有提炼出规则。配置要求直接检索成功轨迹 1 条、失败轨迹 0 条，所以本题没有拿到历史成功示例，也没有拿到学到的规则。

官方 few-shot 示例仍然存在。另外，原版 projector 即使输入为空，也会为两个角色各调用模型一次，生成通用建议。因此本题成功不能解释为“之前学到的成功规则发挥作用”。它提供的是本轮第一个可供后续使用的成功经验。

## 3. 实际的 18 个调度步骤

下面保留原动作文本（第 2 步思考句省略后半句），观察列给出中文概括；完整原文在 `artifacts/first-run/gmemory/episodes.jsonl.gz` 中的 `018.json`。

| 步骤 | 模型输出的动作 | 环境观察与解释 |
|---|---|---|
| 1 | `Open boot.` | 后备箱打开。 |
| 2 | `think: I need to fetch the wrench ...` | 这只是思考，没有改变物理状态，但占一次调度步骤。 |
| 3 | `open boot.` | 重复开箱，无状态变化，被判无效。 |
| 4 | `fetch wrench from boot.` | 拿到扳手。 |
| 5 | `check valid actions.` | 查询当前合法动作，其中包含松螺母、拿千斤顶等。 |
| 6 | `Loosen the nut nuts1 on the hub the-hub1.` | 螺母变松。 |
| 7 | `fetch jack from boot.` | 拿到千斤顶。 |
| 8 | `jack-up the hub the-hub1` | 轮毂离地。 |
| 9 | `undo the fastening of the nut nuts1 on the hub the-hub1.` | 解除固定，拿到螺母。 |
| 10 | `remove-wheel w1 from the hub the-hub1.` | 拆下旧轮胎，轮毂空出。 |
| 11 | `put-away w1 in boot.` | 旧轮胎放进后备箱，满足一个目标条件。 |
| 12 | `fetch r1 from boot.` | 拿到新轮胎。 |
| 13 | `check valid actions.` | 合法动作中出现安装新轮胎。 |
| 14 | `put-on-wheel r1 on the hub the-hub1.` | 安装新轮胎，满足第二个目标条件。 |
| 15 | `inflate r1.` | 无效；此时还没有拿到气泵。 |
| 16 | `check valid actions.` | 合法动作列表提示可拿气泵。 |
| 17 | `fetch pump from boot.` | 拿到气泵。 |
| 18 | `inflate r1.` | 轮胎充气，三个目标全部满足，环境返回成功。 |

这里可以看出：模型没有一次生成完美计划，而是通过查询、试错和环境反馈完成任务。18 步包括 1 次思考、3 次查询和 14 次物理动作尝试，其中 2 次物理动作无效。思考不增加环境内部计数，所以结果里的 `environment_steps` 是 17。

## 4. 为什么有些正确动作的 reward 仍是 0？

原版环境有两个不同接口。`step()` 对普通有效动作通常返回 0，最终成功返回 1；查询返回当前累计进度，无效动作和思考返回 -1。另一个 `feedback()` 返回任务全过程达到过的最大目标满足比例，最终实验结果使用它。

因此，第 11 步确实满足了一个条件，但状态链里该步的即时 reward 是 0；第 13 步查询时才显示 1/3。第 14 步满足第二个条件，第 16 步查询显示 2/3；最后一步显示 1。不能把每步的即时 reward 简单求平均当作本题进度，也不能将思考的 -1 算作无效物理动作。

## 5. 成功之后怎样写入记忆？

调度循环结束后，工作流读取本地环境的最终反馈，再调用 `save_task_context(label=True)`。上下文包括目标、初始描述、整段轨迹和角色消息。GMemory 随后调用语言模型提炼关键步骤，再将任务记录存入 Chroma，更新任务图，并保存对应文件。

本题的真实调用量是 **21 次**：18 次行动生成、2 次空输入角色投影、1 次轨迹提炼。它成功了，所以没有失败分析调用；此时累计记录数是 19，尚未到下一次统一规则更新点。按收到的 usage 估算，本题约 0.042604 CA，历时约 42.64 秒。

下一题结束时累计 20 条记录，才执行规则更新与聚类合并。之后 `task_id=20` 读取了本题的成功轨迹和 3 条规则。这正是“当前任务结束 → 存下经验 → 新任务开始 → 检索旧经验”的跨任务过程，详见 [WALKTHROUGH_zh.md 第 12、13 节](WALKTHROUGH_zh.md#12-正式重跑中第-20-题后的合并)。

## 6. 自己核对原始记录

在仓库目录下运行以下 Python 代码，无需 Key，也不会调用 API：

```python
import gzip
import json

with gzip.open('artifacts/first-run/gmemory/episodes.jsonl.gz', 'rt', encoding='utf-8') as stream:
    rows = [json.loads(line) for line in stream]
episode = next(row['episode'] for row in rows if row['file'] == '018.json')
print(episode['result']['task_main'])
for number, state in enumerate(json.loads(episode['context']['state_chain']), 1):
    graph = state['graph']
    print(number, graph['action'], graph['observation'], graph['reward'])
print(episode['result']['success'], episode['result']['reward'])
```

要看模型实际收到的完整系统提示和用户提示，再读取同组的 `calls.jsonl.gz`，筛选 `task_id == 18` 和 `purpose == 'agent_action'`，检查 `messages`。这比只看最终动作更接近一次完整的 API 调用。
