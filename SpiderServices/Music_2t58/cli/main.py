"""小影音乐爬虫 CLI 入口

用法:
    交互式菜单:   python SpiderServices/Music_2t58/cli/main.py
    命令行方式:
        python SpiderServices/Music_2t58/cli/main.py crawl --start 1 --end 3 [--site 域名] [--out 文件] [--log 日志] [--retry 3]
        python SpiderServices/Music_2t58/cli/main.py retry  [--site 域名] [--out 文件] [--log 日志] [--retry 3]
        python SpiderServices/Music_2t58/cli/main.py precheck --file 输出文件
        python SpiderServices/Music_2t58/cli/main.py stat --file 输出文件
        python SpiderServices/Music_2t58/cli/main.py cache --show|--clear
        python SpiderServices/Music_2t58/cli/main.py log --tail 50 [--log 日志]

顶层兜底: 任何未预期异常都会被捕获并写入日志，程序不崩溃。
"""
import argparse
import os
import sys

# 支持两种运行方式: python cli/main.py 或 python -m cli.main
# 将 Music_2t58/ 加入 sys.path，使绝对导入 from cli.xxx 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.config import DEFAULT_OUT, DEFAULT_LOG, DEFAULT_RETRY, DEFAULT_THREADS, MAX_THREADS
from cli.logger import Logger, read_errors, tail_log, install_global_guard
from cli import config, crawler, storage
from urllib.parse import urlsplit


def _apply_site(args, logger):
    """应用 --site 指定的站点域名，并重建爬虫实例使新域名生效

    域名统一保存在 cli.config.SITE_BASE（可用环境变量 MUSIC_SITE 或 CLI --site 指定），
    避免硬编码单一域名。未传 --site 时保持当前配置不变。
    """
    site = getattr(args, 'site', None)
    if site:
        config.set_site(site)
        logger.info(f'站点域名已切换为: {config.SITE_BASE}', status='start')
    crawler.rebuild_spider()


# ==================== 各子命令实现 ====================

def _rewrite_song_host(path, host, logger):
    """把文件内所有歌曲 URL 的域名统一改写为 host（支持 JSONL 暂存与 JSON 数组输出）

    用途: 站点某子域名不可达时，把已抓歌曲的域名切到同站其他镜像域名再补播放源，
    并保持输出文件与暂存文件域名一致，避免同一首歌两个域名版本重复写入。
    """
    if path.endswith('.jsonl'):
        songs = storage.load_pending(path)
        n = sum(1 for s in songs if _apply_host(s, host))
        if n:
            storage.save_pending(path, songs)
    else:
        records = storage.load_records(path)
        n = sum(1 for r in records if _apply_host(r, host))
        if n:
            storage.save_records(path, records)
    if n:
        logger.info(f'已将 {os.path.basename(path)} 的歌曲域名统一改写为 {host}（共 {n} 首）', status='warn')


def _apply_host(item, host):
    """改写单条记录 song_url 的域名；返回是否发生改写"""
    u = item.get('song_url')
    if not u:
        return False
    site = urlsplit(u)
    if site.netloc == host:
        return False
    new = f'{site.scheme}://{host}{site.path}'
    if site.query:
        new += '?' + site.query
    item['song_url'] = new
    return True


def cmd_resume(args, logger):
    """补抓暂存文件中的播放源（不重新抓歌手）

    适用场景: 收集阶段已完成（歌曲已落盘暂存 *_pending.jsonl），但播放源
    因站点不可达等原因未抓完。本命令直接处理暂存文件，不重复请求歌手页。
    已写入输出文件的歌曲自动跳过，只补缺失部分。
    建议配合 --limit 分批小量补抓，避免触发站点风控。
    """
    _apply_site(args, logger)
    pend = args.pending or storage.pending_path(args.out)
    if not storage.pending_exists(pend):
        print(f'[提示] 暂存文件不存在或为空: {pend}')
        return 0
    host = getattr(args, 'rewrite_host', None)
    if host:
        _rewrite_song_host(pend, host, logger)      # 改写暂存
        _rewrite_song_host(args.out, host, logger)  # 改写输出（保持一致，避免双域名重复）
    logger.info(f'开始补抓暂存播放源: {os.path.basename(pend)} | 线程数 {args.threads} | 输出: {args.out}', status='start')
    n, fail = crawler._process_pending(logger, pend, args.out, args.retry,
                                       getattr(args, 'limit', 0), args.threads)
    print(f'补抓完成: 处理 {n} 首, 无源 {fail} 首')
    return 0


def cmd_crawl(args, logger):
    """抓取歌手列表指定页范围"""
    _apply_site(args, logger)
    if args.start > args.end:
        print(f'[错误] 起始页 {args.start} 不能大于结束页 {args.end}')
        return 1
    threads = getattr(args, 'threads', DEFAULT_THREADS)  # 兼容交互式菜单
    if not 1 <= threads <= MAX_THREADS:
        print(f'[错误] 线程数必须为 1-{MAX_THREADS}，收到 {threads}')
        return 1
    logger.info(f'开始抓取: 歌手列表第 {args.start}-{args.end} 页 | 线程数 {threads} | 输出: {args.out}', status='start')
    total_added = total_fail = 0
    for page in range(args.start, args.end + 1):
        try:
            limit = getattr(args, 'limit', 0)  # 兼容交互式菜单未传 limit 的情况
            n, fail = crawler.crawl_page(logger, page, args.out, args.retry, limit, threads)
            total_added += n
            total_fail += fail
        except Exception as e:
            logger.error(f'第 {page} 页抓取异常', exc=e, step='0-整页', page=page)
    logger.info(f'抓取完成: 处理 {args.end - args.start + 1} 页, 新增 {total_added} 首, 无源 {total_fail} 首', status='done')
    print(f'输出文件: {args.out}')
    print(f'日志文件: {args.log}')
    return 0


def cmd_retry(args, logger):
    """按错误清单重试失败的歌曲/播放源"""
    _apply_site(args, logger)
    errors = read_errors(args.log)
    song_errors = [e for e in errors if e.get('step') in ('2-歌手歌曲', '3-播放源')]
    if not song_errors:
        print(f'日志 {args.log} 中没有可重试的歌曲/播放源错误')
        return 0
    # 按 URL 去重（同一 URL 多次失败只重试一次）
    by_url = {}
    for e in song_errors:
        by_url[e['url']] = e
    print(f'错误记录 {len(song_errors)} 条, 去重后 {len(by_url)} 个待重试')

    crawler.ensure_session()
    success_records = []
    for url, e in by_url.items():
        try:
            if e['step'] == '2-歌手歌曲':
                # 歌手歌曲页失败: 重抓该歌手全部歌曲 + 播放源
                singer = {'name': e.get('singer', ''), 'singer_url': url}
                songs = crawler.fetch_singer_all_songs(logger, singer, args.retry)
                for song in songs:
                    play_url, _ = crawler.fetch_song_play_url(logger, song, args.retry)
                    success_records.append({
                        'name': song['song_name'],
                        'singer': song['artists'],
                        'online': True,
                        'music_sources': [play_url] if play_url else [],
                        'song_url': song['song_url'],
                    })
                if songs:
                    logger.info(f'重试成功(歌手): {e.get("singer", "")} -> {len(songs)} 首 | {url}')
                else:
                    logger.error('重试后该歌手仍无歌曲', step='重试', url=url)
            else:
                # 播放源失败: 重试该歌曲
                data = crawler.fetch_with_retry(logger, '重试', args.retry,
                                                crawler.spider.get_song_detail, url)
                play_url = data.get('play_url', '') or ''
                song_info = data.get('song', {})
                name = song_info.get('song_name') or e.get('song', '')
                artists = song_info.get('artists') or []
                if play_url:
                    success_records.append({
                        'name': name, 'singer': artists, 'online': True,
                        'music_sources': [play_url], 'song_url': url,
                    })
                    logger.info(f'重试成功: {name} | {url}', status='done')
                else:
                    logger.error('重试后仍无播放源', step='重试', song=name, url=url)
        except Exception as exc:
            logger.error('重试失败', exc=exc, step='重试', url=url)

    if success_records:
        added, total = storage.merge_append(args.out, success_records)
        print(f'重试完成: 新增 {added} 首, 文件累计 {total} 首')
        print(f'输出文件: {args.out}')
    else:
        print('重试完成: 无新增成功记录（详见日志）')
    return 0


def cmd_precheck(args, _logger):
    total, passed, failures = storage.precheck(args.file)
    print(f'预检文件: {args.file}')
    print(f'总条数: {total}, 通过: {passed}, 失败: {len(failures)}')
    for f in failures[:20]:
        print(f"  index={f['index']} name={f['name'][:20]!r} | {f['msg']}")
    if len(failures) > 20:
        print(f'  ... 其余 {len(failures) - 20} 条略')
    return 0 if not failures else 1


def cmd_stat(args, _logger):
    s = storage.stat(args.file)
    print(f'文件: {args.file}')
    for k, v in s.items():
        print(f'  {k}: {v}')
    return 0


def cmd_cache(args, _logger):
    if args.clear:
        storage.clear_cache()
        print('播放源缓存已清空')
        return 0
    total, with_src, no_src = storage.show_cache()
    print(f'播放源缓存: 共 {total} 条, 有源 {with_src}, 无源 {no_src}')
    print(f'缓存文件: {storage.DEFAULT_CACHE}')
    return 0


def cmd_log(args, _logger):
    lines = tail_log(args.log, args.tail)
    if not lines:
        print(f'日志为空或不存在: {args.log}')
        return 0
    for line in lines:
        print(line)
    return 0


# ==================== 命令行解析 ====================

def build_parser():
    parser = argparse.ArgumentParser(prog='小影音乐爬虫', description='按歌手维度抓取爱听音乐网（多域名）音乐，输出小影导入格式 JSON')
    sub = parser.add_subparsers(dest='command')

    c = sub.add_parser('crawl', help='抓取歌手列表指定页范围的全部歌手歌曲')
    c.add_argument('--start', type=int, required=True, help='起始页（1 开始）')
    c.add_argument('--end', type=int, required=True, help='结束页')
    c.add_argument('--site', default=None,
                   help=f'站点域名（默认 {config.SITE_BASE}，也可用环境变量 MUSIC_SITE 指定，切换后全局生效）')
    c.add_argument('--out', default=DEFAULT_OUT, help=f'输出文件（默认 {DEFAULT_OUT}，存在则追加去重）')
    c.add_argument('--log', default=DEFAULT_LOG, help=f'日志文件（默认 {DEFAULT_LOG}，错误统一堆此文件）')
    c.add_argument('--retry', type=int, default=DEFAULT_RETRY, help=f'失败自动重试次数（默认 {DEFAULT_RETRY}）')
    c.add_argument('--limit', type=int, default=0, help='每页最多处理歌曲数（默认 0=不限制，用于快速测试/小批量）')
    c.add_argument('--threads', type=int, default=DEFAULT_THREADS,
                   help=f'并发抓播放源线程数 1-{MAX_THREADS}（默认 {DEFAULT_THREADS}）')

    r = sub.add_parser('retry', help='按错误清单重试失败的歌曲/播放源')
    r.add_argument('--site', default=None,
                   help=f'站点域名（默认 {config.SITE_BASE}，也可用环境变量 MUSIC_SITE 指定）')
    r.add_argument('--out', default=DEFAULT_OUT, help='输出文件（追加到该文件）')
    r.add_argument('--log', default=DEFAULT_LOG, help='日志文件（从该文件读取错误清单）')
    r.add_argument('--retry', type=int, default=DEFAULT_RETRY, help='失败自动重试次数')

    rs = sub.add_parser('resume', help='补抓暂存文件中的播放源（不重新抓歌手，适合收集完成但播放源未抓完的场景）')
    rs.add_argument('--out', default=DEFAULT_OUT, help=f'输出文件（默认 {DEFAULT_OUT}）')
    rs.add_argument('--pending', default=None, help='暂存文件路径（默认由 --out 派生 *_pending.jsonl）')
    rs.add_argument('--log', default=DEFAULT_LOG, help=f'日志文件（默认 {DEFAULT_LOG}）')
    rs.add_argument('--site', default=None,
                    help=f'站点域名（默认 {config.SITE_BASE}，也可用环境变量 MUSIC_SITE 指定）')
    rs.add_argument('--retry', type=int, default=DEFAULT_RETRY, help=f'失败自动重试次数（默认 {DEFAULT_RETRY}）')
    rs.add_argument('--threads', type=int, default=DEFAULT_THREADS,
                    help=f'并发抓播放源线程数 1-{MAX_THREADS}（默认 {DEFAULT_THREADS}）')
    rs.add_argument('--limit', type=int, default=0,
                    help='最多处理歌曲数（0=不限制；建议分批小量补抓，避免触发站点风控）')
    rs.add_argument('--rewrite-host', default=None,
                    help='补抓前把暂存/输出文件中歌曲 URL 的域名统一改写为该域名（原域名不可达时切到同站镜像域名）')

    pc = sub.add_parser('precheck', help='导入格式预检（校验是否符合小影导入接口规则）')
    pc.add_argument('--file', required=True, help='输出文件路径')

    st = sub.add_parser('stat', help='输出文件统计')
    st.add_argument('--file', required=True, help='输出文件路径')

    ca = sub.add_parser('cache', help='播放源缓存管理')
    ca.add_argument('--show', action='store_true', help='查看缓存统计')
    ca.add_argument('--clear', action='store_true', help='清空缓存')

    lg = sub.add_parser('log', help='查看日志')
    lg.add_argument('--tail', type=int, default=50, help='查看末尾 N 行（默认 50）')
    lg.add_argument('--log', default=DEFAULT_LOG, help='日志文件路径')

    return parser


# ==================== 交互式菜单 ====================

def interactive_menu():
    logger = Logger()
    print('=== 小影音乐爬虫 CLI ===')
    print(f'当前站点: {config.SITE_BASE}')
    while True:
        print('\n---------- 菜单 ----------')
        print('1. 抓取歌手（起始页-结束页）')
        print('2. 错误清单重试')
        print('3. 输出文件统计')
        print('4. 导入格式预检')
        print('5. 播放源缓存管理')
        print('6. 查看日志')
        print('7. 切换站点域名')
        print('8. 补抓暂存播放源')
        print('0. 退出')
        choice = input('请选择: ').strip()
        if choice == '0':
            print('再见')
            break
        elif choice == '1':
            try:
                start = int(input(f'起始页(1-{259}): ').strip())
                end = int(input(f'结束页: ').strip())
            except ValueError:
                print('[提示] 页号必须为整数')
                continue
            threads_input = input(f'并发线程数(1-{MAX_THREADS}, 回车默认 {DEFAULT_THREADS}): ').strip()
            threads = int(threads_input) if threads_input else DEFAULT_THREADS
            out = input(f'输出文件(回车默认 {DEFAULT_OUT}): ').strip() or DEFAULT_OUT
            cmd_crawl(argparse.Namespace(start=start, end=end, out=out,
                                         log=logger.log_path, retry=DEFAULT_RETRY,
                                         limit=0, threads=threads), logger)
        elif choice == '2':
            out = input(f'输出文件(回车默认 {DEFAULT_OUT}): ').strip() or DEFAULT_OUT
            cmd_retry(argparse.Namespace(out=out, log=logger.log_path, retry=DEFAULT_RETRY), logger)
        elif choice == '3':
            f = input('输出文件路径: ').strip()
            if f:
                cmd_stat(argparse.Namespace(file=f), logger)
        elif choice == '4':
            f = input('输出文件路径: ').strip()
            if f:
                cmd_precheck(argparse.Namespace(file=f), logger)
        elif choice == '5':
            cmd_cache(argparse.Namespace(show=True, clear=False), logger)
        elif choice == '6':
            cmd_log(argparse.Namespace(tail=50, log=logger.log_path), logger)
        elif choice == '7':
            cur = input(f'当前站点 {config.SITE_BASE}，输入新域名（回车保持不变）: ').strip()
            if cur:
                config.set_site(cur)
                crawler.rebuild_spider()
                print(f'站点域名已切换为: {config.SITE_BASE}')
        elif choice == '8':
            out = input(f'输出文件(回车默认 {DEFAULT_OUT}): ').strip() or DEFAULT_OUT
            limit_input = input('本次补抓数量(回车=全部，建议小批量如 200 防封): ').strip()
            limit = int(limit_input) if limit_input else 0
            threads_input = input(f'并发线程数(1-{MAX_THREADS}, 回车默认 {DEFAULT_THREADS}): ').strip()
            threads = int(threads_input) if threads_input else DEFAULT_THREADS
            cmd_resume(argparse.Namespace(out=out, pending=None, log=logger.log_path,
                                          retry=DEFAULT_RETRY, threads=threads,
                                          limit=limit, rewrite_host=None), logger)
        else:
            print('[提示] 无效选择')


# ==================== 入口 ====================

def main():
    logger = Logger()  # 默认日志器（兜底用）
    install_global_guard(logger)
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == 'crawl':
            return cmd_crawl(args, Logger(args.log))
        if args.command == 'retry':
            return cmd_retry(args, Logger(args.log))
        if args.command == 'resume':
            return cmd_resume(args, Logger(args.log))
        if args.command == 'precheck':
            return cmd_precheck(args, logger)
        if args.command == 'stat':
            return cmd_stat(args, logger)
        if args.command == 'cache':
            return cmd_cache(args, logger)
        if args.command == 'log':
            return cmd_log(args, logger)
        # 无命令 -> 交互式菜单
        interactive_menu()
        return 0
    except KeyboardInterrupt:
        print('\n[提示] 已中断')
        return 130
    except Exception as e:
        logger.error('程序执行异常', exc=e)
        print(f'\n[错误] 程序异常已记录到日志，不会崩溃退出: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
