"""测试脚本共用小工具（仅 `scripts/` 下的回归脚本使用，不参与线上运行）

**为什么要给测试项目充值**：授权模型改成「额度（点数余额）」后，新建项目默认 0 点
→ 任何需要签名的 `/api/` 调用都会先被中间件拦成 `30012 额度不足`。回归脚本都要真的
打接口，所以创建项目后必须补一笔额度，否则整片红了也说不清是功能坏了还是没充值。
"""
from decimal import Decimal

from django.db.models import F

# 测试项目的初始额度：足够跑完整套用例（每次成功调用最多扣几点的量级）
TEST_APP_BALANCE = Decimal('1000000')


def grant_credit(app, amount=TEST_APP_BALANCE):
    """给测试项目补额度（直接落库，不写充值流水 —— 测试不需要审计痕）

    :return: 同一个 app 对象（已刷新 balance），便于链式使用
    """
    from API.models import UserApp

    UserApp.objects.filter(pk=app.pk).update(balance=F('balance') + amount)
    app.refresh_from_db(fields=['balance'])
    return app
