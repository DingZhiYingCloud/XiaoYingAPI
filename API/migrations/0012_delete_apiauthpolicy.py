# 旧 ApiAuthPolicy 逐条策略已被分类树（ApiCategory）替代，删除旧表
# 依赖 0011 保证：先完成分类树建表 + 旧策略数据迁移，再删表

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0011_apicategory'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ApiAuthPolicy',
        ),
    ]
