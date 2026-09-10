"""文档中心左侧菜单：中间件 + 上下文处理器（自动注入，模板零手工维护）

工作方式（与用户侧「左侧菜单」模式一致，但数据源自动来自服务文档注册表）：
1. DocsMenuMiddleware 仅对 /docs/* 请求构建一次菜单并挂到 request.docs_menu；
2. docs_menu_context 将其注入全站模板变量 docs_menu；
3. 模板 include docs/_sidebar.html 渲染，docs.js 按当前 URL/hash 自动高亮与展开。
"""
from .docs.menu import build_docs_menu


class DocsMenuMiddleware:
    """拦截 /docs/* 请求，把自动生成的菜单挂到 request.docs_menu"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/docs/'):
            # 每次构建开销极小（数据源为常量），不做缓存以保证新增服务即时可见
            request.docs_menu = build_docs_menu()
        return self.get_response(request)


def docs_menu_context(request):
    """模板上下文：
    - docs_menu：左侧服务菜单（None 表示非文档页）
    - is_superadmin：是否为可用的超级管理员（Django is_superuser，控制超管子菜单显隐）
    """
    user = getattr(request, 'user', None)
    return {
        'docs_menu': getattr(request, 'docs_menu', None),
        'is_superadmin': bool(user and user.is_authenticated and user.is_superuser and user.is_active),
    }
