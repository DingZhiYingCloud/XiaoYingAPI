# -*- coding: utf-8 -*-
"""数据迁移：将图形验证码相关分类节点显式置为 open（开放）

背景：
0011 建分类树时仅把旧 ApiAuthPolicy 中的 user_center / sms_verify 置为 auth，
其余节点全部默认 inherit。0012 之后旧策略表删除，A-01 fail-closed 生效：
全链 inherit 的节点一律要求项目签名。
但登录/注册/重置密码页的自研验证码、文档页的阿里云验证码是浏览器不带签名
直接访问的公开接口（见 API/common/middleware.py 中 captcha 相关注释），
全新部署时它们被签名中间件拦截（20011），导致前端验证码初始化失败、
页面只提示"请先完成图形验证"却不弹窗。

本迁移幂等地把以下两个节点置为 open：
- /api/captcha_self/        自研图形验证码（generate/verify）
- /api/captcha_auth/aliyun/ 阿里云图形认证（config/verify）
节点若不存在（代码已移除对应服务）则跳过，不报错。
"""
from django.db import migrations

OPEN_PREFIXES = (
    '/api/captcha_self/',
    '/api/captcha_auth/aliyun/',
)


def open_captcha_categories(apps, schema_editor):
    ApiCategory = apps.get_model('API', 'ApiCategory')
    for prefix in OPEN_PREFIXES:
        ApiCategory.objects.filter(path_prefix=prefix).update(auth_mode='open')


def noop_reverse(apps, schema_editor):
    # 不回滚：恢复 inherit 会让全新/回滚环境的验证码接口再次被签名拦截
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0022_api_call_stat'),
    ]

    operations = [
        migrations.RunPython(open_captcha_categories, noop_reverse),
    ]
