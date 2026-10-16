import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ManagedProcess:
    owner: str
    process: subprocess.Popen[Any]


class ManagedProcessRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._processes: dict[int, ManagedProcess] = {}

    def register(self, owner: str, process: subprocess.Popen[Any]) -> subprocess.Popen[Any]:
        with self._lock:
            self._processes[id(process)] = ManagedProcess(owner, process)
        return process

    def unregister(self, process: subprocess.Popen[Any]) -> None:
        with self._lock:
            self._processes.pop(id(process), None)

    def stop_process(self, process: subprocess.Popen[Any], timeout_seconds: float = 3.0) -> None:
        self.unregister(process)
        if process.poll() is not None:
            process.wait()
            return

        timeout_seconds = max(0.1, timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        if os.name == 'nt':
            try:
                subprocess.run(
                    [
                        'taskkill',
                        '/PID',
                        str(process.pid),
                        '/T',
                        '/F',
                    ],
                    check=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=max(0.1, deadline - time.monotonic()),
                )
            except subprocess.TimeoutExpired:
                pass
        else:
            process.terminate()

        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    def stop_owner(self, owner_prefix: str, timeout_seconds: float = 3.0) -> None:
        with self._lock:
            processes = [
                item.process
                for item in self._processes.values()
                if item.owner.startswith(owner_prefix)
            ]
        for process in reversed(processes):
            self.stop_process(process, timeout_seconds)

    def stop_all(self, timeout_seconds: float = 3.0) -> None:
        with self._lock:
            processes = [item.process for item in self._processes.values()]
        for process in reversed(processes):
            self.stop_process(process, timeout_seconds)
