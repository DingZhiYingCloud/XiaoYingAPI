"""短剧「网页直出」转码状态的锁语义回归测试

要守住的契约（源自线上事故：部署重启 uwsgi 后，某集永远停在「正在生成播放地址」）：
  1. 「是否正在转」以**锁文件**为准，不依赖进程内存 —— 多 worker（lazy-apps）下状态一致
  2. 属主进程已死的锁 = 僵尸锁：job_status 必须报 pending（不能报 running 骗前端），
     且 ensure() 要**立刻接管**，不能干等 _STALE_LOCK_SECONDS（30 分钟）
  3. 属主还活着的锁：ensure() 不得重复启动转码；job_status 报 running，elapsed 由锁文件推算
  4. 失败要落到 job_status（带原因），并释放锁以便重试
  5. 释放锁只删自己的锁（已被别人接管时不许误删）
  6. 产物已就绪时一律 ready（锁的内容不再影响判定）
  7. 同一进程内并发调用 ensure() 只启动一次转码
  8. 全局并发上限：同时在转的集数不超过 _MAX_CONCURRENT，溢出请求不启动；
     槽位在转码结束 / 失败后归还，释放后后续请求可在轮询中补上

隔离：把 transcode._STREAM_DIR 指向临时目录、把 transcode._transcode 换成桩，
因此不碰真实缓存、不联网、不起 ffmpeg，秒级跑完。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_hongguo_stream_lock.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from SpiderServices.dramas.hongguo import transcode  # noqa: E402

SERIES = 'xtest0001'
WIDTH = 1080
# 一个确定不存在的 pid（用于模拟「属主进程已死」的僵尸锁）。
# 不用「起个子进程再等它退出」的写法：那会多一次进程启动开销，还可能在奇怪环境下卡住。
DEAD_PID = 1 << 30
TMP_ROOT = tempfile.mkdtemp(prefix='xy-hongguo-lock-')
transcode._STREAM_DIR = TMP_ROOT          # 隔离：产物与锁都落在临时目录

_PASSED = 0
_FAILED = 0
_FAILURES = []


def check(name, condition, detail=''):
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f'  [PASS] {name}')
    else:
        _FAILED += 1
        _FAILURES.append(name)
        print(f'  [FAIL] {name} {detail}')


def cleanup(ep):
    """把某集恢复成「什么都没发生过」"""
    path = transcode.stream_path(SERIES, ep, WIDTH)
    for target in (path, path + '.lock'):
        if os.path.exists(target):
            os.remove(target)
    with transcode._JOBS_LOCK:
        transcode._JOBS.pop(transcode._job_key(SERIES, ep, WIDTH), None)


def make_lock(ep, pid, age_seconds=0):
    """按需造一个锁文件（可指定属主 pid 与年龄）"""
    path = transcode._lock_path(SERIES, ep, WIDTH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(str(pid))
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
    return path


def stub_transcode(*, writes_output=True, exc=None, block=None, counter=None):
    """转码桩：可产出文件 / 抛异常 / 卡住，并像真实现那样在 finally 里释放锁"""
    def fn(series_id, ep, width):
        if counter is not None:
            counter.append(1)
        try:
            if block is not None:
                block.wait(5)
            if exc is not None:
                raise exc
            if writes_output:
                path = transcode.stream_path(series_id, ep, width)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as fh:
                    fh.write(b'x' * 4096)
        finally:
            transcode._release_lock_file(transcode._lock_path(series_id, ep, width))
    return fn


def wait_ready(ep, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if transcode.is_ready(SERIES, ep, WIDTH):
            return True
        time.sleep(0.05)
    return False


def round_basic():
    print('===== 第 1 轮 正常路径 =====')
    ep = 101
    cleanup(ep)
    check('无产物无锁 -> pending', transcode.job_status(SERIES, ep, WIDTH) == {'state': 'pending'})
    transcode._transcode = stub_transcode()
    check('ensure 首次返回 False（刚开始转）', transcode.ensure(SERIES, ep, WIDTH) is False)
    check('转码完成后产物就绪', wait_ready(ep))
    check('就绪后 job_status=ready', transcode.job_status(SERIES, ep, WIDTH) == {'state': 'ready'})
    check('ensure 在就绪后返回 True', transcode.ensure(SERIES, ep, WIDTH) is True)
    check('完成后锁已释放', not os.path.exists(transcode._lock_path(SERIES, ep, WIDTH)))

    make_lock(ep, DEAD_PID)            # 产物已就绪时，锁的内容不应再影响判定
    check('产物就绪时即使有僵尸锁也报 ready',
          transcode.job_status(SERIES, ep, WIDTH) == {'state': 'ready'})
    cleanup(ep)


def round_alive_owner():
    print('===== 第 2 轮 属主存活：不重复转码 =====')
    ep = 102
    cleanup(ep)
    make_lock(ep, os.getpid())           # 本进程就是「存活的属主」
    transcode.ensure(SERIES, ep, WIDTH)
    st = transcode.job_status(SERIES, ep, WIDTH)
    check('job_status=running', st.get('state') == 'running', st)
    check('elapsed 由锁文件推算（0~3s）', 0 <= st.get('elapsed', -1) <= 3, st)
    check('未重复启动转码（无产物）', not transcode.is_ready(SERIES, ep, WIDTH))
    cleanup(ep)


def round_dead_owner():
    print('===== 第 3 轮 僵尸锁（属主已死）：立刻接管 =====')
    ep = 103
    cleanup(ep)
    make_lock(ep, DEAD_PID)            # 部署重启 uwsgi 留下的就是这种锁
    st = transcode.job_status(SERIES, ep, WIDTH)
    check('僵尸锁不报 running（报 pending）', st.get('state') == 'pending', st)
    started = []
    transcode._transcode = stub_transcode(counter=started)
    began = time.time()
    transcode.ensure(SERIES, ep, WIDTH)
    check('接管耗时 < 2s（不必干等 30 分钟）', time.time() - began < 2.0)
    check('接管后转码完成', wait_ready(ep))
    check('接管后状态 ready', transcode.job_status(SERIES, ep, WIDTH) == {'state': 'ready'})
    check('只启动了一次转码', len(started) == 1, started)
    cleanup(ep)


def round_stale_by_age():
    print('===== 第 4 轮 超时锁（属主 pid 假存活但已超时）=====')
    ep = 104
    cleanup(ep)
    make_lock(ep, os.getpid(), age_seconds=transcode._STALE_LOCK_SECONDS + 60)
    check('超时锁按僵尸锁处理', transcode.job_status(SERIES, ep, WIDTH) == {'state': 'pending'})
    transcode._transcode = stub_transcode()
    transcode.ensure(SERIES, ep, WIDTH)
    check('超时锁被接管并转完', wait_ready(ep))
    cleanup(ep)


def round_failure():
    print('===== 第 5 轮 失败：状态与锁释放 =====')
    ep = 105
    cleanup(ep)
    transcode._transcode = stub_transcode(
        writes_output=False, exc=RuntimeError('取流失败: 模拟'))
    transcode.ensure(SERIES, ep, WIDTH)
    st = {}
    deadline = time.time() + 5
    while time.time() < deadline:
        st = transcode.job_status(SERIES, ep, WIDTH)
        if st.get('state') == 'failed':
            break
        time.sleep(0.05)
    check('失败落到 job_status', st.get('state') == 'failed', st)
    check('带上失败原因', '模拟' in (st.get('error') or ''), st)
    check('失败后锁已释放（可重试）', not os.path.exists(transcode._lock_path(SERIES, ep, WIDTH)))
    cleanup(ep)


def round_release_ownership():
    print('===== 第 6 轮 释放锁的归属保护 =====')
    ep = 106
    cleanup(ep)
    others = make_lock(ep, DEAD_PID)
    transcode._release_lock_file(others)
    check('别人的锁不被误删', os.path.exists(others))
    mine = make_lock(ep, os.getpid())
    transcode._release_lock_file(mine)
    check('自己的锁正常释放', not os.path.exists(mine))
    cleanup(ep)


def round_single_flight():
    print('===== 第 7 轮 并发只转一次 =====')
    ep = 107
    cleanup(ep)
    started = []
    block = threading.Event()
    transcode._transcode = stub_transcode(block=block, counter=started)
    threads = [threading.Thread(target=transcode.ensure, args=(SERIES, ep, WIDTH))
               for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    check('5 个并发请求只启动 1 次转码', len(started) == 1, started)
    block.set()
    check('放行后转码完成', wait_ready(ep))
    cleanup(ep)


def round_global_concurrency():
    print('===== 第 8 轮 全局并发上限 =====')
    real_max = transcode._MAX_CONCURRENT
    transcode._MAX_CONCURRENT = 2
    eps = [201, 202, 203, 204, 205]
    try:
        for ep in eps:
            cleanup(ep)
        started = []
        block = threading.Event()

        def stub(series_id, ep, width):
            started.append(ep)
            block.wait(5)                     # 卡住，模拟「正在转」，直到放行
            path = transcode.stream_path(series_id, ep, width)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as fh:
                fh.write(b'x' * 4096)
            transcode._release_lock_file(transcode._lock_path(series_id, ep, width))

        transcode._transcode = stub
        threads = [threading.Thread(target=transcode.ensure, args=(SERIES, ep, WIDTH))
                   for ep in eps]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        deadline = time.time() + 3           # 等两个 worker 线程真正跑起来
        while time.time() < deadline and len(started) < 2:
            time.sleep(0.02)
        check('同时在转不超过上限（2）', len(started) == 2, started)

        block.set()
        deadline = time.time() + 8
        while time.time() < deadline and not all(transcode.is_ready(SERIES, ep, WIDTH) for ep in eps):
            for ep in eps:                    # 模拟前端轮询：槽位空出后再接着转
                transcode.ensure(SERIES, ep, WIDTH)
            time.sleep(0.05)
        check('轮询补上后 5 集全部转完', all(transcode.is_ready(SERIES, ep, WIDTH) for ep in eps))

        deadline = time.time() + 3
        while time.time() < deadline and any(os.path.exists(transcode._slot_path(i))
                                             for i in range(transcode._MAX_CONCURRENT)):
            time.sleep(0.05)
        check('全部完成后槽位已归还',
              not any(os.path.exists(transcode._slot_path(i))
                      for i in range(transcode._MAX_CONCURRENT)))
    finally:
        transcode._MAX_CONCURRENT = real_max
        for ep in eps:
            cleanup(ep)


def main():
    print('短剧转码锁语义回归测试开始')
    print(f'（隔离目录 {TMP_ROOT}；不联网、不启 ffmpeg）\n')
    real_transcode = transcode._transcode
    real_stream_dir = transcode._STREAM_DIR
    # 默认桩兜底：任何一轮都不得碰到真实的 _transcode（会去连源站、拉签名服务）
    transcode._transcode = stub_transcode()
    try:
        round_basic()
        round_alive_owner()
        round_dead_owner()
        round_stale_by_age()
        round_failure()
        round_release_ownership()
        round_single_flight()
        round_global_concurrency()
    finally:
        transcode._transcode = real_transcode
        transcode._STREAM_DIR = real_stream_dir
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    print('\n' + '=' * 70)
    print(f'结果: 通过 {_PASSED} / 失败 {_FAILED}')
    if _FAILURES:
        print('失败项: ' + '；'.join(_FAILURES))
    print('=' * 70)
    return 1 if _FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
