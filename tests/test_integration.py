import json
from pathlib import Path

import pytest
from videodl.cli import main


def invoke(url, directory, capsys, *options, expected=0):
    code = main(
        [
            "download",
            url,
            "-o",
            str(directory),
            "--json",
            "--quiet",
            "--no-install",
            "--browser",
            "off",
            "--timeout",
            "60",
            *options,
        ]
    )
    captured = capsys.readouterr()
    assert code == expected, captured.out + captured.err
    return json.loads(captured.out)


@pytest.mark.parametrize("source", ["clip.mp4", "stream.m3u8", "stream.mpd", "page.html"])
def test_media_downloads(media_server, tmp_path, capsys, source):
    base, _ = media_server
    result = invoke(f"{base}/{source}", tmp_path / "下载 目录", capsys, "--require-audio")
    file = result["results"][0]["files"][0]
    assert file["verification"] == "ffprobe"
    assert {"video", "audio"}.issubset(file["streams"])
    assert Path(file["path"]).is_file()


def test_audio_and_duplicate(media_server, tmp_path, capsys):
    base, _ = media_server
    output = tmp_path / "audio"
    result = invoke(f"{base}/clip.mp4", output, capsys, "--audio")
    path = Path(result["results"][0]["files"][0]["path"])
    assert path.suffix == ".mp3"
    previous = path.stat().st_mtime_ns
    (output / "unrelated.txt").write_text("unrelated file must never be returned")
    repeated = invoke(f"{base}/clip.mp4", output, capsys, "--audio")
    assert repeated["results"][0]["files"][0]["path"] == str(path)
    assert path.stat().st_mtime_ns == previous


def test_http_retry(media_server, tmp_path, capsys):
    base, calls = media_server
    invoke(f"{base}/retry.mp4", tmp_path / "retry", capsys, "--retries", "2")
    assert sum(p == "/retry.mp4" for p, _ in calls) >= 2


@pytest.mark.parametrize("source", ["broken.m3u8", "invalid.mp4", "cut.mp4"])
def test_incomplete_never_succeeds(media_server, tmp_path, capsys, source):
    base, _ = media_server
    result = invoke(f"{base}/{source}", tmp_path / "broken", capsys, "--retries", "0", expected=1)
    assert not result["success"] and not result["results"][0]["files"]


def test_resume_range(media_server, media_root, tmp_path, capsys):
    base, calls = media_server
    output = tmp_path / "resume"
    output.mkdir()
    # The direct Generic extractor's ID/title are the URL basename.
    partial = output / "range [Generic-range].mp4.part"
    original = (media_root / "clip.mp4").read_bytes()
    partial.write_bytes(original[:2048])
    result = invoke(f"{base}/range.mp4", output, capsys)
    path = Path(result["results"][0]["files"][0]["path"])
    assert path.read_bytes() == original
    assert any(p == "/range.mp4" and value == "bytes=2048-" for p, value in calls)


def test_batch_partial_failure_and_report(media_server, tmp_path, capsys):
    base, _ = media_server
    batch, report = tmp_path / "urls.txt", tmp_path / "report.json"
    batch.write_text(f"# two entries\n{base}/missing.mp4\n{base}/clip.mp4\n{base}/clip.mp4\n")
    code = main(
        [
            "download",
            "--batch",
            str(batch),
            "-o",
            str(tmp_path / "batch"),
            "--report",
            str(report),
            "--json",
            "--quiet",
            "--retries",
            "0",
            "--no-install",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and len(result["results"]) == 2
    assert result["results"][1]["success"]
    assert json.loads(report.read_text(encoding="utf-8")) == result


def test_inspect_no_media_created(media_server, tmp_path, capsys):
    base, _ = media_server
    output = tmp_path / "inspect"
    assert main(["inspect", f"{base}/clip.mp4", "--json", "--quiet", "--no-install", "-o", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["items"][0]["formats"]
    assert not output.exists()


def test_browser_media_alternate_and_common_verification(media_server, tmp_path):
    import sys

    from videodl.browser import media_info
    from videodl.cli import parser
    from videodl.common import write_json
    from videodl.engine import attempt

    base, calls = media_server
    payload = {
        "aweme_detail": {
            "aweme_id": "123",
            "desc": "目标视频",
            "video": {"play_addr": {"url_list": [f"{base}/clip.mp4", f"{base}/missing.mp4"]}},
        }
    }
    info = media_info(payload, "123", "douyin", "https://www.douyin.com/video/123", "Test")
    info_file = tmp_path / "media.json"
    write_json(info_file, info)
    args = parser().parse_args(
        ["download", "https://www.douyin.com/video/123", "-o", str(tmp_path / "browser"), "--require-audio", "--quiet"]
    )
    args.inspect = False
    result = attempt(sys.executable, args.urls[0], args, info_file=info_file)
    assert result["success"], result
    assert result["files"][0]["id"] == "123"
    assert result["files"][0]["streams"] == ["audio", "video"]
    assert any(path == "/clip.mp4" for path, _ in calls)


def test_corrupt_existing_file_requires_explicit_overwrite(media_server, tmp_path, capsys):
    base, _ = media_server
    output = tmp_path / "overwrite"
    result = invoke(f"{base}/clip.mp4", output, capsys)
    path = Path(result["results"][0]["files"][0]["path"])
    path.write_text("corrupted final file" * 40)
    failed = invoke(f"{base}/clip.mp4", output, capsys, expected=1)
    assert failed["results"][0]["error"]["code"] == "invalid_output"
    fixed = invoke(f"{base}/clip.mp4", output, capsys, "--overwrite")
    assert fixed["results"][0]["files"][0]["verification"] == "ffprobe"
