"""「计算程序」下载计数：写入（含 60 秒去重）与查询

计数口径（与 `ProgramDownloadStat` 的两个字段一一对应）：
- `pack`：整包下载（`/programs/download/?pack=<程序 rel>`）
- `file`：单文件下载（`/programs/download/?path=<程序 rel>/<文件>`）

**去重**：同一来源 IP + 同一程序 + 同一入口，60 秒内只计一次。用跨 worker 共享的
文件缓存（`CACHES['ratelimit']`，与接口限流共用同一目录）做短时占位 —— 本地 locmem
每个 worker 各算一份，连点两下就可能记两次，不能用于这里。

**不阻塞下载**：统计是旁路能力，任何异常只记日志、不影响文件下发；计数发生在
`FileResponse` 构造之前，代表「已发起下载」，不保证客户端把文件收完（中途取消也计一次，
这是下载量统计的行业通行口径）。
"""
import logging

from django.core.cache import caches
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from API.common.ip_guard import client_ip
from API.models import ProgramDownloadStat

logger = logging.getLogger('website.programs')

#: 同 IP + 同程序 + 同入口的去重窗口（秒）
DEDUPE_SECONDS = 60

#: 计数入口 → 模型字段
_FIELD_BY_KIND = {'pack': 'pack_count', 'file': 'file_count'}

#: 去重缓存别名（文件缓存，跨 worker 共享）
_CACHE_ALIAS = 'ratelimit'


def _dedupe_key(kind: str, rel: str, ip: str) -> str:
    return f'programs_dl:{kind}:{ip}:{rel}'


def _drop_dedupe_key(key: str) -> None:
    """计数写库失败时撤掉占位，让下一次下载还能补记（缓存本身故障则忽略）"""
    try:
        caches[_CACHE_ALIAS].delete(key)
    except Exception:
        logger.warning('下载计数去重缓存不可用，无法撤销占位：%s', key, exc_info=True)


def record_download(rel: str, kind: str, request) -> bool:
    """记录一次下载；返回本次是否真的计入（被去重或失败时为 False）

    :param rel: 程序条目的相对路径（`Program.rel`，已由 programs 层校验过存在）
    :param kind: 'pack'（整包）/ 'file'（单文件）
    :param request: 用于取来源 IP（口径见 API/common/ip_guard.py 的 client_ip）
    """
    field = _FIELD_BY_KIND.get(kind)
    if not field or not rel:
        return False

    cache = caches[_CACHE_ALIAS]
    key = _dedupe_key(kind, rel, client_ip(request) or 'unknown')
    try:
        # add 只在键不存在时写入：返回 False 即 60 秒内已记过一次
        if not cache.add(key, 1, DEDUPE_SECONDS):
            return False
    except Exception:
        # 缓存故障时宁可多记，也不丢计数（下载照常进行）
        logger.warning('下载计数去重缓存不可用，本次照常计数：rel=%s kind=%s',
                       rel, kind, exc_info=True)

    now = timezone.now()
    try:
        updated = (ProgramDownloadStat.objects
                   .filter(rel=rel)
                   .update(**{field: F(field) + 1, 'last_download_time': now}))
        if not updated:
            try:
                ProgramDownloadStat.objects.create(
                    rel=rel, **{field: 1, 'last_download_time': now})
            except IntegrityError:
                # 并发首次创建：另一进程已插入，改为累加
                ProgramDownloadStat.objects.filter(rel=rel).update(
                    **{field: F(field) + 1, 'last_download_time': now})
    except Exception:
        logger.exception('下载计数写入失败：rel=%s kind=%s', rel, kind)
        _drop_dedupe_key(key)
        return False
    return True


def counts_by_rel(rels=None) -> dict:
    """取计数行，返回 {rel: ProgramDownloadStat}；传 rels 时只取这些程序"""
    queryset = ProgramDownloadStat.objects.all()
    if rels is not None:
        queryset = queryset.filter(rel__in=list(rels))
    return {stat.rel: stat for stat in queryset}


def get_stat(rel: str):
    """取单个程序的计数行；从未下载过时返回 None"""
    return ProgramDownloadStat.objects.filter(rel=rel).first()
