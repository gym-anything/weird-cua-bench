#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Callable


def request_json(
    path: str,
    *,
    port: int = 8787,
    payload: dict | None = None,
    timeout: float = 2.0,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"content-type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise RuntimeError(f"{path} returned a non-object JSON value")
    return result


def send_command(
    command: str,
    *,
    port: int = 8787,
    milliseconds: float | None = None,
    start_delay_ms: float = 0,
) -> dict:
    payload: dict[str, object] = {"command": command}
    if command == "run_for":
        if milliseconds is None:
            raise ValueError("run_for requires milliseconds")
        payload.update({"milliseconds": milliseconds, "start_delay_ms": start_delay_ms})
    return request_json("/time-control", port=port, payload=payload)


def get_status(*, port: int = 8787) -> dict:
    return request_json("/time-control/status", port=port)


def wait_for_status(
    predicate: Callable[[dict], bool],
    *,
    port: int = 8787,
    timeout: float = 10.0,
    interval: float = 0.02,
) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        try:
            last = get_status(port=port)
            if predicate(last):
                return last
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(interval)
    raise TimeoutError(f"time controller did not reach the requested state; last status: {last}")


def wait_until_ready(*, port: int = 8787, timeout: float = 30.0) -> dict:
    return wait_for_status(lambda item: item.get("ready") is True, port=port, timeout=timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control the Weird CUA Bench browser clock.")
    parser.add_argument(
        "command",
        choices=("status", "wait-ready", "pause", "settle-pause", "resume", "run-for"),
    )
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--milliseconds", type=float)
    parser.add_argument("--start-delay-ms", type=float, default=0)
    parser.add_argument("--timeout", type=float, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "status":
        result = get_status(port=args.port)
    elif args.command == "wait-ready":
        result = wait_until_ready(port=args.port, timeout=args.timeout)
    else:
        command = args.command.replace("-", "_")
        accepted = send_command(
            command,
            port=args.port,
            milliseconds=args.milliseconds,
            start_delay_ms=args.start_delay_ms,
        )
        sequence = int(accepted["sequence"])
        if command == "run_for":
            result = wait_for_status(
                lambda item: int(item.get("sequence") or -1) == sequence
                and item.get("phase") == "completed",
                port=args.port,
                timeout=args.timeout + float(args.milliseconds or 0) / 1000,
            )
        else:
            expected_state = "paused" if command in {"pause", "settle_pause"} else "running"
            result = wait_for_status(
                lambda item: int(item.get("sequence") or -1) == sequence
                and item.get("state") == expected_state,
                port=args.port,
                timeout=args.timeout,
            )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
