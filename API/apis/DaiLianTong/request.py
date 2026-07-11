"""代练通 DaiLianTong API 请求处理视图

提供 17 个接口，对应爬虫的 17 个对外方法:
    POST /api/dlt/auth/send-code         发送验证码
    POST /api/dlt/auth/register           注册
    POST /api/dlt/auth/login              登录
    GET  /api/dlt/user/info               获取用户信息
    POST /api/dlt/user/set-contact        设置联系方式
    POST /api/dlt/user/set-mysign         设置个性签名
    POST /api/dlt/user/change-password    修改密码
    POST /api/dlt/user/sign-in            签到
    GET  /api/dlt/user/real-name-info     获取实名认证信息
    GET  /api/dlt/orders/public           获取公共订单列表
    GET  /api/dlt/orders/detail           获取订单详情
    POST /api/dlt/orders/receive          接收订单
    POST /api/dlt/orders/publish          发布订单
    POST /api/dlt/orders/delete           删除订单
    GET  /api/dlt/orders/my               获取我的订单
    POST /api/dlt/orders/upload-image     订单留言上传图片
    POST /api/dlt/avatar/upload           上传头像
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

    参数:
        phone    (必填): 手机号
        use_type (选填): 验证码类型，17=注册 12=登录，默认 17
    """
    phone = request.POST.get("phone", "").strip()
    if not phone:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: phone(手机号)")
    use_type = request.POST.get("use_type", "17").strip()

    ok, data = utils.send_code(phone, use_type=use_type)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def register_view(request):
    """注册

    参数:
        phone (必填): 手机号
        code  (必填): 验证码
    """
    phone = request.POST.get("phone", "").strip()
    code = request.POST.get("code", "").strip()
    if not phone:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: phone(手机号)")
    if not code:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: code(验证码)")

    ok, data = utils.register(phone, code)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def login_view(request):
    """登录

    参数:
        phone     (必填): 手机号
        code      (必填): 验证码或密码
        code_type (选填): VerificationCode(验证码) / Password(密码)，默认 VerificationCode
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
        user_id (必填): 用户ID
        token   (必填): 登录令牌
    """
    user_id = request.GET.get("user_id", "").strip()
    token = request.GET.get("token", "").strip()
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")

    ok, data = utils.get_user_info(user_id, token)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def set_contact_view(request):
    """设置联系方式

    参数:
        contact   (必填): 联系方式（QQ号或手机号）
        user_id   (必填): 用户ID
        token     (必填): 登录令牌
        set_type  (选填): qq(QQ号) / mobile(手机号)，默认 qq
    """
    contact = request.POST.get("contact", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    token = request.POST.get("token", "").strip()
    set_type = request.POST.get("set_type", "qq").strip()
    if not contact:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: contact(联系方式)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")
    if set_type not in ("qq", "mobile"):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: set_type 仅支持 qq 或 mobile")

    ok, data = utils.set_contact(contact, user_id, token, set_contact_type=set_type)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def set_mysign_view(request):
    """设置个性签名（无需 token）

    参数:
        mysign  (必填): 个性签名内容
        user_id (必填): 用户ID
    """
    mysign = request.POST.get("mysign", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    if not mysign:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: mysign(个性签名)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")

    ok, data = utils.set_mysign(mysign, user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def change_password_view(request):
    """修改密码

    参数:
        old_password (必填): 旧密码（为空时表示未设置过密码）
        new_password (必填): 新密码
        user_id      (必填): 用户ID
        login_id     (必填): 登录ID
        uid          (必填): UID
        token        (必填): 登录令牌
    """
    old = request.POST.get("old_password", "").strip()
    new = request.POST.get("new_password", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    login_id = request.POST.get("login_id", "").strip()
    uid = request.POST.get("uid", "").strip()
    token = request.POST.get("token", "").strip()

    if not new:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: new_password(新密码)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not login_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: login_id(登录ID)")
    if not uid:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: uid")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")

    ok, data = utils.change_password(old, new, user_id, login_id, uid, token)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def sign_in_view(request):
    """签到得代币

    参数:
        user_id (必填): 用户ID
    """
    user_id = request.POST.get("user_id", "").strip()
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")

    ok, data = utils.sign_in(user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def real_name_info_view(request):
    """获取实名认证信息

    参数:
        user_id (必填): 用户ID
    """
    user_id = request.GET.get("user_id", "").strip()
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")

    ok, data = utils.get_real_name_info(user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 订单模块 ====================


@require_http_methods(["GET"])
def orders_public_view(request):
    """获取公共订单列表

    参数:
        user_id          (必填): 用户ID
        token            (必填): 登录令牌
        page_index       (选填): 页码，默认 1
        page_size        (选填): 每页数量，默认 20
        game_id          (选填): 游戏ID，默认 107(王者荣耀)
        price_str        (选填): 价格范围，默认 10_20
        is_pub           (选填): 是否公共订单，默认 1
        search_str       (选填): 搜索关键词，默认空
        pg_type          (选填): 区服，0=全部 1=安卓 2=IOS，默认 0
        filter_sensitive (选填): 是否过滤敏感词，true/false，默认 false
    """
    user_id = request.GET.get("user_id", "").strip()
    token = request.GET.get("token", "").strip()
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")

    try:
        page_index = int(request.GET.get("page_index", "1"))
        page_size = int(request.GET.get("page_size", "20"))
        game_id = int(request.GET.get("game_id", "107"))
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: page_index/page_size/game_id 必须为整数")

    price_str = request.GET.get("price_str", "10_20").strip()
    is_pub = request.GET.get("is_pub", "1").strip()
    search_str = request.GET.get("search_str", "").strip()
    pg_type = request.GET.get("pg_type", "0").strip()
    filter_sensitive = request.GET.get("filter_sensitive", "false").strip().lower() == "true"

    ok, data = utils.get_public_order_list(
        user_id, token, page_index=page_index, page_size=page_size,
        game_id=game_id, price_str=price_str, is_pub=is_pub,
        search_str=search_str, pg_type=pg_type,
        filter_sensitive=filter_sensitive,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def order_detail_view(request):
    """获取订单详情

    参数:
        user_id  (必填): 用户ID
        token    (必填): 登录令牌
        order_id (必填): 订单ID
    """
    user_id = request.GET.get("user_id", "").strip()
    token = request.GET.get("token", "").strip()
    order_id = request.GET.get("order_id", "").strip()
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")
    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.get_order_detail(user_id, token, order_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def receive_order_view(request):
    """接收订单

    参数:
        order_id  (必填): 订单ID
        pay_pass  (必填): 支付密码
        uid       (必填): UID
        token     (必填): 登录令牌
        user_id   (必填): 用户ID
    """
    order_id = request.POST.get("order_id", "").strip()
    pay_pass = request.POST.get("pay_pass", "").strip()
    uid = request.POST.get("uid", "").strip()
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()

    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")
    if not pay_pass:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: pay_pass(支付密码)")
    if not uid:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: uid")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")

    ok, data = utils.receive_order(order_id, pay_pass, uid, token, user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def publish_order_view(request):
    """发布订单

    参数:
        title            (必填): 订单标题
        uid              (必填): UID
        price            (必填): 价格
        time_limit       (必填): 代练时长
        token            (必填): 登录令牌
        user_id          (必填): 用户ID
        ensure1          (必填): 安全保证金
        ensure2          (必填): 效率保证金
        game_mobile      (必填): 号主联系方式
        pay_pass         (必填): 支付密码
        game_account     (必填): 游戏账号
        game_password    (必填): 游戏密码
        game_author_name (必填): 游戏角色名
        hero_count       (选填): 英雄数量，默认 10
        requirements     (选填): 代练要求，提供默认值
        zone_server_id   (选填): 游戏ID，默认王者荣耀
    """
    title = request.POST.get("title", "").strip()
    uid = request.POST.get("uid", "").strip()
    price = request.POST.get("price", "").strip()
    time_limit = request.POST.get("time_limit", "").strip()
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    ensure1 = request.POST.get("ensure1", "").strip()
    ensure2 = request.POST.get("ensure2", "").strip()
    game_mobile = request.POST.get("game_mobile", "").strip()
    pay_pass = request.POST.get("pay_pass", "").strip()
    game_account = request.POST.get("game_account", "").strip()
    game_password = request.POST.get("game_password", "").strip()
    game_author_name = request.POST.get("game_author_name", "").strip()

    params = {
        "title": title, "uid": uid, "price": price, "time_limit": time_limit,
        "token": token, "user_id": user_id, "ensure1": ensure1, "ensure2": ensure2,
        "game_mobile": game_mobile, "pay_pass": pay_pass,
        "game_account": game_account, "game_password": game_password,
        "game_author_name": game_author_name,
    }
    missing = [k for k, v in params.items() if not v]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, msg=f"参数缺失: {', '.join(missing)}")

    hero_count = request.POST.get("hero_count", "10").strip()
    try:
        hero_count = int(hero_count)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: hero_count 必须为整数")

    requirements = request.POST.get("requirements", (
        "1、未经同意请勿动用账号点券、物品，不要联系或回复好友信息\n\n"
        "2、切勿使用外挂，不允许打广告、挂机、恶意骂人等恶意行为"
    )).strip()
    zone_server_id = request.POST.get("zone_server_id", "107103017095500").strip()

    ok, data = utils.publish_order(
        title=title, uid=uid, price=price, time_limit=time_limit,
        token=token, user_id=user_id, ensure1=ensure1, ensure2=ensure2,
        game_mobile=game_mobile, pay_pass=pay_pass, game_account=game_account,
        game_password=game_password, game_author_name=game_author_name,
        hero_count=hero_count, requirements=requirements,
        zone_serverID=zone_server_id,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def delete_order_view(request):
    """删除订单

    参数:
        order_id (必填): 订单ID
        token    (必填): 登录令牌
        user_id  (必填): 用户ID
        reason   (选填): 删除原因，默认"不用了"
    """
    order_id = request.POST.get("order_id", "").strip()
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    reason = request.POST.get("reason", "不用了").strip()

    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")

    ok, data = utils.delete_order(order_id, token, user_id, reason=reason)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def my_orders_view(request):
    """获取我的订单

    参数:
        token      (必填): 登录令牌
        user_id    (必填): 用户ID
        page_index (选填): 页码，默认 1
        page_size  (选填): 每页数量，默认 20
        over_days  (选填): -99=正在进行, 99=已完成, 默认 -99
        search_str (选填): 搜索关键词，默认空
    """
    token = request.GET.get("token", "").strip()
    user_id = request.GET.get("user_id", "").strip()
    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")

    page_index = request.GET.get("page_index", "1").strip()
    page_size = request.GET.get("page_size", "20").strip()
    over_days = request.GET.get("over_days", "-99").strip()
    search_str = request.GET.get("search_str", "").strip()

    ok, data = utils.get_my_order(token, user_id, page_index=page_index,
                                  page_size=page_size, over_days=over_days,
                                  search_str=search_str)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def upload_image_view(request):
    """在订单留言中上传图片

    参数:
        token      (必填): 登录令牌
        user_id    (必填): 用户ID
        image_path (必填): 图片路径
        order_id   (必填): 订单ID
    """
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    image_path = request.POST.get("image_path", "").strip()
    order_id = request.POST.get("order_id", "").strip()

    if not token:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: token(登录令牌)")
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not image_path:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image_path(图片路径)")
    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.upload_image_in_comment(token, user_id, image_path, order_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 头像模块 ====================


@require_http_methods(["POST"])
def upload_avatar_view(request):
    """上传头像（无需 token）

    参数:
        user_id    (必填): 用户ID
        image_path (必填): 图片URL路径
    """
    user_id = request.POST.get("user_id", "").strip()
    image_path = request.POST.get("image_path", "").strip()
    if not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: user_id(用户ID)")
    if not image_path:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image_path(图片路径)")

    ok, data = utils.upload_avatar(user_id, image_path)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)
