"""代练丸子 DaiLianWanZi API 请求处理视图

提供 23 个接口，对应爬虫的对外方法:
    POST /api/dlwz/auth/send-code         发送验证码
    POST /api/dlwz/auth/login              登录
    GET  /api/dlwz/user/info               获取用户信息
    POST /api/dlwz/user/upload-avatar      上传头像
    POST /api/dlwz/user/set-profile        设置个性信息（签名/QQ号等）
    GET  /api/dlwz/user/real-name          获取实名认证信息
    POST /api/dlwz/user/sign-in            签到
    GET  /api/dlwz/user/balance            获取我的余额
    GET  /api/dlwz/business/order-tabs     获取订单分类（商家版）
    GET  /api/dlwz/business/orders         获取我的订单（商家版）
    POST /api/dlwz/business/orders/cancel  取消订单（商家版）
    GET  /api/dlwz/business/games          获取全部游戏（商家版发单用）
    GET  /api/dlwz/business/order-options  获取发单选项（区服 / 代练类型 / 字段）
    POST /api/dlwz/business/orders/publish 发布订单（商家版）
    GET  /api/dlwz/business/hall/search    搜索接单大厅订单
    GET  /api/dlwz/business/hall/words     大厅热搜词
    GET  /api/dlwz/business/hall/detail    大厅订单详情
    POST /api/dlwz/business/orders/take-password-check 接单密码校验
    POST /api/dlwz/business/orders/take    接单（冻结双金）
    POST /api/dlwz/business/orders/revoke  申请撤销
    POST /api/dlwz/business/orders/revoke/agree  同意撤销
    POST /api/dlwz/business/orders/revoke/cancel 取消撤销
    POST /api/dlwz/business/orders/arbitrate     申请平台仲裁

认证口径（与代练通一致）：除「发送验证码 / 登录」外的接口，authorization 均为**选填** ——
不传时自动回落到后台「账号管理」(/console/accounts/) 里代练丸子（platform=dlwz）的托管账号。
商家版（/business/*）走 bd1.llwanzi.com，打手版（其余）走 m.llwanzi.com，见各自爬虫模块。
"""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一响应"""
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"), msg=result.get("message"))
    else:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result.get("message", "未知错误"))


# ==================== 认证模块 ====================


@require_http_methods(["POST"])
def send_code_view(request):
    """发送验证码

    POST /api/dlwz/auth/send-code
    内部自动完成:

      获取图片验证码 → AI 识别 → 发送短信验证码

    参数:
        phone (必填): 手机号
    """
    phone = request.POST.get("phone", "").strip()
    if not phone:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: phone(手机号)")

    ok, data = utils.send_code(phone)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def login_view(request):
    """登录

    未注册的手机号通过验证码登录会自动注册。

    参数:
        phone     (必填): 手机号
        code      (必填): 验证码或密码（取决于 code_type）
        code_type (选填): VerificationCode(验证码) / Password(密码)；默认 VerificationCode
    """
    phone = request.POST.get("phone", "").strip()
    code = request.POST.get("code", "").strip()
    code_type = request.POST.get("code_type", "VerificationCode").strip()

    if not phone:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: phone(手机号)")
    if not code:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: code(验证码或密码)")
    if code_type not in ("VerificationCode", "Password"):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: code_type 仅支持 VerificationCode 或 Password")

    ok, data = utils.login(phone, code, code_type=code_type)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 用户模块 ====================


@require_http_methods(["GET"])
def user_info_view(request):
    """获取用户信息

    参数:
        authorization (选填, query): 平台登录令牌（形如 "Bearer xxx"）；
                                     不传则用后台「账号管理」的默认代练丸子账号
    """
    auth = request.GET.get("authorization", "").strip()

    ok, data = utils.get_user_info(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def upload_avatar_view(request):
    """上传个人头像

    参数:
        image         (必填): 头像图片URL地址
        authorization (选填): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号
    """
    image = request.POST.get("image", "").strip()
    auth = request.POST.get("authorization", "").strip()
    if not image:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image(头像图片URL)")

    ok, data = utils.upload_own_avatar(image, auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def set_profile_view(request):
    """设置个性信息

    可设置的字段: username(用户名,必填)、signature(个性签名)、qq(QQ号)
    传入需要修改的字段即可。

    参数:
        authorization (选填): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号
        username      (必填): 用户名
        signature     (选填): 个性签名
        qq            (选填): QQ号
    """
    auth = request.POST.get("authorization", "").strip()
    username = request.POST.get("username", "").strip()
    if not username:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: username(用户名)")

    kwargs = {}
    for key in ("signature", "qq"):
        val = request.POST.get(key, "").strip()
        if val:
            kwargs[key] = val

    ok, data = utils.set_mysign(auth, username, **kwargs)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def real_name_view(request):
    """获取实名认证信息

    参数:
        authorization (选填, query): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号
    """
    auth = request.GET.get("authorization", "").strip()

    ok, data = utils.get_real_name_info(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def sign_in_view(request):
    """签到

    参数:
        authorization (选填): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号
    """
    auth = request.POST.get("authorization", "").strip()

    ok, data = utils.sign_in(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 财务模块 ====================


@require_http_methods(["GET"])
def balance_view(request):
    """获取我的余额

    参数:
        authorization (选填, query): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号
    """
    auth = request.GET.get("authorization", "").strip()

    ok, data = utils.get_my_balance(authorization=auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 商家版 · 我的订单 ====================


@require_http_methods(["GET"])
def order_tabs_view(request):
    """获取订单分类（商家版「我的订单」页顶部 tab，含各分类订单数量）

    参数:
        authorization (选填, query): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号

    返回 data 为上游完整响应对象（原样透传）：分类数组在上游 data.tableList，每项含
    table_type（传给「我的订单」接口做筛选）/ table_name / count。
    """
    auth = request.GET.get("authorization", "").strip()

    ok, data = utils.get_order_tabs(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def business_orders_view(request):
    """获取我的订单（商家版）

    参数:
        table_type    (选填): 订单分类，默认 0=全部；取值见「订单分类」接口的 table_type
        keyword       (选填): 搜索关键词（标题 / 角色名 / 订单号 / 号主手机）
        page          (选填): 页码，默认 1
        page_size     (选填): 每页数量，默认 20，1-100
        authorization (选填, query): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号

    返回 data 为上游完整响应对象（原样透传）：分页在上游 data.page，订单数组在上游 data.ordersList。
    """
    auth = request.GET.get("authorization", "").strip()
    keyword = request.GET.get("keyword", "").strip()

    try:
        table_type = int(request.GET.get("table_type", "0") or 0)
        page = int(request.GET.get("page", "1") or 1)
        page_size = int(request.GET.get("page_size", "20") or 20)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg="参数格式错误: table_type/page/page_size 必须为整数")
    if page < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page 必须大于 0")
    if page_size < 1 or page_size > 100:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page_size 必须在 1-100 之间")

    ok, data = utils.get_my_orders(auth, table_type=table_type, keyword=keyword,
                                   page=page, page_size=page_size)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 商家版 · 取消订单 ====================


@require_http_methods(["POST"])
def cancel_order_view(request):
    """取消订单（商家版）

    参数:
        trade_no      (必填): 订单号（「发布订单」返回的 trade_no）
        authorization (选填): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号

    说明：仅「待付待接」等可取消状态下可取消；取消后订单金额原路退回商家余额。
    返回 data 为上游完整响应对象。
    """
    trade_no = request.POST.get("trade_no", "").strip()
    if not trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: trade_no(订单号)")

    ok, data = utils.cancel_order(trade_no, authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 商家版 · 接单大厅 ====================


@require_http_methods(["GET"])
def business_search_orders_view(request):
    """搜索接单大厅订单（商家版）

    参数:
        keyword       (选填): 搜索关键词（标题 / 角色名 / 段位等），不传则按默认顺序返回
        game_id       (选填): 按游戏筛选（见「获取全部游戏」）
        page          (选填): 页码，默认 1
        page_size     (选填): 每页数量，默认 20，1-100
        authorization (选填, query): 平台登录令牌；不传则用后台默认账号

    返回 data 为上游完整响应对象：分页在 data.page，订单数组在 data.ordersList。
    """
    auth = request.GET.get("authorization", "").strip()
    keyword = request.GET.get("keyword", "").strip()
    game_id = request.GET.get("game_id", "").strip()

    try:
        page = int(request.GET.get("page", "1") or 1)
        page_size = int(request.GET.get("page_size", "20") or 20)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg="参数格式错误: page/page_size 必须为整数")
    if page < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page 必须大于 0")
    if page_size < 1 or page_size > 100:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page_size 必须在 1-100 之间")

    ok, data = utils.search_orders(keyword=keyword, game_id=game_id,
                                   page=page, page_size=page_size, authorization=auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def business_search_words_view(request):
    """大厅热搜词（商家版）

    参数:
        authorization (选填, query): 平台登录令牌；不传则用后台默认账号
    """
    ok, data = utils.get_search_words(authorization=request.GET.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def business_hall_detail_view(request):
    """大厅订单详情（商家版；接单前查看金额 / 双金 / 区服 / 代练要求）

    参数:
        trade_no      (必填, query): 订单号
        authorization (选填, query): 平台登录令牌；不传则用后台默认账号
    """
    trade_no = request.GET.get("trade_no", "").strip()
    if not trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: trade_no(订单号)")

    ok, data = utils.get_hall_order(trade_no,
                                    authorization=request.GET.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 商家版 · 接单 ====================


@require_http_methods(["POST"])
def business_take_password_check_view(request):
    """接单密码校验（商家版；指定单接单前先校验）

    参数:
        trade_no      (必填): 订单号
        take_password (必填): 接单密码
        authorization (选填): 平台登录令牌；不传则用后台默认账号
    """
    trade_no = request.POST.get("trade_no", "").strip()
    take_password = request.POST.get("take_password", "").strip()
    if not trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: trade_no(订单号)")
    if not take_password:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: take_password(接单密码)")

    ok, data = utils.take_password_check(
        trade_no, take_password,
        authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def business_take_order_view(request):
    """接单（商家版；会真实接手并从接单方余额冻结双金）

    参数:
        trade_no      (必填): 订单号（由「搜索订单」/「大厅订单详情」得到）
        pay_password  (必填): 支付密码（用于冻结双金）
        take_password (选填): 接单密码（指定单才需要，可先用「接单密码校验」）
        authorization (选填): 平台登录令牌；不传则用后台默认账号

    说明：上游为「先校验后接手」，成功后订单进入「代练中」，双金从接单方余额冻结。
    """
    trade_no = request.POST.get("trade_no", "").strip()
    pay_password = request.POST.get("pay_password", "").strip()
    if not trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: trade_no(订单号)")
    if not pay_password:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: pay_password(支付密码)")

    ok, data = utils.take_order(
        trade_no, pay_password,
        take_password=request.POST.get("take_password", "").strip(),
        authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 商家版 · 撤销 / 仲裁 ====================


def _parse_amount(request, name):
    """解析金额类参数（可空，默认 0；负数/非数字返回错误响应）"""
    raw = request.POST.get(name, "").strip()
    if raw == "":
        return 0, None
    try:
        value = float(raw)
    except ValueError:
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg=f"参数格式错误: {name} 必须为数字")
    if value < 0:
        return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                    msg=f"参数值非法: {name} 不能为负数")
    return value, None


def _parse_initiator(request):
    """解析发起方/操作方：1=发单方 / 2=接单方"""
    raw = request.POST.get("initiator", "").strip()
    if raw not in ("1", "2"):
        return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                    msg="参数值非法: initiator 只能是 1(发单方) 或 2(接单方)")
    return int(raw), None


def _trade_no_or_error(request):
    trade_no = request.POST.get("trade_no", "").strip()
    if not trade_no:
        return None, _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: trade_no(订单号)")
    return trade_no, None


def _parse_images(request):
    """解析凭证图片URL列表（JSON 字符串数组，至少一张）

    撤销 / 仲裁上游强制要求先关联凭证图片，否则申请被拒（「请补充传图」）。
    """
    raw = request.POST.get("images", "").strip()
    if not raw:
        return None, _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: images(凭证图片URL列表)")
    try:
        images = json.loads(raw)
    except ValueError:
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: images 必须是 JSON 数组")
    if not isinstance(images, list) or not images or not all(
            isinstance(item, str) and item.strip() for item in images):
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg="参数格式错误: images 必须是至少含一张图片URL的 JSON 字符串数组")
    return [item.strip() for item in images], None


@require_http_methods(["POST"])
def business_apply_revocation_view(request):
    """申请撤销（商家版；提前终止代练，需对方同意才生效）

    参数:
        trade_no          (必填): 订单号
        initiator         (必填): 发起方：1=发单方 / 2=接单方
        reason            (必填): 订单进度 + 撤销理由（客服据此处理）
        images            (必填): 凭证图片URL列表（JSON 字符串数组，至少一张；上游强制要求）
        deposit           (选填): 对方需赔付的保证金，默认 0（对方无违规填 0）
        pay_amount        (选填): 我愿支付的代练费，默认 0（打手未开始代练填 0）
        if_auto_arbitrate (选填): 对方超时未处理是否自动转仲裁，0/1，默认 0
        authorization     (选填): 平台登录令牌；不传则用后台默认账号

    说明：申请后订单进入「撤销中」，对方同意后按申请单的资金分配方案结算。
    """
    trade_no, err = _trade_no_or_error(request)
    if err:
        return err
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: reason(撤销理由)")
    initiator, err = _parse_initiator(request)
    if err:
        return err
    image_urls, err = _parse_images(request)
    if err:
        return err
    deposit, err = _parse_amount(request, "deposit")
    if err:
        return err
    pay_amount, err = _parse_amount(request, "pay_amount")
    if err:
        return err

    ok, data = utils.apply_revocation(
        trade_no, initiator, reason, image_urls, deposit=deposit, pay_amount=pay_amount,
        if_auto_arbitrate=1 if request.POST.get("if_auto_arbitrate", "").strip() in ("1", "true") else 0,
        authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def business_agree_revocation_view(request):
    """同意撤销（商家版；对方发起撤销后本方同意，生效后按申请单结算）

    参数:
        trade_no      (必填): 订单号
        pay_password  (选填): 支付密码（发单方同意时上游要求必填；接单方可不填）
        authorization (选填): 平台登录令牌；不传则用后台默认账号
    """
    trade_no, err = _trade_no_or_error(request)
    if err:
        return err

    ok, data = utils.agree_revocation(
        trade_no, pay_password=request.POST.get("pay_password", "").strip(),
        authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def business_cancel_revocation_view(request):
    """取消撤销（商家版；撤回已提交的撤销申请）

    参数:
        trade_no      (必填): 订单号
        authorization (选填): 平台登录令牌；不传则用后台默认账号
    """
    trade_no, err = _trade_no_or_error(request)
    if err:
        return err

    ok, data = utils.cancel_revocation(trade_no,
                                       authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def business_apply_arbitration_view(request):
    """申请平台仲裁（商家版）

    参数:
        trade_no      (必填): 订单号
        initiator     (必填): 操作方：1=发单方 / 2=接单方
        reason        (必填): 订单进度 + 仲裁理由
        images        (必填): 举证图片URL列表（JSON 字符串数组，至少一张；上游强制要求）
        amount        (选填): 争议代练费，默认 0
        deposit       (选填): 争议赔付保证金，默认 0
        opera_type    (选填): 操作类型，0/1，默认 0
        authorization (选填): 平台登录令牌；不传则用后台默认账号
    """
    trade_no, err = _trade_no_or_error(request)
    if err:
        return err
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: reason(仲裁理由)")
    initiator, err = _parse_initiator(request)
    if err:
        return err
    image_urls, err = _parse_images(request)
    if err:
        return err
    amount, err = _parse_amount(request, "amount")
    if err:
        return err
    deposit, err = _parse_amount(request, "deposit")
    if err:
        return err

    ok, data = utils.apply_arbitration(
        trade_no, initiator, reason, image_urls, amount=amount, deposit=deposit,
        opera_type=1 if request.POST.get("opera_type", "").strip() in ("1", "true") else 0,
        authorization=request.POST.get("authorization", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 商家版 · 发单 ====================


@require_http_methods(["GET"])
def games_view(request):
    """获取全部游戏（商家版发单用）

    参数:
        authorization (选填, query): 平台登录令牌；不传则用后台「账号管理」的默认代练丸子账号

    返回 data 为游戏数组 [{game_id, game_name}]（代练丸子没有「每个游戏的订单数」）。
    """
    auth = request.GET.get("authorization", "").strip()

    ok, data = utils.get_games(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def order_options_view(request):
    """获取发单选项（商家版）

    参数:
        game_id           (必填, query): 游戏ID（可由「获取全部游戏」取到）
        leveling_type_id  (选填, query): 代练类型ID；传了才返回该类型的子类型字段（段位 / 数量等）
        authorization     (选填, query): 平台登录令牌；不传则用后台默认账号

    返回 data:
        regions        大区列表 [{region_id, region_name, server_id, server_name}]（server 为默认服）
        leveling_types 代练类型 [{leveling_type_id, leveling_type_name}]
        fields         子类型字段（仅传了 leveling_type_id 时）：
                       {sub_type_id, name, type, is_must}，下拉类带 options[]，段位类带 levels[]，
                       数字类带 min_val / max_val
    """
    game_id = request.GET.get("game_id", "").strip()
    if not game_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: game_id(游戏ID)")
    if not game_id.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: game_id 必须为正整数")

    ok, data = utils.get_order_options(
        game_id,
        authorization=request.GET.get("authorization", "").strip(),
        leveling_type_id=request.GET.get("leveling_type_id", "").strip(),
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def publish_order_view(request):
    """发布订单（商家版）

    参数:
        game_id          (选填): 游戏ID，默认 1；当前支持 1=王者荣耀 / 134=三角洲行动
        tasks            (选填): 任务字段 JSON 数组，覆盖该游戏预设默认值，例如
                                 [{"name":"起止段位","start":"青铜3段0星","end":"王者50星"}]
                                 [{"name":"哈夫币(万)","value":100},{"name":"保险箱","value":"2格"}]
        amount           (选填): 订单价格（元），默认 2
        hour             (选填): 代练时长（小时），默认 3
        security_deposit (选填): 安全保证金（元），默认 2
        efficiency_deposit (选填): 效率保证金（元），默认 2
        region_name      (选填): 大区中文名（如 安卓QQ / 手机QQ），默认取该游戏预设
        leveling_type_name (选填): 代练类型中文名（如 排位 / 哈夫币代刷），默认取该游戏预设
        login_method     (选填): 1=扫码上号 / 2=账密上号（默认 2）
        game_account / game_password / game_role (选填): 游戏账号 / 密码 / 角色名
        player_phone / contact_phone / contact_qq (选填): 号主手机 / 发单方联系方式 / 其它联系方式
        title / subtitle (选填): 主标题 / 副标题（留空则按上游规则自动生成）
        explain / requirement (选填): 代练说明 / 代练要求（留空取上游默认文案）
        take_password    (选填): 接单密码（仅指定打手可接时使用）
        authorization    (选填): 平台登录令牌；不传则用后台默认账号

    返回 data 为 {"trade_no": 订单号, "status": 状态}。注意：会真实发布订单。
    """
    tasks = None
    raw_tasks = request.POST.get("tasks", "").strip()
    if raw_tasks:
        try:
            tasks = json.loads(raw_tasks)
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: tasks 必须是 JSON 数组")
        if not isinstance(tasks, list):
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: tasks 必须是 JSON 数组")

    numbers = {}
    for name in ("amount", "hour", "security_deposit", "efficiency_deposit"):
        raw = request.POST.get(name, "").strip()
        if raw == "":
            numbers[name] = None
            continue
        try:
            numbers[name] = float(raw)
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=f"参数格式错误: {name} 必须为数值")

    login_method = None
    raw_login = request.POST.get("login_method", "").strip()
    if raw_login:
        if raw_login not in ("1", "2"):
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg="参数值非法: login_method 仅支持 1(扫码上号) / 2(账密上号)")
        login_method = int(raw_login)

    ok, data = utils.publish_order(
        request.POST.get("game_id", "").strip() or None,
        tasks=tasks,
        amount=numbers["amount"], hour=numbers["hour"],
        security_deposit=numbers["security_deposit"],
        efficiency_deposit=numbers["efficiency_deposit"],
        region_name=request.POST.get("region_name", "").strip(),
        leveling_type_name=request.POST.get("leveling_type_name", "").strip(),
        login_method=login_method,
        game_account=request.POST.get("game_account", "").strip(),
        game_password=request.POST.get("game_password", "").strip(),
        game_role=request.POST.get("game_role", "").strip(),
        player_phone=request.POST.get("player_phone", "").strip(),
        contact_phone=request.POST.get("contact_phone", "").strip(),
        contact_qq=request.POST.get("contact_qq", "").strip(),
        title=request.POST.get("title", "").strip(),
        subtitle=request.POST.get("subtitle", "").strip(),
        explain=request.POST.get("explain", "").strip(),
        requirement=request.POST.get("requirement", "").strip(),
        take_password=request.POST.get("take_password", "").strip(),
        authorization=request.POST.get("authorization", "").strip(),
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)
