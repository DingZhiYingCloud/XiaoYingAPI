"""超管控制台 - 红果短剧（预处理 + 外链登记管理）

鉴权：仅 Django is_superuser（见 admin_auth.py）；匿名与普通用户会被重定向到 /login/。

页面：
    /console/dramas/hongguo/         预处理面板 + 外链登记管理
    /console/dramas/hongguo/status/  预处理运行状态（JSON，供页面轮询）

预处理：本页把 `manage.py hongguo_preprocess` 作为**子进程**拉起，输出追加到
`logs/hongguo_preprocess.log`；页面按该文件「最近一次 RUN 区块」解析进度，
因此不受 Django 多 worker / 热重载影响（状态在文件里，不在进程内存里）。
输出格式约定见 API/management/commands/hongguo_preprocess.py 顶部说明。

外链登记：第 4 集及以后的播放地址由外部平台托管，人工上传后在这里登记。
登记**不提供对外接口**（仅超管后台可用），本页直接调用服务层
`hongguo_utils.save_episode_videos()`，校验逻辑统一收口在那里。
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from API.apis.dramas.hongguo import utils as hongguo_utils
from API.models import HongguoEpisodeVideo

from .admin_auth import superadmin_required

# 预处理日志（子进程 stdout/stderr 都写这里）
_LOG_NAME = 'hongguo_preprocess.log'
# 日志里标记「一次运行开始」的前缀（与命令输出约定一致）
_RUN_MARK = '=== RUN '
# 列表分页
_PAGE_SIZE = 100


def _log_path():
    log_dir = Path(getattr(settings, 'LOG_DIR', str(Path(settings.BASE_DIR) / 'logs')))
    return log_dir / _LOG_NAME


def _read_status(tail=300):
    """解析日志文件的「最近一次 RUN 区块」，返回进度与输出尾部"""
    path = _log_path()
    empty = {'running': False, 'started': False, 'done': 0, 'total': 0,
             'out_dir': '', 'finished': '', 'lines': []}
    if not path.exists():
        return empty

    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(_RUN_MARK):
            start = i
    if start is None:                      # 还没有任何一次运行
        return empty

    block = lines[start:]
    done = total = 0
    out_dir = finished = ''
    for line in block:
        if line.startswith('PROGRESS '):
            parts = line.split()
            if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                done, total = int(parts[1]), int(parts[2])
        elif line.startswith('OUTDIR '):
            out_dir = line[len('OUTDIR '):].strip()
        elif line.startswith('DONE ') or line.startswith('FAILED '):
            finished = line

    return {'running': not finished, 'started': True, 'done': done, 'total': total,
            'out_dir': out_dir, 'finished': finished, 'lines': block[-tail:]}


def _start_preprocess(series_id, episodes):
    """把预处理命令拉起为子进程（输出追加到日志，供页面轮询进度）"""
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (f'{_RUN_MARK}{time.strftime("%Y-%m-%d %H:%M:%S")} '
              f'series={series_id} episodes={episodes or "all"}\n')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(header)

    cmd = [sys.executable, '-u', str(Path(settings.BASE_DIR) / 'manage.py'),
           'hongguo_preprocess', '--series', series_id]
    if episodes:
        cmd += ['--episodes', episodes]

    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    log = open(path, 'ab', buffering=0)     # 子进程结束前持续追加；Popen 会持有自己的副本
    try:
        subprocess.Popen(cmd, cwd=str(settings.BASE_DIR), stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, env=env, creationflags=creationflags)
    finally:
        log.close()


def _redirect_with_series(series_id=''):
    url = reverse('website:console_dramas_hongguo')
    return redirect(f'{url}?series_id={series_id}' if series_id else url)


@superadmin_required
def hongguo_view(request):
    """红果短剧控制台：GET 渲染面板；POST 处理预处理与登记/启停/删除"""
    if request.method == 'POST':
        return _handle_post(request)

    series_id = (request.GET.get('series_id') or '').strip()
    rows = HongguoEpisodeVideo.objects.all()
    if series_id:
        rows = rows.filter(series_id=series_id)

    paginator = Paginator(rows, _PAGE_SIZE)
    return render(request, 'console/dramas_hongguo.html', {
        'status': _read_status(),
        'series_id': series_id,
        'page_obj': paginator.get_page(request.GET.get('page')),
        'paginator': paginator,
        # 分页链接需要带上筛选参数（见 console/_pagination.html）
        'page_prefix': f'series_id={series_id}&' if series_id else '',
        'url_types': hongguo_utils.URL_TYPES,
    })


@superadmin_required
def hongguo_status_view(request):
    """预处理运行状态（JSON，供页面轮询）"""
    return JsonResponse(_read_status())


def _handle_post(request):
    action = (request.POST.get('action') or '').strip()
    series_id = (request.POST.get('series_id') or '').strip()

    if action == 'preprocess_start':
        if not series_id.isdigit():
            messages.error(request, _('剧集 ID 必须为纯数字'))
            return _redirect_with_series()
        _start_preprocess(series_id, (request.POST.get('episodes') or '').strip())
        messages.success(request, _('预处理已启动，进度见下方输出（可离开本页，任务会继续跑）'))
        return _redirect_with_series()

    if action == 'episode_save':
        url_type = (request.POST.get('url_type') or '').strip().lower()
        if not series_id.isdigit():
            messages.error(request, _('剧集 ID 必须为纯数字'))
        elif url_type not in hongguo_utils.URL_TYPES:
            messages.error(request, _('链接类型非法'))
        else:
            ok, result = hongguo_utils.save_episode_videos(
                series_id, request.POST.get('items') or '', url_type,
                (request.POST.get('series_name') or '').strip())
            if ok:
                messages.success(request, _('登记完成：共 %(total)s 条（新增 %(created)s / 更新 %(updated)s）') % result)
            else:
                messages.error(request, result)
        return _redirect_with_series(series_id)

    if action in ('episode_toggle', 'episode_delete'):
        row = get_object_or_404(HongguoEpisodeVideo, pk=request.POST.get('id'))
        sid = row.series_id
        if action == 'episode_toggle':
            row.enabled = not row.enabled
            row.save(update_fields=['enabled', 'updated_time'])
            messages.success(request, _('已切换启用状态'))
        else:
            row.delete()
            messages.success(request, _('已删除该条登记'))
        return _redirect_with_series(sid)

    messages.error(request, _('未知操作'))
    return _redirect_with_series()
