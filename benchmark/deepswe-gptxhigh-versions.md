# DeepSWE GPT xhigh Version Boundaries

The original v1 archive and subsequent execution fixes are separate packages.
No execution fix is applied to the original snapshot.

| Directory | Purpose | Results |
| --- | --- | --- |
| [deepswe-gptxhigh-v1](deepswe-gptxhigh-v1/README.md) | Original 14-file sanitized snapshot, unchanged contents and file modes | Original historical summary only |
| [deepswe-gptxhigh-v1-revised](deepswe-gptxhigh-v1-revised/README.md) | Later execution fixes and offline regression tests | No benchmark results; not rerun or validated end to end |

## Original Snapshot Provenance

The original directory is copied from commit
`98c262a8487ff5688d38091f603a87f7e2a78c64`, subtree
`benchmark/deepswe-five-arm/`. Only the containing directory name changes.
The complete original tree object is
`1bc5d2b3b74761a97d34ba3f3612e977fd610340`.

Verify the snapshot in Git:

```sh
test "$(git rev-parse HEAD:benchmark/deepswe-gptxhigh-v1)" = \
  1bc5d2b3b74761a97d34ba3f3612e977fd610340
```

This verifies file names, executable modes, and exact contents, including the
original README. Its references to "this branch's base" and an in-progress v2
are historical text, not statements about the current PR or project status.
The evaluated LoopX revision recorded by v1 is `2cef51d`.

The archive preserves known defects: absent plain/Claude support files, legacy
entry points, hard-coded environment dependencies, shared profile initialization
races, stale task admission, and launcher/retry failure handling. Preservation
does not make these behaviors correct or the package independently runnable.
Do not patch the original to resolve review findings; apply execution changes
to the revised directory and update its own tests.

## Revised Package Provenance

The revised code and tests come from commit
`a0787c77e91b2271d29ceaad22fcf6d91e645158` of the superseded PR #4466.
Only its README is rewritten here to identify the new directory and remove
historical score attribution. Its execution files and tests are unchanged.

The revised package adds the missing plain runner, removes unsupported legacy
adapters, fixes task admission and revision pinning, serializes profile setup,
propagates launcher failures, separates gateway ports, and changes retry and
invalid-delivery termination behavior. These are execution changes, not just
documentation edits. It remains distinct from any separate v2 benchmark.

## Evidence Limits

No benchmark was rerun for this separation. Offline tests of the revised
package cannot establish that historical v1 scores were produced by revised
code. Keep future runs, receipts, and scores labeled with their actual harness
version; do not mix output directories between these packages.

The [current SWE Marathon publication](swe-marathon/README.md) withdraws SSH Goal
and Codex CLI data and conclusions pending revalidation. The unchanged v1
README is retained as historical material, not as a renewed validated claim.

## 中文说明

`deepswe-gptxhigh-v1` 保留最初提交的 14 个文件，内容及权限完全不变，
包括原始 README；仅调整所在目录名。原始缺陷同样保留，不把后续修复混入历史快照。

`deepswe-gptxhigh-v1-revised` 单独保存后续执行逻辑修复和离线测试。
修复涉及准入、启动、端口、并发、重试和退出行为，可能影响运行结果。
该修订版没有重新跑 benchmark，也没有可归属给它的历史分数，不等同于 v2。
原始结果中的撤回状态及外部环境依赖仍然适用。
