"""4759蜘蛛IP验证 - 爬虫调用封装

本模块对 SpiderServices.SpiderVerification_4759.main 中的 SpiderVerification 进行薄封装：
- 每次调用创建新的爬虫实例（无状态，线程安全）
- 统一捕获异常，返回 (是否成功, 数据或错误信息) 二元组
"""
from SpiderServices.SpiderVerification_4759.main import SpiderVerification


def verify_ip(ip):
    """验证指定 IP 是否属于搜索引擎爬虫

    :param ip: 待验证的 IP 地址（IPv4 或 IPv6）
    :return: tuple[bool, Any]  (是否成功, 成功时为验证结果 dict, 失败时为错误信息)
    """
    spider = SpiderVerification()
    try:
        data = spider.verify(ip)
        return True, data
    except ValueError as e:
        return False, str(e)
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f"验证失败: {e}"
