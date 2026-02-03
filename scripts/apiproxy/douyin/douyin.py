#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import requests
import json
import time
from typing import Tuple, Optional
from apiproxy.douyin import douyin_headers
from apiproxy.douyin.urls import Urls
from apiproxy.douyin.result import Result
from apiproxy.common import utils

utils_instance = utils.Utils()


def replaceStr(filenamestr: str) -> str:
    """替换非法字符，缩短字符长度，使其能成为文件名"""
    match = "([0-9A-Za-z\u4e00-\u9fa5]+)"
    result = re.findall(match, filenamestr)
    result = "".join(result).strip()
    if len(result) > 20:
        result = result[:20]
    return result


class Douyin(object):
    def __init__(self, cookies_dict=None):
        self.urls = Urls()
        self.result = Result()
        self.timeout = 10
        self.cookies_dict = cookies_dict or {}

    def _get_headers(self):
        """获取请求头，包含Cookie"""
        headers = douyin_headers.copy()
        if self.cookies_dict:
            # 将cookies字典转换为Cookie字符串
            cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies_dict.items()])
            headers['Cookie'] = cookie_str
        return headers

    def getShareLink(self, string):
        """从分享链接中提取网址"""
        return re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)[0]

    def getKey(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """获取资源标识 (资源类型, 资源ID)"""
        key = None
        key_type = None
        try:
            r = requests.get(url=url, headers=self._get_headers(), timeout=10)
        except Exception:
            return key_type, key

        urlstr = str(r.request.path_url)
        if "/user/" in urlstr:
            if '?' in r.request.path_url:
                for one in re.finditer(r'user\\/([\\d\\D]*)([?])', str(r.request.path_url)):
                    key = one.group(1)
            else:
                for one in re.finditer(r'user\\/([\\d\\D]*)', str(r.request.path_url)):
                    key = one.group(1)
            key_type = "user"
        elif "/video/" in urlstr:
            key = re.findall('video/(\\d+)?', urlstr)[0]
            key_type = "aweme"
        elif "/note/" in urlstr:
            key = re.findall('note/(\\d+)?', urlstr)[0]
            key_type = "aweme"
        elif "/mix/detail/" in urlstr:
            key = re.findall('/mix/detail/(\\d+)?', urlstr)[0]
            key_type = "mix"
        elif "/collection/" in urlstr:
            key = re.findall('/collection/(\\d+)?', urlstr)[0]
            key_type = "mix"
        elif "/music/" in urlstr:
            key = re.findall('music/(\\d+)?', urlstr)[0]
            key_type = "music"

        if key is None or key_type is None:
            return key_type, key
        return key_type, key

    def getAwemeInfo(self, aweme_id: str) -> dict:
        """获取作品信息"""
        if aweme_id is None:
            return {}
        start = time.time()
        while True:
            try:
                detail_params = f'aweme_id={aweme_id}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50&update_version_code=170400'
                jx_url = self.urls.POST_DETAIL + utils_instance.getXbogus(detail_params)
                response = requests.get(url=jx_url, headers=self._get_headers(), timeout=10)
                if len(response.text) == 0:
                    end = time.time()
                    if end - start > self.timeout:
                        return {}
                    continue
                datadict = json.loads(response.text)
                if datadict is not None and datadict.get("status_code") == 0:
                    break
                else:
                    return {}
            except Exception:
                end = time.time()
                if end - start > self.timeout:
                    return {}

        self.result.clearDict(self.result.awemeDict)
        awemeType = 0
        try:
            if datadict['aweme_detail']["images"] is not None:
                awemeType = 1
        except Exception:
            pass
        self.result.dataConvert(awemeType, self.result.awemeDict, datadict['aweme_detail'])
        return self.result.awemeDict

    def getVideoUrl(self, url: str) -> Optional[str]:
        """直接从URL获取视频下载地址（简化版）"""
        key_type, key = self.getKey(url)
        if key_type != "aweme" or not key:
            return None
        aweme_info = self.getAwemeInfo(key)
        if not aweme_info:
            return None
        try:
            url_list = aweme_info.get("video", {}).get("play_addr", {}).get("url_list", [])
            if url_list:
                return url_list[0]
        except Exception:
            pass
        return None

    def getDownloadInfo(self, url: str) -> dict:
        """获取下载信息，包含视频URL、标题、作者等"""
        key_type, key = self.getKey(url)
        if key_type != "aweme" or not key:
            return {}
        aweme_info = self.getAwemeInfo(key)
        if not aweme_info:
            return {}

        result = {
            "aweme_id": aweme_info.get("aweme_id", ""),
            "desc": aweme_info.get("desc", ""),
            "create_time": aweme_info.get("create_time", ""),
            "awemeType": aweme_info.get("awemeType", 0),
            "author": {
                "nickname": aweme_info.get("author", {}).get("nickname", ""),
                "sec_uid": aweme_info.get("author", {}).get("sec_uid", ""),
            },
            "statistics": aweme_info.get("statistics", {}),
        }

        if aweme_info.get("awemeType") == 0:  # 视频
            url_list = aweme_info.get("video", {}).get("play_addr", {}).get("url_list", [])
            result["video_url"] = url_list[0] if url_list else None
            cover_list = aweme_info.get("video", {}).get("cover", {}).get("url_list", [])
            result["cover_url"] = cover_list[0] if cover_list else None
        elif aweme_info.get("awemeType") == 1:  # 图集
            images = aweme_info.get("images", [])
            result["images"] = [img.get("url_list", [""])[0] for img in images if img.get("url_list")]

        # 音乐
        music_url_list = aweme_info.get("music", {}).get("play_url", {}).get("url_list", [])
        result["music_url"] = music_url_list[0] if music_url_list else None
        result["music_title"] = aweme_info.get("music", {}).get("title", "")

        return result


if __name__ == "__main__":
    pass
