# Video Downloader

通用视频下载工具，支持 YouTube、Bilibili、Twitter/X、抖音、小红书等 1000+ 视频网站。

## 功能特点

- 支持 **1000+ 视频网站**，包括国内外主流平台
- 抖音视频专用下载器（基于 Playwright + Cookie）
- 自动检测并安装依赖
- 命令行简单易用

## 免责声明

> **重要提示**：各个视频平台会随时改变其访问限制策略和反爬虫机制。本工具依赖于这些平台的现有接口工作，**不能保证在任何时候都能正常工作**。如果下载失败，可能是平台策略变化导致的，需要等待工具更新。

## 致谢

本工具基于以下优秀的开源项目：

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - youtube-dl 的分支版本，支持更多网站和更新维护
- **[Playwright](https://github.com/microsoft/playwright-python)** - 微软出品的浏览器自动化工具，用于抖音视频下载
- **[douyin-downloader](https://github.com/jiji262/douyin-downloader)** - 抖音下载参考项目

感谢这些开源项目的作者和贡献者！

## 安装
### Claude Code Skill 一键安装

```bash
npx skills add LeeFeee/video-downloader
```

### 基础依赖（自动安装）

```bash
pip install yt-dlp
```

### 抖音下载（可选）

如果需要下载抖音视频，需要额外安装：

```bash
pip install playwright
playwright install chromium
```

### FFmpeg（可选）

部分视频需要 FFmpeg 进行合并：

```bash
brew install ffmpeg  # macOS
```

## 使用方法

### Claude Code Skill 调用（**推荐用法**）

```bash
url 下载这个视频
```

### 下载视频

```bash
python3 scripts/download.py "<视频URL>"
```

### 指定输出目录

```bash
python3 scripts/download.py "<视频URL>" "/path/to/output"
```

### 下载 YouTube 视频（使用 Android 客户端绕过限制）

```bash
python3 -m yt_dlp --extractor-args "youtube:player_client=android" "<视频URL>" -o "~/Downloads/Videos/%(title)s.%(ext)s"
```

### 抖音视频下载

首次使用需要获取 Cookie：

```bash
python3 scripts/douyin_cookie_extractor.py
```

扫码登录后，Cookie 会自动保存到 `~/Downloads/douyin_cookies_simple.txt`，之后即可直接下载抖音视频。

## 支持的网站

### 国外平台
- YouTube
- Twitter/X
- Instagram
- TikTok
- Vimeo
- Facebook
- Twitch
- ...更多

### 国内平台
- Bilibili
- 抖音
- 快手
- 小红书
- 西瓜视频
- ...更多

完整支持列表请查看 [yt-dlp 支持网站列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## 文件结构

```
video-downloader/
├── SKILL.md                      # 技能说明
├── README.md                     # 本文档
└── scripts/
    ├── download.py               # 主下载脚本
    ├── douyin_downloader.py      # 抖音专用下载器
    ├── douyin_cookie_extractor.py # 抖音 Cookie 提取器
    └── apiproxy/                 # 抖音 API 模块
```

## 常见问题

### Q: YouTube 下载失败，提示访问被拒绝？

A: YouTube 会不定期更新反爬虫策略。可以尝试使用 Android 客户端模式：

```bash
python3 -m yt_dlp --extractor-args "youtube:player_client=android" "<URL>"
```

### Q: 抖音视频下载失败？

A: 可能是 Cookie 过期了。重新运行 Cookie 提取脚本：

```bash
python3 scripts/douyin_cookie_extractor.py
```

### Q: 下载的视频没有声音？

A: 需要安装 FFmpeg：

```bash
brew install ffmpeg  # macOS
sudo apt install ffmpeg  # Ubuntu/Debian
```

## 许可证

MIT License

## 更新日志

### v1.0.0 (2025-02-03)
- 初始版本
- 支持 yt-dlp 下载 1000+ 平台
- 抖音专用下载器（Playwright + Cookie）
- 自动 Cookie 提取工具
