#!/usr/bin/env python3
"""Run one Codex app-server turn without attaching a Goal.

This is the wen-aligned plain control: the transport and permissions match the
Goal/LoopX arms, but no ``thread/goal/set`` call is made and no LoopX command is
invoked. It accepts the same CLI shape as the native Goal runner because
GoalCodex owns the common Pier upload/setup path.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from native_codex_goal import (
    NativeGoalConfig,
    NativeGoalProtocolError,
    NativeGoalTurn,
    StdioNativeGoalTransport,
    _nested,
    compact_native_goal_receipt,
    wait_native_goal_turn,
)


def start_turn_without_goal(
    transport: StdioNativeGoalTransport, config: NativeGoalConfig, *, execute: bool = True
) -> NativeGoalTurn:
    transport.request(
        "initialize",
        {
            "clientInfo": {
                "name": "deepswe_plain_appserver",
                "title": "DeepSWE plain (app-server, no Goal)",
                "version": "0.1.0",
            },
            "capabilities": {"experimentalApi": True},
        },
    )
    transport.notify("initialized", {})
    thread_result = transport.request(
        "thread/start",
        {
            "cwd": config.cwd,
            "sandbox": config.sandbox,
            "approvalPolicy": config.approval_policy,
            **({"model": config.model} if config.model else {}),
        },
    )
    thread = _nested(thread_result, "thread")
    thread_id = str(thread.get("id") or thread_result.get("threadId") or "")
    if not thread_id:
        raise NativeGoalProtocolError("thread_start_id_missing")

    turn = NativeGoalTurn(
        thread_id=thread_id,
        turn_id="",
        response_turn_id="",
        goal_status="none",
        objective_sha256="",
        objective_chars=0,
        task_instruction_sha256="",
        task_instruction_chars=len(config.task_instruction),
        token_budget_present=False,
        methods=["initialize", "initialized", "thread/start"],
    )
    if not execute:
        return turn
    turn_result = transport.request(
        "turn/start",
        {
            "threadId": thread_id,
            "input": [{"type": "text", "text": config.task_instruction}],
            "cwd": config.cwd,
            "approvalPolicy": config.approval_policy,
            **({"model": config.model} if config.model else {}),
            **({"effort": config.effort} if config.effort else {}),
        },
    )
    turn.methods.append("turn/start")
    response_turn = _nested(turn_result, "turn")
    turn_id = str(response_turn.get("id") or turn_result.get("turnId") or "")
    if not turn_id:
        raise NativeGoalProtocolError("turn_start_id_missing")
    turn.turn_id = turn_id
    turn.response_turn_id = turn_id
    turn.turn_status = str(response_turn.get("status") or "accepted")
    return turn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--objective-file", required=True)
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--token-budget", type=int)
    parser.add_argument("--response-timeout-seconds", type=float, default=180)
    parser.add_argument("--goal-timeout-seconds", type=float, default=3600)
    parser.add_argument("--sandbox", default="danger-full-access")
    parser.add_argument("--required-skill-ids", default="")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    config = NativeGoalConfig(
        cwd=args.cwd,
        objective="No Goal is attached in the plain control arm.",
        task_instruction=Path(args.task_file).read_text(encoding="utf-8").strip(),
        model=args.model,
        effort=args.effort,
        token_budget=None,
        approval_policy="never",
        sandbox=args.sandbox,
    )
    command = [
        args.codex_bin,
        "app-server",
        "--listen",
        "stdio://",
        "--enable",
        "goals",
        "--enable",
        "unified_exec",
    ]
    transport = StdioNativeGoalTransport.spawn(
        command,
        cwd=args.cwd,
        env=os.environ.copy(),
        response_timeout_sec=args.response_timeout_seconds,
        stderr=None,
    )
    turn = None
    try:
        turn = start_turn_without_goal(transport, config, execute=not args.preflight_only)
        try:
            if not args.preflight_only:
                wait_native_goal_turn(
                    transport, turn, timeout_sec=args.goal_timeout_seconds
                )
        except NativeGoalProtocolError as exc:
            if str(exc) != "goal_turn_timeout":
                raise
        receipt = compact_native_goal_receipt(turn)
        receipt["execution_mode"] = (
            "plain_appserver_preflight" if args.preflight_only else "plain_appserver_single_turn"
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if args.preflight_only or turn.turn_status == "completed" else 1
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
