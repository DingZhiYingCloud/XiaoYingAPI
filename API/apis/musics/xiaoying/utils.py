"""小影音乐 CRUD 数据库操作封装

所有函数返回 (success, data_or_msg) 二元组，便于视图层统一处理。
异常已在内部捕获，调用方无需再 try/except。
"""
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from API.models.music import Music, MusicSource


def _format_time(dt):
    """时间格式化为字符串，空值返回 None"""
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None


def _music_to_dict(music: Music) -> dict:
    """将 Music 实例序列化为字典"""
    return {
        'id': str(music.id),
        'name': music.name,
        'singer': music.singer,
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

    :param data: 字段字典，必须包含 name 和 singer
    :return: (True, music_dict) 或 (False, msg)
    """
    name = (data.get('name') or '').strip()
    singer = (data.get('singer') or '').strip()
    if not name:
        return False, '参数缺失: name(音乐名称)'
    if not singer:
        return False, '参数缺失: singer(音乐歌手)'

    try:
        music = Music(
            name=name,
            singer=singer,
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
    """
    try:
        music = Music.objects.get(id=music_id)
    except Music.DoesNotExist:
        return False, f'音乐不存在: id={music_id}'
    except Exception as e:
        return False, f'查询音乐失败: {e}'

    for field in ['name', 'singer']:
        if field in data:
            setattr(music, field, (data[field] or '').strip() if isinstance(data[field], str) else data[field])
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
