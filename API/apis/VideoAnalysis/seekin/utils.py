"""Seekin 视频解析(seekin.ai)爬虫调用封装

本模块对 SpiderServices.VideoAnalysis.seekin.main 中的爬虫类进行薄封装:
- 每次调用创建新的爬虫实例(无状态,线程安全)
- 统一捕获 RuntimeError 等异常,返回 (是否成功, 数据或错误信息) 二元组
- 对外提供 3 个与爬虫方法一一对应的函数(抖音/小红书/哔哩哔哩)
  三平台签名与返回结构一致,内部复用 _parse_platform 避免重复
"""
from SpiderServices.VideoAnalysis.seekin.main import SeekinVideoAnalysis


def _parse_platform(method_name, share_text):
    """
    通用解析包装器:创建爬虫实例并调用指定平台方法,统一捕获异常。

    :param method_name: 爬虫实例方法名(parse_video/parse_xiaohongshu/parse_bilibili)
    :param share_text: 分享文本(完整复制内容,含链接和描述)
    :return: tuple[bool, Any]
        - 成功: (True, {title, cover, duration, medias, images})
        - 失败: (False, 错误信息str)
    """
    spider = SeekinVideoAnalysis()
    try:
        method = getattr(spider, method_name)
        data = method(share_text)
        return True, data
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'视频解析失败: {e}'


def parse_video(share_text):
    """解析抖音视频,返回无水印下载链接。"""
    return _parse_platform('parse_video', share_text)


def parse_xiaohongshu(share_text):
    """解析小红书内容,返回视频或图文下载链接。"""
    return _parse_platform('parse_xiaohongshu', share_text)


def parse_bilibili(share_text):
    """解析哔哩哔哩视频,返回下载链接。"""
    return _parse_platform('parse_bilibili', share_text)
