# 兑换汇率（点/元）由「四位小数」收敛为「最多两位小数」
#
# 背景：汇率的输入框原来是 step=any / min=0.0001，能存成 1.2345 这种四位小数，
# 后台看起来碎、也无法限制精度。改为 decimal_places=2 后，Django 在保存时会按两位
# 小数落库；控制台表单与校验（console_pay._save_setting）也一并收紧。
#
# 本迁移做两件事：
#   1. AlterField：把字段精度收到两位小数（表结构层面）；
#   2. RunPython：把存量值精确到两位小数（线上/本地当前都是 1.0000 → 1.00）。
#      只在「四舍五入后仍大于 0」时写入 —— 万一存在 0.004 这类极小值，宁可保持原样
#      让管理员去改，也不要静默改成 0.00（那会破坏「汇率必须大于 0」的约束与换算口径）。
from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models


def round_existing_rate(apps, schema_editor):
    """存量汇率精确到两位小数（四舍五入；结果为 0 时保持原值不动）"""
    PaySetting = apps.get_model('API', 'PaySetting')
    for row in PaySetting.objects.all():
        rounded = row.points_per_yuan.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if rounded > 0 and rounded != row.points_per_yuan:
            PaySetting.objects.filter(pk=row.pk).update(points_per_yuan=rounded)


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0057_payment_refund_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paysetting',
            name='points_per_yuan',
            field=models.DecimalField(decimal_places=2, default=1, help_text='1 元等于多少点数（最多两位小数），用于「用户余额（元）→ 接入项目点数」的兑换；默认 1', max_digits=12, verbose_name='兑换汇率（点/元）'),
        ),
        migrations.RunPython(round_existing_rate, migrations.RunPython.noop),
    ]
