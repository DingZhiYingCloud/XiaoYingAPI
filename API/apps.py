import logging
import os

from django.apps import AppConfig, apps
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_delete, post_save

logger = logging.getLogger('api.workers')

# 持有后台线程 leader 锁的文件句柄：进程存活期间不能释放（详见 _acquire_background_worker_lock）
_WORKER_LOCK_HANDLE = None


def _acquire_background_worker_lock() -> bool:
    """后台常驻线程的单实例选举：拿到文件锁的进程返回 True，其它进程返回 False

    为什么需要：反馈 AI 审核 / 服务余量巡检 / 邮件定时推送三个常驻线程，原先每个 uwsgi worker
    都会各起一份、各自按固定频率轮询（正确性由行级 CAS 抢占保证）。worker 一多，重复轮询与
    SQLite 写竞争就成倍放大，故这里选出一个 leader，只有它真正跑这三个线程。

    实现要点：
    - 用**文件锁**而非「写 pid 文件」：锁由操作系统在进程退出（含被 kill）时自动释放，
      不会留下「pid 文件还在但进程已死」的死锁；
    - 失败一律 **fail-open**（返回 True）：宁可多跑一份，也不能因为加锁失败让「定时邮件 /
      余量告警」整体停摆 —— 所以拿不到锁的路径只有一种：确实被别的进程持有着。
    """
    global _WORKER_LOCK_HANDLE
    if _WORKER_LOCK_HANDLE is not None:      # 同一进程重复调用（如多入口初始化）
        return True
    lock_path = settings.XYAPI_CACHE_ROOT / 'worker.lock'
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, 'a+b')
    except OSError as exc:                   # 磁盘只读 / 权限不足等：退回原行为
        logger.warning('后台线程单实例锁不可用（%s），本进程按原行为启动后台线程', exc)
        return True
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            if handle.read(1) == b'':        # Windows 要求锁的区域存在，空文件先写一个字节
                handle.seek(0, os.SEEK_END)
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        logger.info('后台线程 leader 已被其它进程持有，本进程不重复启动后台线程')
        return False
    _WORKER_LOCK_HANDLE = handle
    logger.info('本进程已成为后台线程 leader（pid=%s）', os.getpid())
    return True


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

        # 这一组常驻线程只在「对外提供服务」的进程里启动（管理命令一律不起，
        # runserver 自动重载时只有子进程起）。
        from API.apis.feedback.ai import is_serving_process, start_review_worker

        # 单实例选举：下面这三个常驻线程只由拿到文件锁的那个「对外服务进程」来跑，
        # 其余 worker 只服务请求（多 worker 下不再各跑一份）；选举不可用时 fail-open 退回原行为。
        run_workers = is_serving_process() and _acquire_background_worker_lock()

        # 反馈中心 AI 审核线程：线程内一次审一条、慢慢来，
        # 多进程靠行级抢占保证同一条不会被审两次（见 API/apis/feedback/ai.py）
        if run_workers:
            start_review_worker()

        # 服务余量巡检线程：定期取各上游服务账号的余量、低于阈值时发邮件；
        # 多进程靠行级抢占保证同一轮告警只发一封（见 API/apis/quota/utils.py）
        from API.apis.quota.utils import start_worker as start_quota_worker

        if run_workers:
            start_quota_worker()

        # 邮件定时推送线程：按间隔扫描到期的 EmailTask 并发送；
        # 多进程靠行级抢占保证同一任务同一时刻只发一次（见 API/apis/push/email_task/utils.py）
        from API.apis.push.email_task.utils import start_worker as start_email_task_worker

        if run_workers:
            start_email_task_worker()

        # collectstatic：把「前端编译源码与工具」排除在收集之外 —— 它们只服务编译期，不是运行时资源：
        #   - css/input.css 第 1 行的 @import "tailwindcss" 会被 Manifest 存储当成待解析的 URL，直接报错；
        #   - tailwindcss.exe 有 109MB，收集它既拖慢部署又会让它被公开下载；
        #   - daisyui*.mjs 是编译用的插件本体（见《前端开发必看》第 2 节）。
        # collectstatic 的忽略规则来自 staticfiles app config（见 Django 源码 set_options），故在此追加。
        staticfiles_config = apps.get_app_config('staticfiles')
        staticfiles_config.ignore_patterns += ['*input.css', '*daisyui*.mjs', '*tailwindcss*']
