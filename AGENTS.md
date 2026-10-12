# AGENTS.md — 代理与新人必读

Closure 是一个确定性执行内核：以可审计的事件链驱动 NPU 算子调优闭环。
先读本文件，再按需查阅 [docs/protocol.md](docs/protocol.md) 与 [README.md](README.md)。

## 核心不变量（违反即 bug）

1. `state.json` 只是派生快照，权威记录是 `events.jsonl` 哈希链；删掉快照必须能全量重放重建。
2. AI/提案输出永不直接进入状态；只经 `proposal.accepted` 后由 reducer 推进。
3. 所有 schema `extra="forbid"`；新增事件/状态/错误码必须同步更新 `schemas/`、reducer、`docs/protocol.md` 与测试。
4. 预算包含失败与基础设施故障的实际消耗；墙钟预算经 `budget.adjusted` 的 `used` 跨 resume 累积。
5. incumbent 只能被「协议哈希一致 + 独立确认 + 回归上限」的候选替换。
6. 未验证能力必须标记 `unsupported`/`blocked` 并给出最小缺口原因，禁止静默绕过。

## 模块地图

| 路径 | 职责 |
|---|---|
| `closure/schemas/` | 全部 pydantic 契约：case/profile/动作 envelope/记录/枚举 |
| `closure/events.py` | 追加式 JSONL 事件日志、哈希链校验、单写者锁 |
| `closure/state.py` | reducer 与 StateStore：快照重建、原子写 |
| `closure/controller.py` | 唯一状态提交入口：预算、提案裁决、候选推进、inspect |
| `closure/planner.py` | Planner 接口与 ReplayPlanner（无模型回放） |
| `closure/executors.py` | local/ssh/docker 执行器与三态能力探测 |
| `closure/adapters/ascend.py` | Ascend 工具链探测与编译 argv 构造 |
| `closure/parsers/` | 编译日志 / trace 的独立解析器（只产出结构化事实） |
| `closure/evaluator.py` | correctness 与 latency 评测、协议哈希 |
| `closure/selection.py` | 证据分级路由与晋级判定 |
| `closure/artifacts.py` | 产物封存、保留期与 GC 计划 |
| `closure/knowledge.py` | 经验库与 dossier |
| `closure/migrate.py` | 跨机器 bundle 导出/导入 |
| `closure/report.py` | Markdown 状态报告 |
| `closure/cli.py` | 命令行入口 |

## 常用命令

```bash
python3 -m pytest -q                                # 全量测试
python3 -m closure.cli init --case demo --case-id kernel-x
python3 -m closure.cli doctor --case demo           # 探测能力并记录 environment.probed
python3 -m closure.cli run --case demo --proposals proposals.json
python3 -m closure.cli status --case demo           # 候选谱系 + 预算已用/上限
python3 -m closure.cli gc --case demo --apply       # 默认 dry-run
```

## 变更规范

- 协议变更（事件/状态/错误码）：同步 `schemas/enums.py`、`state.py` reducer、
  `docs/protocol.md`；不变量测试在 `tests/test_invariants.py`，不删不改语义。
- commit 采用 conventional 风格，中文 body 说明「为什么」而非罗列 diff。
- 新增行为必须补对应用例；`tests/test_controller.py` 走本地 fixture 全链路。
