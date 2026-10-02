# 数据迁移：把「第三方支付」服务（/api/pay/）的调用单价显式设为 0（免费）
#
# 为什么必须显式建这一行：调用单价表的兜底价是 1 点/次（DEFAULT_PRICE），且中间件在
# **调用前**就校验「项目余额 >= 本次单价」。支付服务的用途恰恰是「给项目充值点数」，
# 若走兜底价，一个 0 余额的项目会被 30012（额度不足）拦在下单之前 —— 永远没法给自己充值。
# 因此在价格表里为它建一条服务级节点，把「调一次扣多少点」与「能不能调」解耦开。
#
# 只建一条服务级节点：线路 / 端点未单独配价时逐级继承到它；后续想改成收费，
# 到控制台 /console/prices/ 把这条的单价改掉即可（不会被本迁移覆盖 —— 见下面只创建不覆盖）。
#
# 回滚：本迁移不可逆（无法区分「原本就存在的手工配价」）。如需恢复兜底价，
# 到控制台把 /api/pay/ 这条删掉即可（删行 = 取消显式设价，重新走 DEFAULT_PRICE）。

from django.db import migrations

#: 免费服务的 (前缀, 层级, 单价)
FREE_SERVICES = (
    ('/api/pay/', 'service', 0),
)


def set_free_price(apps, schema_editor):
    """幂等地为支付服务建立 0 元单价节点（已存在则原样保留，不覆盖手工调过的价）"""
    ApiPricePolicy = apps.get_model('API', 'ApiPricePolicy')

    for prefix, level, price in FREE_SERVICES:
        if ApiPricePolicy.objects.filter(path_prefix=prefix).exists():
            continue
        ApiPricePolicy.objects.create(path_prefix=prefix, level=level, price=price)


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0055_payment'),
    ]

    operations = [
        migrations.RunPython(set_free_price, migrations.RunPython.noop),
    ]
