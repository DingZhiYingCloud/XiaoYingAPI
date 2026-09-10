"""生成繁体中文（zh-hant）词条：把源语言（简体中文）逐条转成繁体，写入 locale/zh-hant/

为什么是「生成」而不是手写译文：
    本项目繁体版采用「仅转字形」的通用繁體（用词与简体保持一致），
    因此 zh-hant 的译文可以由 msgid（简体原文）机械转换得到，无需人工翻译，
    也避免了 1000+ 条词条手工维护时出现遗漏或不一致。

词条清单来源：
    locale/en/LC_MESSAGES/django.po 与 djangojs.po 的 msgid 顺序与分组。
    → 新增/修改文案时，请先补齐英文词条（en 的 .po），再执行本脚本。

依赖：
    zhconv（纯 Python，仅构建期需要；运行时 Django 只读 .mo，不需要它）
    安装：python -m pip install zhconv

用法：
    python scripts/make_zh_hant.py     # 重新生成 locale/zh-hant/ 下的 .po
    python scripts/compile_locale.py   # 再编译成 .mo，否则 Django 不会生效
"""
import ast
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EN_DIR = BASE_DIR / 'locale' / 'en' / 'LC_MESSAGES'
# 注意：locale 子目录名必须用 to_locale() 的形式（语言码中的连字符改成下划线、地区首字母大写），
# 例如 zh-hant → zh_Hant、zh-hans → zh_Hans。写成 locale/zh-hant 的话 Django 找不到 .mo。
HANT_DIR = BASE_DIR / 'locale' / 'zh_Hant' / 'LC_MESSAGES'
DOMAINS = ('django', 'djangojs')

HEADER = (
    '# Traditional Chinese (zh-hant) for XiaoYingAPI website\n'
    '# 本文件由 scripts/make_zh_hant.py 自动生成，请勿手工修改（改了会在下次生成时被覆盖）。\n'
    '# 通用繁體：仅做字形转换，用词与简体版保持一致；如需台湾/香港用词，请改为人工维护并停用该脚本。\n'
    '# 重新生成：python scripts/make_zh_hant.py && python scripts/compile_locale.py\n'
)

# zhconv 的通用繁体表在个别字上给的是异体字或港式写法，这里统一校正为港澳台通行的标准字形。
# 注意：只校正「同一字的不同字形」，不动「地区用词」——例如 账号/賬號（保留，不改台灣的帳號）、
# 链接/鏈接（保留，不改台灣的連結）、字段/字段（保留，不改台灣的欄位）。
POST_FIX = {
    '爲': '為',   # 「为」
    '啓': '啟',   # 「启」
    '僞': '偽',   # 「伪」
    '裏': '裡',   # 「里」
}

# 「签」在 zhconv 里一律转成「籤」（于是出现「需籤名」），但通用繁体应为「簽」；
# 只有下列词语才真正用「籤」，转换时先保护、校正后再还原。
KEEP_QIAN = ('標籤', '書籤', '抽籤')


def to_hant(text: str, convert) -> str:
    """转繁体 + 校正用字（见 POST_FIX / KEEP_QIAN 说明）"""
    out = convert(text, 'zh-hant')
    for i, word in enumerate(KEEP_QIAN):
        out = out.replace(word, f'\u0000{i}\u0000')
    out = out.replace('籤', '簽')
    for i, word in enumerate(KEEP_QIAN):
        out = out.replace(f'\u0000{i}\u0000', word)
    for src, dst in POST_FIX.items():
        out = out.replace(src, dst)
    return out


def escape(text: str) -> str:
    """按 gettext .po 规则转义（与生成 en 词条时的口径一致）"""
    return (text.replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\t', '\\t'))


def convert_po(text: str, translate) -> tuple[str, int]:
    """逐行把 msgstr 换成「由 msgid 转出的繁体」

    只改动 msgstr 行：分组注释、词条顺序、msgid 全部原样保留，
    保证 zh-hant 与 en 的结构一一对应，便于对照审阅。
    :param translate: 单参数函数，输入简体原文返回繁体
    """
    out, msgid, count = [], None, 0
    for line in text.splitlines():
        if line.startswith('msgid '):
            msgid = ast.literal_eval(line[6:])
            out.append(line)
        elif line.startswith('msgstr ') and msgid is not None:
            out.append(f'msgstr "{escape(translate(msgid))}"')
            count += 1
        else:
            out.append(line)
    return '\n'.join(out) + '\n', count


def body_of(text: str) -> str:
    """取 .po 正文（跳过文件头注释），用于替换成繁体版自己的文件头"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('# ====='):
            return '\n'.join(lines[i:])
    return text


def main():
    try:
        import zhconv
    except ImportError:
        raise SystemExit(
            '缺少依赖 zhconv（仅用于生成繁体词条）。请先安装：\n'
            '    .venv\\Scripts\\python.exe -m pip install zhconv'
        )

    HANT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for domain in DOMAINS:
        src = EN_DIR / f'{domain}.po'
        if not src.exists():
            print(f'跳过 {domain}.po（英文词条文件不存在）')
            continue
        body, count = convert_po(body_of(src.read_text(encoding='utf-8')),
                                 lambda s: to_hant(s, zhconv.convert))
        dst = HANT_DIR / f'{domain}.po'
        dst.write_text(HEADER + '\n' + body, encoding='utf-8')
        total += count
        print(f'{dst.relative_to(BASE_DIR)}：{count} 条')
    print(f'完成，共 {total} 条繁体词条。记得执行：python scripts/compile_locale.py')


if __name__ == '__main__':
    main()
