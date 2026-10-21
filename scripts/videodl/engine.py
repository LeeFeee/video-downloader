from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import runtime
from .common import DownloadError, platform, public_url, redact
from .process import run_lines

MARKER = "__VIDEO_DOWNLOADER_RESULT__"


def classify(message: str) -> DownloadError:
    lower = message.lower()
    rules = [
        (("drm", "protected content"), "drm", "此视频使用 DRM，普通下载链路无法处理。", "提供可直接播放下载的媒体源。"),
        (
            ("429", "too many requests", "rate limit"),
            "rate_limited",
            "平台限制了请求频率。",
            "稍后重试；不要连续重试或增加并发。",
        ),
        (
            ("sign in", "login", "log in", "cookies", "fresh cookies", "verify you", "captcha", "not a bot"),
            "authentication",
            "平台要求登录或验证。",
            "使用 --cookies、--cookies-from-browser，或 login 保存专用会话。",
        ),
        (
            ("geo restricted", "not available in your country", "geographic"),
            "geo_restricted",
            "当前网络地区无法访问此视频。",
            "检查视频在同一网络下是否可播放；可显式指定 --proxy。",
        ),
        (
            ("private video", "video unavailable", "video is unavailable", "removed", "not found", "404"),
            "unavailable",
            "视频不存在、已删除或当前账户不可访问。",
            "确认原始链接及账户访问权限。",
        ),
        (
            ("403", "forbidden"),
            "http_403",
            "媒体服务器拒绝了请求。",
            "检查登录状态、Referer 和代理；可更新解析器后重试。",
        ),
        (
            ("unsupported url",),
            "unsupported",
            "解析器未支持此链接。",
            "抖音/小红书可使用 --browser on；直链需为 HTTP(S) 媒体地址。",
        ),
        (
            ("requested format",),
            "format_unavailable",
            "没有满足要求的音视频格式。",
            "取消 --format/--max-height 限制，检查 FFmpeg。",
        ),
        (
            ("ffmpeg", "ffprobe"),
            "dependency",
            "音视频处理工具不可用或处理失败。",
            "运行 doctor，安装 FFmpeg/ffprobe 后重试。",
        ),
        (
            (
                "timed out",
                "timeout",
                "http error 500",
                "http error 502",
                "http error 503",
                "http error 504",
                "connection reset",
                "remote end closed",
            ),
            "network",
            "网络暂时不可用或服务器请求失败。",
            "检查网络或代理；重试会续传未完成文件。",
        ),
    ]
    for terms, code, text, hint in rules:
        if any((re.search(rf"(?<!\d){term}(?!\d)", lower) if term.isdigit() else term in lower) for term in terms):
            return DownloadError(code, text, hint)
    return DownloadError("extraction", "视频解析或下载失败。", "运行 update 后重试，参考已脱敏的 diagnostics。")


def verify_file(path: Path, output: Path, *, audio=False, require_audio=False) -> dict:
    path = path.resolve()
    if not path.is_relative_to(output.resolve()) or not path.is_file() or path.suffix in {".part", ".ytdl"}:
        raise DownloadError("invalid_output", "下载器未返回有效的最终媒体文件。")
    size = path.stat().st_size
    if size < 32:
        raise DownloadError("invalid_output", "下载文件为空或不完整。")
    probe = shutil.which("ffprobe")
    if probe:
        try:
            proc = subprocess.run(
                [probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            media = json.loads(proc.stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise DownloadError(
                "invalid_output", "媒体校验失败。", "检查文件和 ffprobe，重试前移走损坏的最终文件。"
            ) from exc
        types = {
            s.get("codec_type") for s in media.get("streams", []) if not s.get("disposition", {}).get("attached_pic")
        }
        wanted = "audio" if audio else "video"
        if proc.returncode or wanted not in types or (require_audio and "audio" not in types):
            raise DownloadError(
                "invalid_output", "文件缺少要求的媒体轨道或无法解码媒体头。", "移走损坏的最终文件后重试。"
            )
        return {
            "path": str(path),
            "bytes": size,
            "verification": "ffprobe",
            "streams": sorted(types),
            "duration": media.get("format", {}).get("duration"),
        }
    with path.open("rb") as stream:
        header = stream.read(512)
    valid = (
        header[4:8] == b"ftyp"
        or header.startswith((b"\x1aE\xdf\xa3", b"OggS", b"ID3", b"fLaC", b"FLV", b"RIFF"))
        or header[:1] == b"G"
        or (header[:1] == b"\xff" and len(header) > 1 and header[1] & 0xE0 == 0xE0)
    )
    if not valid:
        raise DownloadError("invalid_output", "下载结果不是可识别的媒体文件。", "安装 ffprobe 获取完整媒体轨道校验。")
    return {"path": str(path), "bytes": size, "verification": "header_only", "streams": []}


def build_command(python, url, args, *, cookies=None, info_file=None):
    cmd = [
        python,
        "-m",
        "yt_dlp",
        "--ignore-config",
        "--no-plugin-dirs",
        "--no-colors",
        "--newline",
        "--no-progress" if args.quiet else "--progress",
        "--progress-delta",
        "1",
        "--socket-timeout",
        str(args.socket_timeout),
        "--retries",
        str(args.retries),
        "--fragment-retries",
        str(args.retries),
        "--extractor-retries",
        "2",
        "--retry-sleep",
        "http:exp=1:8",
        "--retry-sleep",
        "fragment:exp=1:8",
        "--concurrent-fragments",
        str(args.fragments),
        "--abort-on-unavailable-fragments",
        "--continue",
        "--no-overwrites",
        "--no-post-overwrites",
        "--windows-filenames",
        "--trim-filenames",
        "180",
        "--cache-dir",
        str(runtime.home_dir() / "extractor-cache"),
        "--playlist-end",
        str(args.max_items if args.playlist else 1),
        "--yes-playlist" if args.playlist else "--no-playlist",
    ]
    js = runtime.js_runtime()
    if args.overwrite:
        cmd += ["--force-overwrites", "--post-overwrites"]
    if js:
        cmd += ["--js-runtimes", js]
    if cookies:
        cmd += ["--cookies", str(cookies)]
    elif args.cookies_from_browser:
        cmd += ["--cookies-from-browser", args.cookies_from_browser]
    if args.proxy is not None:
        cmd += ["--proxy", args.proxy]
    if args.referer:
        cmd += ["--referer", args.referer]
    for header in args.header:
        cmd += ["--add-headers", header]
    for value in args.extractor_args:
        cmd += ["--extractor-args", value]
    if args.format:
        selector = args.format
    elif args.audio:
        selector = "ba/b"
    else:
        height = f"[height<=?{args.max_height}]" if args.max_height else ""
        selector = f"bv*{height}+ba/b{height}" if shutil.which("ffmpeg") else f"b{height}[vcodec!=none][acodec!=none]"
    cmd += ["--format", selector]
    if args.inspect:
        cmd += ["--simulate", "--dump-json"]
    else:
        cmd += [
            "--no-simulate",
            "--print",
            f"after_move:{MARKER}%(.{{id,title,filepath,duration,extractor_key}})j",
            "--paths",
            str(args.output),
            "-o",
            "%(title).120B [%(extractor_key)s-%(id)s].%(ext)s",
        ]
        if args.audio:
            cmd += ["--extract-audio", "--audio-format", args.audio_format]
        elif args.container != "auto":
            cmd += ["--merge-output-format", args.container, "--remux-video", args.container]
        if args.subs:
            cmd += ["--write-subs", "--sub-langs", args.subs]
    if info_file:
        cmd += ["--check-formats", "--load-info-json", str(info_file)]
    else:
        cmd += ["--", url]
    return cmd


def metadata(info):
    keys = ("id", "title", "duration", "extractor_key", "uploader", "is_live", "availability")
    result = {k: info[k] for k in keys if info.get(k) is not None}
    result["formats"] = [
        {
            k: f[k]
            for k in ("format_id", "ext", "width", "height", "vcodec", "acodec", "filesize", "format_note")
            if f.get(k) is not None
        }
        for f in info.get("formats", [])
    ]
    return result


def attempt(python, url, args, *, cookies=None, info_file=None, timeout=None):
    files, items, diagnostics = [], [], []
    secrets = [args.proxy, *args.header, *args.extractor_args]

    def handle(line):
        if line.startswith(MARKER):
            try:
                info = json.loads(line[len(MARKER) :])
                verified = verify_file(
                    Path(info["filepath"]), args.output, audio=args.audio, require_audio=args.require_audio
                )
                verified.update({k: info.get(k) for k in ("id", "title", "extractor_key")})
                files.append(verified)
            except (KeyError, TypeError, ValueError) as exc:
                raise DownloadError("invalid_output", "下载器返回了不完整的文件记录。") from exc
        elif args.inspect and line.startswith("{"):
            try:
                items.append(metadata(json.loads(line)))
            except (TypeError, ValueError):
                diagnostics.append("无法解析元数据记录。")
        else:
            safe = redact(line, secrets)
            diagnostics.append(safe[-2000:])
            del diagnostics[:-30]
            if not args.quiet:
                print(safe, file=sys.stderr)

    result = {
        "source": public_url(url),
        "success": False,
        "files": files,
        "items": items,
        "engine": "browser+yt-dlp" if info_file else "yt-dlp",
    }
    try:
        code, tail = run_lines(
            build_command(python, url, args, cookies=cookies, info_file=info_file),
            timeout=timeout or args.timeout,
            on_line=handle,
        )
        if code:
            raise classify(tail)
        if not (items if args.inspect else files):
            raise DownloadError(
                "empty_result", "任务未生成任何媒体结果。", "检查链接是否指向单个视频；合集需要 --playlist。"
            )
        result["success"] = True
    except DownloadError as exc:
        result["error"] = exc.as_dict()
    result["diagnostics"] = diagnostics
    return result


def with_retries(python, url, args, **kwargs):
    deadline = time.monotonic() + args.timeout
    for retry in range(args.retries + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        result = attempt(python, url, args, timeout=remaining, **kwargs)
        if result["success"] or result["files"] or result.get("error", {}).get("code") != "network":
            return result
        delay = min(2**retry, 8)
        if retry == args.retries or time.monotonic() + delay >= deadline:
            break
        if not args.quiet:
            print(f"临时网络错误，{delay} 秒后重试（{retry + 1}/{args.retries}）…", file=sys.stderr)
        time.sleep(delay)
    return result


def download(url, args):
    python = runtime.ensure(auto_install=not args.no_install)
    if (args.audio or args.container != "auto") and not args.inspect and not shutil.which("ffmpeg"):
        raise DownloadError(
            "dependency",
            "此操作需要 FFmpeg。",
            "macOS: brew install ffmpeg；Linux: apt install ffmpeg；Windows: winget install Gyan.FFmpeg。",
        )
    saved = runtime.home_dir() / "cookies" / f"{platform(url)}.txt"
    source_cookie = (
        Path(args.cookies).expanduser()
        if args.cookies
        else (saved if saved.is_file() and not args.cookies_from_browser else None)
    )
    if source_cookie and not source_cookie.is_file():
        raise DownloadError("invalid_input", "指定的 Cookie 文件不存在。")
    with tempfile.TemporaryDirectory(prefix="videodl-") as tmp:
        tmp = Path(tmp)
        cookies = None
        if source_cookie:
            # yt-dlp rewrites its jar on exit; never mutate the user's original.
            from .cookies import load_cookies

            load_cookies(source_cookie)
            cookies = tmp / "session.txt"
            shutil.copyfile(source_cookie, cookies)
            cookies.chmod(0o600)
        first = with_retries(python, url, args, cookies=cookies)
        if first["success"] or args.browser == "off" or first["files"]:
            return first
        if platform(url) not in {"douyin", "xiaohongshu"}:
            return first
        if first["error"]["code"] not in {"authentication", "unsupported", "http_403", "extraction", "empty_result"}:
            return first
        browser_python = runtime.choose_python(browser=True)
        if not browser_python and args.browser == "auto":
            first["error"]["hint"] += " 可运行 setup --browser 后重试，或指定 --browser on。"
            return first
        if not browser_python:
            browser_python = runtime.ensure(browser=True, auto_install=not args.no_install)
        from .browser import capture_subprocess

        try:
            try:
                info, browser_cookies = capture_subprocess(browser_python, url, args, cookies, tmp)
            except DownloadError as exc:
                if exc.code != "browser_missing" or args.browser != "on" or args.no_install:
                    raise
                browser_python = runtime.install(browser=True)
                info, browser_cookies = capture_subprocess(browser_python, url, args, cookies, tmp)
            result = with_retries(python, url, args, cookies=browser_cookies, info_file=info)
            result["fallback_from"] = first["error"]["code"]
            return result
        except DownloadError as exc:
            first["browser_error"] = exc.as_dict()
            return first
