"""统一「对外错误文案」工具

设计意图：
    对外只回一句可读的「人话」，绝不把原始异常文本回显给调用方。原始异常里往往带着
    SQL 原文、`HTTPSConnectionPool(host=...)` 这类连接串、内部类名与堆栈——这些对调用方
    既无意义，也属于内部实现细节的泄露。原始异常（含堆栈）只写进 logs/error.log，
    排查时按 request_id 关联即可。

用法：
    from API.common.errors import safe_error
    try:
        ...
    except Exception as exc:
        return False, safe_error('创建友情链接', exc)
"""
import logging

# 与 API/apis/user_center/sign.py 保持一致，便于按 request_id 关联日志
logger = logging.getLogger('api.request')


def safe_error(action: str, exc: Exception) -> str:
    """把内部异常转成给调用方看的「人话」，原始异常只进日志。

    :param action: 动作名（如「创建友情链接」「查询音乐」），用于拼装对外文案与日志定位
    :param exc: 捕获到的内部异常，仅用于写日志，其文本不出现在返回值里
    :return: 固定对外文案 f'{action}失败，请稍后重试'
    """
    logger.exception('%s', action)
    return f'{action}失败，请稍后重试'
