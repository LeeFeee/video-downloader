# Video Downloader 2

可独立安装、可维护的视频下载 skill 与命令行工具。网站解析交给持续更新的 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，本项目负责依赖隔离、参数与批量任务、登录会话、重试与续传、结果校验，以及抖音/小红书的浏览器辅助解析。无需其他 skill、私人 API、远程解析服务或用户本机的旧脚本。

## 安装

作为 Codex / Claude Code 等工具的 skill：

```bash
npx skills add LeeFeee/video-downloader
```

也可直接克隆并使用（Python 3.10+）：

```bash
git clone https://github.com/LeeFeee/video-downloader.git
cd video-downloader
python3 scripts/download.py setup
python3 scripts/download.py doctor
```

`setup` 在 `~/.cache/video-downloader/runtime-<Python版本>/` 建立独立环境，不向系统 Python 安装包；首次下载也会自动准备。支持 `VIDEO_DOWNLOADER_HOME` 指定私有数据目录、`XDG_CACHE_HOME` 指定缓存根目录。已经安装满足要求的 Python 包时可直接使用当前解释器。`--no-install` 可禁止下载时安装。

FFmpeg / ffprobe 用于音视频合并、提取音频和成品校验：

```bash
brew install ffmpeg                 # macOS
sudo apt install ffmpeg python3-venv # Debian / Ubuntu
winget install Gyan.FFmpeg          # Windows
```

YouTube 还需要 Deno 2.3+（推荐）或 Node 22+；脚本自动启用已安装的兼容运行时。EJS 随 `yt-dlp[default]` 安装，不在每次下载时从网络加载脚本。依据：[上游 EJS 安装说明](https://github.com/yt-dlp/yt-dlp/wiki/EJS)。

Python 命令行包安装方式：

```bash
pipx install 'git+https://github.com/LeeFeee/video-downloader.git'
video-downloader doctor
video-downloader "视频URL"
```

## 使用

```bash
# 分享文本也可直接传入；请用引号保护 URL 中的 & 等字符
python3 scripts/download.py "视频URL"
python3 scripts/download.py "视频URL" "/path/to/output"  # 兼容 v1
python3 scripts/download.py download "视频URL" -o ~/Downloads/Videos --max-height 1080
python3 scripts/download.py "视频URL" --audio --audio-format mp3
python3 scripts/download.py "视频URL" --container mp4 --require-audio

# 只查看信息与格式，不创建媒体文件
python3 scripts/download.py inspect "视频URL" --json

# 多个 URL 或一行一条的 UTF-8 文件；一条失败不会吞掉其他条目的结果
python3 scripts/download.py download "URL1" "URL2" --json --report result.json
python3 scripts/download.py download --batch urls.txt -o ./videos

# 合集必须明确启用，默认限 20 条
python3 scripts/download.py "合集URL" --playlist --max-items 50
```

默认单条链接只取一项；不会意外把播放列表整份下载。默认文件名含站点和视频 ID，避免不同视频因同名覆盖。同名成品不覆盖，但仍会校验；换质量或重下损坏文件时显式传 `--overwrite`。自动保留源容器；`--container mp4` 是重封装，不能保证所有播放器都支持源编码。

## 登录与浏览器辅助

```bash
python3 scripts/download.py "URL" --cookies /private/path/cookies.txt
python3 scripts/download.py "URL" --cookies-from-browser chrome
python3 scripts/download.py setup --browser
python3 scripts/download.py login douyin
python3 scripts/download.py login xiaohongshu
python3 scripts/download.py "完整分享文本" --browser on --headed --browser-timeout 180
```

Cookie 文件使用 Netscape 格式，保留 domain、path、secure、HTTPOnly 和有效期。传入文件会复制到临时目录供解析器使用，不修改原件。专用登录流程只保存所选站点的 Cookie，存入私有缓存的 `cookies/`，文件权限为 `0600`（POSIX）；不打印 Cookie 值，也不自动扫描个人浏览器。旧版 `scripts/douyin_cookie_extractor.py` 会转到新的抖音登录流程。

浏览器是有限的补救路径：先走 yt-dlp；失败后仅对抖音、小红书读取页面状态和 JSON 响应，且必须匹配请求视频 ID。不会把推荐流或广告的媒体请求当成目标。`auto` 只使用已安装组件；`on` 允许安装缺少的组件；`off` 禁用浏览器。图文笔记、DRM、登录权限缺失等会明确失败。登录窗口由用户完成扫码或验证。

## 稳定性约定

- HTTP、分片、解析均有重试上限；临时 5xx 解析失败也会退避重试。每条链接每个引擎默认最长 1800 秒，可用 `--timeout` 修改；浏览器解析另受 `--browser-timeout` 限制。
- HTTP Range 与 HLS/DASH 分片续传由 yt-dlp 负责；缺失分片终止任务，不默默拼出残片视频。
- 只接受 `after_move` 返回的最终文件路径，不扫描“最近修改的文件”。同一输出目录有进程锁，防止并行写入冲突。
- 安装 ffprobe 后检查真实媒体流；音频任务必须有音轨，`--require-audio` 要求视频和音频均存在。没装 ffprobe 时退回文件头校验，并明确标记 `header_only`。
- `--json` 的 stdout 始终为一个结果对象（参数解析错误除外），日志走 stderr。批量任务只要一条失败，整体退出码非零；每条记录包含自身结果及已成功文件。
- 下载 URL 的查询凭据和 Cookie 不写入结果清单；诊断会脱敏。结果中保留视频 ID、标题、最终路径、大小、媒体流和校验方式。
- 不读取外部 yt-dlp 配置或自动加载未知插件，避免其他工具的全局设置改变下载结果。

退出码：`0` 全部成功，`1` 下载/环境失败，`2` 参数错误，`130` 用户中止。

## 更新与诊断

```bash
python3 scripts/download.py doctor --json
python3 scripts/download.py update
python3 scripts/download.py update --channel nightly  # 需要上游预发布修复时
python3 scripts/download.py download --help
```

更新仅作用于本工具的独立环境，不改系统工具。更多代理、请求头、格式表达式和错误处理见 [故障定位](references/troubleshooting.md)。

## 验证与维护

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,browser]'
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check --config pyproject.toml scripts tests
.venv/bin/python -m build
```

Windows 把 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。测试使用本地生成的带音轨视频和受控 HTTP 服务，覆盖 MP4、HLS、DASH、HTML 视频、音频提取、重试、断流、Range 续传、重复下载、批量部分失败和 Cookie 属性；不依赖外部网站或个人登录态。浏览器适配器另有目标 ID 和结构解析测试。CI 在 Linux/macOS/Windows 与多版 Python 上运行。

实网验证记录与范围见 [VALIDATION.md](VALIDATION.md)。网站支持范围跟随 [yt-dlp extractors](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)；列入上游支持列表不等于每个链接、每种登录状态都经过本项目验证。

## 开源来源

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)：网页解析、格式选择、下载及后处理。
- [Playwright](https://github.com/microsoft/playwright)：可选的专用浏览器会话与页面状态读取。
- [FFmpeg](https://ffmpeg.org/)：系统安装的音视频工具，不随本仓库分发。
- v1 抖音流程曾参考 [douyin-downloader](https://github.com/jiji262/douyin-downloader)。v2 已移除未使用的旧 `apiproxy` / X-Bogus 实现，浏览器适配器由本项目维护。

本仓库代码为 MIT，依赖分别遵循其上游许可证。
