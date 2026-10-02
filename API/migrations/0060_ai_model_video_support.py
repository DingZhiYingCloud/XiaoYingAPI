# AI 模型支持「视频理解」+ 种下火山方舟（豆包）厂商与 Doubao-Seed-2.0-mini
#
# 背景：豆包 Doubao-Seed-2.0 是**全模态**模型，官方标注支持「文本 / 图片 / 语音 / 视频」
# 四模态理解（已用 4 秒带音轨的测试视频实测通过：模型既描述了画面，也识别出音轨）。
# 因此给 AI 模型表补两个字段：
#   supports_video - 勾选后才允许 /api/ai/BuiltInModel/chat 携带 videos（走 video_url 内容块）
#   max_videos     - 单次请求最多可携带的视频个数
#
# 同时种下「火山方舟」厂商与豆包模型（**不含 API Key**）：Key 是密钥，绝不能进迁移文件
# （迁移随代码入库），厂商先建好、由超管到 /console/ai/models/ 粘贴（AES-GCM 密文落库），
# 与 DeepSeek 现在的维护方式完全一致。
from django.db import migrations, models

#: 方舟（Ark）OpenAI 兼容接口的根地址（其后拼 /chat/completions）
ARK_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'
ARK_PROVIDER_CODE = 'ark'
#: 对外模型标识（请求参数 model 的取值）
DOUBAO_MODEL_KEY = 'doubao-seed-2-0-mini'
#: 真正发给上游的模型名（带版本号，便于以后不换对外标识就能升版本）
DOUBAO_UPSTREAM = 'doubao-seed-2-0-mini-260428'


def seed_ark_doubao(apps, schema_editor):
    """种下火山方舟厂商与豆包 Seed 2.0 mini 模型（幂等；API Key 留空待后台填写）"""
    AiProvider = apps.get_model('API', 'AiProvider')
    AiModel = apps.get_model('API', 'AiModel')

    provider, _created = AiProvider.objects.get_or_create(
        code=ARK_PROVIDER_CODE,
        defaults={
            'name': '火山方舟（豆包）',
            'base_url': ARK_BASE_URL,
            'enabled': True,
            'sort': 10,
            'remark': '豆包系列模型；Doubao-Seed 2.0 为全模态，支持文本 / 图片 / 语音 / 视频理解。',
        },
    )
    AiModel.objects.get_or_create(
        key=DOUBAO_MODEL_KEY,
        defaults={
            'provider': provider,
            'name': '豆包 Seed 2.0 mini',
            'upstream_name': DOUBAO_UPSTREAM,
            'supports_vision': True,
            'max_images': 10,
            'supports_video': True,
            'max_videos': 1,
            'context_window': 256000,
            'sort': 20,
            'enabled': True,
            'is_default': False,
            'remark': '全模态（文本 / 图片 / 语音 / 视频）；已实测支持视频理解（含音轨）。',
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0059_security_banned_ip'),
    ]

    operations = [
        migrations.AddField(
            model_name='aimodel',
            name='max_videos',
            field=models.PositiveSmallIntegerField(default=1, help_text='仅对支持视频的模型生效；请求携带的 videos 超过此数会返回参数值非法', verbose_name='最多视频数'),
        ),
        migrations.AddField(
            model_name='aimodel',
            name='supports_video',
            field=models.BooleanField(default=False, help_text='勾选后才允许请求携带 videos（如豆包 Seed 2.0 全模态模型）；未勾选传视频会返回参数值非法', verbose_name='支持视频理解'),
        ),
        migrations.RunPython(seed_ark_doubao, migrations.RunPython.noop),
    ]
