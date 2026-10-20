"""超管控制台 - 程序下载统计

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET /console/programs/    「计算程序」各条目的下载次数排行
                               （整包 / 单文件分列，另给合计与最近下载时间）

数据来源：`API/website/programs_stats.py`（计数写在下载视图里，本页只读）。
行清单以磁盘上的程序目录为准；某程序被移出目录后，它的历史计数仍留在表里，
目录恢复即重新出现。
"""
from django.shortcuts import render

from . import programs, programs_stats
from .admin_auth import superadmin_required


@superadmin_required
def program_downloads_view(request):
    """下载排行页：按合计次数倒序，从未下载的程序排在后面"""
    stats = programs_stats.counts_by_rel()
    rows = []
    for program in programs.all_programs():
        stat = stats.get(program.rel)
        rows.append({
            'rel': program.rel,
            'name': program.name,
            'category': program.category,
            'pack_count': stat.pack_count if stat else 0,
            'file_count': stat.file_count if stat else 0,
            'total_count': stat.total_count if stat else 0,
            'last_download_time': stat.last_download_time if stat else None,
        })
    rows.sort(key=lambda row: (-row['total_count'], row['rel']))
    return render(request, 'console/programs.html', {
        'rows': rows,
        'total_downloads': sum(row['total_count'] for row in rows),
        'downloaded_programs': sum(1 for row in rows if row['total_count']),
    })
