"""友情链接数据模型

供多个 SEO 项目共用的友情链接集合，通过 API 服务统一管理。
所有字段在 admin 后台自动可见（admin.py 会自动注册本模型）。
"""
from django.db import models

from API.common.base import BaseModel


class FriendLink(BaseModel):
    """友情链接

    字段说明:
        name        - 网站名称（必填，可重复）
        url         - 网站链接（必填，唯一）
        description - 网站描述（选填，用于 SEO 友链展示）
        logo        - 网站 logo URL（选填）
        category    - 分类（选填，方便后续按类目筛选）
        contact     - 联系方式（选填，QQ/微信/邮箱）
        sort        - 排序权重（越大越靠前，默认 0）
        status      - 启用状态（True=启用，False=禁用，默认 True）
        create_time - 创建时间（继承 BaseModel，自动填充）
        updated_time- 更新时间（继承 BaseModel，自动更新）
    """
    name = models.CharField('网站名称', max_length=100)
    url = models.URLField('网站链接', max_length=500, unique=True)
    description = models.TextField('网站描述', blank=True, default='')
    logo = models.URLField('Logo链接', max_length=500, blank=True, default='')
    category = models.CharField('分类', max_length=50, blank=True, default='', db_index=True)
    contact = models.CharField('联系方式', max_length=100, blank=True, default='')
    sort = models.IntegerField('排序权重', default=0, db_index=True)
    status = models.BooleanField('启用状态', default=True, db_index=True)

    class Meta:
        db_table = 'seo_friend_link'
        verbose_name = '友情链接'
        verbose_name_plural = '友情链接'
        ordering = ['-sort', '-create_time']

    def __str__(self):
        return f'{self.name} ({self.url})'
