"""代练丸子 DaiLianWanZi API 请求处理视图

提供 13 个接口，对应爬虫的 13 个对外方法:
    POST /api/dlwz/auth/send-code         发送验证码
    POST /api/dlwz/auth/login              登录
    GET  /api/dlwz/user/info               获取用户信息
    POST /api/dlwz/user/upload-avatar      上传头像
    POST /api/dlwz/user/set-profile        设置个性信息（签名/QQ号等）
    GET  /api/dlwz/user/real-name          获取实名认证信息
    POST /api/dlwz/user/sign-in            签到
    GET  /api/dlwz/orders/public           公共订单列表
    GET  /api/dlwz/orders/search           搜索订单
    GET  /api/dlwz/orders/detail           订单详情
    POST /api/dlwz/orders/publish          发布订单
    POST /api/dlwz/orders/cancel           取消订单
    GET  /api/dlwz/user/balance            获取我的余额
"""
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


def _require_authorization(request, source="POST"):
    """从 request 中提取 authorization 参数"""
    if source == "POST":
        auth = request.POST.get("authorization", "").strip()
    else:
        auth = request.GET.get("authorization", "").strip()
    return auth


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
        authorization (必填, query): 登录令牌，格式"Bearer xxx"
    """
    auth = request.GET.get("authorization", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")

    ok, data = utils.get_user_info(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def upload_avatar_view(request):
    """上传个人头像

    参数:
        image         (必填): 头像图片URL地址
        authorization (必填): 登录令牌
    """
    image = request.POST.get("image", "").strip()
    auth = request.POST.get("authorization", "").strip()
    if not image:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image(头像图片URL)")
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")

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
        authorization (必填): 登录令牌
        username      (必填): 用户名
        signature     (选填): 个性签名
        qq            (选填): QQ号
    """
    auth = request.POST.get("authorization", "").strip()
    username = request.POST.get("username", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")
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
        authorization (必填, query): 登录令牌
    """
    auth = request.GET.get("authorization", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")

    ok, data = utils.get_real_name_info(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def sign_in_view(request):
    """签到

    参数:
        authorization (必填): 登录令牌
    """
    auth = request.POST.get("authorization", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")

    ok, data = utils.sign_in(auth)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 订单模块 ====================


@require_http_methods(["GET"])
def orders_public_view(request):
    """获取公共订单列表

    参数:
        authorization (必填, query): 登录令牌
        price_gt      (选填, query): 最低价格，默认 10
        price_lt      (选填, query): 最高价格，默认 50
        page_no       (选填, query): 页码，从 1 开始；默认 1
        page_size     (选填, query): 每页数量，默认 30
        game_id       (选填, query): 游戏ID，1=王者(默认值)
    """
    auth = request.GET.get("authorization", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")

    try:
        price_gt = int(request.GET.get("price_gt", "10"))
        price_lt = int(request.GET.get("price_lt", "50"))
        page_no = int(request.GET.get("page_no", "1"))
        page_size = int(request.GET.get("page_size", "30"))
        game_id = int(request.GET.get("game_id", "1"))
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: 数值参数必须为整数")

    ok, data = utils.get_public_order_list(auth, price_gt=price_gt,
                                           price_lt=price_lt, page_no=page_no,
                                           page_size=page_size, game_id=game_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def orders_search_view(request):
    """搜索订单

    参数:
        authorization (必填, query): 登录令牌
        keyword       (必填, query): 搜索关键词
        page_no       (选填, query): 页码，默认 1
        page_size     (选填, query): 每页数量，默认 10
    """
    auth = request.GET.get("authorization", "").strip()
    keyword = request.GET.get("keyword", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")
    if not keyword:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: keyword(搜索关键词)")

    try:
        page_no = int(request.GET.get("page_no", "1"))
        page_size = int(request.GET.get("page_size", "10"))
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: page_no/page_size 必须为整数")

    ok, data = utils.search_order(auth, keyword, page_no=page_no, page_size=page_size)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def order_detail_view(request):
    """获取订单详情

    参数:
        authorization (必填, query): 登录令牌
        order_id      (必填, query): 订单ID
    """
    auth = request.GET.get("authorization", "").strip()
    order_id = request.GET.get("order_id", "").strip()
    if not auth:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: authorization(登录令牌)")
    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.get_order_detail(auth, order_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def publish_order_view(request):
    """发布订单

    参数（加粗为必填）:
        authorization     (必填): 登录令牌
        title             (必填): 订单标题
        amount            (必填): 订单金额（元）
        hour              (必填): 代练时长（小时）
        security_deposit  (必填): 安全保证金
        efficiency_deposit(必填): 效率保证金
        player_phone      (选填): 号主手机号，默认 "3837190115"
        contact_phone     (选填): 发单方联系方式，默认 "3837190115"
        game_region_name  (选填): 游戏区域，安卓QQ/安卓微信/苹果QQ/苹果微信；默认 "安卓QQ"
        hero_number       (选填): 英雄数量
        requirement       (选填): 代练要求
        explain_text      (选填): 订单说明
        game_account      (选填): 游戏账号
        game_password     (选填): 游戏密码
        contact_qq        (选填): 其他联系方式
        game_role         (选填): 游戏角色
        game_id           (选填): 游戏ID，1=王者
        game_server_id    (选填): 服务器ID，122=安卓QQ
        game_region_id    (选填): 区域ID，2=安卓QQ
        game_icon         (选填): 游戏图标URL
        game_name         (选填): 游戏名称，默认"王者"
        game_leveling_type_name (选填): 代练类型，默认"排位"
    """
    auth = request.POST.get("authorization", "").strip()
    title = request.POST.get("title", "").strip()
    amount = request.POST.get("amount", "").strip()
    hour = request.POST.get("hour", "").strip()
    security_deposit = request.POST.get("security_deposit", "").strip()
    efficiency_deposit = request.POST.get("efficiency_deposit", "").strip()

    required = {
        "authorization": auth, "title": title, "amount": amount,
        "hour": hour, "security_deposit": security_deposit,
        "efficiency_deposit": efficiency_deposit,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, msg=f"参数缺失: {', '.join(missing)}")

    try:
        amount_num = float(amount)
        hour_num = int(hour)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: amount 必须为数字，hour 必须为整数")

    player_phone = request.POST.get("player_phone", "3837190115").strip()
    contact_phone = request.POST.get("contact_phone", "3837190115").strip()
    game_region_name = request.POST.get("game_region_name", "安卓QQ").strip()
    hero_number = request.POST.get("hero_number", "").strip()
    requirement = request.POST.get("requirement", "代练要求").strip()
    explain_text = request.POST.get("explain_text", "代练说明").strip()
    game_account = request.POST.get("game_account", "扫码上号").strip()
    game_password = request.POST.get("game_password", "扫码上号").strip()
    contact_qq = request.POST.get("contact_qq", "扫码上号").strip()
    game_role = request.POST.get("game_role", "扫码上号").strip()

    try:
        game_id = int(request.POST.get("game_id", "1"))
        game_server_id = int(request.POST.get("game_server_id", "122"))
        game_region_id = int(request.POST.get("game_region_id", "2"))
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: game_id/game_server_id/game_region_id 必须为整数")

    game_icon = request.POST.get("game_icon", (
        "https://files.llwanzi.com/zympYphpKVhaHN1685523686230531.png"
    )).strip()
    game_name = request.POST.get("game_name", "王者").strip()
    game_leveling_type_name = request.POST.get("game_leveling_type_name", "排位").strip()

    ok, data = utils.publish_order(
        authorization=auth, title=title, amount=amount_num, hour=hour_num,
        security_deposit=security_deposit, efficiency_deposit=efficiency_deposit,
        player_phone=player_phone, contact_phone=contact_phone,
        game_region_name=game_region_name, hero_number=hero_number,
        requirement=requirement, explain_text=explain_text,
        game_account=game_account, game_password=game_password,
        contact_qq=contact_qq, game_role=game_role,
        game_id=game_id, game_server_id=game_server_id,
        game_region_id=game_region_id, game_icon=game_icon,
        game_name=game_name, game_leveling_type_name=game_leveling_type_name,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def cancel_order_view(request):
    """取消订单

    参数:
        order_id       (必填): 订单ID
        authorization  (选填): 登录令牌
    """
    order_id = request.POST.get("order_id", "").strip()
    auth = request.POST.get("authorization", "").strip()
    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.cancel_order(order_id, authorization=auth or None)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 财务模块 ====================


@require_http_methods(["GET"])
def balance_view(request):
    """获取我的余额

    参数:
        authorization (选填, query): 登录令牌
    """
    auth = request.GET.get("authorization", "").strip()

    ok, data = utils.get_my_balance(authorization=auth or None)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)
