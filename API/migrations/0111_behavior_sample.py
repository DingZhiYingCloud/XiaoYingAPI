from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0110_captcha_stat'),
    ]

    operations = [
        migrations.CreateModel(
            name='BehaviorSample',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('scene', models.CharField(choices=[('login', '登录'), ('register', '注册'), ('send_code', '发送验证码'), ('reset', '重置密码'), ('feedback', '问题反馈'), ('other', '其他')], default='other', help_text='表单来源', max_length=16, verbose_name='场景')),
                ('score', models.PositiveSmallIntegerField(default=0, help_text='0-100，越大越可疑', verbose_name='风险分')),
                ('band', models.CharField(choices=[('low', '低风险'), ('mid', '中风险'), ('high', '高风险')], default='low', help_text='low / mid / high', max_length=8, verbose_name='风险档')),
                ('hits', models.JSONField(default=list, help_text='命中的规则键，如 ["too_fast", "webdriver"]', verbose_name='命中规则')),
            ],
            options={
                'verbose_name': '行为验证样本',
                'verbose_name_plural': '行为验证样本',
                'db_table': 'captcha_behavior_sample',
                'ordering': ['-create_time'],
                'indexes': [models.Index(fields=['-create_time'], name='captcha_behavior_time_idx')],
            },
        ),
    ]
