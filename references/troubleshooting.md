# 故障定位与高级参数

先保存 `doctor --json`、脱敏后的错误结果以及可公开访问的示例链接。不要把 Cookie、登录配置或签名媒体 URL 放进 issue。

| 错误代码 | 行动 |
|---|---|
| dependency | `setup`；浏览器缺组件时 `setup --browser`；合并/音频处理安装系统 FFmpeg |
| authentication | 显式提供 Cookie 或指定浏览器；抖音/小红书也可 `login` |
| http_403 | 同一网络下确认可播放；检查 Cookie、Referer、代理；更新解析器一次 |
| network / timeout | 检查网络；重试原命令以续传；必要时增加 `--timeout` |
| rate_limited | 暂停请求，稍后再试，不提高并发 |
| unavailable | 检查视频是否删除、私密或链接错误 |
| geo_restricted | 确认当前地区；需要时显式传入可用代理 |
| format_unavailable | `inspect` 检查格式；去掉高度或格式限制；检查 FFmpeg |
| invalid_output | 不把成品当成功；确认后用 `--overwrite` 重下，保留错误结果用于排查 |
| browser_no_media | 确认完整分享地址；`--headed` 人工完成验证；可能是图文内容或页面结构变化 |
| busy | 同一输出目录或安装环境已有进程，等待其退出或使用另一个目录 |
| drm | 不支持 DRM 媒体 |

## 代理、请求头和格式

```bash
python3 scripts/download.py "URL" --proxy http://127.0.0.1:7890
python3 scripts/download.py "URL" --proxy ""  # 禁用下载器的环境代理
python3 scripts/download.py "媒体直链" --referer "https://example.com/watch"
python3 scripts/download.py "URL" --header "User-Agent: your-client"
python3 scripts/download.py "URL" -f 'bv*[height<=1080]+ba/b[height<=1080]'
python3 scripts/download.py "URL" --subs 'zh.*,en'
```

`--format` 优先于 `--max-height`；默认优先合并最佳视频与最佳音频，没装 FFmpeg 时选自带声音的单文件格式。浏览器辅助抓到的直链没有可靠分辨率信息时，`--max-height` 不保证上限；需要严格限制可用 `-f 'b[height<=720]'`，没有已知满足条件的格式即失败。

高级 `--extractor-args` 可重复指定，直接传给上游。只有在当前上游文档明确适用时才添加 YouTube 客户端/PO Token 参数，不延用旧版的固定 Android 客户端。参考 [Extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors) 和 [EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)。

需要 TLS 指纹模拟的站点可在命令行包环境中安装 `.[impersonation]`；基础安装不强制依赖该平台相关扩展。浏览器辅助使用显式 `--proxy`；Playwright 不自动复用下载器所有环境代理变量。

## 维护浏览器适配器

`scripts/videodl/browser.py` 中的 `media_info` 负责从匹配作品 ID 的节点提取 URL。更新站点结构时添加脱敏的最小 JSON 测试样例，包含目标作品和无关推荐作品，证明适配器不会混淆两者。不要复制整份登录响应或加入硬编码临时签名。

浏览器只负责解析和获取本次会话 Cookie；媒体仍走统一下载、重试、续传与校验流程。任何浏览器数据都不作为 shell 命令执行。
