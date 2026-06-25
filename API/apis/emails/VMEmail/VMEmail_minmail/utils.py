"""VMEmail 虚拟邮件(minmail.app)爬虫调用封装

本模块对 SpiderServices.VMEmail_minmail.main 中的爬虫类进行薄封装:
- 每次调用创建新的爬虫实例(无状态,线程安全)
- 统一捕获 RuntimeError 等异常,返回 (是否成功, 数据或错误信息) 二元组
- 对外提供 2 个与爬虫方法一一对应的函数

设计说明:
    minmail.app 通过 visitor_id(UUID) 标识用户身份,同一 visitor_id 对应同一临时邮箱。
    因此 API 层将 visitor_id 作为"会话凭证"由客户端保管,用于复用邮箱。
    get_emails 内部会先调用 generate_email(refresh=False) 建立会话上下文(设置 address),
    再查询邮件列表,使调用方无需关心爬虫内部的实例状态依赖。
"""
from SpiderServices.VMEmail_minmail.main import VMEmailMinmailSpider


def generate_email(visitor_id=None, expire=VMEmailMinmailSpider.DEFAULT_EXPIRE, refresh=False):
    """
    生成或获取临时邮箱。

    :param visitor_id: 访客标识(UUID)。不传则随机生成(对应新邮箱);
                       传入已知 visitor_id 可复用过期期内的邮箱
    :param expire: 邮箱过期时间(分钟),默认 1440(24小时)
    :param refresh: 是否强制生成新邮箱。True 时原邮箱及其邮件将被丢弃
    :return: tuple[bool, Any]
        - 成功: (True, {address, expire, remaining_time, visitor_id})
        - 失败: (False, 错误信息str)
    """
    spider = VMEmailMinmailSpider(visitor_id=visitor_id)
    try:
        data = spider.generate_email(expire=expire, refresh=refresh)
        return True, data
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'生成邮箱失败: {e}'


def get_emails(visitor_id):
    """
    获取指定 visitor_id 对应邮箱的全部邮件。

    :param visitor_id: 访客标识(UUID),必填。需为生成邮箱时返回的 visitor_id
    :return: tuple[bool, Any]
        - 成功: (True, list[dict] 邮件列表,无邮件时为 [])
        - 失败: (False, 错误信息str)
    """
    spider = VMEmailMinmailSpider(visitor_id=visitor_id)
    try:
        # 先建立会话上下文(获取当前邮箱,不强制刷新)
        spider.generate_email(refresh=False)
        emails = spider.get_emails()
        return True, emails
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'获取邮件失败: {e}'
