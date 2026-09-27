from django.apps import AppConfig, apps
from django.db.backends.signals import connection_created
from django.db.models.signals import m2m_changed, post_delete, post_save


def _configure_sqlite(sender, connection, **kwargs):
    """每条 SQLite 连接建立后设置 PRAGMA（性能优化）

    - journal_mode=WAL：读写不再互相阻塞（默认的 delete 模式下，一次写入会挡住所有读取）。
      本站是「页面在读 + 调用统计/请求日志在写」，收益最直接。
      WAL 是持久化属性（写在库文件里），已是 WAL 时直接跳过，避免每连接多拿一次写锁。
    - synchronous=NORMAL：WAL 下的推荐值（默认 FULL 每次提交都 fsync）。
      极端断电可能丢最后一个已提交事务，但不会损坏数据库。
    非 SQLite（以后换 PostgreSQL）或内存库直接跳过。
    """
    if connection.vendor != 'sqlite':
        return
    if connection.settings_dict.get('NAME') in (':memory:', ''):
        return
    with connection.cursor() as cursor:
        mode = cursor.execute('PRAGMA journal_mode').fetchone()[0]
        if str(mode).lower() != 'wal':
            cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')


class ApiConfig(AppConfig):
    name = 'API'
    verbose_name = 'API服务'

    def ready(self):
        # 服务策略查询缓存失效钩子：后台保存 / 删除 ApiServicePolicy、
        # 或改动白名单项目（M2M 变更走 m2m_changed）后立即失效，改动即时生效、无需等 TTL
        from API.common.middleware import invalidate_api_service_policy_cache
        from API.models.Auth.policy import ApiServicePolicy

        def _invalidate_policy_cache(sender, instance, **kwargs):
            invalidate_api_service_policy_cache()

        post_save.connect(_invalidate_policy_cache, sender=ApiServicePolicy, weak=False)
        post_delete.connect(_invalidate_policy_cache, sender=ApiServicePolicy, weak=False)
        m2m_changed.connect(_invalidate_policy_cache,
                            sender=ApiServicePolicy.apps.through, weak=False)

        # SQLite 连接级 PRAGMA（WAL + synchronous=NORMAL）
        connection_created.connect(_configure_sqlite, weak=False)

        # collectstatic：把「前端编译源码与工具」排除在收集之外 —— 它们只服务编译期，不是运行时资源：
        #   - css/input.css 第 1 行的 @import "tailwindcss" 会被 Manifest 存储当成待解析的 URL，直接报错；
        #   - tailwindcss.exe 有 109MB，收集它既拖慢部署又会让它被公开下载；
        #   - daisyui*.mjs 是编译用的插件本体（见《前端开发必看》第 2 节）。
        # collectstatic 的忽略规则来自 staticfiles app config（见 Django 源码 set_options），故在此追加。
        staticfiles_config = apps.get_app_config('staticfiles')
        staticfiles_config.ignore_patterns += ['*input.css', '*daisyui*.mjs', '*tailwindcss*']
