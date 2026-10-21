from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

from .common import DownloadError, file_lock, home_dir

MIN_YTDLP = (2026, 3, 17)
BASE = ["yt-dlp[default]>=2026.3.17"]


def version_tuple(value):
    import re

    return tuple(int(n) for n in re.findall(r"\d+", value)[:3])


def runtime_python() -> Path:
    return (
        home_dir()
        / f"runtime-{sys.version_info.major}.{sys.version_info.minor}"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )


def packages(python: str) -> dict:
    script = "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name'].lower().replace('_','-'): d.version for d in m.distributions()}))"
    try:
        result = subprocess.run([python, "-c", script], capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def usable(found, browser=False):
    return (
        version_tuple(found.get("yt-dlp", "0")) >= MIN_YTDLP
        and "yt-dlp-ejs" in found
        and (not browser or "playwright" in found)
    )


def choose_python(browser=False) -> str | None:
    for python in dict.fromkeys((str(runtime_python()), sys.executable)):
        if Path(python).is_file() and usable(packages(python), browser):
            return python
    return None


def install(*, browser=False, update=False, channel="stable") -> str:
    target = runtime_python()
    with file_lock(home_dir() / "install.lock", wait=180):
        if not target.exists():
            try:
                venv.EnvBuilder(with_pip=True).create(target.parent.parent)
            except (OSError, subprocess.SubprocessError) as exc:
                raise DownloadError(
                    "dependency",
                    "无法创建独立 Python 环境。",
                    "需要 Python 3.10+ 与 venv/ensurepip；Linux 可安装 python3-venv。",
                ) from exc
        command = [str(target), "-m", "pip", "install", "--disable-pip-version-check"]
        if update:
            command += ["--upgrade"]
        if channel == "nightly":
            command += ["--pre"]
        command += BASE + (["playwright>=1.49"] if browser else [])
        try:
            subprocess.run(command, check=True, stdout=sys.stderr, stderr=sys.stderr, timeout=600)
            if browser:
                subprocess.run(
                    [str(target), "-m", "playwright", "install", "chromium"],
                    check=True,
                    stdout=sys.stderr,
                    stderr=sys.stderr,
                    timeout=600,
                    env={**os.environ, "PLAYWRIGHT_SKIP_BROWSER_GC": "1"},
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DownloadError(
                "dependency", "依赖安装失败。", "检查网络/Python 环境，重新运行 setup；安装失败不会修改系统 Python。"
            ) from exc
    return str(target)


def ensure(*, browser=False, auto_install=True) -> str:
    python = choose_python(browser)
    if python:
        return python
    if not auto_install:
        raise DownloadError(
            "dependency", "缺少下载依赖。", "运行 python3 scripts/download.py setup；浏览器辅助模式加 --browser。"
        )
    print("正在准备独立下载环境…", file=sys.stderr)
    return install(browser=browser)


def js_runtime():
    for name, minimum in (("deno", (2, 3, 0)), ("node", (22, 0, 0))):
        executable = shutil.which(name)
        if executable:
            try:
                p = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5)
                if p.returncode == 0 and version_tuple(p.stdout.splitlines()[0]) >= minimum:
                    return f"{name}:{executable}"
            except (OSError, IndexError, subprocess.TimeoutExpired):
                pass
    return None


def doctor():
    python = choose_python()
    found = packages(python) if python else {}
    return {
        "python": sys.version.split()[0],
        "interpreter": python,
        "yt_dlp": found.get("yt-dlp"),
        "yt_dlp_ejs": found.get("yt-dlp-ejs"),
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "js_runtime": js_runtime(),
        "playwright": found.get("playwright"),
        "home": str(home_dir()),
        "ready": bool(python),
        "hints": [
            "setup 安装/修复独立环境；update 更新解析器；setup --browser 安装浏览器辅助组件。",
            "FFmpeg/ffprobe 用于合并、音频提取和媒体校验；Deno 2.3+ 或 Node 22+ 用于 YouTube。",
        ],
    }
