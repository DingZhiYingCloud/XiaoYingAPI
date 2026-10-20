"""「计算程序」下载次数统计

计算程序本身是「目录即数据」（见 `API/website/programs.py`），磁盘上没有程序表，
因此统计键只能用程序目录相对内容根目录的 POSIX 路径 `rel`（如 `cloak/dp-2026/1`），
与下载白名单、URL 片段共用同一标识。

计数分两个入口（下载视图只有这两个入口）：
- `pack_count`：整包下载（`?pack=<程序 rel>`）次数；
- `file_count`：单文件下载（`?path=<程序 rel>/<文件>`）次数。

同一来源 IP + 同一程序 + 同一入口在 60 秒内只计一次，去重逻辑见
`API/website/programs_stats.py`；本表只存计数结果，不存下载明细。
"""
from django.db import models

from API.common.base import BaseModel


class ProgramDownloadStat(BaseModel):
    """一个程序条目的下载计数（每个 rel 一行，按需创建）"""

    rel = models.CharField(
        '程序相对路径', max_length=255, unique=True,
        help_text='相对内容根目录的 POSIX 路径，如 cloak/dp-2026/1',
    )
    pack_count = models.PositiveIntegerField('整包下载次数', default=0)
    file_count = models.PositiveIntegerField('单文件下载次数', default=0)
    last_download_time = models.DateTimeField('最近下载时间', null=True, blank=True)

    class Meta:
        db_table = 'website_program_download_stat'
        verbose_name = '程序下载统计'
        verbose_name_plural = '程序下载统计'

    def __str__(self):
        return f'{self.rel}（{self.total_count} 次）'

    @property
    def total_count(self) -> int:
        """整包 + 单文件的合计次数（展示与排行用）"""
        return (self.pack_count or 0) + (self.file_count or 0)
