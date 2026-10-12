"""init 生成的示例模板（本地数值 fixture，非 Ascend 工具链）。

这些文件只用于在无 Ascend 环境时验证控制器/evaluator/晋级闭环；
capture/compile/simulate/inject 等 Ascend 阶段仍按 blocked 记录。
"""
from __future__ import annotations

CASE_TOML = """# example local numeric fixture；capture/inject/msprof 需在真实 profile 下另行配置
schema_version = 1
case_id = "{case_id}"
entry = "input/harness.py"
kernel_symbol = "target_kernel"
dtype = "float16"
shape = [1, 16]
grid = [1]
seed = 20261012

[roles]
compile = "server-compile"
simulate = "mac-sim"
validate = "local"
benchmark = "local"

[correctness]
reference = "input/reference.py"
input_mode = "initialized"
rtol = 0.001
atol = 0.001

[simulation]
input_mode = "initialized"
launch_count = 1
capture_after_target_seconds = 600
startup_timeout_seconds = 600
hard_timeout_seconds = 1800
allow_partial = true

[budget]
max_candidates = 5
max_simulator_runs = 6
max_wall_seconds = 7200
max_artifact_bytes = 21474836480
max_model_calls = 20

[search]
mode = "diagnose"
max_stalled_candidates = 3
candidate_pool_size = 3

[evaluation]
protocol = "closure-eval-v1"
protected_reference = true
promotion_requires = "device_confirmed"
confirmation_order = "ABBA"
"""

PROFILE_TOML = """schema_version = 1
name = "{name}"
transport = "local"
runtime = "native"
roles = ["validate", "benchmark"]
"""

REFERENCE_PY = '''import json
import sys


def out_arg(args):
    i = args.index("--out") if "--out" in args else -1
    return args[i + 1] if i >= 0 else "result.json"


def main():
    # 本地数值 fixture：reference 输出固定 values，与 harness 的 candidate 输出一致。
    values = [float(i % 7) for i in range(16)]
    json.dump({"values": values}, open(out_arg(sys.argv), "w"))


if __name__ == "__main__":
    main()
'''

HARNESS_PY = '''import json
import sys

BASELINE_LATENCY_MS = 100.0
CANDIDATE_LATENCY_MS = 60.0


def get(args, key, default):
    i = args.index(key) if key in args else -1
    return args[i + 1] if i >= 0 else default


def main():
    mode = get(sys.argv, "--mode", "baseline")
    out = get(sys.argv, "--out", "result.json")
    # 与 reference 相同的数值输出，证明 correctness 通过。
    values = [float(i % 7) for i in range(16)]
    latency_ms = BASELINE_LATENCY_MS if mode == "baseline" else CANDIDATE_LATENCY_MS
    json.dump({"values": values, "latency_ms": latency_ms}, open(out, "w"))


if __name__ == "__main__":
    main()
'''