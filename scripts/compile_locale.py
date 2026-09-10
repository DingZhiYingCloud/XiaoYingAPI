"""编译多语言文件：locale/<语言码>/LC_MESSAGES/django.po → django.mo

为什么需要这个脚本：
    本机未安装 gettext（无 msgfmt 命令），Django 自带的 `manage.py compilemessages`
    依赖系统的 msgfmt，无法使用。本脚本用纯 Python 实现 .po → .mo 编译（二进制格式
    见 GNU gettext 手册），不依赖任何第三方库。

使用方式：
    在项目根目录执行：python scripts/compile_locale.py
    修改任意 django.po 后必须重新执行本脚本，Django 运行时只读取 django.mo。

约定：
    - 源语言（msgid）为简体中文，因此 locale/zh-hans/ 可留空（找不到译文时原样显示）；
    - 空 msgid 的条目（.po 文件头）由本脚本统一生成，.po 中无需手写头部。
"""
import ast
import struct
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / 'locale'


def parse_po(text: str):
    """解析 .po 文本 → [(msgid, msgstr)]（忽略注释、空条目与文件头）"""
    entries, msgid, msgstr, field = [], None, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('msgid '):
            if msgid:
                entries.append((msgid, msgstr or ''))
            msgid, msgstr, field = ast.literal_eval(line[6:]), None, 'id'
        elif line.startswith('msgstr '):
            msgstr, field = ast.literal_eval(line[7:]), 'str'
        elif line.startswith('"') and field:
            # 多行字符串：msgid "" / msgstr "" 后续的续行
            if field == 'id':
                msgid += ast.literal_eval(line)
            else:
                msgstr = (msgstr or '') + ast.literal_eval(line)
    if msgid:
        entries.append((msgid, msgstr or ''))
    return entries


def build_mo(entries, language: str) -> bytes:
    """.po 条目 → .mo 二进制（含 UTF-8 文件头，Django 依赖它识别字符集）"""
    header = (
        'Project-Id-Version: XiaoYingAPI\n'
        'MIME-Version: 1.0\n'
        'Content-Type: text/plain; charset=UTF-8\n'
        'Content-Transfer-Encoding: 8bit\n'
        f'Language: {language}\n'
    )
    # 空 msgid 条目标识文件头；排序后空串天然排在最前
    pairs = sorted({('', header), *entries})
    ids, strs = b'', b''
    offsets_id, offsets_str = [], []
    for msgid, msgstr in pairs:
        b_id, b_str = msgid.encode('utf-8'), msgstr.encode('utf-8')
        offsets_id.append((len(b_id), len(ids)))
        ids += b_id + b'\x00'
        offsets_str.append((len(b_str), len(strs)))
        strs += b_str + b'\x00'

    count = len(pairs)
    table_id_off = 7 * 4
    table_str_off = table_id_off + count * 8
    data_off = table_str_off + count * 8
    out = struct.pack('<7I', 0x950412DE, 0, count, table_id_off, table_str_off, 0, 0)
    for length, off in offsets_id:
        out += struct.pack('<2I', length, data_off + off)
    for length, off in offsets_str:
        out += struct.pack('<2I', length, data_off + len(ids) + off)
    return out + ids + strs


def main():
    pos = sorted(LOCALE_DIR.glob('*/LC_MESSAGES/*.po'))
    if not pos:
        print(f'未找到任何 .po 文件（目录: {LOCALE_DIR}）')
        return
    for po in pos:
        language = po.parent.parent.name
        entries = parse_po(po.read_text(encoding='utf-8'))
        mo = po.with_suffix('.mo')
        mo.write_bytes(build_mo(entries, language))
        print(f'已编译 {po.relative_to(BASE_DIR)} → {mo.relative_to(BASE_DIR)}（{len(entries)} 条译文）')


if __name__ == '__main__':
    main()
