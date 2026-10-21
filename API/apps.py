import logging
import os
import threading
import time

from django.apps import AppConfig, apps
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_delete, post_save

logger = logging.getLogger('api.workers')

# 持有后台线程 leader 锁的文件句柄：进程存活期间不能释放（详见 _acquire_background_worker_lock）
_WORKER_LOCK_HANDLE = None

# 未选上 leader 时的重试间隔（秒）与“只起一个重试线程”的幂等标记。
# 为什么需要重试：uwsgi --reload 时新 worker 先起、旧 worker 还持有锁，新进程全部落选；
# 旧进程退出后如果没人再试，反馈审核 / 余量巡检 / 邮件推送 / 清理线程会一直停摆到下次重启。
LEADER_RETRY_SECONDS = 30
_LEADER_RETRY_STARTED = False
_LEADER_RETRY_LOCK = threading.Lock()


def _acquire_background_worker_lock(quiet: bool = False) -> bool:
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
        if not quiet:
            logger.info('后台线程 leader 已被其它进程持有，本进程不重复启动后台线程')
        return False
    _WORKER_LOCK_HANDLE = handle
    logger.info('本进程已成为后台线程 leader（pid=%s）', os.getpid())
    return True


def _start_background_workers() -> None:
    """启动四个常驻线程（各 start_worker 自身幂等，重复调用无副作用）"""
    from API.apis.feedback.ai import start_review_worker
    from API.apis.push.email_task.utils import start_worker as start_email_task_worker
    from API.apis.quota.utils import start_worker as start_quota_worker
    from API.common.maintenance import start_worker as start_maintenance_worker

    start_review_worker()
    start_quota_worker()
    start_email_task_worker()
    start_maintenance_worker()


def _start_leader_retry() -> None:
    """落选 leader 后启动一个低频重试线程，抢到锁再启动常驻线程

    只在「对外服务进程」里调用。fail-open 语义不变：锁不可用时
    `_acquire_background_worker_lock` 会直接返回 True，重试线程首轮即启动业务线程。
    """
    global _LEADER_RETRY_STARTED
    with _LEADER_RETRY_LOCK:
        if _LEADER_RETRY_STARTED:
            return
        _LEADER_RETRY_STARTED = True

    def retry():
        while not _acquire_background_worker_lock(quiet=True):
            time.sleep(LEADER_RETRY_SECONDS)
        logger.info('重试取得后台线程 leader，开始启动常驻线程')
        _start_background_workers()

    threading.Thread(target=retry, name='api-worker-leader-retry', daemon=True).start()


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

        # 页面级上下文缓存失效（友链 / 页脚联系方式 / 官网外观）：这些数据每个页面都会读，
        # 现做 60 秒 TTL 缓存；后台保存或删除后立即失效，不必等 TTL。
        from API.models import FriendLink, SiteAppearance, UserApp
        from API.models.Feedback.contact import ContactPlatform, ProjectContact
        from API.website.context import invalidate_context_cache

        def _invalidate_page_cache(sender, instance, **kwargs):
            invalidate_context_cache()

        for model_cls in (FriendLink, SiteAppearance, UserApp, ProjectContact, ContactPlatform):
            post_save.connect(_invalidate_page_cache, sender=model_cls, weak=False)
            post_delete.connect(_invalidate_page_cache, sender=model_cls, weak=False)

        # 签名校验的接入项目缓存（进程内）：停用 / 轮换密钥后立即清掉本进程缓存
        from API.apis.user_center.sign import invalidate_app_cache

        def _invalidate_sign_app_cache(sender, instance, **kwargs):
            invalidate_app_cache(getattr(instance, 'app_id', ''))

        post_save.connect(_invalidate_sign_app_cache, sender=UserApp, weak=False)
        post_delete.connect(_invalidate_sign_app_cache, sender=UserApp, weak=False)

        # SQLite 连接级 PRAGMA（WAL + synchronous=NORMAL）
        connection_created.connect(_configure_sqlite, weak=False)

        # 这一组常驻线程只在「对外提供服务」的进程里启动（管理命令一律不起，
        # runserver 自动重载时只有子进程起）。
        from API.apis.feedback.ai import is_serving_process

        # 单实例选举：拿到文件锁的进程启动常驻线程；落选的进程起一个低频重试线程，
        # 等旧 leader 退出（如 uwsgi --reload）后自动补位，避免四个线程整站停摆。
        if is_serving_process():
            if _acquire_background_worker_lock():
                _start_background_workers()
            else:
                _start_leader_retry()

        # collectstatic：把「前端编译源码与工具」排除在收集之外 —— 它们只服务编译期，不是运行时资源：
        #   - css/input.css 第 1 行的 @import "tailwindcss" 会被 Manifest 存储当成待解析的 URL，直接报错；
        #   - tailwindcss.exe 有 109MB，收集它既拖慢部署又会让它被公开下载；
        #   - daisyui*.mjs 是编译用的插件本体（见《前端开发必看》第 2 节）。
        # collectstatic 的忽略规则来自 staticfiles app config（见 Django 源码 set_options），故在此追加。
        staticfiles_config = apps.get_app_config('staticfiles')
        staticfiles_config.ignore_patterns += ['*input.css', '*daisyui*.mjs', '*tailwindcss*']
