"""Optional browser extraction. Only target-matched state/API records become media.

We deliberately do not download arbitrary observed video requests: a feed can preload
another creator's video while the requested item is blocked or removed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import runtime
from .common import DownloadError, content_id, host_is, platform, redact, write_json
from .cookies import DOMAINS, load_cookies, save_browser_cookies, to_browser
from .process import run_lines


def target_nodes(payload, target, site):
    stack = [(None, payload)]
    visited = 0
    while stack and visited < 50000:
        key, item = stack.pop()
        visited += 1
        if isinstance(item, dict):
            fields = ("aweme_id", "awemeId") if site == "douyin" else ("noteId", "note_id", "id")
            if any(str(item.get(k, "")) == target for k in fields) or str(key) == target:
                yield item.get("note", item)
            stack.extend(item.items())
        elif isinstance(item, list):
            stack.extend((None, value) for value in item)


def media_info(payload, target, site, referer, user_agent):
    for node in target_nodes(payload, target, site):
        video = node.get("video")
        if not isinstance(video, dict):
            continue
        formats, seen = [], set()

        def add(url, width=None, height=None, bitrate=None):
            if not isinstance(url, str) or urlsplit(url).scheme not in {"http", "https"} or url in seen:
                return
            seen.add(url)
            fmt = {"format_id": str(len(formats)), "url": url, "ext": "mp4"}
            for key, value in (("width", width), ("height", height), ("tbr", bitrate)):
                if isinstance(value, (int, float)) and value > 0:
                    fmt[key] = value
            formats.append(fmt)

        if site == "douyin":
            addresses = [video.get("play_addr", {}), video.get("playAddr", {})]
            for rate in video.get("bit_rate", video.get("bitRate", [])) or []:
                if isinstance(rate, dict):
                    addresses.append(rate.get("play_addr", rate.get("playAddr", {})))
            for address in addresses:
                if not isinstance(address, dict):
                    continue
                for url in address.get("url_list", address.get("urlList", [])) or []:
                    add(url, address.get("width", video.get("width")), address.get("height", video.get("height")))
        else:
            streams = video.get("media", {}).get("stream", {})
            if isinstance(streams, dict):
                for group in streams.values():
                    if not isinstance(group, list):
                        continue
                    for stream in group:
                        if not isinstance(stream, dict):
                            continue
                        urls = [stream.get("masterUrl"), *(stream.get("backupUrls") or [])]
                        for url in urls:
                            rate = stream.get("avgBitrate")
                            add(
                                url,
                                stream.get("width"),
                                stream.get("height"),
                                rate / 1000 if isinstance(rate, (float, int)) else None,
                            )
            consumer = video.get("consumer", {})
            if isinstance(consumer, dict):
                add(consumer.get("originVideoUrl"))
        if formats:
            duration = video.get("duration")
            return {
                "id": target,
                "title": node.get("desc") or node.get("title") or f"{site}-{target}",
                "extractor": f"browser:{site}",
                "extractor_key": f"Browser{site.title()}",
                "webpage_url": referer,
                "formats": formats,
                "duration": duration / 1000 if isinstance(duration, (int, float)) else None,
                "http_headers": {"Referer": referer, "User-Agent": user_agent},
            }
    return None


def _proxy(value):
    if not value:
        return None
    p = urlsplit(value)
    if not p.hostname or p.scheme not in {"http", "https", "socks5"}:
        raise DownloadError("invalid_input", "浏览器辅助代理需为 http、https 或 socks5 URL。")
    host = f"[{p.hostname}]" if ":" in p.hostname else p.hostname
    result = {"server": f"{p.scheme}://{host}" + (f":{p.port}" if p.port else "")}
    if p.username:
        result.update(username=unquote(p.username), password=unquote(p.password or ""))
    return result


def capture(config):
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    site, url = config["site"], config["url"]
    payloads = deque(maxlen=15)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not config["headed"], proxy=_proxy(config.get("proxy")))
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            if config.get("cookies"):
                context.add_cookies(to_browser(load_cookies(Path(config["cookies"])), site))
            elif config.get("cookies_from_browser"):
                from yt_dlp import YoutubeDL, parse_options

                opts = parse_options(
                    ["--ignore-config", "--cookies-from-browser", config["cookies_from_browser"]]
                ).ydl_opts
                opts.update(quiet=True, no_warnings=True)
                with YoutubeDL(opts) as ydl:
                    context.add_cookies(to_browser(ydl.cookiejar, site))
            page = context.new_page()

            def response_seen(response):
                host = urlsplit(response.url).hostname or ""
                if not any(host_is(host, d) for d in DOMAINS[site]):
                    return
                if response.request.resource_type not in {"xhr", "fetch"}:
                    return
                try:
                    if "json" not in response.headers.get("content-type", ""):
                        return
                    body = response.body()
                    if len(body) <= 5_000_000:
                        payloads.append(json.loads(body))
                except Exception:
                    # Unrelated/aborted response is expected during redirects and navigation.
                    return

            page.on("response", response_seen)
            deadline = time.monotonic() + config["timeout"]
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=min(30000, config["timeout"] * 1000))
            except PlaywrightTimeout:
                pass
            original_id = content_id(url)
            while time.monotonic() < deadline:
                target = original_id or content_id(page.url)
                if target and platform(page.url) == site:
                    try:
                        data = page.evaluate("""() => {
                      const values = [window.__INITIAL_STATE__, window._ROUTER_DATA];
                      const render = document.getElementById('RENDER_DATA');
                      if (render) { try { values.push(JSON.parse(decodeURIComponent(render.textContent))); } catch (_) {} }
                      return JSON.parse(JSON.stringify(values, (_, v) => typeof v === 'bigint' ? String(v) : v));
                    }""")
                        user_agent = page.evaluate("navigator.userAgent")
                    except PlaywrightError as exc:
                        if "Execution context was destroyed" not in str(exc) and "Cannot find context" not in str(exc):
                            raise
                        # Login/interstitial redirects can replace the JS realm mid-read.
                        page.wait_for_timeout(250)
                        continue
                    for payload in [data, *payloads]:
                        info = media_info(payload, target, site, page.url, user_agent)
                        if info:
                            write_json(Path(config["info_file"]), info)
                            save_browser_cookies(context.cookies(), Path(config["cookie_file"]), site)
                            return {"success": True}
                page.wait_for_timeout(500)
            raise DownloadError(
                "browser_no_media",
                "页面未提供与目标视频 ID 匹配的媒体数据。",
                "运行 login 或使用 --headed 完成人工验证；小红书需保留完整分享链接及 xsec_token。",
            )
        finally:
            browser.close()


def login(config):
    from playwright.sync_api import sync_playwright

    site = config["site"]
    sites = {"douyin": "https://www.douyin.com/", "xiaohongshu": "https://www.xiaohongshu.com/"}
    session_names = {"douyin": {"sessionid", "sessionid_ss"}, "xiaohongshu": {"web_session"}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(sites[site], wait_until="domcontentloaded", timeout=60000)
            print("请在打开的专用浏览器中完成登录；检测到会话后自动保存。", file=sys.stderr, flush=True)
            deadline = time.monotonic() + config["timeout"]
            while time.monotonic() < deadline:
                cookies = context.cookies()
                if any(c["name"] in session_names[site] and c["value"] for c in cookies):
                    count = save_browser_cookies(cookies, Path(config["cookie_file"]), site)
                    return {
                        "success": True,
                        "cookies": count,
                        "path": config["cookie_file"],
                        "note": "已保存会话 Cookie；实际访问权限由平台确认。",
                    }
                page.wait_for_timeout(1000)
            raise DownloadError("authentication", "未在限定时间内检测到登录会话。", "重新运行 login 并完成登录。")
        finally:
            browser.close()


def _run_worker(python, config, directory):
    config_path, result_path = directory / "config.json", directory / "worker-result.json"
    config["result_file"] = str(result_path)
    write_json(config_path, config)
    code = "import sys; sys.path.insert(0, sys.argv.pop(1)); from videodl.browser import worker; worker()"
    command = [python, "-c", code, str(Path(__file__).resolve().parents[1]), str(config_path)]
    run_lines(command, timeout=config["timeout"] + 45, on_line=lambda line: print(redact(line), file=sys.stderr))
    if not result_path.is_file():
        raise DownloadError("browser", "浏览器辅助进程未返回结果。", "运行 setup --browser 修复安装。")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result.get("success"):
        error = result["error"]
        raise DownloadError(error["code"], error["message"], error["hint"])
    return result


def capture_subprocess(python, url, args, cookies, directory):
    info, jar = directory / "media.json", directory / "browser-cookies.txt"
    config = {
        "mode": "capture",
        "url": url,
        "site": platform(url),
        "headed": args.headed,
        "timeout": args.browser_timeout,
        "cookies": str(cookies) if cookies else None,
        "cookies_from_browser": args.cookies_from_browser,
        "proxy": args.proxy,
        "info_file": str(info),
        "cookie_file": str(jar),
    }
    _run_worker(python, config, directory)
    return info, jar


def login_subprocess(args):
    python = runtime.ensure(browser=True, auto_install=not args.no_install)
    config = {
        "mode": "login",
        "site": args.site,
        "timeout": args.timeout,
        "cookie_file": str(runtime.home_dir() / "cookies" / f"{args.site}.txt"),
    }
    with tempfile.TemporaryDirectory(prefix="videodl-login-") as tmp:
        return _run_worker(python, config, Path(tmp))


def worker():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        result = login(config) if config["mode"] == "login" else capture(config)
    except DownloadError as exc:
        result = {"success": False, "error": exc.as_dict()}
    except Exception as exc:
        message = redact(str(exc))
        hint = "运行 setup --browser 检查 Chromium 安装；Linux 可能需要系统浏览器依赖。"
        code = "browser_missing" if "Executable doesn't exist" in str(exc) else "browser"
        result = {"success": False, "error": {"code": code, "message": message, "hint": hint}}
    write_json(Path(config["result_file"]), result)
