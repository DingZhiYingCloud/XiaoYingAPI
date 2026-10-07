"""运行「代练通订单 → 代练丸子发单」搬单流水线

流水线每一轮：取实时余额（代练通 / 丸子）→ 抓单 → 过滤 → 随机抽单 → 逐条「余额够才发」
              → 监控（先代练通原单、后丸子被接单）→ 代练通接单取账号 → 失败兜底撤单。
任一余额不足会中断本轮发单（已发的保留），等下一轮再跑。

⚠ 真实写操作：发单会扣商家余额、接单会冻结代练通双金、取到账号后需人工通过 QQ 交接。
首次务必先用 --dry-run 核对「抓单 + 映射」结果，确认无误再去掉 --dry-run。

用法：
    python manage.py run_order_migration --once --dry-run          # 只跑一轮，只看抓单映射
    python manage.py run_order_migration --once                     # 跑一轮（真实发单/接单）
    python manage.py run_order_migration                            # 常驻轮询（默认间隔取 .env）
    python manage.py run_order_migration --interval 15 --publish-limit 2
"""
import time

from django.core.management.base import BaseCommand

from API.apis.order_migration import utils as om_utils


class Command(BaseCommand):
    help = '运行「代练通订单 → 代练丸子发单」搬单流水线（抓单/发单/监控/接单/兜底）'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='只跑一轮后退出')
        parser.add_argument('--dry-run', action='store_true',
                            help='只做抓单 + 映射，不真实发单 / 接单 / 撤单')
        parser.add_argument('--interval', type=int, default=0,
                            help='轮询间隔秒（默认取 .env 的 ORDER_MIGRATION_INTERVAL 或 20）')
        parser.add_argument('--publish-limit', type=int, default=1,
                            help='每轮最多发布多少条（默认 1）')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        interval = options['interval'] or om_utils.interval_seconds()
        limit = options['publish_limit']

        self.stdout.write(
            f"搬单流水线启动：间隔 {interval}s，每轮发布上限 {limit}"
            + ('（dry-run，不写真实订单）' if dry_run else ''))
        if not dry_run and not om_utils.our_qq():
            self.stderr.write(f"警告：未配置 {om_utils.QQ_ENV}，发单会全部失败")

        while True:
            summary = om_utils.run_once(publish_count=limit, dry_run=dry_run)
            if summary is None:
                # 跨进程互斥：另一进程（如 uwsgi 里的后台线程）正在执行本轮
                self.stdout.write('[一轮] 已有进程在执行本轮，跳过')
            else:
                self.stdout.write(
                    f"[一轮] 抓取 {summary['fetched']} 条，发布 {summary['published']} 条，"
                    f"代练通接单 {summary['taken']} 条，兜底撤单 {summary['rollback']} 条")
                for err in summary['errors']:
                    self.stderr.write(f"  错误: {err}")
            if options['once']:
                break
            time.sleep(interval)
