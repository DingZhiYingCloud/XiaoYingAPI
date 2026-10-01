# 红果短剧「外链登记」下线：第 4 集及以后已改为本站按需解密 + 转 H.264 直出，
# 不再需要人工登记外部平台地址，故删除 hongguo_episode_video 表。
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0046_security_setting'),
    ]

    operations = [
        migrations.DeleteModel(
            name='HongguoEpisodeVideo',
        ),
    ]
