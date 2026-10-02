"""数据库自动备份：SQLite 在线备份 + 完整性校验 + gzip 压缩 + 按份数轮转保留

为什么必须用 SQLite 的 backup API，不能直接 `cp db.sqlite3`：
    db.sqlite3 是**多 worker 并发写**的（uwsgi prefork + 后台巡检线程 + 批量导入），
    而且开启了 WAL。`cp` 出来的副本很可能停在「写了一半」的状态——恢复时轻则丢最近的
    写入、重则直接 `database disk image is malformed`。`Connection.backup()` 是 SQLite
    官方的**在线备份**接口：在事务边界上分页拷贝，**不用停服务、不阻塞写入**，产出的
    副本与源库自洽。

为什么要先校验再留：
    一个「看起来成功了」的坏备份比没有备份更危险——出事时才发现恢复不了。所以副本落盘后
    先跑 `PRAGMA integrity_check`，不是 `ok` 就立刻失败退出（并把半成品删掉），绝不把坏
    备份留在备份目录里。

压缩与轮转：
    SQLite 库 gzip 后通常只剩零头；落盘用「临时文件 + rename」，避免留下半个文件。
    轮转按文件名里的时间戳排序，只保留最新 N 份（`--keep`，默认 14），更早的删除。

使用方式（本地）：
    .venv\\Scripts\\python.exe scripts\\backup_db.py
    .venv\\Scripts\\python.exe scripts\\backup_db.py --keep 30 --out D:\\db_backups

生产（cron，**必须用运行用户 www 执行**，否则产物属主是 root，见部署手册第五节第 13 条）：
    # 每天 03:30 备份，日志追加到 logs/backup.log
    30 3 * * * cd /www/XiaoYing/XiaoYingAPI && runuser -u www -- bash -c \
      'cd /www/XiaoYing/XiaoYingAPI && .venv/bin/python scripts/backup_db.py >> logs/backup.log 2>&1'

恢复方式（先停服务，再覆盖，最后起服务）：
    gunzip -c backups/db-20261002-033000.sqlite3.gz > db.sqlite3
    rm -f db.sqlite3-wal db.sqlite3-shm      # WAL/SHM 是旧库的伴生文件，必须一并清掉

**离线副本请加密**：备份与源库同盘时，不加密不会新增暴露面（本来就在那里）；但拷到异地
/ 对象存储前应当加密，例如：
    openssl enc -aes-256-cbc -pbkdf2 -in db-xxx.sqlite3.gz -out db-xxx.sqlite3.gz.enc
"""
import argparse
import gzip
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 默认值（可用命令行参数覆盖；数据库路径与 settings.DATABASES['default']['NAME'] 一致）
DEFAULT_DB = BASE_DIR / 'db.sqlite3'
DEFAULT_OUT = BASE_DIR / 'backups'
DEFAULT_KEEP = 14
# 备份文件名前缀与时间戳格式（轮转靠它排序，改格式等于放弃对旧备份的轮转）
FILENAME_PREFIX = 'db-'
TIMESTAMP_FMT = '%Y%m%d-%H%M%S'


def _log(message: str) -> None:
    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {message}', flush=True)


def _snapshot(db_path: Path, tmp_path: Path) -> None:
    """用 SQLite 在线备份接口把源库拷到 tmp_path（源库保持可读写，不清空、不锁库）"""
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(tmp_path))
    try:
        src.backup(dst)          # 分页拷贝，事务边界对齐，并发写入下依然自洽
        dst.commit()
    finally:
        dst.close()
        src.close()


def _integrity_ok(db_path: Path) -> bool:
    """对副本跑 PRAGMA integrity_check；只有唯一一行 'ok' 才算通过"""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute('PRAGMA integrity_check').fetchall()
    finally:
        conn.close()
    return len(rows) == 1 and str(rows[0][0]).strip().lower() == 'ok'


def _rotate(out_dir: Path, keep: int) -> list:
    """只保留最新 keep 份备份（keep <= 0 表示不轮转），返回被删除的文件名"""
    if keep <= 0:
        return []
    candidates = sorted((p for p in out_dir.iterdir()
                         if p.is_file() and p.name.startswith(FILENAME_PREFIX)),
                        key=lambda p: p.name, reverse=True)   # 文件名时间戳倒序 = 新在前
    removed = []
    for stale in candidates[keep:]:
        try:
            stale.unlink()
            removed.append(stale.name)
        except OSError as exc:            # 删不掉不该让整次备份失败（备份本身已成功）
            _log(f'警告：清理旧备份失败 {stale.name}（{exc}）')
    return removed


def backup(db_path: Path, out_dir: Path, keep: int, compress: bool) -> Path:
    """执行一次备份，返回最终产物路径"""
    if not db_path.is_file():
        raise SystemExit(f'数据库文件不存在：{db_path}')
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime(TIMESTAMP_FMT)
    tmp_path = out_dir / f'.{FILENAME_PREFIX}{stamp}.tmp'
    gz_tmp = tmp_path.with_name(tmp_path.name + '.gz')
    final_path = out_dir / (f'{FILENAME_PREFIX}{stamp}.sqlite3'
                            + ('.gz' if compress else ''))
    try:
        _log(f'开始备份：{db_path} → {final_path.name}')
        _snapshot(db_path, tmp_path)

        if not _integrity_ok(tmp_path):
            raise SystemExit('备份校验失败：副本 integrity_check 未通过，已丢弃（源库未受影响）')

        if compress:
            # 压缩也先写临时文件、最后 rename：直接写 final_path 的话，压缩途中失败
            # （磁盘满 / IO 错误）会在备份目录留下一个**残缺的 .gz**，而它的名字看起来
            # 和正常备份一样，恢复时才发现打不开 —— 比没有更坏。
            # 用 GzipFile 而不是 gzip.open：只有它接受 mtime（gzip.open 不接受该参数）。
            # mtime=0 让 gzip 头不带时间戳，避免「同一份内容每次压缩字节都不同」。
            with open(tmp_path, 'rb') as fin, open(gz_tmp, 'wb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as fout:
                    shutil.copyfileobj(fin, fout)
            gz_tmp.replace(final_path)
        else:
            tmp_path.replace(final_path)

        size_mb = final_path.stat().st_size / 1024 / 1024
        _log(f'完成：{final_path.name}（{size_mb:.1f} MB，校验通过）')
    finally:
        # 任何环节失败都不留半成品（临时名以 `.` 开头，_rotate 不会把它们当备份）
        for leftover in (gz_tmp, tmp_path):
            if leftover.exists():
                leftover.unlink()

    removed = _rotate(out_dir, keep)
    if removed:
        _log(f'轮转：保留最新 {keep} 份，已删除 {len(removed)} 份 → {", ".join(removed)}')
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description='SQLite 在线备份 + 校验 + 压缩 + 按份数轮转保留')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB,
                        help=f'源数据库路径（默认 {DEFAULT_DB}）')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT,
                        help=f'备份输出目录（默认 {DEFAULT_OUT}）')
    parser.add_argument('--keep', type=int, default=DEFAULT_KEEP,
                        help=f'保留最新几份，0 表示不轮转（默认 {DEFAULT_KEEP}）')
    parser.add_argument('--no-compress', action='store_true',
                        help='不压缩，直接产出 .sqlite3（便于立刻挂载查看）')
    args = parser.parse_args()

    backup(args.db, args.out, args.keep, compress=not args.no_compress)
    return 0


if __name__ == '__main__':
    # 退出码约定：0 成功、1 失败（cron / 监控据此判断，失败时不要静默）
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:                                  # noqa: BLE001
        _log(f'备份失败：{type(exc).__name__}: {exc}')
        sys.exit(1)
