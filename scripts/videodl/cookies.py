from __future__ import annotations

import os
import tempfile
import time
from http.cookiejar import HTTPONLY_ATTR, Cookie, LoadError, MozillaCookieJar
from pathlib import Path

from .common import DownloadError, host_is

DOMAINS = {"douyin": ("douyin.com", "iesdouyin.com", "aweme.cn"), "xiaohongshu": ("xiaohongshu.com", "xhslink.com")}


def load_cookies(path: Path) -> MozillaCookieJar:
    jar = MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=False)
    except (OSError, LoadError) as exc:
        raise DownloadError(
            "invalid_input",
            "Cookie 文件不是有效的 Netscape 格式。",
            "重新导出 Netscape Cookie，或运行 login；不再自动读取 Downloads 中的旧 Cookie。",
        ) from exc
    return jar


def to_browser(jar, site):
    result = []
    for cookie in jar:
        if cookie.is_expired() or not any(host_is(cookie.domain.lstrip("."), d) for d in DOMAINS[site]):
            continue
        item = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path or "/",
            "secure": cookie.secure,
            "httpOnly": cookie.has_nonstandard_attr(HTTPONLY_ATTR) or cookie.has_nonstandard_attr("HttpOnly"),
        }
        if cookie.expires and cookie.expires > 0:
            item["expires"] = cookie.expires
        result.append(item)
    return result


def save_browser_cookies(cookies, path: Path, site):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    jar = MozillaCookieJar()
    for c in cookies:
        domain = c.get("domain", "")
        if not any(host_is(domain.lstrip("."), d) for d in DOMAINS[site]):
            continue
        expires = c.get("expires", -1)
        if expires > 0 and expires <= time.time():
            continue
        jar.set_cookie(
            Cookie(
                0,
                c["name"],
                c["value"],
                None,
                False,
                domain,
                domain.startswith("."),
                domain.startswith("."),
                c.get("path", "/"),
                True,
                bool(c.get("secure")),
                int(expires) if expires > 0 else None,
                expires <= 0,
                None,
                None,
                {HTTPONLY_ATTR: None} if c.get("httpOnly") else {},
                False,
            )
        )
    fd, tmp = tempfile.mkstemp(prefix=".cookies-", dir=path.parent)
    os.close(fd)
    try:
        jar.save(tmp, ignore_discard=True, ignore_expires=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return len(jar)
