from django.apps import AppConfig, apps
from django.db.backends.signals import connection_created
from django.db.models.signals import post_delete, post_save


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
        # 服务策略查询缓存失效钩子：后台保存 / 删除 ApiServicePolicy 后立即失效，
        # 改动即时生效、无需等 TTL
        from API.common.middleware import invalidate_api_service_policy_cache
        from API.models.Auth.policy import ApiServicePolicy

        def _invalidate_policy_cache(sender, instance, **kwargs):
            invalidate_api_service_policy_cache()

        post_save.connect(_invalidate_policy_cache, sender=ApiServicePolicy, weak=False)
        post_delete.connect(_invalidate_policy_cache, sender=ApiServicePolicy, weak=False)

        # 调用单价缓存失效钩子：「线路价格」页保存 / 删除 ApiPricePolicy 后立即失效
        from API.common.credit_guard import invalidate_api_price_cache
        from API.models.Credit.price import ApiPricePolicy

        def _invalidate_price_cache(sender, instance, **kwargs):
            invalidate_api_price_cache()

        post_save.connect(_invalidate_price_cache, sender=ApiPricePolicy, weak=False)
        post_delete.connect(_invalidate_price_cache, sender=ApiPricePolicy, weak=False)

        # AI 模型清单缓存失效钩子：后台保存 / 删除厂商、模型或系统提示词后立即失效，
        # 文档页下拉与 /api/ai/BuiltInModel/models 立刻反映改动，无需等 TTL
        from API.apis.ai.BuiltInModel.utils import invalidate_models_cache
        from API.models.AI.provider import AiModel, AiProvider, AiSystemPrompt

        def _invalidate_ai_cache(sender, instance, **kwargs):
            invalidate_models_cache()

        for model_cls in (AiProvider, AiModel, AiSystemPrompt):
            post_save.connect(_invalidate_ai_cache, sender=model_cls, weak=False)
            post_delete.connect(_invalidate_ai_cache, sender=model_cls, weak=False)

        # SQLite 连接级 PRAGMA（WAL + synchronous=NORMAL）
        connection_created.connect(_configure_sqlite, weak=False)

        # 反馈中心 AI 审核线程：只在「对外提供服务」的进程里启动（管理命令一律不起，
        # runserver 自动重载时只有子进程起），线程内一次审一条、慢慢来，
        # 多 worker 部署靠行级抢占保证同一条不会被审两次（见 API/apis/feedback/ai.py）
        from API.apis.feedback.ai import is_serving_process, start_review_worker

        if is_serving_process():
            start_review_worker()

        # 服务余量巡检线程：同样只在「对外提供服务」的进程里启动，定期取各上游服务账号的
        # 余量、低于阈值时发邮件；多 worker 靠行级抢占保证同一轮告警只发一封
        # （见 API/apis/quota/utils.py）
        from API.apis.quota.utils import start_worker as start_quota_worker

        if is_serving_process():
            start_quota_worker()

        # 上游故障告警巡检线程：按服务统计上游调用失败率（业务码 4xxxx），超阈值发邮件；
        # 与余量线程分开跑（间隔不同：故障要更灵敏），多 worker 靠行级抢占保证只发一封
        # （见 API/apis/monitor/utils.py）
        from API.apis.monitor.utils import start_worker as start_monitor_worker

        if is_serving_process():
            start_monitor_worker()

        # collectstatic：把「前端编译源码与工具」排除在收集之外 —— 它们只服务编译期，不是运行时资源：
        #   - css/input.css 第 1 行的 @import "tailwindcss" 会被 Manifest 存储当成待解析的 URL，直接报错；
        #   - tailwindcss.exe 有 109MB，收集它既拖慢部署又会让它被公开下载；
        #   - daisyui*.mjs 是编译用的插件本体（见《前端开发必看》第 2 节）。
        # collectstatic 的忽略规则来自 staticfiles app config（见 Django 源码 set_options），故在此追加。
        staticfiles_config = apps.get_app_config('staticfiles')
        staticfiles_config.ignore_patterns += ['*input.css', '*daisyui*.mjs', '*tailwindcss*']
