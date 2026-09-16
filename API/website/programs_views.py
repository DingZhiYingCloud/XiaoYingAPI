"""「计算程序」模块视图：列表页 / 详情页 / 文件下载 / 在线预览

对外开放策略：
- 页面与文件均公开可见（与文档中心一致），不做登录校验；
- 下载分两种：?path= 取单个文件，?pack= 取该程序整包 zip；
- 两者都只接受「内容根目录内的相对路径」，由 programs.resolve_download 统一拦截
  ../ 越界与符号链接逃逸，视图本身不拼接任何文件系统路径；
- 在线预览仅回传文本正文，超过 programs.PREVIEW_MAX_BYTES 的文件一律拒绝。
"""
import tempfile
import zipfile

from django.http import FileResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from API.common import StatusCode

from . import programs


def _json(code, msg='', data=None):
    """统一响应结构（与官网其他 JSON 动作接口一致）"""
    return JsonResponse({'code': code, 'msg': msg, 'data': data})


def index(request):
    """/programs/ 列表页：按分类展示全部程序条目"""
    catalog = programs.load_catalog()
    return render(request, 'programs/index.html', {
        'categories': catalog,
        'intro_html': programs.module_intro(),
        'total': sum(len(cat.programs) for cat in catalog),
    })


def detail(request, rel):
    """/programs/<rel>/ 详情页：说明文档正文 + 可下载文件清单"""
    program = programs.get_program(rel.strip('/'))
    if program is None:
        return render(request, '404.html', status=404)
    return render(request, 'programs/detail.html', {
        'program': program,
        'readme_html': programs.read_readme(program.directory),
        'path_parts': program.rel.split('/'),
    })


def download(request):
    """/programs/download/ 文件下载

    ?path=<相对路径>           下载单个文件
    ?pack=<程序相对路径>       打包下载该程序目录下的全部文件（含 README）
    """
    pack = (request.GET.get('pack') or '').strip()
    if pack:
        return _download_pack(pack)

    rel_path = (request.GET.get('path') or '').strip()
    target = programs.resolve_download(rel_path)
    if target is None:
        return HttpResponseNotFound('文件不存在')
    return FileResponse(target.open('rb'), as_attachment=True, filename=target.name)


def _download_pack(rel):
    """打包下载：把程序目录下的全部文件写进临时文件再作为附件回传

    用临时文件而非内存缓冲，避免程序目录体积增长后整包占满内存；
    FileResponse 结束时关闭句柄，临时文件随之自动删除。
    """
    program = programs.get_program(rel.strip('/'))
    if program is None:
        return HttpResponseNotFound('程序不存在')

    handle = tempfile.TemporaryFile()
    with zipfile.ZipFile(handle, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(program.directory.rglob('*')):
            if entry.is_file():
                zf.write(entry, entry.relative_to(program.directory).as_posix())
    handle.seek(0)
    return FileResponse(handle, as_attachment=True,
                        filename=f'{program.name}.zip', content_type='application/zip')


@require_GET
def content(request):
    """/programs/content/ 在线预览：返回文件正文，供详情页「查看内容」弹窗展示

    超过 PREVIEW_MAX_BYTES 或无法按 UTF-8 解码的文件直接拒绝（提示改为下载），
    避免大文件与二进制内容拖垮浏览器。
    """
    target = programs.resolve_download((request.GET.get('path') or '').strip())
    if target is None:
        return _json(StatusCode.NOT_FOUND, _('文件不存在'))
    if target.stat().st_size > programs.PREVIEW_MAX_BYTES:
        return _json(StatusCode.PARAM_VALUE_INVALID, _('文件超过 1 MB，不支持在线预览，请下载后查看'))
    try:
        text = target.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return _json(StatusCode.PARAM_VALUE_INVALID, _('该文件不是文本文件，不支持在线预览，请下载后查看'))
    return _json(StatusCode.SUCCESS, '', {'content': text})
