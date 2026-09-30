"""红果短剧预处理：把剧集解密导出为明文 mp4（供人工上传到外部平台）

背景：源站只对每部剧**前 3 集**下发明文直链，第 4 集及以后是 DRM 加密的 H.265
（CENC AES-CTR），桌面浏览器无法直接播放，源站也没有明文 / m3u8 通道。因此改为：
本命令在服务端取流 + 解密，按 `{剧名}_{剧集ID}` 目录导出成明文 mp4 →
人工上传到外部平台 / 对象存储 → 在超管控制台登记链接（登记无对外接口）。

用法：
    python manage.py hongguo_preprocess --series 7686894628578020414
    python manage.py hongguo_preprocess --series 7686894628578020414 --episodes 4-222
    python manage.py hongguo_preprocess --series 7686894628578020414 --episodes 4,5,6
    python manage.py hongguo_preprocess --series 7686894628578020414 --root D:\\drama

输出目录（根目录见 settings.HONGGUO_PREPROCESS_DIR）：
    {根目录}/{剧名}_{剧集ID}/001.mp4 002.mp4 ...

输出格式（超管面板据此解析进度，改动需同步 API/website/console_dramas.py）：
    OUTDIR <绝对路径>
    PROGRESS <已完成> <总数>
    DONE <成功> <失败>
文件已存在的集默认跳过（可断点续跑）。
"""
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from SpiderServices.dramas.hongguo import app_api
from SpiderServices.dramas.hongguo import offline
from SpiderServices.dramas.hongguo.main import HongguoDramaSpider

# 文件名里不允许出现的字符（Windows / POSIX 取并集），统一替换为下划线
_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')


def _safe_dirname(name, fallback):
    """把剧名转成安全的目录名（去掉非法字符、压掉多余空白、限制长度）"""
    cleaned = _ILLEGAL.sub('_', name or '').strip(' .')
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned[:80] or fallback


def _parse_episodes(spec, allowed):
    """
    解析 --episodes，返回升序的集号列表（只保留 allowed 中存在的集）。

    支持：'' 或 all = 全部；'4-222' 区间；'4-' 表示 4 到最后一集；'4,5,6' 逐条列出。
    """
    spec = (spec or '').strip()
    available = sorted(allowed)
    if not spec or spec.lower() == 'all':
        return available

    picked = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start_raw, _, end_raw = part.partition('-')
            if not start_raw.strip().isdigit():
                raise CommandError(f'--episodes 区间起点非法: {part!r}')
            start = int(start_raw)
            end = int(end_raw) if end_raw.strip() else (available[-1] if available else 0)
            if end_raw.strip() and not end_raw.strip().isdigit():
                raise CommandError(f'--episodes 区间终点非法: {part!r}')
            picked.update(range(start, end + 1))
        elif part.isdigit():
            picked.add(int(part))
        else:
            raise CommandError(f'--episodes 格式非法: {part!r}（示例 4-222 / 4,5,6）')

    return [ep for ep in sorted(picked) if ep in set(available)]


class Command(BaseCommand):
    help = '红果短剧预处理：解密导出剧集明文 mp4（供上传外部平台后登记链接）'

    def add_arguments(self, parser):
        parser.add_argument('--series', required=True, help='剧集 ID（纯数字）')
        parser.add_argument('--episodes', default='',
                            help='集数范围：留空/all=全部；也支持 4-222、4-、4,5,6')
        parser.add_argument('--root', default='',
                            help='输出根目录，默认 settings.HONGGUO_PREPROCESS_DIR')

    def handle(self, *args, **options):
        # 统一留终止标记：面板按日志里有无 DONE/FAILED 判定任务是否结束，
        # 缺了标记（如参数错误直接抛 CommandError）会一直显示「运行中」
        try:
            self._process(options)
        except Exception as e:  # noqa: BLE001
            self.stdout.write(f'FAILED {e}')
            self.stdout.flush()
            raise

    def _process(self, options):
        series_id = str(options['series']).strip()
        if not series_id.isdigit():
            raise CommandError(f'--series 必须为纯数字剧集 ID: {series_id!r}')

        detail = HongguoDramaSpider().get_detail(series_id)
        if not detail:
            raise CommandError(f'剧集不存在或源站未返回数据: {series_id}')
        name = _safe_dirname(detail.get('name'), series_id)

        # 一次取全部 vid 复用，避免每集重复签名（签名约 1s/次）
        vids = app_api.get_episode_vids(series_id)
        episodes = _parse_episodes(options['episodes'], vids)
        if not episodes:
            raise CommandError('未解析到任何可处理的集号（检查 --episodes 是否在该剧范围内）')

        root = options['root'] or getattr(settings, 'HONGGUO_PREPROCESS_DIR', '')
        if not root:
            raise CommandError('未配置输出根目录（--root 或 settings.HONGGUO_PREPROCESS_DIR）')
        out_dir = os.path.join(str(root), f'{name}_{series_id}')
        os.makedirs(out_dir, exist_ok=True)

        self.stdout.write(f'剧名: {detail.get("name")}')
        self.stdout.write(f'OUTDIR {out_dir}')
        self.stdout.write(f'共 {len(episodes)} 集待处理（源站该剧共 {len(vids)} 集）')
        self.stdout.flush()

        ok = failed = 0
        for idx, ep in enumerate(episodes, 1):
            out_path = os.path.join(out_dir, f'{ep:03d}.mp4')
            try:
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    self.stdout.write(f'  第 {ep} 集 跳过（已存在）')
                    ok += 1
                else:
                    info = offline.decrypt_episode(series_id, ep, out_path, vids=vids)
                    self.stdout.write(
                        f'  第 {ep} 集 完成 {info["quality"]} '
                        f'{info["size"] / 1e6:.1f}MB')
                    ok += 1
            except Exception as e:  # noqa: BLE001 - 单集失败不中断整批
                failed += 1
                self.stdout.write(f'  第 {ep} 集 失败: {e}')
            self.stdout.write(f'PROGRESS {idx} {len(episodes)}')
            self.stdout.flush()

        self.stdout.write(f'DONE {ok} {failed}')
        self.stdout.write(f'输出目录: {out_dir}')
        self.stdout.flush()
