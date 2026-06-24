from django.db import models

"""
Django数据库迁移命令
py manage.py makemigrations
py manage.py migrate
"""

class BaseModel(models.Model):
    """项目基础模型，所有业务模型继承此类"""

    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        abstract = True