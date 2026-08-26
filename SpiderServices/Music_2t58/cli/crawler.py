"""小影音乐爬虫 CLI 抓取核心

流程:
    1. 抓歌手列表页 -> 该页全部歌手
    2. 逐歌手抓详情页全部歌曲（自动遍历分页）
    3. 逐首抓播放源（play.php + AES 解密）

错误策略:
    - 任一步骤失败自动重试 N 次（指数退避），全部失败则跳过该项继续
    - 每次失败调用 logger.error 写入日志（结构化字段，便于 AI 检查）
    - 播放源带断点缓存，中断后重跑自动续抓
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 复用同目录旧爬虫（含人机验证处理、play.php 解密等逻辑）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from main import Music2t58Spider  # noqa: E402

from cli.config import (SINGER_LIST_FIRST, SINGER_LIST_PAGE_TMPL,  # noqa: E402
                        SINGER_LIST_MAX_PAGE, DEFAULT_RETRY, RETRY_INTERVAL,
                        DEFAULT_THREADS, MAX_THREADS)
from cli import config, storage  # noqa: E402

import lxml.etree as etree  # noqa: E402

# 多线程相关（并发抓播放源）:
# - _cache: 播放源缓存字典，进程内懒加载一次，多线程通过 _cache_lock 读写（避免并发写同一缓存文件）
# - _thread_local: 每个线程独立的爬虫实例（独立 Session，避免共享 Session 的并发问题）
_cache = None
_cache_lock = threading.Lock()
_thread_local = threading.local()


def _load_cache_once():
    """缓存字典懒加载（首次读取文件，之后常驻内存）"""
    global _cache
    if _cache is None:
        _cache = storage.load_cache()
    return _cache


def _thread_spider():
    """获取当前线程的爬虫实例（每个线程独立 Session）"""
    s = getattr(_thread_local, 'spider', None)
    if s is None:
        s = Music2t58Spider(proxy=False)
        _thread_local.spider = s
    return s


def fetch_with_retry(logger, step, retries, func, *args, **kwargs):
    """带自动重试的调用（指数退避）

    :param logger: Logger 实例（重试失败时不在这里记录，由调用方记录）
    :param step: 步骤名（供日志定位）
    :param retries: 重试次数
    :param func: 要调用的函数
    :return: func(*args, **kwargs) 的结果
    :raises: 全部重试失败后抛出最后一次异常
    """
    last = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last = e
            if attempt < retries:
                delay = RETRY_INTERVAL * attempt
                logger.info(f'{step} 失败，{delay}s 后重试 {attempt}/{retries - 1} 次 | {e}', status='warn')
                time.sleep(delay)
    raise last


def parse_singer_list(html):
    """解析歌手列表页的歌手条目

    页面结构: a[title][href="/singer/xxx.html"]（排除 singerlist 分类链接）

    :param html: 页面 HTML 文本
    :return: list[dict] 每项含 name / singer_url（完整 URL）
    """
    tree = etree.HTML(html)
    singers = []
    for a in tree.xpath('//a[contains(@href, "/singer/")]'):
        href = a.get('href', '')
        if '/singerlist/' in href:
            continue  # 排除分类/筛选等 singerlist 链接
        name = (a.get('title') or a.text or '').strip()
        if name:
            singers.append({'name': name, 'singer_url': config.SITE_BASE + href})
    return singers


def collect_singers(logger, page, retries=DEFAULT_RETRY):
    """步骤1: 抓取歌手列表指定页的全部歌手

    :param logger: Logger 实例
    :param page: 歌手列表页号（1 开始）
    :param retries: 失败自动重试次数
    :return: list[dict] 每项含 name / singer_url；失败时抛出异常由调用方记录
    """
    if not 1 <= page <= SINGER_LIST_MAX_PAGE:
        raise ValueError(f'歌手列表页号必须在 1-{SINGER_LIST_MAX_PAGE} 之间，收到 {page}')
    url = config.SITE_BASE + (SINGER_LIST_FIRST if page == 1 else SINGER_LIST_PAGE_TMPL.format(page=page))
    html = fetch_with_retry(logger, '步骤1-歌手列表', retries, spider._get_html, url)
    singers = parse_singer_list(html)
    # 歌手按 URL 去重（页面可能重复出现同一歌手链接）
    unique = {}
    for s in singers:
        unique.setdefault(s['singer_url'], s)
    if len(unique) != len(singers):
        logger.info(f'歌手列表第 {page} 页去重: {len(singers)} -> {len(unique)}', status='page')
    return list(unique.values())


def fetch_singer_all_songs(logger, singer, retries=DEFAULT_RETRY):
    """步骤2: 抓取单个歌手详情页的全部歌曲（自动遍历分页，线程安全）

    :param logger: Logger 实例
    :param singer: {name, singer_url}
    :param retries: 失败自动重试次数
    :return: list[dict] 每项含 song_name / artists / song_url
    线程安全: 使用当前线程独立的爬虫实例（_thread_spider），供并发收集阶段调用。
    """
    songs, visited = [], set()
    current = singer['singer_url']
    page_no = 0
    while current and current not in visited:
        page_no += 1
        visited.add(current)
        try:
            logger.info(f'[歌曲页] 正在抓 {singer["name"]} 歌曲页 {page_no}', status='songpage')
            data = fetch_with_retry(logger, '步骤2-歌手歌曲', retries, _thread_spider().get_singer_detail, current)
            songs.extend(data['songs'])
            pag = data.get('pagination')
            nxt = pag.get('next') if pag else None
            current = nxt['url'] if nxt else None
        except Exception as e:
            # 该页失败拿不到下一页链接，只能结束该歌手；记录后继续下一个歌手
            logger.error('歌手歌曲页抓取失败', exc=e, step='2-歌手歌曲',
                         singer=singer['name'], page=page_no, url=current)
            current = None
    return songs


def fetch_song_play_url(logger, song, retries=DEFAULT_RETRY):
    """步骤3: 获取单首歌曲的播放链接（断点缓存，线程安全）

    :param logger: Logger 实例
    :param song: {song_name, artists, song_url}
    :param retries: 失败自动重试次数
    :return: (play_url, from_cache) play_url 为播放链接（无源为空串），
             from_cache 为 True 表示命中缓存（未请求网络）
    线程安全说明: 缓存读写经 _cache_lock 串行化（避免并发写同一缓存文件），
    网络抓取不持锁（并发核心）；每个线程使用独立 Session（_thread_spider）。
    """
    url = song['song_url']
    with _cache_lock:
        play_url = _load_cache_once().get(url)
        if play_url is not None:
            return play_url, True  # 命中缓存（空串=已抓过但无源）
    # 缓存缺失: 网络抓取（不持锁）
    try:
        data = fetch_with_retry(logger, '步骤3-播放源', retries, _thread_spider().get_song_detail, url)
        play_url = data.get('play_url', '') or ''
    except Exception as e:
        logger.error('播放源抓取失败', exc=e, step='3-播放源',
                     song=song['song_name'], url=url)
        return '', False  # 无源继续（不入错误，保留在缓存后由调用方决定是否跳过）
    with _cache_lock:
        _load_cache_once()[url] = play_url
        storage.save_cache(_load_cache_once())
    return play_url, False


# 全局复用的爬虫实例
spider = Music2t58Spider(proxy=False)


def ensure_session():
    """初始化会话: 歌手列表页首次请求会返回 JS 重定向空壳（需先访问首页建立会话 cookie）"""
    spider._get_html(config.SITE_BASE + '/')


def rebuild_spider():
    """切换站点域名后重建爬虫实例（全局 + 线程本地），使新的 SITE_BASE 生效

    调用时机: CLI 传 --site 时在抓取前调用（见 cli/main.py cmd_crawl/cmd_retry）。
    """
    global spider
    spider = Music2t58Spider(proxy=False)
    _thread_local.__dict__.clear()


def _process_pending(logger, pend_path, out_path, retries=DEFAULT_RETRY, limit=0, threads=DEFAULT_THREADS):
    """处理收集暂存文件: 读取 -> 去重 -> 并发抓播放源 -> 合并写入输出 -> 删除暂存

    收集阶段实时落盘（crawl_page 每歌手完成即 append_pending），因此任何一步
    崩溃后重跑，残留暂存都会先在这里补处理，已抓歌曲不丢失。

    :param logger: Logger 实例
    :param pend_path: 收集暂存文件路径
    :param out_path: 输出文件路径
    :param retries: 失败自动重试次数
    :param limit: 最多处理歌曲数（0=不限制）
    :param threads: 并发抓播放源线程数
    :return: (处理条数, 无源/失败数)
    """
    songs = storage.load_pending(pend_path)
    if not songs:
        storage.clear_pending(pend_path)
        return 0, 0

    # 跳过输出文件已存在的歌曲（resume 补抓场景: 只补缺失部分，避免重复请求播放源）
    existing = {r.get('song_url') for r in storage.load_records(out_path) if r.get('song_url')}
    if existing:
        before = len(songs)
        songs = [s for s in songs if s.get('song_url') not in existing]
        if len(songs) != before:
            logger.info(f'跳过输出文件已有的 {before - len(songs)} 首（不重复抓播放源）', status='cache')
    if not songs:
        storage.clear_pending(pend_path)
        logger.info('暂存歌曲均已写入输出文件，无需补抓，已清理暂存', status='done')
        return 0, 0

    # 统一去重（跨歌手重复只保留一次；limit 截断用于快速测试）
    song_map = {}
    skipped = 0
    for song in songs:
        url = song.get('song_url')
        if not url or url in song_map:
            skipped += 1
            continue
        song_map[url] = {'song_name': song.get('song_name', ''),
                         'artists': song.get('artists', []),
                         'song_url': url}
        if limit and len(song_map) >= limit:
            break

    total = len(song_map)
    if total == 0:
        storage.clear_pending(pend_path)
        logger.info(f'暂存文件无有效歌曲（去重跳过 {skipped}），已清理', status='done')
        return 0, 0

    # 并发抓播放源（每首即时写断点缓存，崩了也有 url->play_url 缓存兜底）
    threads = min(max(threads, 1), MAX_THREADS)
    logger.info(f'暂存歌曲 {total} 首，开始并发抓播放源（线程数 {threads}）', status='page')
    play_urls = {}
    fail_count = 0
    completed = 0
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(fetch_song_play_url, logger, meta, retries): url
                   for url, meta in song_map.items()}
        for fut in as_completed(futures):
            url = futures[fut]
            play_url, from_cache = fut.result()
            play_urls[url] = play_url
            completed += 1
            if not play_url:
                fail_count += 1
            meta = song_map[url]
            artist = meta['artists'][0] if meta['artists'] else '未知歌手'
            status, tag = ('cache', '[缓存] ') if from_cache else ('progress', '')
            logger.info(f'播放源 [完成 {completed}/{total}] {artist} - {tag}{meta["song_name"]}', status=status)

    # 组装记录 + 追加写入输出（按 song_url 去重） + 删除暂存
    records = [{
        'name': song_map[u]['song_name'],
        'singer': song_map[u]['artists'],
        'online': True,
        'music_sources': [play_urls[u]] if play_urls[u] else [],
        'song_url': u,  # 附加字段：跨页去重 key（导入接口自动忽略）
    } for u in song_map]
    added, file_total = storage.merge_append(out_path, records)
    # 防丢: 受 --limit 截断未处理的歌曲写回暂存，下次继续补抓；全部处理完才删除暂存
    leftover = [s for s in songs if s.get('song_url') not in song_map]
    if leftover:
        storage.save_pending(pend_path, leftover)
        logger.info(f'本次受 --limit 截断，剩余 {len(leftover)} 首写回暂存，下次补抓继续', status='warn')
    else:
        storage.clear_pending(pend_path)
    logger.info(f'暂存处理完成: 新增 {added} 首（去重跳过 {skipped}，无源 {fail_count}），文件累计 {file_total} 首', status='done')
    return len(records), fail_count


def crawl_page(logger, page, out_path, retries=DEFAULT_RETRY, limit=0, threads=DEFAULT_THREADS):
    """抓取歌手列表指定页: 收集歌曲（实时落盘暂存）-> 并发抓播放源 -> 合并输出

    防丢设计: 收集阶段每完成一个歌手立即把歌曲追加写入暂存文件
    （由 out_path 派生 *_pending.jsonl），之后任一步骤崩溃，重跑原命令
    会自动先补处理残留暂存，已抓歌曲不丢失。

    :param logger: Logger 实例
    :param page: 歌手列表页号
    :param out_path: 输出文件路径
    :param retries: 失败自动重试次数
    :param limit: 每页最多处理的歌曲数（0=不限制，用于快速测试/小批量）
    :param threads: 并发抓播放源线程数（1-MAX_THREADS）
    :return: (该页处理记录数, 该页无源/失败数)
    """
    ensure_session()
    pend = storage.pending_path(out_path)
    fail_count = 0

    # 0. 崩溃恢复: 上次残留暂存先补处理（抓播放源写输出），再继续新抓取
    if storage.pending_exists(pend):
        logger.info('检测到上次残留的收集暂存文件，先补处理再继续', status='warn')
        _, f = _process_pending(logger, pend, out_path, retries, limit, threads)
        fail_count += f

    # 1. 歌手列表
    try:
        singers = collect_singers(logger, page, retries)
    except Exception as e:
        logger.error(f'歌手列表第 {page} 页抓取失败，跳过该页', exc=e, step='1-歌手列表', page=page)
        return 0, fail_count + 1
    logger.info(f'歌手列表第 {page} 页 -> {len(singers)} 个歌手', status='page')

    # 2. 并发收集所有歌手的歌曲页（每歌手一个任务，线程池并行）
    #    limit>0 时只收集前 limit 个歌手（快速截断，避免为测试抓全页所有歌手）
    #    每完成一个歌手立即 append_pending 落盘（防崩溃丢数据）
    threads = min(max(threads, 1), MAX_THREADS)
    target_singers = singers if not limit else singers[:limit]
    logger.info(f'第 {page} 页 {len(singers)} 个歌手，开始并发抓歌曲页（线程数 {threads}，本次收集 {len(target_singers)} 个）', status='page')
    done_singers = 0
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(fetch_singer_all_songs, logger, singer, retries): singer
                   for singer in target_singers}
        for fut in as_completed(futures):
            singer = futures[fut]
            songs = fut.result()
            storage.append_pending(pend, songs)  # 实时落盘，中断不丢
            done_singers += 1
            logger.info(f'歌手 [完成 {done_singers}/{len(target_singers)}] {singer["name"]} -> {len(songs)} 首（已写入暂存）', status='singer')

    # 3. 统一处理暂存（去重、抓播放源、合并输出、删除暂存）
    n, f = _process_pending(logger, pend, out_path, retries, limit, threads)
    return n, fail_count + f
