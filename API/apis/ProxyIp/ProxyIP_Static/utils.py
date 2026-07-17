"""ProxyIP_Static 爬虫调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 StaticIPService 进行包装:
- 每次调用创建新的服务实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
"""
import sys
import os

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ProxyIp.ProxyIP_Static.home import StaticIPService


def _make_service(json_path: str = None) -> StaticIPService:
    """创建 StaticIPService 实例"""
    return StaticIPService(json_path=json_path)


def get_proxies(json_path: str = None) -> tuple:
    """获取全部静态代理列表

    :param json_path: 自定义 JSON 文件路径（可选）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        service = _make_service(json_path)
        result = service.get_proxies()
        return True, result
    except Exception as e:
        return False, f'get_proxies 调用异常: {e}'


def add_proxy(ip: str, port: str, username: str = "", password: str = "", json_path: str = None) -> tuple:
    """新增静态代理

    :param ip: IP 地址
    :param port: 端口
    :param username: 用户名（可选）
    :param password: 密码（可选）
    :param json_path: 自定义 JSON 文件路径（可选）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        service = _make_service(json_path)
        result = service.add_proxy(ip=ip, port=port, username=username, password=password)
        return True, result
    except Exception as e:
        return False, f'add_proxy 调用异常: {e}'


def delete_proxy(ip: str, port: str, json_path: str = None) -> tuple:
    """删除静态代理

    :param ip: IP 地址
    :param port: 端口
    :param json_path: 自定义 JSON 文件路径（可选）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        service = _make_service(json_path)
        result = service.delete_proxy(ip=ip, port=port)
        return True, result
    except Exception as e:
        return False, f'delete_proxy 调用异常: {e}'


def reload_proxies(json_path: str = None) -> tuple:
    """重新从 JSON 文件加载代理列表

    :param json_path: 自定义 JSON 文件路径（可选）
    :return: (True, dict) 或 (False, error_msg)
    """
    try:
        service = _make_service(json_path)
        service.reload()
        count = service.count
        return True, {"code": 0, "message": f"重载成功，当前共 {count} 条代理", "data": {"count": count}}
    except Exception as e:
        return False, f'reload 调用异常: {e}'
