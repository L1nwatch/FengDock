"""Run FengDock, TriggerToDo, and codex proxy backends in one container."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def _spawn() -> list[subprocess.Popen[bytes]]:
    fengdock = subprocess.Popen(
        [
            "/app/.venv/bin/uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd="/app",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = "/app/vendor/TriggerToDo"
    triggertodo = subprocess.Popen(
        [
            "/app/vendor/TriggerToDo/.venv/bin/uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
        ],
        cwd="/app/vendor/TriggerToDo",
        env=env,
    )

    codex_proxy = subprocess.Popen(
        [
            "/app/.venv/bin/uvicorn",
            "codex_proxy_with_interception:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8002",
            "--app-dir",
            "/app",
        ],
        cwd="/app",
    )
    fire_env = os.environ.copy()
    fire_env["PYTHONPATH"] = "/app/vendor/fire"
    fire_app = subprocess.Popen(
        [
            "/app/.venv/bin/uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8003",
        ],
        cwd="/app/vendor/fire",
        env=fire_env,
    )
    return [fengdock, triggertodo, codex_proxy, fire_app]


def _terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    deadline = time.time() + 10
    while time.time() < deadline:
        if all(proc.poll() is not None for proc in processes):
            return
        time.sleep(0.2)
    for proc in processes:
        if proc.poll() is None:
            proc.kill()


def main() -> int:
    processes = _spawn()
    stopping = False

    def on_signal(_signum: int, _frame: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        _terminate(processes)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    while True:
        exit_codes = [proc.poll() for proc in processes]
        if any(code is not None for code in exit_codes):
            _terminate(processes)
            non_zero = [code for code in (proc.poll() for proc in processes) if code and code != 0]
            return non_zero[0] if non_zero else 0
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
