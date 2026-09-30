"""把 .env 里的 DeepSeek 配置一次性灌进 AI 厂商 / 模型表

为什么用数据迁移而不是手工命令：AI 的 Key 从此由数据库维护（`.env` 中的
`DEEPSEEK_API_KEY` / `DEEPSEEK_API_URL` 随本次改造移除）。若只写文档让人手工录入，
升级到「接口不可用、等后台填 Key」之间会有一段空窗；放进迁移里，`migrate` 一跑就完成，
不漏步骤。

行为：
- 厂商 `deepseek` 不存在则创建，地址取 `DEEPSEEK_API_URL`（缺省用官方地址），
  平台 Key 取 `DEEPSEEK_API_KEY`（未配置则留空，到后台补填即可）；
- 两个内置模型按当前的对外标识原样建好（`deepseek-v4-flash` 为默认模型），
  改动前后对外行为一致；
- 已存在则**不覆盖**（避免把后台已经改过的 Key / 模型配置冲掉）。

Key 落库即由 EncryptedSecretField 加密（AES-256-GCM），明文只在本函数执行期间存在于内存。
"""
import os

from django.db import migrations

DEFAULT_BASE_URL = 'https://api.deepseek.com'


def _mask(key):
    """由明文 Key 生成掩码（与模型 AiProvider.mask_key 同口径，迁移内自带一份避免依赖易变代码）"""
    key = (key or '').strip()
    if not key:
        return ''
    if len(key) <= 8:
        return f'{key[:2]}…'
    return f'{key[:3]}…{key[-4:]}'


SEED_MODELS = [
    {'key': 'deepseek-v4-flash', 'name': 'DeepSeek 快速版', 'sort': 0, 'is_default': True},
    {'key': 'deepseek-v4-pro', 'name': 'DeepSeek 专业版', 'sort': 1, 'is_default': False},
]


def seed_ai_deepseek(apps, schema_editor):
    AiProvider = apps.get_model('API', 'AiProvider')
    AiModel = apps.get_model('API', 'AiModel')

    key = (os.getenv('DEEPSEEK_API_KEY') or '').strip()
    base_url = (os.getenv('DEEPSEEK_API_URL') or '').strip() or DEFAULT_BASE_URL
    base_url = base_url.rstrip('/')
    if base_url.endswith('/beta'):
        base_url = base_url[:-5]

    provider = AiProvider.objects.filter(code='deepseek').first()
    if provider is None:
        provider = AiProvider.objects.create(
            code='deepseek',
            name='深度求索 DeepSeek',
            base_url=base_url,
            api_key=key,
            key_hint=_mask(key),
            sort=0,
            remark='由 0038 迁移依据 .env 初始化',
        )
    elif not (provider.api_key or '').strip() and key:
        provider.api_key = key
        provider.key_hint = _mask(key)
        provider.save()

    for item in SEED_MODELS:
        AiModel.objects.get_or_create(
            key=item['key'],
            defaults={
                'provider': provider,
                'name': item['name'],
                'sort': item['sort'],
                'is_default': item['is_default'],
                'remark': '由 0038 迁移初始化',
            },
        )


def unseed_ai_deepseek(apps, schema_editor):
    AiProvider = apps.get_model('API', 'AiProvider')
    # 模型随外键级联删除
    AiProvider.objects.filter(code='deepseek').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0037_ai_provider_model'),
    ]

    operations = [
        migrations.RunPython(seed_ai_deepseek, unseed_ai_deepseek),
    ]
