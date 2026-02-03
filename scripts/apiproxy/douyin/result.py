#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
import copy

class Result(object):
    def __init__(self):
        # 作者信息
        self.authorDict = {
            "avatar_thumb": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "avatar": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_url": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "favoriting_count": "",
            "follower_count": "",
            "following_count": "",
            "nickname": "",
            "prevent_download": "",
            "sec_uid": "",
            "secret": "",
            "short_id": "",
            "signature": "",
            "total_favorited": "",
            "uid": "",
            "unique_id": "",
            "user_age": "",
        }
        # 图片信息
        self.picDict = {
            "height": "",
            "mask_url_list": "",
            "uri": "",
            "url_list": [],
            "width": ""
        }
        # 音乐信息
        self.musicDict = {
            "cover_hd": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_large": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_medium": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_thumb": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "owner_handle": "",
            "owner_id": "",
            "owner_nickname": "",
            "play_url": {
                "height": "",
                "uri": "",
                "url_key": "",
                "url_list": [],
                "width": ""
            },
            "title": "",
        }
        # 视频信息
        self.videoDict = {
            "play_addr": {
                "uri": "",
                "url_list": [],
            },
            "cover_original_scale": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "dynamic_cover": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "origin_cover": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            }
        }
        # mix信息
        self.mixInfo = {
            "cover_url": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": 720
            },
            "ids": "",
            "is_serial_mix": "",
            "mix_id": "",
            "mix_name": "",
            "mix_pic_type": "",
            "mix_type": "",
            "statis": {
                "current_episode": "",
                "updated_to_episode": ""
            }
        }
        # 作品信息
        self.awemeDict = {
            "create_time": "",
            "awemeType": "",  # 0=视频, 1=图集, 2=直播
            "aweme_id": "",
            "author": self.authorDict,
            "desc": "",
            "images": [],
            "music": self.musicDict,
            "mix_info": self.mixInfo,
            "video": self.videoDict,
            "statistics": {
                "admire_count": "",
                "collect_count": "",
                "comment_count": "",
                "digg_count": "",
                "play_count": "",
                "share_count": ""
            }
        }
        # 用户作品信息
        self.awemeList = []
        # 直播信息
        self.liveDict = {
            "awemeType": "",
            "status": "",
            "title": "",
            "cover": "",
            "avatar": "",
            "user_count": "",
            "nickname": "",
            "sec_uid": "",
            "display_long": "",
            "flv_pull_url": "",
            "partition": "",
            "sub_partition": "",
            "flv_pull_url0": "",
        }

    def dataConvert(self, awemeType, dataNew, dataRaw):
        for item in dataNew:
            try:
                if item == "create_time":
                    dataNew['create_time'] = time.strftime(
                        "%Y-%m-%d %H.%M.%S", time.localtime(dataRaw['create_time']))
                    continue
                if item == "awemeType":
                    dataNew["awemeType"] = awemeType
                    continue
                if item == "images":
                    if awemeType == 1:
                        for image in dataRaw[item]:
                            for i in image:
                                self.picDict[i] = image[i]
                            self.awemeDict["images"].append(copy.deepcopy(self.picDict))
                        continue
                if item == "video":
                    if awemeType == 0:
                        self.dataConvert(awemeType, dataNew[item], dataRaw[item])
                    continue
                if item == "avatar":
                    for i in dataNew[item]:
                        if i == "url_list":
                            for j in self.awemeDict["author"]["avatar_thumb"]["url_list"]:
                                dataNew[item][i].append(j.replace("100x100", "1080x1080"))
                        elif i == "uri":
                            dataNew[item][i] = self.awemeDict["author"]["avatar_thumb"][i].replace("100x100", "1080x1080")
                        else:
                            dataNew[item][i] = self.awemeDict["author"]["avatar_thumb"][i]
                    continue
                if item == "cover_url":
                    self.dataConvert(awemeType, dataNew[item], dataRaw[item][0])
                    continue
                if item == "play_addr":
                    dataNew[item]["uri"] = dataRaw["bit_rate"][0]["play_addr"]["uri"]
                    dataNew[item]["url_list"] = copy.deepcopy(dataRaw["bit_rate"][0]["play_addr"]["url_list"])
                    continue
                if isinstance(dataNew[item], dict):
                    self.dataConvert(awemeType, dataNew[item], dataRaw[item])
                else:
                    dataNew[item] = dataRaw[item]
            except Exception:
                pass

    def clearDict(self, data):
        for item in data:
            if isinstance(data[item], dict):
                self.clearDict(data[item])
            elif isinstance(data[item], list):
                data[item] = []
            else:
                data[item] = ""

if __name__ == '__main__':
    pass
