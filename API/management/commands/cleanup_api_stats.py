"""清理调用统计的历史残留数据（幂等，可重复执行）

统计表（ApiCallStat / ApiCallStatHour）是**按维度聚合且只追加**的：路径或接入项目一旦
不复存在，那些行不会自动消失，反而会在看板上变成「未匹配路径」「已删除项目」这类残影。
本命令按**当前统计口径**把历史数据折算一遍，共两类：

1. **路径残影**：把解析不到真实路由的历史路径（扫描器探测 /api/phpinfo.php、
   /api/.git-credentials 之类）合并到 `/api/_unmatched_/`；把当时按真实 ID 记录的行
   归并到路由模板（如 /api/music/xiaoying/musics/<uuid> → …/<param>）。
   合并是**累加**：调用次数与耗时总量都保留，历史总量不失真。
2. **项目残影**（`--no-drop-orphan-apps` 可关）：APPID 已不存在于接入项目表的行
   （冒烟脚本建了又删的临时项目、被删除的接入项目）。保留还是清理由你决定 ——
   保留时看板会把它显示成「已删除项目」。

用法：
    python manage.py cleanup_api_stats --dry-run              # 只统计影响面，不写库
    python manage.py cleanup_api_stats                        # 实际执行
    python manage.py cleanup_api_stats --no-drop-orphan-apps  # 只做路径归并，保留项目残影
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest

from API.common.api_stats import canonical_path, service_of
from API.models import UserApp
from API.models.Statistics.api_call_stat import NO_APP, ApiCallStat, ApiCallStatHour

# 两张表各自的聚合键（与 API/common/api_stats.py 的写入口径一致）
_DAY_KEY_FIELDS = ('stat_date', 'path', 'app_id', 'status_code')
_HOUR_KEY_FIELDS = ('stat_date', 'stat_hour', 'path', 'app_id', 'status_code')


class Command(BaseCommand):
    help = '清理调用统计的历史残留：路径归并到当前口径，并可选清理已不存在项目的行'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='只统计将受影响的源行数，不写库')
        parser.add_argument('--no-drop-orphan-apps', action='store_true',
                            help='保留 APPID 已不存在于接入项目表的行（只做路径归并）')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        suffix = '（dry-run，未写库）' if dry_run else ''

        merged_day = self._merge_paths(ApiCallStat, _DAY_KEY_FIELDS, dry_run)
        merged_hour = self._merge_paths(ApiCallStatHour, _HOUR_KEY_FIELDS, dry_run)
        self.stdout.write(f'路径归并：按天表 {merged_day} 行、按小时表 {merged_hour} 行{suffix}')

        if options['no_drop_orphan_apps']:
            self.stdout.write('项目残影：已跳过（--no-drop-orphan-apps）')
            return

        kept = set(UserApp.objects.values_list('app_id', flat=True))
        count = 0
        for model in (ApiCallStat, ApiCallStatHour):
            # NO_APP 是「开放接口 / 未认证」这一桶，不是项目残影，必须保留
            doomed = model.objects.exclude(app_id=NO_APP).exclude(app_id__in=kept)
            count += doomed.count()
            if not dry_run:
                doomed.delete()
        self.stdout.write(f'项目残影：已清理 {count} 行{suffix}')

    def _merge_paths(self, model, key_fields, dry_run):
        """把 path 需要折算的行归并到折算后的路径，返回受影响的源行数

        折算口径与运行时完全一致（API/common/api_stats.canonical_path）：
        已是 <param> 模板的原样保留；能解析到真实路由的用路由模板；解析不到的归并为
        /api/_unmatched_/。因此执行一次之后再次运行不会再有可归并的行（幂等）。
        """
        mapping = {}
        for path in model.objects.values_list('path', flat=True).distinct():
            target = canonical_path(path)
            if target != path:
                mapping[path] = target
        if not mapping:
            return 0

        sources = model.objects.filter(path__in=list(mapping))
        affected = sources.count()
        if dry_run:
            return affected

        # 先按「折算后的聚合键」把源行累加进桶，再写入目标行、最后删源行
        buckets = defaultdict(lambda: [0, 0, 0])
        for row in sources.values(*key_fields, 'call_count', 'cost_sum_ms', 'cost_max_ms'):
            key = tuple(mapping[row['path']] if field == 'path' else row[field]
                        for field in key_fields)
            item = buckets[key]
            item[0] += row['call_count']
            item[1] += row['cost_sum_ms']
            if row['cost_max_ms'] > item[2]:
                item[2] = row['cost_max_ms']

        with transaction.atomic():
            for key, (count, cost_sum, cost_max) in buckets.items():
                lookup = dict(zip(key_fields, key))
                updated = model.objects.filter(**lookup).update(
                    call_count=F('call_count') + count,
                    cost_sum_ms=F('cost_sum_ms') + cost_sum,
                    cost_max_ms=Greatest(F('cost_max_ms'), Value(cost_max)),
                )
                if not updated:
                    model.objects.create(**lookup, service=service_of(lookup['path']),
                                         call_count=count, cost_sum_ms=cost_sum,
                                         cost_max_ms=cost_max)
            # 目标行不可能是源行（源行是原始路径、目标是折算后的路径），故删源行安全
            model.objects.filter(path__in=list(mapping)).delete()
        return affected
