from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0109_click_word_challenge'),
    ]

    operations = [
        migrations.CreateModel(
            name='CaptchaStat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('day', models.DateField(db_index=True, help_text='按服务器本地时区切日', verbose_name='统计日期')),
                ('kind', models.CharField(choices=[('char', '字符图片'), ('arithmetic', '算术'), ('slider', '滑块'), ('click', '汉字点选')], help_text='char / arithmetic / slider / click', max_length=12, verbose_name='线路')),
                ('generated', models.PositiveIntegerField(default=0, verbose_name='生成次数')),
                ('passed', models.PositiveIntegerField(default=0, verbose_name='通过次数')),
                ('failed', models.PositiveIntegerField(default=0, help_text='答案错误 / 过期 / 已使用等业务失败，不含限流拦截', verbose_name='失败次数')),
                ('blocked', models.PositiveIntegerField(default=0, help_text='被 IP 限流或连续失败冷却拦截的请求', verbose_name='拦截次数')),
                ('fail_expired', models.PositiveIntegerField(default=0, verbose_name='失败-已过期')),
                ('fail_used', models.PositiveIntegerField(default=0, verbose_name='失败-已使用')),
                ('fail_wrong', models.PositiveIntegerField(default=0, verbose_name='失败-答案错误')),
                ('fail_abnormal', models.PositiveIntegerField(default=0, verbose_name='失败-轨迹异常')),
                ('fail_invalid', models.PositiveIntegerField(default=0, verbose_name='失败-不存在')),
            ],
            options={
                'verbose_name': '验证码统计',
                'verbose_name_plural': '验证码统计',
                'db_table': 'captcha_stat',
                'ordering': ['-day', 'kind'],
                'constraints': [models.UniqueConstraint(fields=('day', 'kind'), name='uniq_captcha_stat_day_kind')],
            },
        ),
    ]
