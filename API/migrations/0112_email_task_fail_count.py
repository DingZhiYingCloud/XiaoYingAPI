from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0111_behavior_sample'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailtask',
            name='fail_count',
            field=models.PositiveIntegerField(default=0, help_text='发送失败累加，成功后清零；一次性任务连续失败达到上限后自动停用', verbose_name='连续失败次数'),
        ),
        migrations.AlterField(
            model_name='emailtask',
            name='last_ok',
            field=models.BooleanField(blank=True, help_text='从未发送时为空；失败会自动重试（重复任务等下一周期，一次性任务按短间隔重试）', null=True, verbose_name='上次是否成功'),
        ),
    ]
