"""小影音乐爬虫 CLI 存储与文件管理

功能:
    - 输出文件读写: 不存在则新建，存在则追加并按歌曲 URL 去重
    - 播放源断点缓存: 查看/清理
    - 导入格式预检: 按小影「批量导入音乐」接口校验规则校验输出文件
    - 输出文件统计
"""
import json
import os
from urllib.parse import urlparse

from cli.config import DEFAULT_CACHE, MAX_NAME_LEN, MAX_URL_LEN


# ==================== 输出文件读写（追加去重） ====================

def load_records(path):
    """读取输出文件记录；文件不存在返回空列表，解析失败抛出异常"""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f'输出文件格式错误（应为 JSON 数组）: {path}')
    return data


def save_records(path, records):
    """全量写输出文件（UTF-8，缩进 2）"""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def merge_append(path, new_records):
    """把 new_records 追加合并到输出文件（按 song_url 去重）

    - 文件不存在则新建
    - 已有记录与新记录按 song_url 去重（同 URL 不重复写入）
    - 无 song_url 的记录不做去重（直接追加）

    :param path: 输出文件路径
    :param new_records: 新抓取的记录列表
    :return: (新增条数, 合并后文件总条数)
    """
    existing = load_records(path)
    seen = {r.get('song_url') for r in existing if r.get('song_url')}
    added = 0
    for r in new_records:
        url = r.get('song_url')
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        existing.append(r)
        added += 1
    if added:
        save_records(path, existing)
    return added, len(existing)


# ==================== 收集暂存文件（防崩溃丢数据） ====================

def pending_path(out_path):
    """由输出文件路径派生收集暂存文件路径（同目录，后缀 _pending.jsonl）"""
    root, _ = os.path.splitext(out_path)
    return root + '_pending.jsonl'


def pending_exists(path):
    """收集暂存文件是否存在且有内容"""
    return os.path.exists(path) and os.path.getsize(path) > 0


def append_pending(path, songs):
    """把歌曲清单追加到收集暂存文件（JSONL: 一行一首，追加写 O(1)）

    收集阶段每完成一个歌手立即调用，保证中途崩溃不丢已抓歌曲。

    :param path: 暂存文件路径（由 pending_path 派生）
    :param songs: list[dict] 每项含 song_name / artists / song_url
    """
    if not songs:
        return
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        for s in songs:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')


def load_pending(path):
    """读取收集暂存文件全部歌曲（损坏行跳过，容忍崩溃残留的半行写入）"""
    if not pending_exists(path):
        return []
    records = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


def save_pending(path, songs):
    """全量覆写收集暂存文件（JSONL: 一行一首）"""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for s in songs:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')


def clear_pending(path):
    """删除收集暂存文件（处理完成后调用）"""
    if os.path.exists(path):
        os.remove(path)


# ==================== 播放源断点缓存 ====================

def load_cache():
    """读取播放源缓存（song_url -> play_url）"""
    if os.path.exists(DEFAULT_CACHE):
        with open(DEFAULT_CACHE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    """写播放源缓存"""
    parent = os.path.dirname(os.path.abspath(DEFAULT_CACHE))
    os.makedirs(parent, exist_ok=True)
    with open(DEFAULT_CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def show_cache():
    """查看缓存统计"""
    cache = load_cache()
    with_src = sum(1 for v in cache.values() if v)
    return len(cache), with_src, len(cache) - with_src


def clear_cache():
    """清空播放源缓存"""
    if os.path.exists(DEFAULT_CACHE):
        os.remove(DEFAULT_CACHE)
    return True


# ==================== 导入格式预检 ====================

def precheck(path):
    """按小影「批量导入音乐」接口校验规则预检输出文件

    规则（与导入接口一致）:
        - name: 必填非空，长度 <= 200
        - singer: 必填非空列表
        - music_sources: 元素须为合法 http(s) URL，长度 <= 500
        - online: 布尔

    :param path: 输出文件路径
    :return: (总条数, 通过条数, 失败明细 list[{index, name, msg}])
    """
    try:
        records = load_records(path)
    except Exception as e:
        return 0, 0, [{'index': 0, 'name': '', 'msg': f'文件读取失败: {e}'}]

    failures = []
    for i, r in enumerate(records):
        name = r.get('name')
        if not isinstance(name, str) or not name.strip():
            failures.append({'index': i, 'name': '', 'msg': 'name 缺失或为空'})
            continue
        if len(name) > MAX_NAME_LEN:
            failures.append({'index': i, 'name': name, 'msg': f'name 超长（>{MAX_NAME_LEN}）'})
            continue
        singer = r.get('singer')
        if not isinstance(singer, list) or not singer:
            failures.append({'index': i, 'name': name, 'msg': 'singer 缺失或为空'})
            continue
        for u in (r.get('music_sources') or []):
            if not isinstance(u, str) or not u:
                failures.append({'index': i, 'name': name, 'msg': '播放源含非字符串/空项'})
                break
            parsed = urlparse(u)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                failures.append({'index': i, 'name': name, 'msg': f'播放源非合法 URL: {u[:40]}'})
                break
            if len(u) > MAX_URL_LEN:
                failures.append({'index': i, 'name': name, 'msg': f'播放源超长（>{MAX_URL_LEN}）: {u[:40]}'})
                break
    return len(records), len(records) - len(failures), failures


# ==================== 输出文件统计 ====================

def stat(path):
    """统计输出文件: 总条数 / 按 URL 去重后条数 / 多歌手 / 无源 / 失败数"""
    try:
        records = load_records(path)
    except Exception as e:
        return {'error': f'文件读取失败: {e}'}
    urls = {r.get('song_url') for r in records if r.get('song_url')}
    return {
        'total': len(records),
        'unique_by_url': len(urls),
        'multi_singer': sum(1 for r in records if isinstance(r.get('singer'), list) and len(r['singer']) > 1),
        'no_source': sum(1 for r in records if not (r.get('music_sources') or [])),
        'duplicated': len(records) - len(urls),
    }
