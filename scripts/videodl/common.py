from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit


class DownloadError(Exception):
    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code, self.hint = code, hint

    def as_dict(self):
        return {"code": self.code, "message": str(self), "hint": self.hint}


def home_dir() -> Path:
    return (
        Path(
            os.environ.get(
                "VIDEO_DOWNLOADER_HOME",
                str(Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "video-downloader"),
            )
        )
        .expanduser()
        .resolve()
    )


def host_is(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for name, domains in {
        "douyin": ("douyin.com", "iesdouyin.com", "aweme.cn"),
        "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
        "youtube": ("youtube.com", "youtu.be"),
        "bilibili": ("bilibili.com", "b23.tv"),
    }.items():
        if any(host_is(host, domain) for domain in domains):
            return name
    return "generic"


def normalize_url(text: str) -> str:
    matches = re.findall(r"https?://[^\s<>\"\u3000]+", text.strip(), re.I)
    if len(matches) != 1:
        raise DownloadError("invalid_input", "每条输入必须包含一个 HTTP(S) 视频链接。")
    url = matches[0].rstrip("。！，、；：）》】")
    if text.strip() != matches[0]:
        url = url.rstrip("'.,!;)")
    try:
        parsed = urlsplit(url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.netloc.endswith(":"):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise DownloadError("invalid_input", "链接地址无效；认证请使用 Cookie 或请求头参数。") from None
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))


def content_id(url: str) -> str | None:
    p = platform(url)
    parts = urlsplit(url)
    pattern = (
        r"/(?:video|note)/(\d+)"
        if p == "douyin"
        else r"/(?:explore|discovery/item)/([a-fA-F0-9]+)"
        if p == "xiaohongshu"
        else None
    )
    match = re.search(pattern, parts.path) if pattern else None
    if match:
        return match[1]
    if p == "douyin":
        value = parse_qs(parts.query).get("modal_id", [None])[0]
        return value if value and value.isdigit() else None
    return None


def public_url(url: str) -> str:
    try:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.hostname or "", p.path, "[redacted]" if p.query else "", ""))
    except ValueError:
        return "[invalid URL]"


def redact(text: str, secrets=()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "[redacted]")
    text = re.sub(r"https?://[^\s\"<>]+", lambda m: public_url(m[0]), text)
    return re.sub(r"(?i)((?:cookie|authorization|token|password)\s*[:=]\s*)[^\n]+", r"\1[redacted]", text)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".vd-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def file_lock(path: Path, wait: float = 0):
    """OS lock: released even after a crash; the small lock file stays in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        deadline = time.monotonic() + wait
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    if not stream.read(1):
                        stream.write(b"0")
                        stream.flush()
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise DownloadError(
                        "busy", "另一个下载进程正在使用同一输出目录或安装环境。", "等待当前任务结束后重试。"
                    ) from None
                time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def output_lock(directory: Path) -> Path:
    digest = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()
    return home_dir() / "locks" / (digest + ".lock")
