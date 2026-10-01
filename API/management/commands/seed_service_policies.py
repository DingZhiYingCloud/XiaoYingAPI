"""按「建议策略」清单补齐服务策略表（幂等，可反复执行）

用途：策略表是接口鉴权的唯一来源，全局兜底又是 fail-closed（未命中即「需要签名」）。
验证码、海角社区图片 / m3u8、红果直出流、反馈中心子项目前端这几个「浏览器直连、
带不了签名」的例外一旦丢失，对应功能会整片挂掉。而它们原本写在各条**数据迁移**里，
迁移标记为已执行后不会再跑，策略表被清空 / 换环境重建时数据不会回来。

因此清单收敛到 API/website/service_presets.py（唯一出处），本命令按它补齐**缺失的**条目；
已存在的一律跳过，绝不覆盖后台里的自定义配置。后台 `/console/services/` 的
「一键新建建议策略」用的是同一份清单、同一套语义。

用法：
    python manage.py seed_service_policies --dry-run   # 只列出将新建的条目，不写库
    python manage.py seed_service_policies             # 实际补齐
"""
from django.core.management.base import BaseCommand

from API.website.service_presets import SERVICE_POLICY_PRESETS, apply_presets, preset_rows


class Command(BaseCommand):
    help = '按建议策略清单幂等补齐服务策略表（只新建缺失的，已存在的原样保留）'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='只列出将新建的条目，不写库')

    def handle(self, *args, **options):
        if options['dry_run']:
            # 预览与执行共用 preset_rows() 的「是否已存在」判定，避免两处口径漂移
            created = [row['path_prefix'] for row in preset_rows() if not row['exists']]
        else:
            created, _ = apply_presets()

        names = {row[0]: row[1] for row in SERVICE_POLICY_PRESETS}
        for prefix in created:
            self.stdout.write(f'  新建  {prefix}  {names[prefix]}')
        suffix = '（dry-run，未写库）' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'建议策略共 {len(SERVICE_POLICY_PRESETS)} 条：新建 {len(created)} 条、'
            f'已存在跳过 {len(SERVICE_POLICY_PRESETS) - len(created)} 条{suffix}'))
