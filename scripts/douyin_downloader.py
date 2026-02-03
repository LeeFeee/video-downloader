#!/usr/bin/env python3
"""
抖音专用下载器 - 使用 Playwright 拦截 API 请求
适用于 douyin.com 和 v.douyin.com 短链接
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def parse_cookie_file(content: str) -> list:
    """解析 simple 格式的 cookie 为 Playwright 格式"""
    cookies = []
    for item in content.split(';'):
        item = item.strip()
        if '=' in item and item and not item.startswith('='):
            try:
                key, value = item.split('=', 1)
                cookies.append({
                    'name': key.strip(),
                    'value': value.strip(),
                    'domain': '.douyin.com',
                    'path': '/',
                })
            except ValueError:
                continue
    return cookies


def find_cookie_file():
    """查找抖音 cookie 文件"""
    possible_paths = [
        Path.home() / 'Downloads' / 'douyin_cookies_simple.txt',
        Path.home() / 'Downloads' / 'douyin.com_cookies.txt',
        Path.home() / 'Downloads' / 'www.douyin.com_cookies.txt',
        Path(__file__).parent / 'douyin_cookies_simple.txt',
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return None


async def download_video_file(video_url: str, save_path: Path) -> bool:
    """下载视频文件"""
    import requests

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': 'https://www.douyin.com/',
    }

    try:
        resp = requests.get(video_url, headers=headers, stream=True, timeout=60)
        if resp.status_code == 200:
            save_path.parent.mkdir(parents=True, exist_ok=True)

            downloaded = 0
            total = int(resp.headers.get('content-length', 0))

            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int(downloaded / total * 100)
                            print(f"\r下载中... {percent}%", end='', flush=True)

            print(f"\n✓ 下载完成: {save_path.name}")
            return True
        else:
            print(f"\n✗ 下载失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"\n✗ 下载出错: {e}")
        return False


async def download_douyin(url: str, output_dir: Path) -> dict:
    """
    下载抖音视频

    Args:
        url: 抖音视频链接 (支持短链接)
        output_dir: 输出目录

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'path': str or None,
            'title': str,
            'author': str
        }
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            'success': False,
            'message': 'Playwright 未安装，请运行: pip install playwright && playwright install chromium',
            'path': None,
            'title': '',
            'author': ''
        }

    # 查找 cookie 文件
    cookie_file = find_cookie_file()
    if not cookie_file:
        return {
            'success': False,
            'message': '未找到 Cookie 文件，请先运行 douyin_cookie_extractor.py 获取 Cookie',
            'path': None,
            'title': '',
            'author': ''
        }

    # 加载 cookies
    with open(cookie_file, 'r', encoding='utf-8') as f:
        cookie_content = f.read()

    cookies = parse_cookie_file(cookie_content)
    print(f"🍪 加载了 {len(cookies)} 条 cookie")

    result = {
        'success': False,
        'message': '',
        'path': None,
        'title': '',
        'author': ''
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        await context.add_cookies(cookies)

        page = await context.new_page()

        # 存储捕获的视频数据
        captured_data = {}
        video_id = None

        # 拦截 API 响应
        async def handle_response(response):
            nonlocal captured_data, video_id

            url = response.url

            # 查找视频详情 API
            if 'aweme/v1/web/aweme/detail' in url:
                try:
                    data = await response.json()
                    if 'aweme_detail' in data or 'awemeDetail' in data:
                        captured_data['aweme'] = data
                        # 尝试从 URL 提取 video_id
                        match = re.search(r'aweme_id=(\d+)', url)
                        if match:
                            video_id = match.group(1)
                        print(f"✓ 捕获到视频 API 数据")
                except:
                    pass

        page.on('response', handle_response)

        # 访问链接
        print(f"📥 正在访问: {url}")
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            await browser.close()
            return {
                'success': False,
                'message': f'访问链接失败: {e}',
                'path': None,
                'title': '',
                'author': ''
            }

        # 等待 API 调用
        print("⏳ 等待视频数据加载...")
        for i in range(20):  # 最多等待 10 秒
            await asyncio.sleep(0.5)
            if captured_data.get('aweme'):
                break

        # 获取最终 URL
        final_url = page.url
        print(f"🔗 最终地址: {final_url}")

        # 从 URL 提取 video_id
        if not video_id:
            match = re.search(r'/video/(\d+)', final_url)
            if match:
                video_id = match.group(1)

        if video_id:
            print(f"🆔 视频 ID: {video_id}")

        # 处理捕获的数据
        if captured_data.get('aweme'):
            aweme_data = captured_data['aweme']

            # 导航数据结构
            aweme = None
            if isinstance(aweme_data, dict):
                aweme = aweme_data.get('aweme_detail') or aweme_data.get('awemeDetail') or aweme_data

            if aweme:
                title = aweme.get('desc', 'video').strip()
                # 清理文件名
                title = re.sub(r'[<>:"/\\|?*]', '_', title)[:50]
                result['title'] = title

                # 获取作者信息
                author_info = aweme.get('author', {})
                author = author_info.get('nickname', '未知用户')
                result['author'] = author

                print(f"📝 视频标题: {title}")
                print(f"👤 作者: {author}")

                # 获取视频 URL
                video = aweme.get('video', {})
                play_addr = video.get('play_addr', {})
                url_list = play_addr.get('url_list', [])

                if url_list:
                    video_download_url = url_list[0]

                    save_path = output_dir / f'{title}.mp4'

                    # 尝试下载
                    success = await download_video_file(video_download_url, save_path)

                    if success:
                        result['success'] = True
                        result['message'] = f'下载成功: {title}.mp4'
                        result['path'] = str(save_path)
                    else:
                        # 尝试备用 URL
                        for i, alt_url in enumerate(url_list[1:5]):
                            print(f"尝试备用 URL {i+2}...")
                            if await download_video_file(alt_url, save_path):
                                result['success'] = True
                                result['message'] = f'下载成功: {title}.mp4'
                                result['path'] = str(save_path)
                                break

                        if not result['success']:
                            result['message'] = '所有下载 URL 都失败了'
                else:
                    result['message'] = '未找到视频 URL'
            else:
                result['message'] = '无法解析视频数据结构'
        else:
            result['message'] = '未能捕获到视频 API 数据，可能 Cookie 已过期'

        await browser.close()

    return result


def download_douyin_sync(url: str, output_dir=None) -> dict:
    """
    同步包装器，用于从非异步代码调用

    Args:
        url: 抖音视频链接
        output_dir: 输出目录 (默认 ~/Downloads/Videos)

    Returns:
        dict: 下载结果
    """
    if output_dir is None:
        output_dir = Path.home() / 'Downloads' / 'Videos'

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    return asyncio.run(download_douyin(url, output_dir))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 douyin_downloader.py <抖音视频URL> [输出目录]")
        print("示例: python3 douyin_downloader.py 'https://v.douyin.com/xxxxx/'")
        sys.exit(1)

    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    result = download_douyin_sync(url, output_dir)

    if result['success']:
        print(f"\n✅ {result['message']}")
        print(f"📂 文件位置: {result['path']}")
    else:
        print(f"\n❌ {result['message']}")
        sys.exit(1)
