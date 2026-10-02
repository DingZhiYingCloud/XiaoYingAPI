# 数据迁移：授权模型从「服务白名单」换成「项目额度」
#
# 背景：白名单（app_scope + 多对多 apps）只解决「哪个项目能调哪个服务」，但它挂在**服务**上，
# 项目一多就得逐服务配置，且与「先充值后使用」的商业模式不匹配。现改为**额度（点数余额）**：
# 新建项目默认 0 → 什么都调不了（开放接口除外）；有余额就能调全部服务；调用成功（业务码 10000）
# 按服务单价扣点（单价在 ApiServicePolicy.price 上，服务 / 线路 / 端点三级继承）。
# 判定与扣费见 API/common/credit_guard.py。
#
# 本迁移做三件事：
#   1. 删除白名单与旧的「日/月调用配额」字段（配额已被额度取代，两套限流概念不并存）；
#   2. 新增 UserApp.balance（默认 0）与 ApiServicePolicy.price（null=跟随上级）；
#   3. 建额度流水表 app_credit_ledger（只记充值 / 人工调整，逐次扣费不进表）。
#
# 注意：**既有项目的余额一律为 0**（迁移不做任何放行），上线后需要在控制台
# 「项目额度」页逐个充值才能恢复调用 —— 这是明确的产品口径。

import django.db.models.deletion
import uuid
from django.db import migrations, models


def rename_whitelist_nodes(apps, schema_editor):
    """把迁移 0052 建出来的「XX-仅白名单」策略节点改回正常名字

    0052 只在这些服务**还没有策略节点**时才按 `XX-仅白名单` 命名；白名单能力已删除，
    名字里的后缀会误导运维，故去掉（只动名字，其余字段原样保留）。
    """
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    for policy in ApiServicePolicy.objects.filter(name__endswith='-仅白名单'):
        policy.name = policy.name[: -len('-仅白名单')]
        policy.save(update_fields=['name', 'updated_time'])


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0052_restrict_sensitive_services'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='apiservicepolicy',
            name='app_scope',
        ),
        migrations.RemoveField(
            model_name='apiservicepolicy',
            name='apps',
        ),
        migrations.RemoveField(
            model_name='userapp',
            name='daily_limit',
        ),
        migrations.RemoveField(
            model_name='userapp',
            name='monthly_limit',
        ),
        migrations.AddField(
            model_name='apiservicepolicy',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=4, default=None, help_text='调用成功一次扣的点数；留空=跟随上级，最终兜底 1 点/次', max_digits=12, null=True, verbose_name='单价（点/次）'),
        ),
        migrations.AddField(
            model_name='userapp',
            name='balance',
            field=models.DecimalField(decimal_places=2, default=0, help_text='点数余额：新建默认 0（什么都调不了），超管在控制台充值后增加，调用成功按服务单价扣减；允许为负（欠费，下次充值抵扣）', max_digits=16, verbose_name='可用额度'),
        ),
        migrations.CreateModel(
            name='AppCreditLedger',
            fields=[
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='流水ID')),
                ('amount', models.DecimalField(decimal_places=2, help_text='正数=充值，负数=扣回 / 纠错（单位：点）', max_digits=16, verbose_name='调整金额')),
                ('balance_after', models.DecimalField(decimal_places=2, help_text='本次调整完成后该项目的余额快照，便于对账', max_digits=16, verbose_name='调整后余额')),
                ('operator', models.CharField(blank=True, default='', help_text='执行本次调整的超管用户名', max_length=150, verbose_name='操作人')),
                ('remark', models.CharField(blank=True, default='', max_length=255, verbose_name='备注')),
                ('app', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credit_ledger', to='API.userapp', verbose_name='接入项目')),
            ],
            options={
                'verbose_name': '额度流水',
                'verbose_name_plural': '额度流水',
                'db_table': 'app_credit_ledger',
                'ordering': ['-create_time'],
                'indexes': [models.Index(fields=['app', '-create_time'], name='idx_credit_app_time')],
            },
        ),
        migrations.RunPython(rename_whitelist_nodes, migrations.RunPython.noop),
    ]
