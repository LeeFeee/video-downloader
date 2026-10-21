from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from collections import deque

from .common import DownloadError


def run_lines(command, *, timeout, on_line, env=None):
    """Stream output without unbounded log buffers; terminate descendants on POSIX."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        start_new_session=os.name != "nt",
    )
    messages = queue.Queue(maxsize=128)
    stopped = threading.Event()

    def read():
        try:
            for line in process.stdout:
                while not stopped.is_set():
                    try:
                        messages.put(line.rstrip("\n"), timeout=0.1)
                        break
                    except queue.Full:
                        pass
        finally:
            process.stdout.close()
            while not stopped.is_set():
                try:
                    messages.put(None, timeout=0.1)
                    break
                except queue.Full:
                    pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    tail = deque(maxlen=40)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DownloadError(
                    "timeout", f"任务超过 {timeout:g} 秒，已保留可续传的临时文件。", "重试相同命令，或提高 --timeout。"
                )
            try:
                line = messages.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if line is None:
                break
            tail.append(line[-4000:])
            on_line(line)
        try:
            return process.wait(timeout=max(0.1, deadline - time.monotonic())), "\n".join(tail)
        except subprocess.TimeoutExpired as exc:
            raise DownloadError("timeout", "下载进程超时，已保留续传文件。", "重试或提高 --timeout。") from exc
    finally:
        stopped.set()
        if process.poll() is None:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                # terminate() only stops the Python parent on Windows, not FFmpeg/Chromium.
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=5, check=False
                    )
                except (OSError, subprocess.TimeoutExpired):
                    process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
        reader.join(timeout=1)
