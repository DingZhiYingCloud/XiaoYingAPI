from django.db import models

"""
Django数据库迁移命令
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
source .venv/bin/activate

1P面板: pip install -r requirements.txt && python manage.py makemigrations && python manage.py migrate && python manage.py runserver 0.0.0.0:10000
"""

class BaseModel(models.Model):
    """项目基础模型，所有业务模型继承此类"""

    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        abstract = True