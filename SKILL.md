---
name: video-downloader
description: 下载视频、提取音频并保存到本地。接收视频网站 URL、分享文本、MP4/HLS/DASH 直链，支持质量选择、批量任务、登录 Cookie、断点续传及抖音/小红书浏览器辅助解析。用户要求下载、保存网络视频或提取网络视频音频时使用。
---

# 视频下载

使用此 skill 自带的 `scripts/download.py`，不依赖其他 skill 或第三方解析服务。将下列脚本路径替换为本 SKILL.md 所在目录的绝对路径；不假设当前工作目录。需要 Python 3.10+，首次下载会在用户缓存目录准备独立依赖环境。`--help` 和 `doctor` 不安装任何东西。

## 执行

```bash
python3 /absolute/path/video-downloader/scripts/download.py "视频链接或完整分享文本" --json
```

默认保存至 `~/Downloads/Videos`，下载单个视频、选择最佳可用音视频、续传 `.part` 文件且不覆盖同名成品。最终返回文件绝对路径、大小和校验级别，只有 `success: true` 才算成功。不要按目录修改时间猜结果。`--json` 的 stdout 只有一个 JSON，进度及诊断位于 stderr；退出码 0 成功、1 下载/环境失败、2 输入错误、130 用户中止。

按用户要求添加参数：

| 需求 | 参数 |
|---|---|
| 保存目录 | `-o "/absolute/output/path"` |
| 最高 1080p | `--max-height 1080` |
| 提取 MP3 | `--audio` |
| 其他音频格式 | `--audio --audio-format m4a` |
| MP4 容器 | `--container mp4`（重封装，不强制转码） |
| 确认视频含声音 | `--require-audio` |
| 批量链接 | `--batch urls.txt`（一行一个链接或分享文本） |
| 合集 | `--playlist --max-items 20`；仅在用户要求合集时使用 |
| 保存结果清单 | `--report result.json` |
| 原文件损坏/更换质量 | `--overwrite`，仅在需要替换原文件时使用 |

仅查询格式或定位问题：

```bash
python3 /absolute/path/video-downloader/scripts/download.py inspect "URL" --json
python3 /absolute/path/video-downloader/scripts/download.py doctor --json
```

## 恢复失败

先读结果中的 `error.code`、`hint`、`diagnostics`，以及可能存在的 `browser_error`。批量任务的 `results` 分别记录成败；失败任务仍可能带有已完成、校验过的文件。

- `dependency`：运行 `setup`。合并、音频提取需要系统 FFmpeg；严格媒体校验需要 ffprobe。YouTube 需要 Deno 2.3+ 或 Node 22+，脚本自动检测；不要硬编码旧 Android 客户端。
- `network` / `timeout`：脚本已做有上限的重试。检查网络后重跑同一命令会续传；长视频可提高 `--timeout`。有明确代理时传 `--proxy`。
- `authentication` / `http_403`：使用用户提供的 Netscape 文件 `--cookies "/path/cookies.txt"`，或用户指定的浏览器 `--cookies-from-browser chrome`。不搜集无关浏览器或 Downloads 目录中的 Cookie。
- 抖音/小红书：普通解析失败后，默认 `--browser auto` 使用已安装的浏览器组件。缺组件时运行 `setup --browser`，或用 `--browser on` 安装并尝试。需要验证时使用 `--headed --browser-timeout 180`，或运行 `login douyin` / `login xiaohongshu` 让用户在专用窗口登录。保留小红书分享 URL 的 `xsec_token` 等查询参数。
- 平台解析变化：运行一次 `update` 后重试；稳定版仍有已确认的上游问题时可用 `update --channel nightly`。不要每次下载强制升级。
- `rate_limited`：停止连续重试，告知具体状态。`unavailable` / `drm` / `geo_restricted`：按实际原因报告，不承诺更换脚本即可下载。
- `invalid_output`：不得报告成功；需要重新下载时，使用明确的 `--overwrite`。缺 ffprobe 时只做媒体文件头检查，结果为 `header_only`，不能声称已校验音视频轨道。

完整参数、安装和验收说明见 [README.md](README.md)；特殊参数和故障定位见 [references/troubleshooting.md](references/troubleshooting.md)。最终向用户给出已校验文件的可点击本地链接；登录 Cookie、签名媒体 URL 和原始会话数据不进入回复或仓库。
