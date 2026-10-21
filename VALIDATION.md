# 验收记录

日期：2026-10-21（Asia/Kuala_Lumpur）。本记录区分可复现的本地验收和当次平台实测，不把单个样例外推为整站保证。

## 环境

- macOS / Apple Silicon，Python 3.14.5。
- yt-dlp 2026.08.19，yt-dlp-ejs 0.8.0，Playwright 1.64.0，Deno 2.8.2。
- 系统 FFmpeg 与 ffprobe；独立 Python 环境通过 `setup` 在仓库外目录成功建立，`setup --browser` 成功安装可选组件。

## 自动验收

本地测试涵盖：分享文本、非法 URL、精确域名匹配、签名参数保留、旧版入口、Cookie 作用域/有效期/HTTPOnly、抖音/小红书目标 ID 匹配、日志脱敏、超时与目录锁、错误分类、缺 FFmpeg 的格式选择、文件头降级检查；真实下载测试覆盖 MP4/HLS/DASH/HTML 视频、双轨校验、MP3 提取、不覆盖成品、503 退避重试、缺失分片/伪媒体/断流失败、Range 续传、批量部分失败、只解析不落媒体、备用 CDN 和损坏成品显式重下。

运行命令和结果计数以当前提交 CI 与 `pytest -q` 输出为准；测试只使用自动生成的媒体和本机 HTTP 服务。另检查 Ruff、skill frontmatter、sdist/wheel 构建，以及从仓库外启动入口。

## 平台实测

没有读取个人浏览器 Cookie 或使用既有登录态。样例取自公开链接或上游测试样例。

| 平台 | 样例 | 当次结果 |
|---|---|---|
| YouTube | `jNQXAC9IVRw`，Me at the zoo | 下载成功，474,478 字节，19.021 秒，ffprobe 确认 audio + video |
| Bilibili | `BV1xx411c7Xg`，弹幕测试专用 | 下载成功，12,949,064 字节，1213.8 秒，ffprobe 确认 audio + video |
| 抖音 | `6961737553342991651` | yt-dlp 提示 fresh cookies 后自动切换浏览器，匹配目标 ID 并下载成功；6,281,768 字节，19.735 秒，audio + video |
| 小红书 | `6411cf99000000001300b6d9`、`674051740000000007027a15` | 现有匿名样例未提供目标媒体；返回失败，未生成假成品。已验证状态结构解析，但尚未完成有效登录态下的实网下载验收 |

YouTube 旧测试样例 `BaW_jenozKc` 返回 unavailable，已正确报告，不作为可用样例。小红书实测发现的页面跳转导致 JS context 销毁问题已修复为在既定超时内继续读取。

未实测：登录二维码流程的实际账户会话、付费/私密内容、所有上游支持站点、长时间直播。Linux/Windows 行为由仓库的跨平台 CI 检查；没有将仅在 macOS 上运行的结果标记为跨平台实测。
