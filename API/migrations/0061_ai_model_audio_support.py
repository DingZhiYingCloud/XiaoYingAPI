# AI 模型支持「音频理解」+ 打开已实测通过的视频/音频模型能力
#
# 背景：豆包 Doubao-Seed-2.0 是**全模态**模型，官方标注支持「文本 / 图片 / 语音 / 视频」
# 四模态理解。音频能力已用 3 秒的 mp3 实测通过（走 Chat API 的 input_audio 内容块，
# HTTP 200 并识别出音频内容，用量里 audio_tokens 有计数）。因此给 AI 模型表补两个字段：
#   supports_audio - 勾选后才允许 /api/ai/BuiltInModel/chat 携带 audios（走 input_audio 块）
#   max_audios     - 单次请求最多可携带的音频个数
#
# 同时把此前种下的豆包模型的「支持音频理解」打开（迁移 0060 种下的模型只有视频能力）。
from django.db import migrations, models

#: 迁移 0060 种下的豆包模型标识
DOUBAO_MODEL_KEY = 'doubao-seed-2-0-mini'


def enable_doubao_audio(apps, schema_editor):
    """打开豆包模型的音频能力（仅当该模型存在时才动它）"""
    AiModel = apps.get_model('API', 'AiModel')
    AiModel.objects.filter(key=DOUBAO_MODEL_KEY).update(supports_audio=True)


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0060_ai_model_video_support'),
    ]

    operations = [
        migrations.AddField(
            model_name='aimodel',
            name='max_audios',
            field=models.PositiveSmallIntegerField(default=1, help_text='仅对支持音频的模型生效；请求携带的 audios 超过此数会返回参数值非法', verbose_name='最多音频数'),
        ),
        migrations.AddField(
            model_name='aimodel',
            name='supports_audio',
            field=models.BooleanField(default=False, help_text='勾选后才允许请求携带 audios（如豆包 Seed 2.0 全模态模型）；未勾选传音频会返回参数值非法', verbose_name='支持音频理解'),
        ),
        migrations.RunPython(enable_doubao_audio, migrations.RunPython.noop),
    ]
