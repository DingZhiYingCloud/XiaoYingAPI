"""小影音乐 CRUD 数据库操作封装

所有函数返回 (success, data_or_msg) 二元组，便于视图层统一处理。
异常已在内部捕获，调用方无需再 try/except。
"""
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction

from API.models.music import Music, MusicSource

# 批量导入接口配置（可按需调整）
MAX_IMPORT_COUNT = 9999                 # 单次导入最大条数
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 上传文件大小上限：10MB


def _format_time(dt):
    """时间格式化为字符串，空值返回 None"""
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None


def _normalize_singers(singer) -> list:
    """歌手统一为列表

    兼容旧数据（CharField 时期存的字符串）与列表数据，
    API 返回时一律为列表形式，如 ["周杰伦", "蔡依林"]。
    """
    if isinstance(singer, str):
        return [singer] if singer else []
    if isinstance(singer, (list, tuple)):
        return [s for s in singer if s]
    return []


def _music_to_dict(music: Music) -> dict:
    """将 Music 实例序列化为字典"""
    return {
        'id': str(music.id),
        'name': music.name,
        'singer': _normalize_singers(music.singer),
        'online': music.online,
        'create_time': _format_time(music.create_time),
        'updated_time': _format_time(music.updated_time),
    }


def _source_to_dict(source: MusicSource) -> dict:
    """将 MusicSource 实例序列化为字典"""
    return {
        'id': str(source.id),
        'music_id': str(source.music_id),
        'url': source.url,
        'create_time': _format_time(source.create_time),
        'updated_time': _format_time(source.updated_time),
    }


def _parse_uuid(value) -> tuple:
    """解析 UUID 字符串

    :return: (True, UUID对象) 或 (False, 错误消息)
    """
    try:
        return True, uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False, None


# ==================== Music 增删改查 ====================

def list_musics(keyword: str = '', online: str = '', page: int = 1, page_size: int = 10) -> tuple:
    """查询音乐列表（分页）

    :param keyword: 搜索关键词，匹配名称/歌手
    :param online: 在线状态过滤，'true'/'false'；不传时默认只返回在线音乐（离线不返回）
    :param page: 页码，从 1 开始
    :param page_size: 每页条数，最大 100（调用方已校验，此处兜底）
    :return: (True, {items, total, page, page_size, total_pages}) 或 (False, msg)
    """
    try:
        qs = Music.objects.all()
        if keyword:
            qs = qs.filter(name__icontains=keyword) | qs.filter(singer__icontains=keyword)
        if online in ('true', 'false'):
            qs = qs.filter(online=(online == 'true'))
        else:
            # 默认只返回在线音乐
            qs = qs.filter(online=True)

        total = qs.count()
        # 分页（page >= 1，1 <= page_size <= 100）
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        start = (page - 1) * page_size
        items = list(qs[start:start + page_size])
        total_pages = (total + page_size - 1) // page_size if total else 0

        return True, {
            'items': [_music_to_dict(x) for x in items],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        }
    except Exception as e:
        return False, f'查询音乐失败: {e}'


def get_music(music_id: uuid.UUID) -> tuple:
    """按 ID 查询单条音乐，并附带其全部播放源

    :return: (True, {music字段..., music_sources: [播放源列表]}) 或 (False, msg)
    """
    try:
        music = Music.objects.get(id=music_id)
        data = _music_to_dict(music)
        data['music_sources'] = [_source_to_dict(s) for s in music.music_sources.all()]
        return True, data
    except Music.DoesNotExist:
        return False, f'音乐不存在: id={music_id}'
    except Exception as e:
        return False, f'查询音乐失败: {e}'


def create_music(data: dict) -> tuple:
    """创建音乐

    :param data: 字段字典，必须包含 name 和 singer（singer 支持字符串或列表，至少一个歌手）
    :return: (True, music_dict) 或 (False, msg)
    """
    name = (data.get('name') or '').strip()
    if not name:
        return False, '参数缺失: name(音乐名称)'
    if 'singer' not in data:
        return False, '参数缺失: singer(音乐歌手)'
    singers = _normalize_singers(data['singer'])
    if not singers:
        return False, '参数值非法: singer(音乐歌手) 不能为空'

    try:
        music = Music(
            name=name,
            singer=singers,
            online=_parse_bool(data.get('online'), default=True),
        )
        music.full_clean()
        music.save()
        return True, _music_to_dict(music)
    except ValidationError as e:
        return False, f'参数校验失败: {"; ".join(f"{k}: {v[0]}" for k, v in e.message_dict.items())}'
    except Exception as e:
        return False, f'创建音乐失败: {e}'


def update_music(music_id: uuid.UUID, data: dict) -> tuple:
    """更新音乐（部分字段）

    只更新 data 中出现的字段，未传入的字段保持不变。
    singer 为整体替换：传 singer 时将歌手列表整体更新。
    """
    try:
        music = Music.objects.get(id=music_id)
    except Music.DoesNotExist:
        return False, f'音乐不存在: id={music_id}'
    except Exception as e:
        return False, f'查询音乐失败: {e}'

    if 'name' in data:
        music.name = (data['name'] or '').strip()
    if 'singer' in data:
        singers = _normalize_singers(data['singer'])
        if not singers:
            return False, '参数值非法: singer(音乐歌手) 不能为空'
        music.singer = singers
    if 'online' in data:
        music.online = _parse_bool(data['online'], default=music.online)

    try:
        music.full_clean()
        music.save()
        return True, _music_to_dict(music)
    except ValidationError as e:
        return False, f'参数校验失败: {"; ".join(f"{k}: {v[0]}" for k, v in e.message_dict.items())}'
    except Exception as e:
        return False, f'更新音乐失败: {e}'


def delete_music(music_id: uuid.UUID) -> tuple:
    """按 ID 删除音乐（关联播放源级联删除）"""
    try:
        music = Music.objects.get(id=music_id)
        music.delete()
        return True, None
    except Music.DoesNotExist:
        return False, f'音乐不存在: id={music_id}'
    except Exception as e:
        return False, f'删除音乐失败: {e}'


# ==================== MusicSource 增删改查 ====================

def create_music_source(data: dict) -> tuple:
    """创建播放源

    :param data: 字段字典，必须包含 music_id（音乐UUID）和 url
    :return: (True, source_dict) 或 (False, msg)
    """
    music_id_str = (data.get('music_id') or '').strip()
    url = (data.get('url') or '').strip()
    if not music_id_str:
        return False, '参数缺失: music_id(关联音乐ID)'
    if not url:
        return False, '参数缺失: url(播放链接)'

    ok, music_uuid = _parse_uuid(music_id_str)
    if not ok:
        return False, '参数格式错误: music_id 必须为合法的 UUID'

    try:
        # 外键校验：关联的音乐必须存在
        if not Music.objects.filter(id=music_uuid).exists():
            return False, f'关联音乐不存在: music_id={music_id_str}'

        source = MusicSource(
            music_id=music_uuid,
            url=url,
        )
        source.full_clean()
        source.save()
        return True, _source_to_dict(source)
    except ValidationError as e:
        return False, f'参数校验失败: {"; ".join(f"{k}: {v[0]}" for k, v in e.message_dict.items())}'
    except IntegrityError as e:
        return False, f'数据冲突: {e}'
    except Exception as e:
        return False, f'创建播放源失败: {e}'


def update_music_source(source_id: uuid.UUID, data: dict) -> tuple:
    """更新播放源（部分字段）

    只更新 data 中出现的字段，未传入的字段保持不变。
    """
    try:
        source = MusicSource.objects.get(id=source_id)
    except MusicSource.DoesNotExist:
        return False, f'播放源不存在: id={source_id}'
    except Exception as e:
        return False, f'查询播放源失败: {e}'

    if 'music_id' in data:
        music_id_str = (data['music_id'] or '').strip()
        ok, music_uuid = _parse_uuid(music_id_str)
        if not ok:
            return False, '参数格式错误: music_id 必须为合法的 UUID'
        if not Music.objects.filter(id=music_uuid).exists():
            return False, f'关联音乐不存在: music_id={music_id_str}'
        source.music_id = music_uuid
    if 'url' in data:
        source.url = (data['url'] or '').strip()

    try:
        source.full_clean()
        source.save()
        return True, _source_to_dict(source)
    except ValidationError as e:
        return False, f'参数校验失败: {"; ".join(f"{k}: {v[0]}" for k, v in e.message_dict.items())}'
    except IntegrityError as e:
        return False, f'数据冲突: {e}'
    except Exception as e:
        return False, f'更新播放源失败: {e}'


def delete_music_source(source_id: uuid.UUID) -> tuple:
    """按 ID 删除播放源"""
    try:
        source = MusicSource.objects.get(id=source_id)
        source.delete()
        return True, None
    except MusicSource.DoesNotExist:
        return False, f'播放源不存在: id={source_id}'
    except Exception as e:
        return False, f'删除播放源失败: {e}'


# ==================== 批量导入 ====================

# URL 格式校验器（schemes 默认 http/https，与模型 URLField 一致）
_url_validator = URLValidator()


def _extract_sources(record: dict) -> list:
    """提取记录中的播放源 url 列表

    music_sources 可为字符串（单条 url）或字符串数组；缺省/空返回空列表。
    """
    sources = record.get('music_sources') or []
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, (list, tuple)):
        raise ValueError('参数格式错误: music_sources 必须为字符串或数组')
    return [str(s).strip() for s in sources]


def _build_import_item(record) -> tuple:
    """内存校验并构建 Music / MusicSource 实例（不写库）

    校验规则与 create_music / create_music_source 保持一致：
    name/singer 必填且非空、name ≤ 200 字符、url 必填且为合法 URL(≤500 字符)。
    校验失败抛 ValueError，由调用方将该条判为失败（不产生任何半成品数据）。

    :return: (music, [source, ...])
    """
    if not isinstance(record, dict):
        raise ValueError('记录必须为 JSON 对象')
    name = (record.get('name') or '').strip()
    if not name:
        raise ValueError('参数缺失: name(音乐名称)')
    if len(name) > 200:
        raise ValueError('参数值非法: name(音乐名称) 最长 200 字符')
    if 'singer' not in record:
        raise ValueError('参数缺失: singer(音乐歌手)')
    singers = _normalize_singers(record['singer'])
    if not singers:
        raise ValueError('参数值非法: singer(音乐歌手) 不能为空')

    music = Music(name=name, singer=singers, online=_parse_bool(record.get('online'), default=True))
    sources = []
    for url in _extract_sources(record):
        if not url:
            raise ValueError('参数缺失: url(播放链接)')
        if len(url) > 500:
            raise ValueError('参数值非法: url(播放链接) 最长 500 字符')
        try:
            _url_validator(url)
        except ValidationError:
            raise ValueError('url: 输入一个有效的 URL。') from None
        # 关联未保存的 music 实例：此处访问 music.id 会触发 UUID default 生成，
        # 与后续 bulk_create 写入的 id 保持一致
        sources.append(MusicSource(music=music, url=url))
    return music, sources


def import_musics(records: list) -> tuple:
    """批量导入音乐（含播放源），部分成功模式

    性能优化：先对所有记录做纯内存校验，将合法记录组装为实例，
    再通过 bulk_create 在单个事务内批量写入，避免逐条 save 与逐条事务的
    数据库往返开销（9999 条由约 80 秒降至秒级）。
    非法记录在校验阶段即被筛出并返回失败原因，其余正常入库，不去重。

    :param records: 数据列表，每条为 dict:
        {"name": str, "singer": [str, ...], "online": bool?, "music_sources": [url, ...]?}
    :return: (True, {total, success_count, failed_count, failures})
    """
    total = len(records)
    musics, sources, failures = [], [], []
    for index, record in enumerate(records):
        # 校验失败时也要能返回原始名称，故先提取（非对象记录取不到则留空）
        name = record.get('name') if isinstance(record, dict) else ''
        try:
            music, item_sources = _build_import_item(record)
        except Exception as e:
            failures.append({'index': index, 'name': name, 'msg': str(e)})
            continue
        musics.append(music)
        sources.extend(item_sources)

    if musics:
        try:
            with transaction.atomic():
                Music.objects.bulk_create(musics, batch_size=500)
                if sources:
                    MusicSource.objects.bulk_create(sources, batch_size=500)
        except Exception as e:
            # 不可预期的数据库错误：整批回滚（所有可预期失败已在校验阶段拦截）
            return False, f'批量导入失败: {e}'

    return True, {
        'total': total,
        'success_count': len(musics),
        'failed_count': len(failures),
        'failures': failures,
    }


def _parse_bool(val, default: bool) -> bool:
    """宽松解析布尔值，支持字符串/数字/布尔"""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ('true', '1', 'yes', 'on', '启用'):
        return True
    if s in ('false', '0', 'no', 'off', '禁用'):
        return False
    return default
