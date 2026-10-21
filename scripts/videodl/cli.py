from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, runtime
from .common import DownloadError, file_lock, normalize_url, output_lock, redact, write_json


def positive(value):
    try:
        result = int(value)
        if result <= 0:
            raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("必须是正整数") from None


def nonnegative(value):
    try:
        result = int(value)
        if result < 0:
            raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("必须是非负整数") from None


def parser():
    p = argparse.ArgumentParser(description="独立视频下载器：网站链接、分享文本、MP4/HLS/DASH 直链。")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("download", "inspect"):
        d = sub.add_parser(name, help="下载视频" if name == "download" else "只解析元数据和格式")
        d.add_argument("urls", nargs="*", help="一个或多个 URL，也可传入完整分享文本")
        d.add_argument("-o", "--output", type=Path, default=Path.home() / "Downloads" / "Videos")
        d.add_argument("--batch", type=Path, help="UTF-8 文件，一行一个链接/分享文本，# 为注释")
        d.add_argument("--audio", action="store_true")
        d.add_argument("--audio-format", choices=("mp3", "m4a", "opus", "flac", "wav", "best"), default="mp3")
        d.add_argument("--max-height", type=positive)
        d.add_argument("-f", "--format", help="yt-dlp 格式表达式，优先于 max-height")
        d.add_argument("--container", choices=("auto", "mp4", "mkv"), default="auto")
        d.add_argument("--require-audio", action="store_true", help="校验最终视频必须包含音轨（需要 ffprobe）")
        d.add_argument("--overwrite", action="store_true", help="显式覆盖同名文件，用于更换质量或重新下载损坏文件")
        auth = d.add_mutually_exclusive_group()
        auth.add_argument("--cookies", help="Netscape 格式 Cookie 文件")
        auth.add_argument("--cookies-from-browser", help="浏览器名[:配置目录]，如 chrome 或 firefox")
        d.add_argument("--proxy", help="显式代理；空字符串禁用代理")
        d.add_argument("--referer")
        d.add_argument("--header", action="append", default=[], help="Name: value，可重复")
        d.add_argument("--extractor-args", action="append", default=[], help="传给 yt-dlp 的解析器参数，可重复")
        d.add_argument("--subs", help="字幕语言，如 zh.*,en；仅下载已有字幕")
        d.add_argument("--playlist", action="store_true", help="显式允许合集，默认最多 20 条")
        d.add_argument("--max-items", type=positive, default=20)
        d.add_argument("--retries", type=nonnegative, default=3)
        d.add_argument("--fragments", type=positive, default=4)
        d.add_argument("--socket-timeout", type=positive, default=20)
        d.add_argument("--timeout", type=positive, default=1800, help="每条链接每个引擎的最长秒数")
        d.add_argument(
            "--browser",
            choices=("auto", "on", "off"),
            default="auto",
            help="抖音/小红书失败后的浏览器辅助；auto 只用已安装组件",
        )
        d.add_argument("--headed", action="store_true", help="显示辅助浏览器，供人工完成验证")
        d.add_argument("--browser-timeout", type=positive, default=45)
        d.add_argument("--no-install", action="store_true", help="依赖缺失时报错，不自动安装")
        d.add_argument("--json", action="store_true", help="stdout 仅输出一个结果 JSON；日志在 stderr")
        d.add_argument("--report", type=Path, help="另外保存 JSON 结果清单")
        d.add_argument("--quiet", action="store_true")
    d = sub.add_parser("doctor", help="只读环境诊断，不安装依赖")
    d.add_argument("--json", action="store_true")
    for name in ("setup", "update"):
        d = sub.add_parser(name, help="准备独立依赖环境" if name == "setup" else "更新独立环境中的解析器")
        d.add_argument("--browser", action="store_true")
        d.add_argument("--channel", choices=("stable", "nightly"), default="stable")
        d.add_argument("--json", action="store_true")
    d = sub.add_parser("login", help="打开专用浏览器会话，保存指定平台的 Cookie")
    d.add_argument("site", choices=("douyin", "xiaohongshu"))
    d.add_argument("--timeout", type=positive, default=300)
    d.add_argument("--no-install", action="store_true")
    d.add_argument("--json", action="store_true")
    return p


def legacy_args(argv):
    if not argv or argv[0] in {
        "download",
        "inspect",
        "doctor",
        "setup",
        "update",
        "login",
        "-h",
        "--help",
        "--version",
    }:
        return argv
    argv = list(argv)
    # v1 accepted URL [output_dir]. Keep it without confusing --audio with a path.
    if len(argv) > 1 and "http" in argv[0] and not argv[1].startswith("-") and "http" not in argv[1]:
        argv = [argv[0], "--output", argv[1], *argv[2:]]
    return ["download", *argv]


def emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
        return
    if "results" in result:
        for item in result["results"]:
            for media in item.get("files", []):
                print(f"已保存：{media['path']}（{media['bytes'] / 1024 / 1024:.2f} MB，{media['verification']}）")
            for info in item.get("items", []):
                print(json.dumps(info, ensure_ascii=False, indent=2))
            for key in ("error", "browser_error"):
                if item.get(key):
                    e = item[key]
                    print(f"失败 [{e['code']}]：{e['message']} {e['hint']}", file=sys.stderr)
        print(f"完成：{sum(x['success'] for x in result['results'])}/{len(result['results'])} 条链接成功。")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(legacy_args(argv))
    try:
        if sys.version_info < (3, 10):
            raise DownloadError("dependency", "需要 Python 3.10 或更新版本。")
        if args.command == "doctor":
            result = runtime.doctor()
            emit(result, args.json)
            return 0 if result["ready"] else 1
        if args.command in {"setup", "update"}:
            python = runtime.install(browser=args.browser, update=args.command == "update", channel=args.channel)
            emit({"success": True, "interpreter": python, "packages": runtime.packages(python)}, args.json)
            return 0
        if args.command == "login":
            from .browser import login_subprocess

            result = login_subprocess(args)
            emit(result, args.json)
            return 0
        inputs = list(args.urls)
        if args.batch:
            inputs.extend(
                line.strip()
                for line in args.batch.expanduser().read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        if not inputs:
            raise DownloadError("invalid_input", "请提供视频 URL 或 --batch 文件。")
        urls = list(dict.fromkeys(normalize_url(value) for value in inputs))
        args.inspect = args.command == "inspect"
        args.output = args.output.expanduser().resolve()
        if args.fragments > 16:
            raise DownloadError("invalid_input", "分片并发数不得超过 16。")
        if args.audio and args.require_audio:
            args.require_audio = False
        for header in args.header:
            if ":" not in header or "\n" in header or "\r" in header:
                raise DownloadError("invalid_input", "请求头格式必须是 Name: value，且不能包含换行。")
        if args.require_audio:
            import shutil

            if not shutil.which("ffprobe"):
                raise DownloadError("dependency", "--require-audio 需要 ffprobe。")
        from .engine import download

        results = []
        # Lock per output directory, so distinct URLs with identical IDs cannot race.
        with file_lock(output_lock(args.output)):
            if not args.inspect:
                args.output.mkdir(parents=True, exist_ok=True)
            for url in urls:
                try:
                    results.append(download(url, args))
                except DownloadError as exc:
                    from .common import public_url

                    results.append({"source": public_url(url), "success": False, "files": [], "error": exc.as_dict()})
        result = {"version": __version__, "success": all(r["success"] for r in results), "results": results}
        if args.report:
            write_json(args.report.expanduser().resolve(), result)
        emit(result, args.json)
        return 0 if result["success"] else 1
    except DownloadError as exc:
        emit({"success": False, "error": exc.as_dict()}, getattr(args, "json", False))
        return 2 if exc.code == "invalid_input" else 1
    except (OSError, ValueError) as exc:
        emit(
            {
                "success": False,
                "error": {"code": "local_error", "message": redact(str(exc)), "hint": "检查本地文件、目录权限和参数。"},
            },
            getattr(args, "json", False),
        )
        return 1
    except KeyboardInterrupt:
        print("已中止；重试相同命令可续传。", file=sys.stderr)
        return 130
