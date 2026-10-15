from django.db import models

"""
Django数据库迁移命令（A-05：迁移文件入库，线上仅 migrate，不在线上 makemigrations）
本地开发模型变更：python manage.py makemigrations API --name <迁移名>
部署执行：python manage.py migrate
python manage.py collectstatic --noinput
source .venv/bin/activate

删除缓存
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

1P面板: pip install -r requirements.txt && python manage.py migrate && python manage.py runserver 0.0.0.0:10000
"""

class BaseModel(models.Model):
    """项目基础模型，所有业务模型继承此类

    注：`create_time` 故意**不加 db_index** —— Django 在 SQLite 上为「给字段加索引」发出的
    是整表重建（CREATE new_ / INSERT SELECT / DROP / RENAME），45 张表全量重建不可接受。
    需要「不带过滤条件、只按 -create_time 排序分页」的追加型大表，在其自身 Meta.indexes 里
    单独加索引（见 Music / User / PushLog / Feedback），那才是纯 CREATE INDEX。
    """

    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        abstract = True