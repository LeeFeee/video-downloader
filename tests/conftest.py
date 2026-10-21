import functools
import http.server
import shutil
import socket
import subprocess
import threading

import pytest


@pytest.fixture(autouse=True)
def private_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_DOWNLOADER_HOME", str(tmp_path / "cache"))


@pytest.fixture(scope="session")
def media_root(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Integration tests require ffmpeg and ffprobe")
    root = tmp_path_factory.mktemp("media")
    base = ["ffmpeg", "-v", "error", "-y"]
    subprocess.run(
        [
            *base,
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x90:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "10",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(root / "clip.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            *base,
            "-i",
            str(root / "clip.mp4"),
            "-c",
            "copy",
            "-hls_time",
            "1",
            "-hls_list_size",
            "0",
            str(root / "stream.m3u8"),
        ],
        check=True,
    )
    # Use a relative manifest so Windows FFmpeg writes its segments beside the MPD.
    subprocess.run([*base, "-i", "clip.mp4", "-c", "copy", "-f", "dash", "stream.mpd"], check=True, cwd=root)
    (root / "invalid.mp4").write_text("<html>login required</html>" * 100)
    (root / "broken.m3u8").write_text((root / "stream.m3u8").read_text().replace("stream0.ts", "missing.ts"))
    (root / "page.html").write_text(
        '<html><head><title>Integration video</title></head><body><video src="clip.mp4" controls></video></body></html>'
    )
    return root


@pytest.fixture
def media_server(media_root):
    calls = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("Range")))
            path = self.path.split("?", 1)[0]
            if path == "/retry.mp4" and sum(p == self.path for p, _ in calls) == 1:
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path in {"/range.mp4", "/retry.mp4", "/cut.mp4"}:
                data = (media_root / "clip.mp4").read_bytes()
                start = int(self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
                is_range = self.headers.get("Range") is not None
                self.send_response(206 if is_range else 200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data) - start))
                self.send_header("Accept-Ranges", "bytes")
                if is_range:
                    self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                self.end_headers()
                if path == "/cut.mp4":
                    self.wfile.write(data[start : start + 1024])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.wfile.write(data[start:])
                return
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(media_root)))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
