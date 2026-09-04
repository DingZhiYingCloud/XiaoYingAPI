"""通用防刷与去重守卫（S-03 登录锁定/验证码失败上限、S-05 nonce 去重）

背景与选型：
- 该库 django_migrations 记录已应用但迁移文件缺失，无法再用标准迁移演进表结构；
  本模块因此直接对 SQLite 库操作两张原生表（首次使用自动 CREATE TABLE IF NOT EXISTS，
  各环境幂等；不写入 django_migrations，不影响既有迁移历史）。
- 时间统一用 Python 生成的定长字符串存 TEXT，保证字典序比较正确。

表结构：
    api_login_guard(key TEXT PRIMARY KEY, fail_count INTEGER,
                    lock_until TEXT NULL, update_time TEXT)
        key         - 维度键：login 为 f"login:{app_id}:{principal}:{ip}"；
                      验证码计数为 f"code:{verify_record_id}"
        fail_count  - 连续失败次数（锁定后重置）
        lock_until  - 锁定截止时间（NULL=未锁定）
    api_nonce(app_id TEXT, nonce TEXT, ts TEXT, PRIMARY KEY(app_id, nonce))
        签名 nonce 去重：窗口内已出现则拒绝，过期由清理逻辑删除

所有函数幂等、无事务依赖（依赖 SQLite 自动提交），单次调用开销极小。
"""
from datetime import timedelta
import datetime
import threading

from django.db import connection
from django.utils import timezone

# ==================== 阈值配置 ====================

# S-03: 登录连续失败次数与锁定分钟数
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_MINUTES = 15

# S-03: 同一验证码记录的猜解失败上限（超过即作废并要求重发）
CODE_MAX_FAILS = 5

# S-05: 签名 nonce 有效窗口（秒），与 sign.SIGN_TIMESTAMP_WINDOW 保持一致
NONCE_WINDOW_SECONDS = 300

# 未锁定计数行的最长保留时间（避免僵尸行堆积）
STALE_COUNTER_HOURS = 6

_TS_FMT = '%Y-%m-%d %H:%M:%S.%f'

_ensure_lock = threading.Lock()
_created = False


def _now_str() -> str:
    """当前时间定长字符串（可字典序比较）"""
    return timezone.now().strftime(_TS_FMT)


def _minutes_left(lock_until_str: str) -> int:
    """锁定截止字符串 → 剩余分钟数（向上取整，至少 1 分钟）"""
    lock_dt = timezone.datetime.strptime(lock_until_str, _TS_FMT)
    now = timezone.now()
    if timezone.is_aware(now):
        lock_dt = timezone.make_aware(lock_dt, datetime.timezone.utc)
    diff = lock_dt - now
    return max(1, int(diff.total_seconds() // 60) + 1)


def _ensure_tables():
    """首次使用时自举建表（幂等）"""
    global _created
    if _created:
        return
    with _ensure_lock:
        if _created:
            return
        with connection.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_login_guard (
                    key         TEXT PRIMARY KEY,
                    fail_count  INTEGER NOT NULL DEFAULT 0,
                    lock_until  TEXT NULL,
                    update_time TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_nonce (
                    app_id TEXT NOT NULL,
                    nonce  TEXT NOT NULL,
                    ts     TEXT NOT NULL,
                    PRIMARY KEY (app_id, nonce)
                )
            """)
        _created = True


def _purge_guard_rows():
    """清理：已过期锁 / 过期计数 / 过期 nonce（每次操作顺带执行，控制表体积）"""
    now = _now_str()
    stale = (timezone.now() - timedelta(hours=STALE_COUNTER_HOURS)).strftime(_TS_FMT)
    old_nonce = (timezone.now() - timedelta(seconds=NONCE_WINDOW_SECONDS)).strftime(_TS_FMT)
    with connection.cursor() as cur:
        cur.execute("DELETE FROM api_login_guard WHERE lock_until IS NOT NULL AND lock_until <= ?", [now])
        cur.execute("DELETE FROM api_login_guard WHERE lock_until IS NULL AND update_time < ?", [stale])
        cur.execute("DELETE FROM api_nonce WHERE ts < ?", [old_nonce])


# ==================== S-03：登录失败锁定 ====================

def login_locked(key: str):
    """是否已处于锁定状态。返回 (locked, minutes_left)。

    minutes_left：仅 locked=True 时有意义（分钟，向上取整）
    """
    _ensure_tables()
    _purge_guard_rows()
    now = _now_str()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT lock_until FROM api_login_guard WHERE key = ?", [key]
        )
        row = cur.fetchone()
    if not row or not row[0] or row[0] <= now:
        return False, 0
    return True, _minutes_left(row[0])


def login_fail(key: str, max_fails: int = LOGIN_MAX_FAILS,
               lock_minutes: int = LOGIN_LOCK_MINUTES):
    """记录一次登录失败。返回 (locked, minutes_left)。

    连续失败达到 max_fails 即锁定 lock_minutes 分钟（锁定期间继续失败保持锁定，
    到期后首次失败重新计数）。
    """
    _ensure_tables()
    _purge_guard_rows()
    now = _now_str()
    lock_until_val = None
    if lock_minutes:
        lock_until_val = (timezone.now() + timedelta(minutes=lock_minutes)).strftime(_TS_FMT)

    with connection.cursor() as cur:
        # 读取当前行（锁定中或计数器）
        cur.execute("SELECT fail_count, lock_until FROM api_login_guard WHERE key = ?", [key])
        row = cur.fetchone()
        if row and row[1] and row[1] > now:
            # 仍在锁定：返回剩余时间，不累加
            return True, _minutes_left(row[1])

        # 无行 / 锁定已过期 / 纯计数行 → 计数 +1
        new_count = (row[0] if row else 0) + 1
        if new_count >= max_fails and lock_until_val:
            cur.execute(
                "INSERT INTO api_login_guard(key, fail_count, lock_until, update_time) "
                "VALUES(?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "fail_count=excluded.fail_count, lock_until=excluded.lock_until, update_time=excluded.update_time",
                [key, new_count, lock_until_val, now],
            )
            return True, lock_minutes
        # 未达上限（或 max_fails<=0 仅计数）
        cur.execute(
            "INSERT INTO api_login_guard(key, fail_count, lock_until, update_time) "
            "VALUES(?, ?, NULL, ?) ON CONFLICT(key) DO UPDATE SET "
            "fail_count=excluded.fail_count, lock_until=NULL, update_time=excluded.update_time",
            [key, new_count, now],
        )
        return False, 0


def login_clear(key: str):
    """登录成功后清除失败记录"""
    _ensure_tables()
    with connection.cursor() as cur:
        cur.execute("DELETE FROM api_login_guard WHERE key = ?", [key])


# ==================== S-03：验证码猜解失败上限（按验证记录） ====================

def code_fail_exhausted(key: str, max_fails: int = CODE_MAX_FAILS) -> bool:
    """验证码记录失败一次。达到上限返回 True（调用方应将验证记录作废）。

    key 建议用验证记录 id（如 f"code:{record.id}"），新验证码 = 新记录 = 新计数。
    """
    _ensure_tables()
    _purge_guard_rows()
    now = _now_str()
    with connection.cursor() as cur:
        cur.execute("SELECT fail_count FROM api_login_guard WHERE key = ?", [key])
        row = cur.fetchone()
        new_count = (row[0] if row else 0) + 1
        if new_count >= max_fails:
            cur.execute("DELETE FROM api_login_guard WHERE key = ?", [key])
            return True
        cur.execute(
            "INSERT INTO api_login_guard(key, fail_count, lock_until, update_time) "
            "VALUES(?, ?, NULL, ?) ON CONFLICT(key) DO UPDATE SET "
            "fail_count=excluded.fail_count, lock_until=NULL, update_time=excluded.update_time",
            [key, new_count, now],
        )
        return False


# ==================== S-05：签名 nonce 去重 ====================

def nonce_replayed(app_id: str, nonce: str) -> bool:
    """nonce 是否已在窗口内出现过（True=重放，应拒绝）。

    首次出现的 nonce 落库并返回 False；窗口内重复返回 True。
    过期 nonce 由清理逻辑删除后可再次使用（窗口已过，无重放意义）。
    """
    _ensure_tables()
    _purge_guard_rows()
    now = _now_str()
    with connection.cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO api_nonce(app_id, nonce, ts) VALUES(?, ?, ?)",
            [app_id, nonce, now],
        )
        return cur.rowcount == 0
