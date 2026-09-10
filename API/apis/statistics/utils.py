"""API 调用统计服务 - 业务封装

查询实现复用 API/common/api_stats_query.py（与超管看板、文档中心同一份口径），
本层只做「公开口径」的整理：补上服务中文名，去掉项目/失败率/耗时等敏感维度。
"""
from API.common import api_stats_query
from API.website.services import SERVICES, localize as localize_services


def service_names():
    """服务前缀 -> 服务名称（按当前语言翻译，与官网服务清单同源）"""
    return {svc['url_prefix']: svc['name'] for svc in localize_services(SERVICES)}


def api_calls(path):
    """某个接口的公开调用量：累计次数 + 今日次数"""
    return api_stats_query.public_path_calls(path)


def service_calls():
    """各服务的公开调用量（累计 + 今日），按累计降序；附服务名称"""
    names = service_names()
    rows = api_stats_query.public_service_calls()
    for row in rows:
        row['name'] = names.get(row['service'], row['service'])
    return rows
