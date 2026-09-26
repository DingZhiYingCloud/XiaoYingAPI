"""555电影 线路爬虫调用封装

本模块对 SpiderServices.movies.movie_555.main 中的 Movie555Spider 进行薄封装：
- 每次调用创建新的爬虫实例（无状态，线程安全）
- 统一捕获异常，返回 (是否成功, 数据或错误信息) 二元组
- 与爬虫对外方法一一对应：categories / filters / home / list / detail / play / search
"""
from SpiderServices.movies.movie_555.main import Movie555Spider


def _run(action, fn):
    """
    执行爬虫操作，统一异常处理。

    :param action: 操作名称（用于错误提示前缀）
    :param fn: 接收爬虫实例的回调
    :return: tuple[bool, Any] (True, data) 或 (False, message)
    """
    spider = Movie555Spider()
    try:
        return True, fn(spider)
    except Exception as e:
        return False, f"{action}失败: {e}"


def get_categories():
    """获取分类列表（主分类 + 子分类 + 专题）"""
    return _run("获取分类", lambda s: s.get_categories())


def get_home():
    """获取首页聚合（轮播 + 各推荐区块）"""
    return _run("获取首页", lambda s: s.get_home())


def get_list(type_id, page=1, order=None, year=None, area=None, genre=None, lang=None):
    """
    获取分类列表（地区 / 题材 / 语言 / 年份 / 排序可任意组合）。

    :param type_id: 分类 id（1=电影 2=连续剧 3=综艺纪录 4=动漫 124=福利 126=擦边短剧，或子分类 id）
    :param page: 页码，从 1 开始
    :param order: 排序方式 time/hits/score
    :param year: 年份，如 2026
    :param area: 地区，如 大陆（取值见「筛选条件」接口）
    :param genre: 题材，如 动作（取值见「筛选条件」接口）
    :param lang: 语言，如 国语（取值见「筛选条件」接口）
    """
    return _run("获取列表", lambda s: s.get_list(
        type_id, page=page, order=order, year=year, area=area, genre=genre, lang=lang))


def get_filters(type_id):
    """获取某分类可用的筛选条件（子分类 / 地区 / 题材 / 语言 / 年份 / 排序）"""
    return _run("获取筛选条件", lambda s: s.get_filters(type_id))


def get_detail(vod_id):
    """获取影片详情（含播放源与选集）"""
    return _run("获取详情", lambda s: s.get_detail(vod_id))


def get_play(vod_id, sid, nid):
    """获取 m3u8 播放地址"""
    return _run("获取播放地址", lambda s: s.get_play(vod_id, sid, nid))


def search(keyword):
    """搜索影片"""
    return _run("搜索", lambda s: s.search(keyword))
