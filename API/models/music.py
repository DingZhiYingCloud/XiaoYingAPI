"""音乐底层数据模型

供多个音乐平台爬虫共用的统一存储框架，通过小影音乐 API 服务统一管理。
不同平台爬取到的音乐数据，先归一化为 Music(元数据) + MusicSource(播放源) 两层结构再入库，
解决各平台数据格式不一致的问题。

字段说明:
    Music:
        id          - 音乐唯一ID（UUID 主键，音乐名称/歌手可重复，唯独 ID 不可重复）
        name        - 音乐名称（必填，可重复）
        singer      - 音乐歌手（必填，可重复）
        online      - 是否在线（True=在线，False=离线，默认 True）
                      查询接口默认只返回在线音乐，离线音乐不返回（过滤逻辑在 API 层处理）
        create_time - 创建时间（继承 BaseModel，自动填充）
        updated_time- 更新时间（继承 BaseModel，自动更新）

    MusicSource:
        id          - 播放源唯一ID（UUID 主键）
        music       - 关联 Music 的外键（music_id），通过它关联到音乐元数据
        url         - 可直接播放的音乐链接（必填）
        create_time - 创建时间（继承 BaseModel，自动填充）
        updated_time- 更新时间（继承 BaseModel，自动更新）
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class Music(BaseModel):
    """音乐元数据（模型 A）

    一首音乐可对应多条播放源（MusicSource，一对多）。
    """
    id = models.UUIDField('音乐ID', primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('音乐名称', max_length=200)
    singer = models.CharField('音乐歌手', max_length=200)
    online = models.BooleanField('是否在线', default=True, db_index=True)

    class Meta:
        db_table = 'music'
        verbose_name = '音乐'
        verbose_name_plural = '音乐'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.name} - {self.singer}'


class MusicSource(BaseModel):
    """音乐播放源（模型 B）

    存放可直接播放的音乐链接，通过外键 music_id 关联到 Music。
    同一首音乐可有多个播放源（不同平台/不同清晰度）。
    """
    id = models.UUIDField('播放源ID', primary_key=True, default=uuid.uuid4, editable=False)
    music = models.ForeignKey(
        Music,
        on_delete=models.CASCADE,
        related_name='music_sources',
        verbose_name='关联音乐',
    )
    url = models.URLField('播放链接', max_length=500)

    class Meta:
        db_table = 'music_source'
        verbose_name = '播放源'
        verbose_name_plural = '播放源'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.url}'
