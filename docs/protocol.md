# 事件与状态协议参考

权威实现：`closure/events.py`、`closure/state.py`、`closure/schemas/enums.py`。
本文是契约速查；实现与文档冲突时以代码 + 测试为准，并回改本文。

## 事件（Event）

`events.jsonl` 每行一个事件，字段 `extra="forbid"`：

| 字段 | 说明 |
|---|---|
| `schema_version` | 当前为 1 |
| `seq` | 从 1 递增，断裂即校验失败 |
| `event_id` | uuid4 |
| `type` | EventType 枚举值 |
| `created_at` | UTC ISO 时间 |
| `previous_hash` | 前一事件哈希，创世事件为全零哈希 |
| `payload` | dict，见下表 |
| `hash` | 规范化 SHA-256（排除事件自身 `hash` 字段） |

链校验（`verify_chain`）：seq 连续、`previous_hash` 指向前一事件哈希、
`hash` 与内容一致；任一项断裂抛 `ValueError`（错误码 `CHAIN_CORRUPTED`）。
写入中断留下的末尾不完整行在读取时被忽略。

## 事件类型与 reducer 效果

| 事件 | payload 要点 | reducer 效果 |
|---|---|---|
| `case.created` | `case_id`, `budget_limits` | 初始化 case、预算上限与阶段表 |
| `environment.probed` | `capabilities`, `reasons?`, `per_profile?` | `state.environment = payload` |
| `proposal.accepted` | `proposal`, `plan_hash` | 登记提案哈希，`model_calls` +1 |
| `proposal.rejected` | `proposal_id`, `reason` | `model_calls` +1，清 pending |
| `stage.planned` | `stage`, `plan_hash` | 阶段置 pending |
| `stage.started` | `stage`, `candidate_id?` | 阶段置 running |
| `stage.result_committed` | `stage`, `status`, `candidate_id?`, `checks?`, `cost?` | 阶段落状态；候选阶段与目标（benchmark ratio）更新；`cost` 累加预算 |
| `candidate.registered` | `candidate{candidate_id,...}`, `is_baseline?` | 登记候选；非基线时 `candidates` 预算 +1 |
| `candidate.promoted` | `candidate_id` | incumbent 指向该候选；已注册者置 confirmed |
| `candidate.rejected` | `candidate_id`, `reason` | 置 rejected 并记录原因 |
| `budget.adjusted` | `limits?` / `used?` | `limits` 覆盖上限；`used` 累加实际消耗 |
| `run.stopped` | `reason` | `run_status=stopped` |
| `artifact.sealed` | `artifact{id,...}` | 登记产物 |
| `sync.verified` | `level` | `facts.sync.verified` |
| `review.attested` | `id`, ... | `facts.review` 登记 |

## 预算

上限来自 `case.toml` 的 `[budget]`：`max_model_calls`、`max_candidates`、
`max_simulator_runs`、`max_wall_seconds`；可经 `budget.adjusted.limits` 调整。

实际消耗记账：

- `model_calls`：每个提案（接受或拒绝）+1
- `candidates`：每个非基线候选登记 +1
- `runs`：子进程实际次数（validate=2，benchmark=6），经 `stage.result_committed.cost`
- `wall_seconds`：run/freeze 退出时经 `budget.adjusted.used` 落盘，
  **跨 resume 累积**，新进程不重置墙钟预算

## 错误码（ErrorCode）

`CONFIG_INVALID` / `EVALUATION_CONFIG_MISSING` / `CAPABILITY_UNSUPPORTED` /
`STALE_PROPOSAL` / `ARTIFACT_MISSING` / `HASH_MISMATCH` / `ENVIRONMENT_BLOCKED` /
`COMPILE_FAILED` / `INJECTION_UNVERIFIED` / `TARGET_NOT_MATCHED` / `TRACE_PARTIAL` /
`CORRECTNESS_FAILED` / `PERFORMANCE_INCONCLUSIVE` / `BUDGET_EXHAUSTED` / `PLANNER_INVALID`

## 能力三态与证据分级

- Capability：`supported` / `unknown` / `unsupported`；`unknown`（未烟测）
  不得当 supported 使用，能力缺口必须附 `reasons`。
- EvidenceLevel（由 `search.mode` 与设备可用性路由，见 `selection.py`）：
  E0 诊断 / E1 复现 / E2 捕获 / E3 编译后仿真。
- 保留期：`essential` > `evidence` > `reproducible` > `scratch`；
  GC 仅删 scratch/reproducible，evidence 与被引用的唯一副本不删。

## 快照重建

`state.json` 为派生快照，随时可删：`StateStore.replay()` 会对全链
`verify_chain` + `reduce` 重建；快照写入为 tmp + fsync + rename 原子操作。
