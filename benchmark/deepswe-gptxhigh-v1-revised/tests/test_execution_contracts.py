"""Offline regression tests for experiment admission and launcher failures."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def admission(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return load_module("study_admission", ROOT / "preflight_loopx_rerun.py")


@pytest.mark.parametrize("contents,count", [("", 59), ("a\na\n", 2), ("../a\n", 1), ("a\n\n", 2), ("a\n", 59)])
def test_reject_invalid_task_lists(admission, tmp_path, contents, count):
    manifest = tmp_path / "tasks.txt"
    manifest.write_text(contents)
    with pytest.raises(ValueError):
        admission.load_task_list(manifest, count)


def test_manifest_covers_actual_selected_tasks(admission, tmp_path):
    tasks = tuple(f"task-{i}" for i in range(59))
    for task in tasks:
        directory = tmp_path / task
        directory.mkdir()
        (directory / "task.toml").write_text(
            '[metadata]\nbase_commit_hash = "abcdef1"\n[agent]\ntimeout_sec = 6000\n'
        )
    digest, timeout, missing = admission.task_manifest(tmp_path, tasks)
    assert timeout == 6000 and not missing
    assert digest != admission.task_manifest(tmp_path, tasks[:54])[0]
    (tmp_path / tasks[-1] / "task.toml").write_text("invalid toml = [")
    assert admission.task_manifest(tmp_path, tasks)[2] == [tasks[-1]]


def test_revision_cannot_be_overridden(monkeypatch, admission):
    monkeypatch.setenv("MR_EXPECTED_LOOPX_REVISION", "f" * 40)
    reloaded = load_module("study_pinned_admission", ROOT / "preflight_loopx_rerun.py")
    assert reloaded.EXPECTED_LOOPX_REVISION == "2cef51d08b2a0103f4ba026bf47fd70dc8acee30"


@pytest.fixture
def launcher(tmp_path):
    for name in (
        "run_five_arms_remaining59_20260910.sh", "run_loopx_rerun_54_20260908.sh",
        "preflight_loopx_rerun.py", "workspace_delivery.py",
    ):
        shutil.copy2(ROOT / name, tmp_path / name)
    (tmp_path / "remaining59.txt").write_text("".join(f"task-{i}\n" for i in range(59)))
    (tmp_path / "overlay.yaml").write_text("services: {}\n")
    subprocess.run(["git", "init", "-q", str(tmp_path / "repo")], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path / "repo"), "-c", "user.name=Test", "-c",
         "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "base"],
        check=True,
    )
    python = tmp_path / "python"
    python.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "if sys.argv[1].endswith('preflight_loopx_rerun.py'):\n"
        "    args = sys.argv[2:]\n"
        "    arm = args[args.index('--arm') + 1]\n"
        "    tasks = pathlib.Path(args[args.index('--task-list') + 1]).read_text().splitlines()\n"
        "    assert len(tasks) == int(args[args.index('--expected-task-count') + 1])\n"
        "    with open(os.environ['ADMISSION_LOG'], 'a') as log:\n"
        "        log.write(json.dumps({'arm': arm, 'tasks': tasks}) + '\\n')\n"
        "    sys.exit(7 if os.environ.get('FAIL_ADMISSION') == arm else 0)\n"
        "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
    )
    python.chmod(0o755)
    runner = tmp_path / "run.sh"
    runner.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s %s %s\\n" "$MR_CODEX_ARM" "$MR_GATEWAY_PORT" "$MR_API_BASE" >> "$LAUNCH_LOG"\n'
        '[[ "$MR_CODEX_ARM" != "${FAIL_ARM:-}" ]]\n'
    )
    runner.chmod(0o755)
    env = {
        **os.environ, "MR_PYTHON": str(python), "MR_LOOPX_ROOT": str(tmp_path / "repo"),
        "MR_MODELONLY_COMPOSE": str(tmp_path / "overlay.yaml"),
        "LAUNCH_LOG": str(tmp_path / "launched"), "ADMISSION_LOG": str(tmp_path / "admitted"),
    }
    for key in ("MR_TASK_LIST", "FAIL_ARM", "FAIL_ADMISSION"):
        env.pop(key, None)
    return tmp_path, env


def run_launcher(launcher, name="run_five_arms_remaining59_20260910.sh", *args):
    directory, env = launcher
    return subprocess.run(["bash", str(directory / name), *args], env=env, capture_output=True, text=True, timeout=20)


@pytest.mark.parametrize("contents", [None, "", "task-0\n" * 59])
def test_no_launch_with_missing_empty_or_duplicate_tasks(launcher, contents):
    directory, _ = launcher
    tasks = directory / "remaining59.txt"
    tasks.unlink() if contents is None else tasks.write_text(contents)
    assert run_launcher(launcher).returncode != 0
    assert not (directory / "launched").exists()


def test_admission_failure_stops_all_arms(launcher):
    directory, env = launcher
    env["FAIL_ADMISSION"] = "codex-cli"
    assert run_launcher(launcher).returncode != 0
    assert not (directory / "launched").exists()


@pytest.mark.parametrize("failed_arm", ["", "plain", "loopx-native-heartbeat"])
def test_waits_for_each_arm_and_uses_selected_tasks_and_ports(launcher, failed_arm):
    directory, env = launcher
    env["FAIL_ARM"] = failed_arm
    result = run_launcher(launcher)
    assert (result.returncode == 0) == (not failed_arm), result.stderr
    receipts = [json.loads(line) for line in (directory / "admitted").read_text().splitlines()]
    assert len(receipts) == 3
    assert all(row["tasks"] == [f"task-{i}" for i in range(59)] for row in receipts)
    launches = (directory / "launched").read_text().splitlines()
    assert len(launches) == 5
    assert "plain 4394 http://127.0.0.1:4394/v1" in launches
    assert "goal 4393 http://127.0.0.1:4393/v1" in launches
    assert ("all arms finished" in result.stdout) == (not failed_arm)


def test_missing_54_subset_modules_fail_before_launch(launcher):
    directory, _ = launcher
    result = run_launcher(launcher, "run_loopx_rerun_54_20260908.sh")
    assert result.returncode != 0
    assert not (directory / "launched").exists()


@pytest.mark.parametrize("selected", [("task-4", "task-8"), ("task-4", "task-4"), ("outside",)])
def test_54_launcher_admits_exact_selection(launcher, selected):
    directory, env = launcher
    (directory / "goal30_subset.py").write_text(f"SUBSET = {[f'task-{i}' for i in range(30)]!r}\n")
    (directory / "hard24_subset.py").write_text(f"HARD_SUBSET = {[f'task-{i}' for i in range(30, 54)]!r}\n")
    (directory / "remaining4_subset.py").write_text("REMAINING_SUBSET = []\n")
    for command, code in (("ss", 0), ("pgrep", 1)):
        executable = directory / command
        executable.write_text(f"#!/bin/sh\nexit {code}\n")
        executable.chmod(0o755)
    env["PATH"] = str(directory) + os.pathsep + env["PATH"]
    result = run_launcher(launcher, "run_loopx_rerun_54_20260908.sh", "heartbeat", *selected)
    if selected == ("task-4", "task-8"):
        assert result.returncode == 0, result.stderr
        receipts = [json.loads(line) for line in (directory / "admitted").read_text().splitlines()]
        assert receipts == [{"arm": "heartbeat", "tasks": list(selected)}]
    else:
        assert result.returncode != 0
        assert not (directory / "launched").exists()


def test_profile_initialization_is_serialized(monkeypatch, tmp_path):
    goal = ModuleType("goal_codex")
    goal.GoalCodex = object
    goal._CODEX_EXEC_MARKER = "codex exec "
    goal._REMOTE_DIR = "/tmp/test-goal"
    monkeypatch.setitem(sys.modules, "goal_codex", goal)
    api = ModuleType("loopx.capabilities.benchmark_toolkit.native_codex_profile")
    installs = []

    def install(source, target):
        installs.append(target)
        target.mkdir()
        (target / "partial").touch()
        time.sleep(0.05)
        (target / "ready").touch()
        return {"ready": True}

    def inspect(target, **kwargs):
        assert (target / "ready").is_file(), "observed partially installed profile"
        return {"ready": True}

    api.install_native_codex_profile = install
    api.inspect_native_codex_profile = inspect
    api.compact_native_codex_profile_receipt = lambda value: value
    monkeypatch.setitem(sys.modules, api.__name__, api)
    native = load_module("study_native_profile", ROOT / "loopx_native_codex.py")
    barrier = threading.Barrier(2)

    def build():
        barrier.wait()
        return native.build_host_profile(str(tmp_path), str(tmp_path / "profile"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: build(), range(2)))
    assert results == [{"ready": True}, {"ready": True}]
    assert len(installs) == 1


@pytest.mark.parametrize("execute", [False, True])
def test_plain_transport_never_attaches_goal(monkeypatch, execute):
    native = load_module("native_codex_goal", ROOT.parents[1] / "loopx/capabilities/benchmark_toolkit/native_codex_goal.py")
    monkeypatch.setitem(sys.modules, "native_codex_goal", native)
    plain = load_module("study_plain", ROOT / "plain_appserver_runner.py")

    class Transport:
        def __init__(self):
            self.calls = []

        def request(self, method, payload):
            self.calls.append((method, payload))
            return {"thread": {"id": "thread"}, "turn": {"id": "turn"}}

        def notify(self, method, payload):
            self.calls.append((method, payload))

    transport = Transport()
    config = native.NativeGoalConfig(cwd="/tmp", objective="unused", task_instruction="task", effort="xhigh")
    plain.start_turn_without_goal(transport, config, execute=execute)
    methods = [method for method, _ in transport.calls]
    assert methods == ["initialize", "initialized", "thread/start"] + (["turn/start"] if execute else [])
    if execute:
        assert transport.calls[-1][1]["effort"] == "xhigh"


@pytest.mark.parametrize("key,value", [("MR_CLAUDE_ARM", "loopx"), ("MR_CODEX_ARM", "loopx")])
def test_unsupported_legacy_arms_fail_before_importing_pier(monkeypatch, key, value):
    module = load_module("study_pier", ROOT / "pier_cn.py")
    monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit):
        (module.patch_claude_arm if key == "MR_CLAUDE_ARM" else module.patch_goal_mode)()


def test_terminal_todo_without_delivery_stops_immediately(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    runner = load_module("study_cli_runner", ROOT / "loopx_codex_cli_runner.py")
    claims = []
    monkeypatch.setattr(runner, "head_sha", lambda _: "base")
    monkeypatch.setattr(runner, "normalize_delivery", lambda *_: {"treatment_valid": False})
    monkeypatch.setattr(runner, "write_receipt", lambda *_: None)

    def claim(*args):
        claims.append(True)
        return {"terminal": True, "ok": True}

    monkeypatch.setattr(runner, "_claim_primary_p0", claim)
    result, code = runner.run(SimpleNamespace(
        cwd="/tmp", goal_timeout_seconds=60, preflight_only=False, max_segments=5,
        model="test", effort="xhigh",
    ))
    assert code != 0 and result["treatment_valid"] is False
    assert result["segments"][0]["status"] == "terminal_todo_without_valid_delivery"
    assert len(claims) == 1


@pytest.mark.parametrize("error,retryable", [
    ({"status": 429, "message": "busy"}, True),
    ({"status": 503, "message": "temporarily unavailable"}, True),
    ({"status": 401, "message": "server error timeout"}, False),
    ({"code": "insufficient_quota", "status": 429}, False),
    ({"codexErrorInfo": {"httpConnectionFailed": {"httpStatusCode": 403}}}, False),
    ({"code": "request_timeout"}, True),
    ("unknown timeout text", False),
])
def test_retry_classification_uses_structured_error(monkeypatch, error, retryable):
    monkeypatch.syspath_prepend(str(ROOT))
    native = load_module("native_codex_goal", ROOT.parents[1] / "loopx/capabilities/benchmark_toolkit/native_codex_goal.py")
    monkeypatch.setitem(sys.modules, "native_codex_goal", native)
    runner = load_module("study_native_runner", ROOT / "loopx_wen_native_runner.py")
    event = {"method": "turn/completed", "params": {"turn": {"error": error}}}
    assert runner._terminal_error(event).retryable is retryable


def test_unmatched_install_step_fails_closed(monkeypatch):
    pier = load_module("study_mirrors", ROOT / "pier_cn.py")

    class Agent:
        def install_spec(self):
            return SimpleNamespace(steps=[SimpleNamespace(run="unknown installer", env={})])

    monkeypatch.setattr(pier, "HARNESSES", (("fake", "Agent"),))
    monkeypatch.setattr(pier.importlib, "import_module", lambda _: SimpleNamespace(Agent=Agent))
    pier.patch_harnesses()
    with pytest.raises(RuntimeError, match="refusing an unpatched harness"):
        Agent().install_spec()


def test_external_network_overlay_is_required_and_used(monkeypatch, tmp_path):
    pier = load_module("study_network", ROOT / "pier_cn.py")

    class Docker:
        environment_dir = tmp_path / "environment"
        _docker_compose_paths = property(lambda self: [])

        def agent_process_env(self, env):
            return env

    module = ModuleType("pier.environments.docker.docker")
    module.DockerEnvironment = Docker
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv("MR_MODELONLY_NET", "1")
    monkeypatch.delenv("MR_LOCAL_AGENT_BASE_IMAGE", raising=False)
    monkeypatch.delenv("MR_MODELONLY_COMPOSE", raising=False)
    with pytest.raises(SystemExit, match="MR_MODELONLY_COMPOSE"):
        pier.patch_modelonly_network()
    overlay = tmp_path / "overlay.yaml"
    monkeypatch.setenv("MR_MODELONLY_COMPOSE", str(overlay))
    with pytest.raises(SystemExit, match="missing model-only"):
        pier.patch_modelonly_network()
    overlay.write_text("services: {}\n")
    pier.patch_modelonly_network()
    assert Docker()._docker_compose_paths == [overlay]
    verifier = Docker()
    verifier.environment_dir = tmp_path / "tests"
    assert verifier._docker_compose_paths == []
