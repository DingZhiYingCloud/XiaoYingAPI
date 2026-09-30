"""i18n 体检：扫出「漏包翻译」与「词条缺失」，CI / 提交前自查用

用法：
    .venv\\Scripts\\python.exe scripts\\check_i18n.py            # 只报问题
    .venv\\Scripts\\python.exe scripts\\check_i18n.py -v         # 附带每条命中的位置

检查三类问题（源语言是简体中文，词条见 locale/en/LC_MESSAGES/*.po）：

  1. 多行 `{# … #}` 注释 —— Django 的注释正则是 `{#.*?#}`，**点号不匹配换行**，
     所以跨行的 `{# #}` 根本不被当作注释：
       · 在 `{% include %}` 的片段里 → 原样渲染到页面上（用户可见的模板源码）
       · 在 `{% extends %}` 的子模板里 → 块外文本被丢弃，暂时看不出问题，但一样是雷
     修法：压成单行，或改用 `{% comment %}…{% endcomment %}`。

  2. 用了 `{% trans %}` / `{% blocktrans %}` / `gettext()` 但 .po 里查不到对应 msgid
     —— 页面上**不会报错**，只是静默回退中文，最难发现的一类。
     注意 `{% blocktrans %}` 里的 `{{ 变量 }}` 在 msgid 里会写成 `%(变量)s`，
     本脚本会自动归一化后再比对，所以不用手工核。

  3. 模板 / JS 里「裸奔」的中文（既没包 i18n，也不是注释）
     —— 这一类需要人工判断：数据库里的内容（项目名、反馈类型字典、服务名）
     与品牌名「小影API」本来就不该翻译，属于正常；其余才是漏网。

已知不检查 / 会误报的情形（看到时人工跳过即可）：
  · 语言切换器里的「简体中文 / 繁體中文」来自 Django 的 name_local（本族语写法），
    按 i18n 惯例不翻译。
  · 单字中文（多为品牌名被切碎的残片）。
"""
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / 'API' / 'templates').rglob('*.html'))
SCRIPTS = sorted((ROOT / 'API' / 'static' / 'js').rglob('*.js'))
PO_FILES = [
    ROOT / 'locale' / 'en' / 'LC_MESSAGES' / 'django.po',
    ROOT / 'locale' / 'en' / 'LC_MESSAGES' / 'djangojs.po',
]

# 第三方产物 / 自带中文的资源，不纳入检查
SKIP_PARTS = (
    'vendor/', 'lucide.min.js', 'tailwindcss',
    'captcha_auth/aliyun/ct4.js',   # 阿里云官方 SDK 原始产物
    'templates/母版引入代码.html',   # 给开发者参考的母版示例，「站点名称」是占位文案，本就该由使用者替换
)
# 明确不翻译的短词（品牌名等）
ALLOW_WORDS = {'小影', '小影API', '影'}

CJK = r'\u4e00-\u9fff'
CJK_RUN = re.compile(f'[{CJK}][{CJK}\\uff08\\uff09\\u3001\\uff0c\\u3002\\uff1a\\uff1b\\uff1f\\uff01'
                     f'\\u201c\\u201d\\u2014\\u2026\\u00b7\\-\\d%()]*')


def load_msgids(path):
    """读 .po 的全部 msgid（json 反转义，处理 \\" 与 \\\\）"""
    text = io.open(path, encoding='utf-8').read()
    out = set()
    for raw in re.findall(r'^msgid "((?:[^"\\]|\\.)*)"$', text, re.M):
        if not raw:
            continue
        try:
            out.add(json.loads('"' + raw + '"'))
        except ValueError:
            out.add(raw)
    return out


def normalize(text):
    """把模板写法和 .po 写法对齐：{{ x }} → %(x)s、空白折叠"""
    text = re.sub(r'\{\{\s*(\w+)\s*\}\}', r'%(\1)s', text)
    return re.sub(r'\s+', ' ', text).strip()


def strip_js_comments(text):
    """剥掉 JS 注释（含**行尾注释**），但不碰字符串里的 `//`

    简单正则会误伤 `'http://x'` 里的 `//`，也会漏掉 `code; // 注释` 这种行尾注释，
    所以这里按字符走一遍状态机：只在「代码态」识别注释，进入字符串后原样保留。
    """
    out = []
    i, n = 0, len(text)
    quote = None          # 当前所处的字符串引号；None = 代码态
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if quote:
            out.append(ch)
            if ch == '\\':
                if nxt:
                    out.append(nxt)
                    i += 2
                    continue
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'", '`'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and nxt == '/':
            while i < n and text[i] != '\n':
                i += 1
            continue
        if ch == '/' and nxt == '*':
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def strip_comments(text, is_template):
    """模板只对 <script> 块跑 JS 注释剥离；HTML 正文里的撇号会把状态机带偏"""
    if not is_template:
        return strip_js_comments(text)
    return re.sub(r'(?is)(<script\b[^>]*>)(.*?)(</script>)',
                  lambda m: m.group(1) + strip_js_comments(m.group(2)) + m.group(3), text)


def mask_i18n(text, is_template):
    """剔除注释与已被 i18n 包裹的片段，返回 (剩余正文, 用到的词条)"""
    used = []

    # ---- 注释 ----
    text = re.sub(r'\{%\s*comment\s*%\}[\s\S]*?\{%\s*endcomment\s*%\}', '', text)
    text = re.sub(r'\{#[\s\S]*?#\}', '', text)          # 跨行的另行单独报告
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    text = strip_comments(text, is_template)

    # ---- {% trans "…" %} / {% translate "…" %} ----
    for m in re.finditer(r"""\{%\s*(?:trans|translate)\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", text):
        used.append(m.group(1) or m.group(2) or '')
    text = re.sub(r"""\{%\s*(?:trans|translate)\s+(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')(?:\s+[^%]*?)?%\}""", '', text)

    # ---- {% blocktrans … %}…{% endblocktrans %} ----
    for m in re.finditer(r'\{%\s*blocktrans[^%]*%\}([\s\S]*?)\{%\s*endblocktrans\s*%\}', text):
        used.append(m.group(1))
    text = re.sub(r'\{%\s*blocktrans[^%]*%\}[\s\S]*?\{%\s*endblocktrans\s*%\}', '', text)

    # ---- JS gettext('…') / _t('…') / _ti('…', ctx) / _i('…', ctx) / interpolate('…') ----
    #    站点各脚本自带 _t / _ti / _i 包装（见 docs_image.js、captcha-client.js 顶部），
    #    漏掉它们会把已经翻译好的句子误报成「未包翻译」
    HELPER = r'(?:gettext|gettext_noop|_t|_ti|_tt|_i|interpolate)'
    for m in re.finditer(
            HELPER + r"""\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", text):
        used.append(m.group(1) or m.group(2) or '')
    text = re.sub(HELPER + r"""\(\s*(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""", '', text)

    # ---- 剩下的模板标签 ----
    text = re.sub(r'\{%[\s\S]*?%\}', '', text)
    return text, [u for u in used if u.strip()]


def check_file(path, msgids):
    rel = str(path.relative_to(ROOT)).replace('\\', '/')
    raw = io.open(path, encoding='utf-8').read()
    problems = []

    def line_of(pos):
        return raw[:pos].count('\n') + 1

    # 1. 跨行 {# … #}
    for m in re.finditer(r'\{#', raw):
        end = raw.find('#}', m.start())
        if end < 0:
            problems.append(('多行注释', line_of(m.start()), '{# 没有配对的 #}'))
        elif '\n' in raw[m.start():end]:
            problems.append(('多行注释', line_of(m.start()),
                             '跨行 {# #}（不会被当成注释）: ' + normalize(raw[m.start():end + 2])[:70]))

    body, used = mask_i18n(raw, path.suffix == '.html')

    # 2. 用了 i18n 但 .po 里没有该词条
    normalized_ids = {normalize(i) for i in msgids}
    for item in used:
        key = normalize(item)
        if not re.search(f'[{CJK}]', item):
            continue
        if key in normalized_ids or item in msgids:
            continue
        problems.append(('词条缺失', line_of(raw.find(item)) if item in raw else 0, key[:70]))

    # 3. 裸奔的中文
    for m in CJK_RUN.finditer(body):
        text = m.group(0)
        if len(text) < 2 or text in ALLOW_WORDS:
            continue
        if text in msgids or normalize(text) in normalized_ids:
            continue
        problems.append(('未包翻译', body[:m.start()].count('\n') + 1, text[:70]))
    return rel, problems


def main():
    verbose = '-v' in sys.argv
    msgids = set()
    for po in PO_FILES:
        msgids |= load_msgids(po)

    total = 0
    buckets = {}
    for path in TEMPLATES + SCRIPTS:
        rel = str(path.relative_to(ROOT)).replace('\\', '/')
        if any(s in rel for s in SKIP_PARTS):
            continue
        rel, problems = check_file(path, msgids)
        if not problems:
            continue
        buckets[rel] = problems
        total += len(problems)

    if not total:
        print('i18n 体检通过：没有发现漏包翻译、词条缺失或多行模板注释。')
        return 0

    for rel, problems in buckets.items():
        print(f'\n{rel}')
        for kind, line, text in problems:
            where = f':{line}' if line else ''
            print(f'  [{kind}]{where} {text}')
    print(f'\n共 {total} 处，分布在 {len(buckets)} 个文件。')
    print('提示：「未包翻译」里若为数据库内容（项目名、反馈类型字典、服务名）或品牌名，属正常，可忽略。')
    if not verbose:
        print('加 -v 可查看全部明细。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
