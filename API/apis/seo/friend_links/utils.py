"""友情链接 CRUD 数据库操作封装

所有函数返回 (success, data_or_msg) 二元组，便于视图层统一处理。
异常已在内部捕获，调用方无需再 try/except。
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .models import FriendLink


def _to_dict(link: FriendLink) -> dict:
    """将 FriendLink 实例序列化为字典"""
    return {
        'id': link.id,
        'name': link.name,
        'url': link.url,
        'description': link.description,
        'logo': link.logo,
        'category': link.category,
        'contact': link.contact,
        'sort': link.sort,
        'status': link.status,
        'create_time': link.create_time.strftime('%Y-%m-%d %H:%M:%S') if link.create_time else None,
        'updated_time': link.updated_time.strftime('%Y-%m-%d %H:%M:%S') if link.updated_time else None,
    }


def list_friend_links(keyword: str = '',
                       category: str = '', status: str = '') -> tuple:
    """查询全部友情链接

    :param keyword: 搜索关键词，匹配名称/URL/描述
    :param category: 分类精确匹配
    :param status: 状态过滤，'true'/'false' 字符串
    :return: (True, {items, total}) 或 (False, msg)
    """
    try:
        qs = FriendLink.objects.all()
        if keyword:
            qs = qs.filter(name__icontains=keyword) | \
                 qs.filter(url__icontains=keyword) | \
                 qs.filter(description__icontains=keyword)
        if category:
            qs = qs.filter(category=category)
        if status in ('true', 'false'):
            qs = qs.filter(status=(status == 'true'))

        qs = qs.order_by('-sort', '-create_time')
        items = list(qs)

        return True, {
            'items': [_to_dict(x) for x in items],
            'total': len(items),
        }
    except Exception as e:
        return False, f'查询友情链接失败: {e}'


def get_friend_link(link_id: int) -> tuple:
    """按 ID 查询单条友情链接"""
    try:
        link = FriendLink.objects.get(id=link_id)
        return True, _to_dict(link)
    except FriendLink.DoesNotExist:
        return False, f'友情链接不存在: id={link_id}'
    except Exception as e:
        return False, f'查询友情链接失败: {e}'


def create_friend_link(data: dict) -> tuple:
    """创建友情链接

    :param data: 字段字典，必须包含 name 和 url
    :return: (True, link_dict) 或 (False, msg)
    """
    name = (data.get('name') or '').strip()
    url = (data.get('url') or '').strip()
    if not name:
        return False, '参数缺失: name(网站名称)'
    if not url:
        return False, '参数缺失: url(网站链接)'

    try:
        link = FriendLink(
            name=name,
            url=url,
            description=(data.get('description') or '').strip(),
            logo=(data.get('logo') or '').strip(),
            category=(data.get('category') or '').strip(),
            contact=(data.get('contact') or '').strip(),
            sort=int(data.get('sort', 0) or 0),
            status=_parse_bool(data.get('status'), default=True),
        )
        link.full_clean()
        link.save()
        return True, _to_dict(link)
    except ValidationError as e:
        return False, f'参数校验失败: {"; ".join(f"{k}: {v[0]}" for k, v in e.message_dict.items())}'
    except IntegrityError as e:
        return False, f'数据冲突（url 已存在）: {e}'
    except Exception as e:
        return False, f'创建友情链接失败: {e}'


def update_friend_link(link_id: int, data: dict) -> tuple:
    """更新友情链接（部分字段）

    只更新 data 中出现的字段，未传入的字段保持不变。
    """
    try:
        link = FriendLink.objects.get(id=link_id)
    except FriendLink.DoesNotExist:
        return False, f'友情链接不存在: id={link_id}'
    except Exception as e:
        return False, f'查询友情链接失败: {e}'

    # 逐字段更新（仅更新 data 中存在的字段）
    updated_fields = []
    for field in ['name', 'url', 'description', 'logo', 'category', 'contact']:
        if field in data:
            setattr(link, field, (data[field] or '').strip() if isinstance(data[field], str) else data[field])
            updated_fields.append(field)
    if 'sort' in data:
        try:
            link.sort = int(data['sort'])
            updated_fields.append('sort')
        except (ValueError, TypeError):
            return False, '参数格式错误: sort 必须为整数'
    if 'status' in data:
        link.status = _parse_bool(data['status'], default=link.status)
        updated_fields.append('status')

    try:
        link.full_clean()
        link.save()
        return True, _to_dict(link)
    except ValidationError as e:
        return False, f'参数校验失败: {"; ".join(f"{k}: {v[0]}" for k, v in e.message_dict.items())}'
    except IntegrityError as e:
        return False, f'数据冲突（url 已存在）: {e}'
    except Exception as e:
        return False, f'更新友情链接失败: {e}'


def delete_friend_link(link_id: int) -> tuple:
    """按 ID 删除友情链接"""
    try:
        link = FriendLink.objects.get(id=link_id)
        link.delete()
        return True, None
    except FriendLink.DoesNotExist:
        return False, f'友情链接不存在: id={link_id}'
    except Exception as e:
        return False, f'删除友情链接失败: {e}'


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
