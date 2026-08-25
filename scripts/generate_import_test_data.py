"""模拟爬虫生成「批量导入音乐」接口的边界测试数据（默认 10000 条）

用法：
    python scripts/generate_import_test_data.py                # 生成默认 10000 条
    python scripts/generate_import_test_data.py --count 100    # 自定义条数（按比例缩放）
    python scripts/generate_import_test_data.py --out xxx.json # 自定义输出路径

输出文件格式与导入接口约定一致：JSON 数组，每条含 name/singer/online/music_sources。
脚本会打印各类数据的条数与预期结果（成功/失败），便于导入后对照接口返回的统计。
所有记录名称统一以 "Mock-" 前缀开头，便于导入后按名称清理测试数据。
"""
import argparse
import json
import os
import random

PREFIX = 'Mock-'  # 名称统一前缀，便于导入后清理
SPECIAL_CHARS = '🎵🎶"\' \n\tＡＢＣ１２３<>/\\&《》·、，。！？'


def _name(seed, extra_len=0):
    """生成以 Mock- 开头、长度可扩展的名称"""
    return f'{PREFIX}{seed}{"x" * extra_len}'


# ==================== 合法数据（预期成功） ====================

def gen_normal(count):
    """普通合法：多歌手 + 播放源"""
    return [
        {'name': _name(f'normal{i}'), 'singer': [f'歌手A{i}', f'歌手B{i}'],
         'online': True, 'music_sources': [f'https://example.com/{i}.mp3', f'https://example.com/{i}_hd.mp3']}
        for i in range(count)
    ]


def gen_special_name(count):
    """特殊字符名称（emoji/引号/换行/全角/HTML 等，应正常入库）"""
    rows = []
    for i in range(count):
        chars = SPECIAL_CHARS * ((i % 5) + 1)
        rows.append({'name': f'{PREFIX}special{i}{chars}', 'singer': ['歌手']})
    return rows


def gen_boundary_name(count):
    """name 恰好 200 字符（边界值，应成功）"""
    return [
        {'name': _name(f'boundary{i}', 200 - len(_name(f'boundary{i}'))), 'singer': ['歌手']}
        for i in range(count)
    ]


def gen_special_singer(count):
    """singer 含特殊字符/数字字符串（应成功）"""
    return [
        {'name': _name(f'singer{i}'), 'singer': ['蔡依林（Jolin）', 'The "Weeknd"', f'歌手{int(i / 2)}号']}
        for i in range(count)
    ]


def gen_string_sources(count):
    """music_sources 为单个 URL 字符串（兼容形式，应成功）"""
    return [
        {'name': _name(f'strsrc{i}'), 'singer': ['歌手'], 'music_sources': f'https://example.com/{i}.mp3'}
        for i in range(count)
    ]


def gen_online_variants(count):
    """online 各种合法写法（true/false/1/0/是/否，应成功）"""
    variants = [True, False, 'true', 'false', '1', '0', '是', '否']
    return [
        {'name': _name(f'online{i}'), 'singer': ['歌手'], 'online': variants[i % len(variants)]}
        for i in range(count)
    ]


def gen_no_sources(count):
    """无 music_sources 字段（应成功）"""
    return [{'name': _name(f'nosrc{i}'), 'singer': ['歌手']} for i in range(count)]


def gen_empty_sources(count):
    """music_sources 为空数组（应成功）"""
    return [
        {'name': _name(f'emptysrc{i}'), 'singer': ['歌手'], 'music_sources': []}
        for i in range(count)
    ]


# ==================== 非法数据（预期失败） ====================

def gen_long_name(count):
    """name 超过 200 字符（失败：name 最长 200）"""
    return [{'name': _name(f'long{i}', 220), 'singer': ['歌手']} for i in range(count)]


def gen_missing_name(count):
    """缺 name 字段（失败：参数缺失 name）"""
    return [{'singer': ['歌手']} for i in range(count)]


def gen_missing_singer(count):
    """缺 singer 字段（失败：参数缺失 singer）"""
    return [{'name': _name(f'missinger{i}')} for i in range(count)]


def gen_empty_singer(count):
    """singer 为空数组/空串/None（失败：singer 不能为空）"""
    empties = [[], [''], [None], None]
    return [
        {'name': _name(f'emptysinger{i}'), 'singer': empties[i % len(empties)]}
        for i in range(count)
    ]


def gen_url_no_scheme(count):
    """url 无协议头（失败：url 非法）"""
    return [
        {'name': _name(f'noscheme{i}'), 'singer': ['歌手'], 'music_sources': [f'example.com/{i}.mp3']}
        for i in range(count)
    ]


def gen_url_garbage(count):
    """url 为乱码（失败：url 非法）"""
    return [
        {'name': _name(f'garbage{i}'), 'singer': ['歌手'], 'music_sources': ['not a url']}
        for i in range(count)
    ]


def gen_url_too_long(count):
    """url 超过 500 字符（失败：url 最长 500）"""
    return [
        {'name': _name(f'longurl{i}'), 'singer': ['歌手'], 'music_sources': ['https://example.com/' + 'x' * 600]}
        for i in range(count)
    ]


def gen_sources_wrong_type(count):
    """music_sources 类型错误：数字/对象/布尔（失败：music_sources 必须为字符串或数组）

    注：None 会被宽容为"无源"成功导入（与不传字段等价），不作为失败场景。
    """
    wrong = [123, {'a': 1}, True]
    return [
        {'name': _name(f'wrongsrc{i}'), 'singer': ['歌手'], 'music_sources': wrong[i % len(wrong)]}
        for i in range(count)
    ]


def gen_not_object(count):
    """记录不是 JSON 对象（失败：记录必须为 JSON 对象）"""
    wrong = [123, 'string', None, [1, 2, 3]]
    return [wrong[i % len(wrong)] for i in range(count)]


def gen_empty_url(count):
    """url 为空字符串（失败：url 缺失）"""
    return [
        {'name': _name(f'emptyurl{i}'), 'singer': ['歌手'], 'music_sources': ['']}
        for i in range(count)
    ]


def gen_combined(count):
    """组合问题：name 超长 + 非法 url + 空歌手 多个问题叠加（失败）"""
    return [
        {'name': _name(f'combined{i}', 250), 'singer': [], 'music_sources': ['bad url']}
        for i in range(count)
    ]


def gen_singer_wrong_type(count):
    """singer 类型错误：数字/对象（归一化为空后失败：singer 不能为空）"""
    wrong = [123, {'name': 'x'}, 3.14]
    return [
        {'name': _name(f'wrongsinger{i}'), 'singer': wrong[i % len(wrong)]}
        for i in range(count)
    ]


# 分类注册表：(生成函数, 基准条数, 预期结果, 说明)
CATEGORIES = [
    (gen_normal,           2000, 'success', '普通合法（多歌手+播放源）'),
    (gen_special_name,     1000, 'success', '特殊字符名称（emoji/引号/换行/HTML）'),
    (gen_boundary_name,     500, 'success', 'name 恰好 200 字符（边界）'),
    (gen_special_singer,    500, 'success', 'singer 含特殊字符/数字字符串'),
    (gen_string_sources,    500, 'success', 'music_sources 为单个 URL 字符串'),
    (gen_online_variants,   300, 'success', 'online 各种合法写法'),
    (gen_no_sources,        400, 'success', '无 music_sources'),
    (gen_empty_sources,     300, 'success', 'music_sources 空数组'),
    (gen_long_name,        1000, 'fail',    'name 超过 200 字符'),
    (gen_missing_name,      600, 'fail',    '缺 name'),
    (gen_missing_singer,    500, 'fail',    '缺 singer'),
    (gen_empty_singer,      400, 'fail',    'singer 空数组/空串/None'),
    (gen_url_no_scheme,     300, 'fail',    'url 无协议头'),
    (gen_url_garbage,       300, 'fail',    'url 乱码'),
    (gen_url_too_long,      200, 'fail',    'url 超过 500 字符'),
    (gen_sources_wrong_type, 150, 'fail',   'music_sources 类型错误'),
    (gen_not_object,        150, 'fail',    '记录非 JSON 对象'),
    (gen_empty_url,         100, 'fail',    'url 空字符串'),
    (gen_combined,          100, 'fail',    '多问题叠加（超长name+空singer+非法url）'),
    (gen_singer_wrong_type, 200, 'fail',    'singer 类型错误（数字/对象）'),
]


def main():
    parser = argparse.ArgumentParser(description='生成批量导入接口的模拟爬虫测试数据')
    parser.add_argument('--count', type=int, default=10000, help='生成总条数（默认 10000）')
    parser.add_argument('--out', default=os.path.join(os.path.dirname(__file__), 'mock_crawler_data.json'),
                        help='输出 JSON 文件路径')
    args = parser.parse_args()

    total = args.count
    base_total = sum(c[1] for c in CATEGORIES)
    scale = total / base_total

    # 按基准条数等比缩放各分类，并修正取整偏差（差额补/扣到第一个成功分类）
    counts, success_idx = [], []
    for i, (_, base, expect, _) in enumerate(CATEGORIES):
        counts.append(round(base * scale))
        if expect == 'success':
            success_idx.append(i)
    diff = total - sum(counts)
    if diff and success_idx:
        counts[success_idx[0]] += diff

    records = []
    success_expect = 0
    for (func, _, expect, desc), n in zip(CATEGORIES, counts):
        records.extend(func(n))
        print(f'  [{"成功" if expect == "success" else "失败"}] {desc}: {n} 条')
        if expect == 'success':
            success_expect += n
    random.shuffle(records)  # 打乱分类顺序，更贴近真实爬虫数据

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    print(f'\n共生成 {len(records)} 条 -> {args.out}')
    print(f'预期成功 {success_expect} 条，预期失败 {len(records) - success_expect} 条')


if __name__ == '__main__':
    main()
