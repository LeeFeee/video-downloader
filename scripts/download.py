#!/usr/bin/env python3
"""
视频下载脚本 - 基于 yt-dlp 和 douyin-downloader
支持 YouTube, Bilibili, Twitter 等数百个视频网站
抖音使用专用下载器
自动检测并安装依赖
"""

import sys
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

def get_yt_dlp_command():
    """获取 yt-dlp 命令，优先使用 Python 模块方式"""
    # 先尝试直接调用
    try:
        subprocess.run(['yt-dlp', '--version'],
                      capture_output=True,
                      check=True,
                      timeout=10)
        return ['yt-dlp']
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # 使用 Python 模块方式
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'yt_dlp', '--version'],
            capture_output=True,
            check=True,
            timeout=10
        )
        if result.returncode == 0:
            return [sys.executable, '-m', 'yt_dlp']
    except:
        pass

    return None

def get_cookies_file(url):
    """根据 URL 查找对应的 cookies 文件"""
    script_dir = Path(__file__).parent

    # 从 URL 提取域名
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    # 提取主域名（处理子域名，如 v.douyin.com -> douyin.com）
    parts = domain.split('.')
    if len(parts) >= 2:
        # 尝试多种域名组合
        domain_variants = [
            domain,  # 完整域名: v.douyin.com
            '.'.join(parts[-2:]),  # 主域名: douyin.com
            '.'.join(parts[-3:]),  # 二级域名: www.douyin.com
        ]
    else:
        domain_variants = [domain]

    # 可能的 cookies 文件位置
    possible_paths = []
    for variant in domain_variants:
        possible_paths.extend([
            Path.home() / "Downloads" / f"{variant}_cookies.txt",
            Path.home() / "Downloads" / f"www.{variant}_cookies.txt",
        ])

    # 通用 cookies 文件
    possible_paths.extend([
        Path.home() / "Downloads" / "cookies.txt",
        script_dir / "cookies.txt",
    ])

    for path in possible_paths:
        if path.exists():
            return path

    return None

def check_and_install_yt_dlp():
    """检查并安装 yt-dlp"""
    cmd = get_yt_dlp_command()
    if cmd:
        return True

    print("⚠️  yt-dlp 未安装，正在自动安装...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'yt-dlp'],
                      check=True)
        print("✅ yt-dlp 安装成功！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 自动安装失败: {e}")
        print("   请手动运行: pip install yt-dlp")
        return False

def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    try:
        subprocess.run(['ffmpeg', '-version'],
                      capture_output=True,
                      check=True,
                      timeout=5)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

def get_default_output_dir():
    """获取默认下载目录"""
    home = Path.home()
    return home / "Downloads" / "Videos"


def is_douyin_url(url: str) -> bool:
    """检测是否为抖音URL"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    douyin_domains = [
        'douyin.com',
        'www.douyin.com',
        'v.douyin.com',
        'iesdouyin.com',
        'www.iesdouyin.com',
        'aweme.cn',
        'www.aweme.cn',
    ]
    return any(d in domain for d in douyin_domains)


def download_douyin_video(url, output_dir=None):
    """
    使用抖音专用下载器 (Playwright) 下载视频

    Args:
        url: 抖音视频URL
        output_dir: 输出目录

    Returns:
        (success: bool, message: str, output_path: str)
    """
    if output_dir is None:
        output_dir = get_default_output_dir()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 添加scripts目录到Python路径
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))

    try:
        import douyin_downloader

        print(f"📥 检测到抖音链接，使用 Playwright 专用下载器...")
        print(f"🔗 正在解析: {url}")

        result = douyin_downloader.download_douyin_sync(url, output_dir)

        return result['success'], result['message'], result['path']

    except ImportError as e:
        return False, f"抖音下载器组件未安装: {e}", None
    except Exception as e:
        return False, f"抖音下载出错: {str(e)}", None

def download_video(url, output_dir=None, quality='best', audio_only=False, cookies_file=None):
    """
    下载视频

    Args:
        url: 视频 URL
        output_dir: 输出目录 (默认 ~/Downloads/Videos)
        quality: 视频质量 (best/worst/best[ext=mp4]/worst[ext=mp4])
        audio_only: 仅下载音频

    Returns:
        (success: bool, message: str, output_path: str)
    """
    if output_dir is None:
        output_dir = get_default_output_dir()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "%(title)s.%(ext)s")

    # 获取 yt-dlp 命令
    yt_dlp_cmd = get_yt_dlp_command()
    if not yt_dlp_cmd:
        return False, "yt-dlp 不可用，请重新运行脚本", None

    # 如果没有指定 cookies 文件，尝试自动查找
    if cookies_file is None:
        cookies_file = get_cookies_file(url)

    # 构建命令
    cmd = yt_dlp_cmd + [
        '--no-warnings',
        '--newline',
        '-o', output_template,
    ]

    # 添加 cookies 支持
    if cookies_file and cookies_file.exists():
        cmd.extend(['--cookies', str(cookies_file)])
        print(f"🍪 使用 cookies: {cookies_file.name}")

    if audio_only:
        cmd.extend(['-x', '--audio-format', 'mp3'])
    else:
        cmd.extend(['-f', quality])

    cmd.append(url)

    try:
        print(f"📥 开始下载: {url}")
        print(f"📁 输出目录: {output_dir}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=None
        )

        if result.returncode == 0:
            # 尝试找到下载的文件
            files = list(output_dir.glob('*'))
            if files:
                # 按修改时间排序，获取最新的文件
                latest = max(files, key=os.path.getmtime)
                # 只返回最近5分钟内修改的文件
                import time
                if time.time() - os.path.getmtime(latest) < 300:
                    file_size = os.path.getsize(latest)
                    size_mb = file_size / (1024 * 1024)
                    return True, f"下载成功！文件: {latest.name} ({size_mb:.1f} MB)", str(latest)

            return True, "下载完成！", None
        else:
            error_msg = result.stderr or result.stdout or "未知错误"
            # 简化错误信息
            if 'HTTP Error 403' in error_msg or '403' in error_msg:
                error_msg = "访问被拒绝，视频可能有地区限制"
            elif 'Video unavailable' in error_msg:
                error_msg = "视频不可用或已被删除"
            elif 'ffmpeg' in error_msg and 'not found' in error_msg:
                error_msg = "需要 ffmpeg: brew install ffmpeg"
            elif 'Sign in' in error_msg or 'login' in error_msg:
                error_msg = "需要登录才能下载此视频"
            return False, f"下载失败: {error_msg}", None

    except subprocess.TimeoutExpired:
        return False, "下载超时", None
    except Exception as e:
        return False, f"下载出错: {str(e)}", None

def main():
    # 检查并安装 yt-dlp
    if not check_and_install_yt_dlp():
        sys.exit(1)

    # 检查 ffmpeg（可选）
    if not check_ffmpeg():
        print("⚠️  ffmpeg 未安装，某些视频可能无法下载")
        print("   安装: brew install ffmpeg")

    if len(sys.argv) < 2:
        print("用法: python3 download.py <视频URL> [输出目录]")
        print("示例: python3 download.py 'https://www.youtube.com/watch?v=xxx'")
        sys.exit(0)

    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    # 检测是否为抖音链接，使用专用下载器
    if is_douyin_url(url):
        success, message, output_path = download_douyin_video(url, output_dir)
    else:
        success, message, output_path = download_video(url, output_dir)

    print()
    if success:
        print(f"✅ {message}")
        if output_path:
            print(f"📂 文件位置: {output_path}")
    else:
        print(f"❌ {message}")
        sys.exit(1)

if __name__ == "__main__":
    main()
