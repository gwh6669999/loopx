# DeepSWE Five-Arm Harness (v1-revised, Unvalidated)

This directory contains post-publication execution fixes derived from v1.
It is **not the original v1 snapshot** and has not produced validated benchmark
results. Admission still pins LoopX `2cef51d`; that pin does not imply that this
revised harness was used for the historical experiment.

The unchanged original files live in [v1](../deepswe-gptxhigh-v1/README.md).
See the [version comparison](../deepswe-gptxhigh-versions.md) for provenance,
known original defects, and the behavior changes isolated here.
This is `benchmark/deepswe-gptxhigh-v1-revised/`, not the separate v2 experiment.

## Execution Changes

- Include the missing plain app-server runner, with no Goal attachment.
- Remove unsupported Claude and legacy `MR_CODEX_ARM=loopx` entry points.
- Validate the actual selected task list, reject missing/duplicate task ids,
  and hash the selected task definitions in admission receipts.
- Fix the evaluated LoopX revision instead of allowing an environment override.
- Serialize shared profile installation and inspection with a file lock.
- Complete admission before launch and propagate each background arm's failure.
- Use separate plain/goal gateway ports and a configurable Python interpreter.
- Fail on a terminal Todo without valid delivery and unmatched install scripts.
- Classify model retries using structured status/code fields, not message text.

These changes can affect execution, retries, termination, and outcomes. They
must not be attributed retroactively to the original v1 run.

## External Prerequisites

This is not a standalone reproduction bundle. It requires the external Pier
environment, `run.sh`, task definitions under `upstream/tasks/<id>/task.toml`,
task manifests, and separately supplied model gateway configuration.
Set `MR_LOOPX_ROOT` to a clean checkout of the pinned revision and
`MR_PYTHON` to the required Python environment (defaults to `python3`).

Both launchers require `MR_MODELONLY_COMPOSE` to name an existing external
Docker Compose overlay defining the model-only network. Its gateway must be
reachable from task containers; loopback placeholders are not a portable
network configuration.

The remaining-59 launcher uses `MR_TASK_LIST` (default `remaining59.txt`) and
requires 59 unique task directory names, one per line. The 54-task launcher
requires `goal30_subset.py`, `hard24_subset.py`, and `remaining4_subset.py`,
and validates any explicitly selected subset.

Run the revised package in a separate experiment workspace. Legacy output
names and receipt schema identifiers remain in the scripts; they are not
version labels and must not be used to mix revised runs with original results.

## Arms And Validation

The five arm selectors remain `plain`, `goal`, `loopx-native`,
`loopx-native-codex-cli`, and `loopx-native-heartbeat`.
The independent verifier remains the correctness authority; Goal/Todo
completion alone does not prove task success.

Offline tests from the repository root:

```sh
python3 -m pytest -q benchmark/deepswe-gptxhigh-v1-revised/tests/
```

These tests do not run models, Pier containers, or the full benchmark.

## Results

No benchmark results are published for v1-revised. The historical summary
remains only in the unchanged v1 archive. The current
[SWE Marathon correction](../swe-marathon/README.md) withdraws SSH Goal and
Codex CLI data and conclusions pending revalidation.
