"""VMEmail 虚拟邮件(mail.cx)爬虫调用封装

本模块对 SpiderServices.VMEmail_mailcx.main 中的爬虫类进行薄封装:
- 每次调用创建新的爬虫实例(无状态, 线程安全)
- 统一捕获异常, 返回 (是否成功, 数据或错误信息) 二元组
- 对外函数与爬虫公开方法一一对应

会话机制:
    mail.cx 无服务端会话, 邮箱地址本身即邮箱唯一标识, 直接查询即可收信;
    client_id(X-Client-ID) 标识客户端身份, 未传时爬虫自动生成 UUID。
    generate_email 会把 client_id 一并返回, 客户端可保存后在其余接口回传以复用同一身份。
"""
from SpiderServices.VMEmail_mailcx.main import VMEmailMailcxSpider

# 官网支持的后缀域名 / 默认域名：唯一来源为爬虫类常量，避免在多处重复定义
SUPPORTED_DOMAINS = list(VMEmailMailcxSpider.DEFAULT_DOMAINS)
DEFAULT_DOMAIN = VMEmailMailcxSpider.DEFAULT_DOMAIN


def list_domains():
    """获取官网当前可用的全部后缀域名。

    :return: tuple[bool, Any]
        - 成功: (True, list[str]) 域名列表, 如 ["ddker.com", "9k3r.com", "uqu.me"]
        - 失败: (False, 错误信息 str)
    """
    spider = VMEmailMailcxSpider()
    try:
        return True, spider.list_domains()
    except Exception as e:
        return False, f'获取域名列表失败: {e}'


def generate_email(domain=None, client_id=None):
    """生成一个临时邮箱地址(本地随机生成, 无需服务端注册)。

    :param domain: 指定后缀域名, 不传使用默认域名(uqu.me)
    :param client_id: 客户端标识, 不传则爬虫随机生成 UUID
    :return: tuple[bool, Any]
        - 成功: (True, {address, domain, client_id})
        - 失败: (False, 错误信息 str)
    """
    spider = VMEmailMailcxSpider(client_id=client_id)
    try:
        return True, spider.generate_email(domain=domain)
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f'生成邮箱失败: {e}'


def get_emails(address, since=None, client_id=None):
    """获取指定邮箱的邮件列表(长轮询, 无新邮件时上游挂起约 25 秒后返回空列表)。

    :param address: 邮箱地址, 必填
    :param since: 增量时间戳(秒), 不传返回当前全部邮件, 传入后仅返回该时间之后的新邮件
    :param client_id: 客户端标识, 不传则爬虫随机生成 UUID
    :return: tuple[bool, Any]
        - 成功: (True, list[dict] 邮件摘要列表, 无邮件时为 [])
        - 失败: (False, 错误信息 str)
    """
    spider = VMEmailMailcxSpider(client_id=client_id)
    try:
        return True, spider.get_emails(address=address, since=since)
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'获取邮件失败: {e}'


def get_email_detail(email_id, client_id=None):
    """获取单封邮件的完整详情(含完整正文与附件)。

    :param email_id: 邮件 id, 来自 get_emails 返回的 id 字段
    :param client_id: 客户端标识, 不传则爬虫随机生成 UUID
    :return: tuple[bool, Any]
        - 成功: (True, dict) 含 id / from / from_email / from_name / to /
                subject / text_body / html_body / attachments / date / created_at
        - 失败: (False, 错误信息 str)
    """
    spider = VMEmailMailcxSpider(client_id=client_id)
    try:
        return True, spider.get_email_detail(email_id)
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:
        return False, f'获取邮件详情失败: {e}'
