"""清理过期的 API 小时粒度统计命令

背景：调用统计分两级预聚合（见 API/models/Statistics/api_call_stat.py）：
- 按天（ApiCallStat）：全历史保留，是调用量的唯一真值表
- 按小时（ApiCallStatHour）：只为时段分布 / 星期×小时热力图 / 日内峰值提供数据，
  保留 HOUR_RETENTION_DAYS（90）天即可，超期数据必须删除以免无限膨胀

本命令删除过期的小时行，只保留最近 HOUR_RETENTION_DAYS（90）天；按天表不做任何改动，
因此历史总量、成功率等按天指标不受影响，也无需额外归档任务。

用法（幂等，可重复执行；建议配宝塔/系统计划任务每天跑一次）：
    python manage.py prune_api_call_hour            # 按默认 90 天保留期清理
    python manage.py prune_api_call_hour --days 30  # 临时指定保留天数
    python manage.py prune_api_call_hour --dry-run  # 只统计将删除的行数，不实际删除
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from API.models.Statistics.api_call_stat import HOUR_RETENTION_DAYS, ApiCallStatHour


class Command(BaseCommand):
    help = f'删除超过保留期（默认 {HOUR_RETENTION_DAYS} 天）的 API 小时粒度统计行'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=HOUR_RETENTION_DAYS,
            help=f'小时数据保留天数（默认 {HOUR_RETENTION_DAYS}）',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='只统计将被删除的行数，不实际删除',
        )

    def handle(self, *args, **options):
        days = options['days']
        # 保留「最近 days 天（含今天）」：即保留 stat_date >= 今天-(days-1)，删除更早的
        # （口径与查询侧 api_stats_query._hour_qs 一致，避免留下查不到的死数据）
        cutoff = timezone.localdate() - timezone.timedelta(days=days - 1)
        queryset = ApiCallStatHour.objects.filter(stat_date__lt=cutoff)

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] 保留期 {days} 天（截止 {cutoff}），'
                f'将删除 {queryset.count()} 行，未实际执行'
            ))
            return

        deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(
            f'小时统计清理完成：保留期 {days} 天（截止 {cutoff}），删除 {deleted} 行'
        ))
