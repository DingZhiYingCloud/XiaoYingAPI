"""数据维护线程：定期清理「只增不减」的表

背景：小时级调用统计表（`api_call_stat_hour`）原先只有 `manage.py prune_api_call_hour`
一条命令，靠人工在服务器上配计划任务 —— 忘了配就会无限增长。这里把它纳入应用内的
常驻线程（与反馈审核 / 余量巡检 / 邮件推送同一套 leader 选举机制，见 API/apps.py），
让清理不再依赖运维记得手动配置。

行为：进程启动后先等 FIRST_DELAY_SECONDS（避开启动风暴），此后每 INTERVAL_SECONDS 跑一次；
清理动作复用既有 management command，不重复实现。
"""
import logging
import threading
import time

from django.core.management import call_command

logger = logging.getLogger('api.workers')

#: 首次执行的延迟（秒）：先等进程稳定，避免启动瞬间与其它初始化抢数据库
FIRST_DELAY_SECONDS = 300
#: 清理间隔（秒）：24 小时
INTERVAL_SECONDS = 24 * 60 * 60


def _loop():
    time.sleep(FIRST_DELAY_SECONDS)
    while True:
        try:
            call_command('prune_api_call_hour')
        except Exception:
            # 清理失败不影响对外服务：记录后等下一轮
            logger.exception('定时清理失败，将于下一轮重试')
        time.sleep(INTERVAL_SECONDS)


def start_worker():
    """启动数据维护线程（本进程只启动一次；多进程由 apps.py 的 leader 选举保证只有一个）"""
    threading.Thread(target=_loop, daemon=True, name='xyapi-maintenance').start()
    logger.info('数据维护线程已启动（每 %s 小时清理一次）', INTERVAL_SECONDS // 3600)
