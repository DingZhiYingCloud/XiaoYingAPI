from django.db import models

"""
Django数据库迁移命令（A-05：迁移文件入库，线上仅 migrate，不在线上 makemigrations）
本地开发模型变更：python manage.py makemigrations API --name <迁移名>
部署执行：python manage.py migrate
python manage.py collectstatic --noinput
source .venv/bin/activate

1P面板: pip install -r requirements.txt && python manage.py migrate && python manage.py runserver 0.0.0.0:10000
"""

class BaseModel(models.Model):
    """项目基础模型，所有业务模型继承此类"""

    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        abstract = True