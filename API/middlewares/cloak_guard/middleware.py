"""cloak_guard 主中间件：开关 → 路径排除 → IP 白名单 → 分类 → 动作执行 → 标记注入

配置项（settings.py）:
    CLOAK_GUARD_ENABLED       = True                # 是否启用（默认 False）
    CLOAK_GUARD_ACTIONS       = {                   # 类型动作策略
        'spider':  {'action': 'pass'},              #   spider  → 放行
        'human':   {'action': 'redirect', 'url': 'https://example.com/'},  # human → 302
        'direct':  {'action': 'not_found'},         #   direct  → 404
        'unknown': {'action': 'render', 'html': '<h1>403</h1>'},           # unknown → 自定义内容
    }
    CLOAK_GUARD_WHITELIST     = ['127.0.0.1', '192.168.1.0/24']  # IP 白名单（支持 CIDR），命中直接放行
    CLOAK_GUARD_EXEMPT_PATHS  = ['/admin', '/static', '/api']    # 路径前缀白名单，命中直接放行

标记注入（放行时视图也可用）:
    request.guard_type  - 'spider'/'human'/'direct'/'unknown'
    request.is_spider / is_human / is_direct / is_unknown
"""
import ipaddress
import logging

from django.conf import settings

from .actions import build_response, resolve_action
from .classifier import classify

logger = logging.getLogger('cloak_guard')


class CloakGuardMiddleware:
    """本地判定请求类型，按配置执行 放行 / 302 / 404 / render"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 未启用 → 直接放行
        if not getattr(settings, 'CLOAK_GUARD_ENABLED', False):
            return self.get_response(request)

        # 路径排除：后台/静态/接口等前缀命中 → 放行
        if self._is_exempt_path(request.path):
            return self.get_response(request)

        # IP 白名单（支持单个 IP 与 CIDR）→ 放行
        ip = request.META.get('REMOTE_ADDR', '')
        if self._is_whitelisted_ip(ip):
            return self.get_response(request)

        # 分类 + 标记注入（放行时视图层也可基于标记差异化渲染）
        req_type = classify(request)
        request.guard_type = req_type
        request.is_spider = (req_type == 'spider')
        request.is_human = (req_type == 'human')
        request.is_direct = (req_type == 'direct')
        request.is_unknown = (req_type == 'unknown')

        # 解析并执行动作；返回非 None 表示已拦截
        action, cfg = resolve_action(req_type, getattr(settings, 'CLOAK_GUARD_ACTIONS', None))
        response = build_response(action, cfg)
        if response is not None:
            logger.info('cloak_guard type=%s action=%s', req_type, action)
            return response

        logger.info('cloak_guard type=%s action=pass', req_type)
        return self.get_response(request)

    @staticmethod
    def _is_exempt_path(path):
        prefixes = getattr(settings, 'CLOAK_GUARD_EXEMPT_PATHS', []) or []
        return any(path.startswith(p) for p in prefixes)

    @staticmethod
    def _is_whitelisted_ip(ip):
        whitelist = getattr(settings, 'CLOAK_GUARD_WHITELIST', []) or []
        if not whitelist or not ip:
            return False
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for item in whitelist:
            try:
                if '/' in item:
                    if ip_obj in ipaddress.ip_network(item, strict=False):
                        return True
                elif ip_obj == ipaddress.ip_address(item):
                    return True
            except ValueError:
                continue
        return False
