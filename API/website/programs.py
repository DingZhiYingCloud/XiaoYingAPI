"""「计算程序」（CalculationProgram）模块数据层：扫描内容目录、提取条目元数据、渲染说明文档。

目录约定（根目录见 settings.PROGRAMS_ROOT）：

    CalculationProgram/
    ├── Documents.md          # 模块总述（可选的列表页导语）
    └── <分类>/                # 一级子目录即一个分类
        ├── README.md         # 分类说明（可选）
        └── <程序目录>/        # 「含 README.md 且含普通文件」的目录 = 一个程序条目
            ├── README.md     # 程序说明（详情页正文）
            └── ...           # 其余文件全部作为可下载文件对外提供

设计要点：
- 目录即数据：新增程序只需在根目录下建目录并写 README.md，无需改代码、无需建表。
- 只读不写：本模块不修改内容目录，也不感知版本控制，纯按磁盘现状展示。
- 相对标识 rel 统一使用 POSIX 风格（如 cloak/dp-2026/1），既是 URL 片段也是下载白名单键；
  由 _safe_dir 统一阻断 ../ 与符号链接越界，其余函数一律不自行拼接路径。
"""
import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from django.conf import settings
from django.utils.translation import gettext as _

README_NAME = 'readme.md'        # 程序 / 分类说明文件名（大小写不敏感匹配）
MODULE_DOC_NAME = 'Documents.md'  # 模块总述文件名（内容根目录下，可选）

# 在线预览的体积上限：超过该值的文件不提供「查看内容」，只能下载。
# 判定在扫描时完成（模板块据此决定按钮是否可用），视图侧仍会再校验一次，防止直接调接口绕过。
PREVIEW_MAX_BYTES = 1024 * 1024

# 渲染说明文档用的扩展：extra 含表格/围栏代码/属性列表，toc 生成标题锚点（供文档内跳转）
_MD_EXTENSIONS = ['extra', 'toc', 'sane_lists']
# toc 扩展的锚点分隔符，需与说明文档里手写的 #5-常见问题 这类锚点保持一致
_MD_EXTENSION_CONFIGS = {'toc': {'separator': '-'}}


@dataclass(frozen=True)
class ProgramFile:
    """程序目录内的单个文件（相对所属程序目录的路径 + 体积）"""
    path: str
    size: int
    size_label: str
    previewable: bool   # 是否允许在线预览（超过 PREVIEW_MAX_BYTES 的文件只能下载）


@dataclass(frozen=True)
class Program:
    """一个程序条目"""
    rel: str            # 相对内容根目录的 POSIX 路径，如 cloak/dp-2026/1
    name: str           # 展示名（去掉分类后的路径片段，用 "-" 连接），如 dp-2026-1
    category: str       # 所属分类（一级目录名）
    directory: Path
    files: tuple        # tuple[ProgramFile, ...]，按路径排序
    total_size: int
    total_size_label: str


@dataclass(frozen=True)
class Category:
    """内容根目录下的一个一级分类"""
    name: str           # 分类目录名，如 cloak
    desc_html: str      # 分类 README 的渲染结果（无 README 时为空串）
    programs: tuple     # tuple[Program, ...]


def _human_size(num: int) -> str:
    """把字节数格式化为人类可读体积（用于展示，不参与计算）"""
    size = float(num)
    for unit in ('B', 'KB', 'MB'):
        if size < 1024:
            return f'{int(size)} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} GB'


def _natural_key(text: str):
    """自然排序键：让 2 排在 10 之前（目录名多为 1、2、… 这类序号）"""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text)]


def _render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=_MD_EXTENSIONS, extension_configs=_MD_EXTENSION_CONFIGS)


def _read_doc_html(path: Path) -> str:
    """读取说明文档并渲染成 HTML；读不出来时退化为一段提示，不让整页 500。

    说明文档由人工维护，Windows 记事本「另存为」默认就是 ANSI/GBK，此时
    read_text 会抛 UnicodeDecodeError；文件正被占用/删除时抛 OSError。
    两种情况都只影响这一段说明，页面其余内容照常展示。
    """
    try:
        return _render_markdown(path.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, OSError):
        return f'<p class="text-warning">{_("该说明文档读取失败，请确认文件编码为 UTF-8。")}</p>'


def _find_readme(directory: Path) -> Path | None:
    """在目录内查找 README.md（大小写不敏感）"""
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.name.lower() == README_NAME:
            return entry
    return None


def _collect_files(directory: Path) -> tuple:
    """收集程序目录内的全部可下载文件（递归；README 已作为正文展示，不计入）"""
    files = []
    for entry in sorted(directory.rglob('*')):
        if not entry.is_file() or entry.name.lower() == README_NAME:
            continue
        size = entry.stat().st_size
        files.append(ProgramFile(
            path=entry.relative_to(directory).as_posix(),
            size=size,
            size_label=_human_size(size),
            previewable=size <= PREVIEW_MAX_BYTES,
        ))
    return tuple(files)


def _is_program_dir(directory: Path) -> bool:
    """判定是否为程序目录：含 README.md，且除 README 外至少还有一个普通文件"""
    if not directory.is_dir() or _find_readme(directory) is None:
        return False
    return any(e.is_file() and e.name.lower() != README_NAME for e in directory.iterdir())


def _walk(directory: Path, rel: str, category: str, out: list) -> None:
    """自顶向下收集程序目录：命中的目录不再向下递归，避免父子目录重复收录"""
    if _is_program_dir(directory):
        files = _collect_files(directory)
        total = sum(f.size for f in files)
        out.append(Program(
            rel=rel,
            name=rel[len(category) + 1:].replace('/', '-'),
            category=category,
            directory=directory,
            files=files,
            total_size=total,
            total_size_label=_human_size(total),
        ))
        return
    for child in sorted((e for e in directory.iterdir() if e.is_dir()), key=lambda p: _natural_key(p.name)):
        _walk(child, f'{rel}/{child.name}', category, out)


def load_catalog() -> tuple:
    """扫描内容根目录，返回全部分类（每个分类含其下的程序条目）。

    根目录不存在（如尚未投放内容）时返回空元组，由页面展示空态，不抛异常。
    """
    root = Path(settings.PROGRAMS_ROOT)
    if not root.is_dir():
        return ()
    categories = []
    for entry in sorted((e for e in root.iterdir() if e.is_dir()), key=lambda p: _natural_key(p.name)):
        found = []
        _walk(entry, entry.name, entry.name, found)
        if not found:
            continue  # 分类下没有程序条目的目录不展示，避免出现空分类
        readme = _find_readme(entry)
        categories.append(Category(
            name=entry.name,
            desc_html=_read_doc_html(readme) if readme else '',
            programs=tuple(found),
        ))
    return tuple(categories)


def all_programs() -> tuple:
    """全部程序条目（跨分类展平）"""
    return tuple(p for cat in load_catalog() for p in cat.programs)


def get_program(rel: str) -> Program | None:
    """按相对路径取单个程序条目；不存在或越界返回 None"""
    for program in all_programs():
        if program.rel == rel:
            return program
    return None


def read_readme(directory: Path) -> str:
    """读取并渲染某程序目录的 README.md（缺失时返回空串）"""
    readme = _find_readme(directory)
    return _read_doc_html(readme) if readme else ''


def module_intro() -> str:
    """模块总述（内容根目录下 Documents.md 的渲染结果，缺失时返回空串）"""
    root = Path(settings.PROGRAMS_ROOT)
    doc = root / MODULE_DOC_NAME
    return _read_doc_html(doc) if doc.is_file() else ''


def resolve_download(rel_path: str) -> Path | None:
    """把下载请求的相对路径解析为内容根目录内的真实文件。

    rel_path 形如 cloak/dp-2026/1/dp-code.js；越界、指向目录或不存在均返回 None。
    """
    root = Path(settings.PROGRAMS_ROOT)
    if not root.is_dir():
        return None
    resolved_root = root.resolve()
    candidate = (resolved_root / rel_path.replace('\\', '/')).resolve()
    if candidate == resolved_root or not candidate.is_relative_to(resolved_root):
        return None
    return candidate if candidate.is_file() else None
