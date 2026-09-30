"""短剧 - 红果线路 剧集外部播放地址

背景：源站只对每部剧**前 3 集**下发明文直链；第 4 集及以后是 DRM 加密的 H.265
（CENC AES-CTR + 自定义 spade 密钥包装），桌面浏览器无法直接播放，源站也不提供
明文 / m3u8 通道。故改为「外部托管 + 链接登记」：

    预处理工具（manage.py hongguo_preprocess）解密导出
        → 人工上传到外部平台 / 对象存储
        → 本表登记可播地址
        → /api/dramas/hongguo/play 查到就返回、查不到返回「正在扩展存储」的提示
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class HongguoEpisodeVideo(BaseModel):
    """红果短剧 单集外部播放地址（第 4 集及以后）"""

    class UrlType(models.TextChoices):
        MP4 = 'mp4', 'MP4'
        M3U8 = 'm3u8', 'M3U8'

    id = models.UUIDField('记录ID', primary_key=True, default=uuid.uuid4, editable=False)
    series_id = models.CharField('剧集ID', max_length=32, db_index=True)
    series_name = models.CharField('剧集名', max_length=200, blank=True, default='')
    ep = models.PositiveIntegerField('集数')
    url = models.URLField('播放地址', max_length=1000)
    url_type = models.CharField('链接类型', max_length=8, choices=UrlType.choices,
                                default=UrlType.MP4,
                                help_text='mp4=直链文件；m3u8=HLS 播放列表')
    enabled = models.BooleanField('启用', default=True)

    class Meta:
        db_table = 'hongguo_episode_video'
        verbose_name = '红果短剧外链'
        verbose_name_plural = '红果短剧外链'
        ordering = ['series_id', 'ep']
        constraints = [
            models.UniqueConstraint(fields=['series_id', 'ep'],
                                    name='uniq_hongguo_episode_video'),
        ]

    def __str__(self):
        return f'{self.series_id}#{self.ep}'
