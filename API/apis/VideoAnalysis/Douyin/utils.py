"""抖音视频/图文解析爬虫调用封装

本模块对 SpiderServices.VideoAnalysis.Douyin.home 中的 DouyinVideoAnalysis 进行薄封装:
- 每次调用创建新的爬虫实例(无状态,线程安全)
- 统一捕获 RuntimeError 等异常,返回 (是否成功, 数据或错误信息) 二元组
- 对外提供 1 个与爬虫方法对应的函数: parse_video(解析抖音视频/图文)
"""
from SpiderServices.VideoAnalysis.Douyin.home import DouyinVideoAnalysis


def parse_video(share_text):
    """
    解析抖音视频/图文,返回无水印下载信息。

    :param share_text: 抖音分享文本(完整复制内容,含链接和描述),
        支持纯数字 aweme_id、短链(v.douyin.com)、完整视频页链接
    :return: tuple[bool, Any]
        - 成功: (True, {title, cover, duration, medias, images})
        - 失败: (False, 错误信息str)
    """
    spider = DouyinVideoAnalysis()
    try:
        data = spider.parse(share_text)
        return True, data
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'视频解析失败: {e}'
