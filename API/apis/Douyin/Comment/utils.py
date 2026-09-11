"""抖音评论发布爬虫调用封装

本模块对 SpiderServices.Douyin.Comment.home 中的 DouyinCommentPublisher 进行薄封装:
- 每次调用创建新的爬虫实例(无状态,线程安全)
- 统一捕获 RuntimeError 等异常,返回 (是否成功, 数据或错误信息) 二元组
- 对外提供 1 个与爬虫方法对应的函数: publish_comment(发布评论)
"""
from SpiderServices.Douyin.Comment.home import DouyinCommentPublisher


def publish_comment(cookie, aweme_id, text):
    """发布一条抖音一级评论

    :param cookie: 抖音登录 Cookie(完整字符串)
    :param aweme_id: 目标视频 ID
    :param text: 评论内容
    :return: tuple[bool, Any]
        - 成功: (True, {cid, text, create_time})
        - 失败: (False, 错误信息str)
    """
    spider = DouyinCommentPublisher()
    try:
        data = spider.publish_comment(cookie, aweme_id, text)
        return True, data
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'评论发布失败: {e}'
