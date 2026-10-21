import json
import os
import sys
import time

import pytest
from videodl.browser import media_info
from videodl.cli import legacy_args, main
from videodl.common import DownloadError, content_id, file_lock, normalize_url, platform, redact
from videodl.cookies import load_cookies, save_browser_cookies, to_browser
from videodl.engine import classify, verify_file
from videodl.process import run_lines


@pytest.mark.parametrize(
    "value,expected",
    [
        ("复制链接 https://v.douyin.com/abc/ 看视频", "https://v.douyin.com/abc/"),
        ("https://example.com/a?xsec_token=a%2Fb#fragment", "https://example.com/a?xsec_token=a%2Fb"),
        ("打开：https://example.com/v。", "https://example.com/v"),
    ],
)
def test_share_text(value, expected):
    assert normalize_url(value) == expected


def test_literal_url_signature_is_preserved():
    assert normalize_url("https://example.com/v?signature=abc.").endswith("signature=abc.")


@pytest.mark.parametrize(
    "value",
    [
        "file:///etc/passwd",
        "ftp://example.com/a",
        "hello",
        "https://u:p@example.com/v",
        "https://a/x https://b/y",
        "https://example.com:bad/v",
    ],
)
def test_bad_input(value):
    with pytest.raises(DownloadError):
        normalize_url(value)


def test_platform_exact_host():
    assert platform("https://v.douyin.com/a") == "douyin"
    assert platform("https://douyin.com.attacker.example/a") == "generic"
    assert platform("https://notdouyin.com/a") == "generic"
    assert content_id("https://www.douyin.com/?modal_id=123") == "123"


def test_cli_legacy():
    assert legacy_args(["https://example.com/a", "/tmp/out", "--audio"]) == [
        "download",
        "https://example.com/a",
        "--output",
        "/tmp/out",
        "--audio",
    ]
    assert legacy_args(["https://example.com/a", "--audio"])[-1] == "--audio"


def test_invalid_input_does_not_install(monkeypatch, capsys):
    monkeypatch.setattr("videodl.runtime.ensure", lambda **kw: pytest.fail("must not install"))
    assert main(["download", "bad", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


def test_cookie_roundtrip_and_scope(tmp_path):
    path = tmp_path / "private" / "session.txt"
    now = int(time.time())
    cookies = [
        {
            "name": "sessionid",
            "value": "secret",
            "domain": ".douyin.com",
            "path": "/video",
            "expires": now + 3600,
            "secure": True,
            "httpOnly": True,
        },
        {"name": "other", "value": "not-saved", "domain": ".evil.example", "path": "/"},
        {"name": "expired", "value": "old", "domain": ".douyin.com", "expires": now - 10},
    ]
    assert save_browser_cookies(cookies, path, "douyin") == 1
    loaded = to_browser(load_cookies(path), "douyin")
    assert loaded[0]["path"] == "/video" and loaded[0]["httpOnly"] and loaded[0]["secure"]
    assert loaded[0]["expires"] == now + 3600
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_invalid_cookie(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("sessionid=abc; xyz=123")
    with pytest.raises(DownloadError):
        load_cookies(path)


def test_browser_target_identity():
    payload = {
        "aweme_list": [
            {
                "aweme_id": "111",
                "desc": "wrong",
                "video": {"play_addr": {"url_list": ["https://cdn.example/wrong.mp4"]}},
            },
            {
                "aweme_id": "222",
                "desc": "right",
                "video": {"play_addr": {"url_list": ["https://cdn.example/right.mp4"], "height": 1080}},
            },
        ]
    }
    assert media_info(payload, "333", "douyin", "https://www.douyin.com/video/333", "test") is None
    result = media_info(payload, "222", "douyin", "https://www.douyin.com/video/222", "test")
    assert result["title"] == "right" and result["formats"][0]["url"].endswith("right.mp4")


def test_xhs_state():
    payload = {
        "note": {
            "noteDetailMap": {
                "a123": {
                    "note": {
                        "title": "small red book",
                        "video": {
                            "media": {
                                "stream": {
                                    "h264": [
                                        {
                                            "masterUrl": "https://cdn.example/main.mp4",
                                            "backupUrls": ["https://cdn2.example/main.mp4"],
                                            "height": 720,
                                        }
                                    ]
                                }
                            }
                        },
                    }
                }
            }
        }
    }
    result = media_info(payload, "a123", "xiaohongshu", "https://www.xiaohongshu.com/explore/a123", "test")
    assert len(result["formats"]) == 2


def test_redaction():
    value = redact("GET https://u:p@host/v?token=secret Cookie: abc=secret")
    assert "secret" not in value and "u:p" not in value


def test_timeout_and_lock(tmp_path):
    with pytest.raises(DownloadError, match="超过"):
        run_lines([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.1, on_line=lambda _: None)
    path = tmp_path / "test.lock"
    with file_lock(path):
        with pytest.raises(DownloadError):
            with file_lock(path):
                pass
    with file_lock(path):
        pass


def test_reject_invalid_output(tmp_path):
    path = tmp_path / "fake.mp4"
    path.write_text("<html>Forbidden</html>" * 50)
    with pytest.raises(DownloadError):
        verify_file(path, tmp_path)
    with pytest.raises(DownloadError):
        verify_file(path, tmp_path / "different")


@pytest.mark.parametrize(
    "message,code",
    [
        ("HTTP Error 429", "rate_limited"),
        ("Sign in to confirm", "authentication"),
        ("HTTP Error 403", "http_403"),
        ("Unsupported URL", "unsupported"),
        ("DRM protected", "drm"),
    ],
)
def test_error_codes(message, code):
    assert classify(message).code == code


def test_numeric_video_id_is_not_http_status():
    assert classify("ERROR [Douyin] 6961737553342991651: Fresh cookies are needed").code == "authentication"


def test_no_ffmpeg_uses_combined_format(monkeypatch, tmp_path):
    from videodl.cli import parser
    from videodl.engine import build_command

    monkeypatch.setattr("videodl.engine.shutil.which", lambda _: None)
    args = parser().parse_args(["download", "https://example.com/v", "--max-height", "720", "-o", str(tmp_path)])
    args.inspect = False
    command = build_command(sys.executable, args.urls[0], args)
    assert command[command.index("--format") + 1] == "b[height<=?720][vcodec!=none][acodec!=none]"


def test_header_only_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr("videodl.engine.shutil.which", lambda _: None)
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom" + bytes(100))
    assert verify_file(path, tmp_path)["verification"] == "header_only"
