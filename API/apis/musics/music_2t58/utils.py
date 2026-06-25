"""爱听音乐网(2t58.com)爬虫调用封装

本模块对 SpiderServices.Music_2t58.main 中的爬虫类进行薄封装:
- 每次调用创建新的爬虫实例,避免多线程下 session 共享导致的竞态问题
- 统一捕获 requests 异常,返回 (是否成功, 数据或错误信息) 二元组
- 对外提供 4 个与爬虫方法一一对应的函数
"""
import requests

from SpiderServices.Music_2t58.main import Music2t58Spider


def _run(method_name, *args, **kwargs):
    """
    通用调用包装器:创建爬虫实例并调用指定方法,统一捕获网络异常。

    :param method_name: 爬虫实例方法名
    :param args/kwargs: 透传给爬虫方法的参数
    :return: tuple[bool, Any]  (是否成功, 成功时为数据dict, 失败时为错误信息str)
    """
    spider = Music2t58Spider()
    try:
        method = getattr(spider, method_name)
        data = method(*args, **kwargs)
        return True, data
    except requests.RequestException as e:
        # 网络层异常(连接超时、DNS失败、HTTP错误等)
        return False, f'请求音乐网站失败: {e}'
    except Exception as e:
        # 其他未预期异常(解析失败等)
        return False, f'数据解析失败: {e}'


def fetch_home_data():
    """获取首页数据(热门歌手/歌曲飙升榜/流行趋势榜)。无参数。"""
    return _run('get_home_data')


def fetch_singer_detail(url):
    """获取歌手详情页数据。:param url: 歌手歌曲列表页完整URL"""
    return _run('get_singer_detail', url)


def fetch_song_detail(url):
    """获取歌曲详情页数据。:param url: 歌曲详情页完整URL"""
    return _run('get_song_detail', url)


def search_music(keyword, page=1):
    """搜索音乐。:param keyword: 关键词, :param page: 页码(默认1)"""
    return _run('search_music', keyword, page=page)
