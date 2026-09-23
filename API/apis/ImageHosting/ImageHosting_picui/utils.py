"""PicUI 图床服务 API 调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ImageHostingService 进行包装，
并负责服务端 Token 池的选取与容量记账：

- 上传时自动选取第一个仍有余量的 Token（PicUI 账号 Token，由服务端统一持有）；
- 上传成功后按 PicUI 返回的图片大小累加已用容量（服务器不存储图片，只做容量记录）；
- 容量用尽（已用 >= 容量）时自动删除该 Token，后续上传自动切换下一个。

统一返回 (True, data) 或 (False, error_msg) 二元组。
"""
import logging
import os
import re
import sys

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from API.apis.emails.v1.utils import send_email
from API.models import ImageHostingToken

logger = logging.getLogger(__name__)

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ImageHosting.home import ImageHostingService

# 每个 Token 的默认容量：50MB
MEBIBYTE = 1024 * 1024
DEFAULT_CAPACITY_MB = 50

# 池剩余容量跌破该值时，向管理员发送补货告警邮件（仅在「跌破」的那一次发送）
LOW_CAPACITY_ALERT_MB = 50
LOW_CAPACITY_ALERT_BYTES = LOW_CAPACITY_ALERT_MB * MEBIBYTE

# 单次最多导入的 Token 数量
MAX_IMPORT_COUNT = 1000

# PicUI 储存策略 ID：不传该参数时 PicUI 返回「服务异常，请稍后再试」，
# 经实测（/api/v1/strategies）测试账号的「普通用户」策略 ID 为 1，故默认透传 1。
DEFAULT_STRATEGY_ID = "1"


# ==================== Token 池 ====================

def _split_tokens(values) -> list:
    """把按行 / 逗号分隔的输入拆成去重后的 Token 列表（保持原顺序）

    只按换行与逗号切分（Token 本身不包含这两种字符），避免把内容误切；
    每段去除首尾空白后再去重。
    """
    result, seen = [], set()
    for raw in values:
        for part in re.split(r"[\n\r,]+", str(raw or "")):
            part = part.strip()
            if part and part not in seen:
                seen.add(part)
                result.append(part)
    return result


def _capacity_bytes(capacity_mb) -> tuple:
    """换算并校验容量（MB -> 字节）

    :return: (capacity_bytes, None) 或 (None, 错误消息)
    """
    if capacity_mb in (None, ""):
        return DEFAULT_CAPACITY_MB * MEBIBYTE, None
    try:
        mb = float(capacity_mb)
    except (TypeError, ValueError):
        return None, "参数格式错误: capacity_mb 必须为数字"
    if mb <= 0:
        return None, "参数值非法: capacity_mb 必须大于 0"
    return int(mb * MEBIBYTE), None


def _to_mb(size_bytes: int) -> float:
    """字节换算为 MB（保留 2 位小数，便于阅读）"""
    return round(size_bytes / MEBIBYTE, 2)


def _pick_token():
    """取第一个仍有余量的 Token（按入库顺序），无可用返回 None"""
    return ImageHostingToken.objects.filter(used_bytes__lt=F("capacity_bytes")).first()


def _pool_remaining_bytes() -> int:
    """池内所有 Token 的剩余容量合计（字节）"""
    return sum(t.remaining_bytes for t in ImageHostingToken.objects.all())


def _notify_low_capacity(remaining_bytes: int) -> tuple:
    """池剩余容量跌破告警阈值时，向管理员发送补货提醒邮件

    收件人取 settings.EMAIL_HOST_USER（由环境变量 QQ_MAIL_ACCOUNT 配置），
    未配置时直接跳过、不发送邮件。

    :param remaining_bytes: 当前池内剩余容量合计（字节）
    :return: (是否发送成功, 描述信息)
    """
    recipient = (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    if not recipient:
        return False, "未配置 QQ_MAIL_ACCOUNT，跳过图床容量告警邮件"

    subject = f"【小影API】图床 Token 池剩余容量不足 {LOW_CAPACITY_ALERT_MB}MB，请及时补货"
    body = (
        "图床（PicUI 线路）Token 池剩余容量已跌破告警阈值，请及时补充新的 Token。\n\n"
        f"告警阈值：{LOW_CAPACITY_ALERT_MB}MB\n"
        f"当前剩余：{_to_mb(remaining_bytes)}MB\n"
        f"池内 Token 数量：{ImageHostingToken.objects.count()}\n"
        f"统计时间：{timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "补充方式：调用 POST /api/ImageHosting/picui/tokens 导入新的 Token"
        "（tokens 可直接多个一起传，token_file 可按行存放）。\n"
        "余量查询：GET /api/ImageHosting/picui/tokens\n"
    )
    return send_email(subject, body, [recipient])


def _consume(token_obj, used_bytes: int) -> bool:
    """累加 Token 的已用容量，容量用尽则删除该 Token

    :return: 是否因容量用尽被删除
    """
    ImageHostingToken.objects.filter(pk=token_obj.pk).update(
        used_bytes=F("used_bytes") + used_bytes)
    token_obj.refresh_from_db(fields=["used_bytes"])
    if token_obj.used_bytes >= token_obj.capacity_bytes:
        ImageHostingToken.objects.filter(pk=token_obj.pk).delete()
        return True
    return False


def list_tokens() -> tuple:
    """查询 Token 池（Token 做脱敏展示；容量同时给出字节与 MB，便于阅读）

    :return: (True, dict) 或 (False, error_msg)
    """
    queryset = ImageHostingToken.objects.all()
    items = [{
        "token": _mask_token(t.token),
        "capacity_bytes": t.capacity_bytes,
        "capacity_mb": _to_mb(t.capacity_bytes),
        "used_bytes": t.used_bytes,
        "used_mb": _to_mb(t.used_bytes),
        "remaining_bytes": t.remaining_bytes,
        "remaining_mb": _to_mb(t.remaining_bytes),
        "create_time": t.create_time.strftime("%Y-%m-%d %H:%M:%S"),
    } for t in queryset]

    total_capacity = sum(i["capacity_bytes"] for i in items)
    total_used = sum(i["used_bytes"] for i in items)
    total_remaining = sum(i["remaining_bytes"] for i in items)
    return True, {
        "count": len(items),
        "total_capacity_bytes": total_capacity,
        "total_capacity_mb": _to_mb(total_capacity),
        "total_used_bytes": total_used,
        "total_used_mb": _to_mb(total_used),
        "total_remaining_bytes": total_remaining,
        "total_remaining_mb": _to_mb(total_remaining),
        "items": items,
    }


def add_tokens(raw_tokens, capacity_mb=None) -> tuple:
    """新增 Token 到池中（Token 唯一，已存在的不会重复导入）

    去重口径：Token 按原文精确比对（含大小写），同一个 Token 只会入库一条；
    同一批请求内重复、以及库中已存在的，都会计入 duplicated 并跳过。

    :param raw_tokens: 待新增的 Token 原始输入（按行或逗号分隔，Token 内不能含空白字符）
    :param capacity_mb: 每个 Token 的容量（MB），默认 50
    :return: (True, dict) 或 (False, error_msg)
    """
    tokens = _split_tokens(raw_tokens)
    if not tokens:
        return False, "参数缺失: 请提供 tokens(可多个) 或 token_file(按行存放) 至少一项"
    # Token 不含空白字符：命中说明文件里混入了注释/多余列（如 "657|xxx # 备注"），
    # 这类内容若入库会变成永远不可用的“僵尸 Token”，直接拒绝并提示
    if any(re.search(r"\s", t) for t in tokens):
        return False, "参数格式错误: Token 不能包含空格等空白字符（请按行或逗号分隔，一行一个 Token）"
    if len(tokens) > MAX_IMPORT_COUNT:
        return False, f"参数值非法: 单次最多导入 {MAX_IMPORT_COUNT} 个 Token"

    capacity_bytes, err = _capacity_bytes(capacity_mb)
    if err:
        return False, err

    existing = set(ImageHostingToken.objects.filter(
        token__in=tokens).values_list("token", flat=True))
    candidates = [t for t in tokens if t not in existing]
    if candidates:
        # ignore_conflicts: 并发导入同一 Token 时以库中已有记录为准，不报错也不重复写入
        ImageHostingToken.objects.bulk_create(
            [ImageHostingToken(token=t, capacity_bytes=capacity_bytes) for t in candidates],
            ignore_conflicts=True)

    # 以库中实际存在的结果为准，避免并发场景下把已被抢占的 Token 统计成新增
    in_pool = set(ImageHostingToken.objects.filter(
        token__in=candidates).values_list("token", flat=True))
    duplicated = [t for t in tokens if t not in in_pool]

    return True, {
        "submitted": len(tokens),
        "created": len(in_pool),
        "duplicated": len(duplicated),
        "duplicated_tokens": [_mask_token(t) for t in duplicated],
        "capacity_bytes": capacity_bytes,
        "capacity_mb": _to_mb(capacity_bytes),
    }


def _mask_token(token: str) -> str:
    """Token 脱敏：保留首 6 位与末 4 位"""
    if len(token) <= 12:
        return "****"
    return f"{token[:6]}****{token[-4:]}"


# ==================== 上传 ====================

def upload_image(image=None, image_filename=None, upload_token=None,
                 permission=None, strategy_id=None, album_id=None,
                 expired_at=None) -> tuple:
    """上传图片到 PicUI 图床（线路 picui）

    鉴权 Token 由服务端 Token 池自动提供，调用方无需（也不允许）自带 Token。

    :param image: 本地图片（Django UploadedFile / file-like / bytes / (文件名, bytes)）
    :param image_filename: image 为 bytes 时指定文件名（可选）
    :param upload_token: 临时上传 Token（Body 字段 token），一般不传
    :param permission: 图片权限 "1"=公开（PicUI 默认） / "0"=私有
    :param strategy_id: 储存策略 ID，默认 "1"（不传 PicUI 会返回「服务异常」）
    :param album_id: 相册 ID（可选）
    :param expired_at: 图片过期时间，格式 yyyy-MM-dd HH:mm:ss（可选）
    :return: (True, dict) 或 (False, error_msg)
    """
    # 先校验入参，再取 Token：避免缺文件时报出「无可用 Token」这类与调用方无关的错误
    if image is None:
        return False, "参数缺失: image(本地图片)"

    pool_token = _pick_token()
    if pool_token is None:
        return False, "无可用 Token: Token 池为空或容量已用尽，请先导入新的 Token"

    service = ImageHostingService()
    try:
        result = service.upload_image(
            source="picui", image=image, image_filename=image_filename,
            auth_token=pool_token.token, upload_token=upload_token,
            permission=permission,
            strategy_id=strategy_id or DEFAULT_STRATEGY_ID,
            album_id=album_id, expired_at=expired_at,
        )
    except Exception as e:
        return False, f"upload_image 调用异常: {e}"

    if result.get("code") == 0:
        used_bytes = (result.get("data") or {}).get("size_bytes") or 0
        if used_bytes > 0:
            remaining_before = _pool_remaining_bytes()
            _consume(pool_token, used_bytes)
            remaining_after = _pool_remaining_bytes()
            # 仅在剩余容量「跌破」阈值的那一次发送补货告警（补货回到阈值以上后再次跌破会重新告警）
            if remaining_before > LOW_CAPACITY_ALERT_BYTES >= remaining_after:
                sent, message = _notify_low_capacity(remaining_after)
                if sent:
                    logger.info("图床 Token 池剩余 %sMB，已发送补货告警邮件", _to_mb(remaining_after))
                else:
                    logger.warning("图床 Token 池补货告警邮件未发送: %s", message)
    return True, result
