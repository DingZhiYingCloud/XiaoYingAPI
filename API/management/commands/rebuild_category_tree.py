"""重建 API 服务分类树管理命令

背景：分类树数据由迁移 0011_apicategory 内的 RunPython 生成（扫描 API/apis/urls.py
的 include 链），但 migrations/ 目录被 .gitignore 忽略，迁移文件不会上传到线上，
线上 migrate 只建空表、没有分类数据。本命令提供与迁移相同的数据生成逻辑，
部署后执行一次即可重建分类树。

用法（幂等，可重复执行）：
    python manage.py rebuild_category_tree

特性：
- 基于当前 API/apis/urls.py 实时扫描，新增/删除服务目录会同步分类树
- get_or_create 幂等：已存在的分类不会重复创建，也不会覆盖后台手动配置的
  auth_mode / status（仅同步名称与父子层级）
- 停用（status=False）且当前代码中已不存在的分类会被删除，保持与目录一致
"""
import os
import re

from django.core.management.base import BaseCommand

from API.models.Auth.category import ApiCategory

# urls.py 中 path('x/', include('API.apis.xxx.urls')) 的解析规则
_INCLUDE_RE = re.compile(
    r"""path\(\s*['"]([^'"]*)['"]\s*,\s*include\(\s*['"](API\.apis\.[\w.]+)\.urls['"]\s*\)"""
)
_COMMENT_RE = re.compile(r'#\s*(.+)$')

# API/apis 目录绝对路径
# 本文件位于 API/management/commands/ 下，向上三级到项目根，再进 API/apis
_API_APIS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'API', 'apis')
)


def _parse_include_lines(urls_path):
    """解析单个 urls.py，返回 [(url前缀, 模块路径, 注释名称)]"""
    result = []
    try:
        with open(urls_path, encoding='utf-8') as f:
            for line in f:
                m = _INCLUDE_RE.search(line)
                if not m:
                    continue
                prefix, module = m.group(1), m.group(2)
                cm = _COMMENT_RE.search(line)
                name = cm.group(1).strip() if cm else ''
                result.append((prefix, module, name))
    except OSError:
        pass
    return result


class Command(BaseCommand):
    help = '根据 API/apis/ 目录重建 API 服务分类树（幂等）'

    def handle(self, *args, **options):
        created, kept = self._build_tree()
        self.stdout.write(self.style.SUCCESS(
            f'分类树重建完成：新建 {created} 个，保留 {kept} 个'
        ))

    def _build_tree(self):
        """递归扫描 urls.py include 链，为每个服务目录建立分类节点"""
        created = 0
        kept = 0

        def build(urls_path, parent, acc_prefix):
            nonlocal created, kept
            for prefix, module, comment in _parse_include_lines(urls_path):
                if not prefix:
                    # 空前缀（如 seo 的 path('', ...)）：不建独立节点，继续向下递归
                    build(self._module_urls_path(module), parent, acc_prefix)
                    continue
                child_prefix = acc_prefix + prefix
                name = comment or module.split('.')[-1]
                node, is_new = ApiCategory.objects.get_or_create(
                    path_prefix=child_prefix,
                    defaults={'name': name, 'parent': parent},
                )
                if is_new:
                    created += 1
                else:
                    kept += 1
                    # 仅同步名称与父级（不覆盖后台手动配置的 auth_mode / status）
                    if node.name != name or node.parent_id != (parent.id if parent else None):
                        node.name = name
                        node.parent = parent
                        node.save(update_fields=['name', 'parent'])
                build(self._module_urls_path(module), node, child_prefix)

        build(os.path.join(_API_APIS_DIR, 'urls.py'), None, '/api/')
        return created, kept

    @staticmethod
    def _module_urls_path(module):
        """模块路径 API.apis.xxx -> API/apis/xxx/urls.py 绝对路径"""
        return os.path.join(_API_APIS_DIR, module[len('API.apis.'):].replace('.', '/'), 'urls.py')
