"""清理过期的 QQ 好友消息（后台「QQBot」页「好友消息」的数据源）

好友消息是 NapCat 事件上报的流水，只会越积越多；后台每个会话只显示最近若干条，更早的留着
只为回看。本命令按两条线清理（都在生效时取「并集」）：

    · `--keep`：只保留最新的 N 条（默认 5000）；
    · `--days`：只保留最近 N 天（默认 30）。

建议配每日计划任务（与 `prune_api_call_hour` 同一套路；部署手册见 README 第 7 章）：

    python manage.py prune_qq_messages                # 默认：留最近 5000 条 + 最近 30 天
    python manage.py prune_qq_messages --keep 20000   # 条数上限放宽到 2 万
    python manage.py prune_qq_messages --days 7       # 只保留最近 7 天
    python manage.py prune_qq_messages --days 0       # 关掉「按天」这条线，只按条数
    python manage.py prune_qq_messages --dry-run      # 只统计会删多少，不真删
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from API.models import QQPrivateMessage

# 默认保留条数 / 天数
DEFAULT_KEEP_ROWS = 5000
DEFAULT_KEEP_DAYS = 30


class Command(BaseCommand):
    help = '清理过期的 QQ 好友消息（按条数上限 + 天数保留）'

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=DEFAULT_KEEP_ROWS,
                            help=f'只保留最新的 N 条（默认 {DEFAULT_KEEP_ROWS}；0 = 不按条数清理）')
        parser.add_argument('--days', type=int, default=DEFAULT_KEEP_DAYS,
                            help=f'只保留最近 N 天（默认 {DEFAULT_KEEP_DAYS}；0 = 不按天数清理）')
        parser.add_argument('--dry-run', action='store_true', help='只统计将删除的行数，不真删')

    def handle(self, *args, **options):
        keep = max(0, int(options['keep']))
        days = max(0, int(options['days']))
        if not keep and not days:
            self.stderr.write(self.style.ERROR('--keep 与 --days 不能同时为 0（否则会删掉全部消息）'))
            return

        conditions = []
        if keep:
            # 第 keep 条（含）之后的行 —— 用 id 排序，自增主键即时间序
            boundary = list(QQPrivateMessage.objects.order_by('-id')
                            .values_list('id', flat=True)[keep - 1:keep])
            if boundary:
                conditions.append(Q(id__lt=boundary[0]))
        cutoff = None
        if days:
            cutoff = timezone.now() - timedelta(days=days)
            conditions.append(Q(create_time__lt=cutoff))

        query = conditions[0]
        for extra in conditions[1:]:
            query |= extra
        target = QQPrivateMessage.objects.filter(query)
        total = target.count()

        if options['dry_run']:
            self.stdout.write(f'将删除 {total} 条（keep={keep or "不限"} · days={days or "不限"}）')
            return
        if not total:
            self.stdout.write(self.style.SUCCESS('没有需要清理的 QQ 好友消息'))
            return

        deleted, _ = target.delete()
        self.stdout.write(self.style.SUCCESS(
            f'已清理 {deleted} 条 QQ 好友消息（保留最新 {keep or "不限"} 条 / 最近 {days or "不限"} 天'
            + (f'，截止 {cutoff:%Y-%m-%d %H:%M}' if cutoff else '') + '）'))
