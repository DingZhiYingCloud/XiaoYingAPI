"""把 security_guard 的防刷 / 去重原生表纳入迁移台账

背景见 API/common/security_guard.py：`api_login_guard`（登录失败锁定、验证码猜解上限）与
`api_nonce`（签名 nonce 去重）这两张表此前只由代码在运行期自建（CREATE TABLE IF NOT
EXISTS 兜底），不在迁移台账里 —— 新库要等到第一次请求才建表。本迁移给出**权威表结构**，
让 `migrate` 阶段就建好。

SQL 全部幂等（IF NOT EXISTS）：对既有库是无副作用的空操作，不会动到既有数据，也不会与
security_guard 里的「自愈兜底建表」冲突（两侧语句一致）。这两个表存的是可重建的临时数据
（锁定计数、nonce 窗口），故反向迁移直接 DROP。
"""
from django.db import migrations

# 与 API/common/security_guard.py 的 _ensure_tables 保持逐字一致
CREATE_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS api_login_guard ("
    " key         TEXT PRIMARY KEY,"
    " fail_count  INTEGER NOT NULL DEFAULT 0,"
    " lock_until  TEXT NULL,"
    " update_time TEXT NOT NULL"
    ")",

    "CREATE TABLE IF NOT EXISTS api_nonce ("
    " app_id TEXT NOT NULL,"
    " nonce  TEXT NOT NULL,"
    " ts     TEXT NOT NULL,"
    " PRIMARY KEY (app_id, nonce)"
    ")",

    # 清理语句的过滤列必须走索引（见 security_guard._purge_guard_rows）
    "CREATE INDEX IF NOT EXISTS idx_login_guard_lock_until "
    "ON api_login_guard(lock_until)",

    "CREATE INDEX IF NOT EXISTS idx_login_guard_update_time "
    "ON api_login_guard(update_time)",

    "CREATE INDEX IF NOT EXISTS idx_api_nonce_ts ON api_nonce(ts)",
]

DROP_STATEMENTS = [
    "DROP TABLE IF EXISTS api_nonce",
    "DROP TABLE IF EXISTS api_login_guard",
]


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0103_hot_table_create_time_index'),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_STATEMENTS, reverse_sql=DROP_STATEMENTS),
    ]
