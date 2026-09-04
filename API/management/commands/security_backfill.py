"""S-06 存量数据回填命令

将存量明文凭据按新策略落库：
1. user_app.app_secret      → enc:v1: AES-GCM 密文（已带前缀的行自动跳过）
2. user_token.token         → SHA-256 哈希（仅首次执行转换，见下方幂等策略）
3. user_verify_record.token → SHA-256 哈希（同上；仅处理非空 token）
4. user_verify_record.code  → 已使用 / 已过期的验证码直接清空

说明：由于项目无可用迁移历史，此命令以原生 SQL 操作 SQLite 列值，
不写入 django_migrations；任何环境部署新代码后执行一次即可。

幂等策略：token 原始值（hex64）与其 SHA-256 哈希同为 64 位 hex，仅凭值无法区分
"已哈希"与"未哈希"，因此采用一次性标记行（api_login_guard 表
key='__s6_backfill_v1__'）保证命令只真正转换一次；重复执行直接跳过，
避免二次哈希损坏既有 Token。

用法：
    python manage.py security_backfill
"""
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.db import connection

from API.common.credential_crypto import ENC_PREFIX, encrypt_credential, hash_token

# 一次性迁移标记（写入 api_login_guard 表）
_MARKER_KEY = '__s6_backfill_v1__'


class Command(BaseCommand):
    help = 'S-06 存量明文凭据回填：app_secret 加密 / token 哈希 / 验证码清空（仅执行一次）'

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM api_login_guard WHERE key = ?", [_MARKER_KEY])
            if cur.fetchone():
                self.stdout.write(self.style.WARNING(
                    '已执行过 S-06 存量回填（标记存在），跳过以避免重复处理损坏数据'))
                return

        stats = {'app_secret_encrypted': 0, 'token_hashed': 0,
                 'verify_token_hashed': 0, 'code_cleared': 0}

        with connection.cursor() as cur:
            # 1) app_secret 加密（raw 读取以识别已加密行）
            cur.execute("SELECT id, app_secret FROM user_app")
            for pk, raw in cur.fetchall():
                if raw and not raw.startswith(ENC_PREFIX):
                    cipher = encrypt_credential(raw)
                    cur.execute("UPDATE user_app SET app_secret = ? WHERE id = ?", [cipher, pk])
                    stats['app_secret_encrypted'] += 1

            # 2) 登录 Token 哈希（首轮执行时 DB 内均为旧代码产生的明文 Token）
            cur.execute("SELECT id, token FROM user_token")
            for pk, raw in cur.fetchall():
                if raw:
                    cur.execute("UPDATE user_token SET token = ? WHERE id = ?",
                                [hash_token(raw), pk])
                    stats['token_hashed'] += 1

            # 3) 激活令牌哈希（仅邮箱激活链接记录持有 token）
            cur.execute("SELECT id, token FROM user_verify_record WHERE token IS NOT NULL AND token <> ''")
            for pk, raw in cur.fetchall():
                if raw:
                    cur.execute("UPDATE user_verify_record SET token = ? WHERE id = ?",
                                [hash_token(raw), pk])
                    stats['verify_token_hashed'] += 1

            # 4) 已使用 / 已过期的验证码清空
            cutoff = datetime.now(dt_timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S.%f')
            cur.execute(
                "UPDATE user_verify_record SET code = '' "
                "WHERE (is_used = 1 OR expire_time <= ?) AND code <> ''",
                [cutoff],
            )
            stats['code_cleared'] = cur.rowcount

            # 写入一次性迁移标记（此后重复执行将直接跳过，防止二次哈希损坏数据）
            cur.execute(
                "INSERT OR IGNORE INTO api_login_guard(key, fail_count, lock_until, update_time) "
                "VALUES(?, 0, NULL, ?)",
                [_MARKER_KEY, datetime.now(dt_timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S.%f')],
            )

        self.stdout.write(self.style.SUCCESS(
            f'回填完成: app_secret 加密 {stats["app_secret_encrypted"]} 条, '
            f'登录 Token 哈希 {stats["token_hashed"]} 条, '
            f'激活令牌哈希 {stats["verify_token_hashed"]} 条, '
            f'验证码清空 {stats["code_cleared"]} 条'
        ))
