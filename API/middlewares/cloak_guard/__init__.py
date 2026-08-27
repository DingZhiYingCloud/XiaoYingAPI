"""cloak_guard - 请求访问策略守卫（斗篷）中间件

判定纯本地完成（零网络依赖）；render 动作可按需从本地文件 / 远程 url / iframe 域名
获取渲染内容。按「类型 → 动作」策略对请求执行 放行 / 302 / 404 / render。
"""
__version__ = '1.1.0'

from .middleware import CloakGuardMiddleware

__all__ = ['CloakGuardMiddleware', '__version__']
