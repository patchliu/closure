# closure

Closure：从性能分析到编译器优化的闭环（Triton Ascend → BiShengIR → 仿真/板上性能优化）。首版为单控制器、单活跃候选、文件事件日志的确定性执行内核，AI 只提交提案，程序掌握执行、事实、状态与验收。

## 安装与测试

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python3 -m pytest -q
```

## 四条最短路径

### 1. 运行 fixture 演示（无需 Ascend 硬件）

本地数值 fixture 验证控制器/evaluator/晋级闭环：

```bash
closure init --case demo --case-id example-kernel
closure doctor --case demo
closure run --case demo --proposals proposals.json
closure status --case demo
closure report --case demo
```

其中 `proposals.json` 是 replay planner 的预录提案列表，例如：

```json
[
  {
    "proposal_id": "p001",
    "packet_hash": "__stub__",
    "expected_state_seq": 0,
    "action": "propose_variant",
    "payload": {
      "baseline": "v000",
      "parent_variant": "v000",
      "change_kind": "ir_patch",
      "hypothesis": "候选延迟低于基线",
      "change": {"patch_artifact": "proposal:patch-1"}
    }
  }
]
```

`run` 结束后 `incumbent` 应变为 `v001`，`latency_ratio_to_baseline > 0`。capture/compile/simulate 阶段按 `blocked` 记录，不伪造硬件验收。

### 2. 接入本机容器

在 `profiles/<name>.toml` 中配置 Docker 执行目标后，`doctor` 探测容器内能力：

```toml
# profiles/mac-docker.toml
schema_version = 1
name = "mac-docker"
transport = "local"
runtime = "docker"
container = "<你的容器名或镜像>"
roles = ["compile", "simulate"]
```

容器未启动时 `doctor` 返回 `unknown`/`unsupported` 及缺口原因，不会悄悄换 SoC 或放宽容差绕过。

### 3. 接入服务器 / 板卡

在 `profiles/<name>.toml` 中配置 SSH 目标与 SoC/device，再由 `doctor` 探测真实工具链：

```toml
# profiles/board.toml（占位，需替换为实际主机与工具版本）
schema_version = 1
name = "board"
transport = "ssh"
runtime = "native"
ssh_alias = "<你的 ssh 别名>"
soc = "<目标版本>"
device = "<设备号>"
roles = ["validate", "benchmark"]
```

未连接或未授权时 `doctor` 明确报 `unknown`，板上验收独立于快筛结果。

### 4. 恢复或迁移

事件日志 `events.jsonl` 是权威记录，`state.json` 是可重建快照：

```bash
closure resume --case demo --proposals more.json   # 从事件恢复并继续
closure export --case demo --output bundle --level essentials
closure import --bundle bundle --case copy
```

删除 `state.json` 后 `resume`/`status` 会自动从事件链重建；导出/导入通过哈希校验完整性。

## 子命令

`init` / `doctor` / `run` / `resume` / `status` / `report` / `freeze` / `export` / `import` / `gc` / `compiler-plan`。详细见 `closure --help` 与各子命令 `--help`。

## 状态与验收边界

- 本机/fixture 通过仅称「实现完成，硬件验收未完成」；Ascend 实机相关门槛逐项列为 `blocked`。
- 自动生成并验证编译器源码补丁属于后续里程碑 T6，`compiler-plan` 只产出可审查的 dossier。