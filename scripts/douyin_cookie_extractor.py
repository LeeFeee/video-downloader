#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抖音Cookie自动提取器
使用Playwright自动登录并提取Cookie
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional
import time

try:
    from playwright.async_api import async_playwright, Browser, Page
except ImportError:
    print("请安装必要的依赖: pip install playwright")
    print("并运行: playwright install chromium")
    sys.exit(1)


class CookieExtractor:
    """Cookie提取器"""

    def __init__(self):
        self.cookies = {}

    async def extract_cookies(self, headless: bool = False) -> Dict:
        """提取Cookie

        Args:
            headless: 是否无头模式运行
        """
        print("\n" + "="*50)
        print("抖音Cookie自动提取器")
        print("="*50)
        print("\n将自动打开浏览器，请在浏览器中完成登录\n")

        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            # 创建上下文（模拟真实浏览器）
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            # 添加初始化脚本（隐藏自动化特征）
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            # 创建页面
            page = await context.new_page()
            try:
                # 访问抖音登录页（增加超时时间到60秒，网络慢也能加载）
                print("正在打开抖音登录页面...")
                await page.goto('https://www.douyin.com', wait_until='domcontentloaded', timeout=60000)

                # 等待用户登录
                print("\n" + "="*50)
                print("请在浏览器中完成登录操作")
                print("="*50)
                print("登录方式：")
                print("  1. 扫码登录（推荐）- 打开抖音App扫二维码")
                print("  2. 手机号登录")
                print("  3. 第三方账号登录（微信/QQ/微博）")
                print("\n⏱️  最长等待时间: 5分钟")
                print("💡 提示: 登录成功后会自动提取Cookie\n")

                # 等待登录成功的标志
                logged_in = await self._wait_for_login(page)
                if logged_in:
                    print("\n登录成功！正在提取Cookie...")

                    # 提取Cookie
                    cookies = await context.cookies()
                    # 转换为字典格式
                    cookie_dict = {}
                    cookie_string = ""
                    for cookie in cookies:
                        if 'douyin.com' in cookie.get('domain', ''):
                            cookie_dict[cookie['name']] = cookie['value']
                            cookie_string += f"{cookie['name']}={cookie['value']}; "

                    self.cookies = cookie_dict

                    # 显示重要Cookie
                    print("\n提取到的关键Cookie:")
                    important_cookies = ['sessionid', 'sessionid_ss', 'ttwid', 'passport_csrf_token', 'msToken']
                    for name in important_cookies:
                        if name in cookie_dict:
                            value = cookie_dict[name]
                            print(f"  {name}: {value[:20]}..." if len(value) > 20 else f"  {name}: {value}")

                    # 保存Cookie到文件
                    self._save_cookies(cookie_dict, cookie_string)
                    print("\nCookie已保存到配置文件")
                    return cookie_dict
                else:
                    print("\n登录超时或失败")
                    return {}
            except Exception as e:
                print(f"\n提取Cookie失败: {e}")
                return {}
            finally:
                await browser.close()

    async def _wait_for_login(self, page: Page, timeout: int = 300) -> bool:
        """等待用户登录

        Args:
            page: 页面对象
            timeout: 超时时间（秒），默认5分钟
        """
        start_time = time.time()
        last_print_time = 0

        while time.time() - start_time < timeout:
            try:
                # 检查是否有用户头像
                avatar = await page.query_selector('div[class*="avatar"]')
                if avatar:
                    await asyncio.sleep(2)  # 等待Cookie完全加载
                    return True
                # 检查URL是否包含用户ID
                current_url = page.url
                if '/user/' in current_url:
                    await asyncio.sleep(2)
                    return True
                # 检查是否有特定的登录后元素
                user_menu = await page.query_selector('[class*="user-info"]')
                if user_menu:
                    await asyncio.sleep(2)
                    return True
            except:
                pass

            await asyncio.sleep(2)

            # 每10秒显示一次进度，避免刷屏
            current_time = time.time()
            if current_time - last_print_time >= 10:
                elapsed = int(current_time - start_time)
                remaining = timeout - elapsed
                minutes = remaining // 60
                seconds = remaining % 60
                print(f"⏳ 等待登录中... 已等待 {elapsed}秒，剩余 {minutes}分{seconds}秒")
                last_print_time = current_time

        return False

    def _save_cookies(self, cookies: Dict, cookie_string: str):
        """保存Cookie到文件（同时保存Netscape格式和简单格式）"""
        save_dir = Path.home() / "Downloads"
        save_dir.mkdir(parents=True, exist_ok=True)

        # 保存Netscape格式（用于yt-dlp）
        netscape_file = save_dir / "douyin.com_cookies.txt"
        with open(netscape_file, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This file is generated by douyin cookie extractor\n\n")
            for name, value in cookies.items():
                # Netscape格式: domain \t flag \t path \t secure \t expiration \t name \t value
                f.write(f".douyin.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
        print(f"✅ Netscape格式Cookie已保存到: {netscape_file}")

        # 保存简单格式（用于程序读取）
        simple_file = save_dir / "douyin_cookies_simple.txt"
        with open(simple_file, 'w', encoding='utf-8') as f:
            f.write(cookie_string.strip())
        print(f"✅ 简单格式Cookie已保存到: {simple_file}")


async def main():
    """主函数"""
    extractor = CookieExtractor()

    print("\n请选择提取方式：")
    print("1. 自动登录提取（推荐）")
    print("2. 无头模式（不显示浏览器）")

    choice = input("请选择 [1/2] (默认1): ").strip() or "1"

    if choice == "2":
        cookies = await extractor.extract_cookies(headless=True)
    else:
        cookies = await extractor.extract_cookies(headless=False)

    if cookies:
        print("\nCookie提取完成！")
        print("您现在可以运行下载器了")
    else:
        print("\n未能提取Cookie")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户取消操作")
    except Exception as e:
        print(f"\n程序异常: {e}")
