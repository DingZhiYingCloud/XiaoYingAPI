"""代练通 DaiLianTong API 请求处理视图

提供 21 个接口，对应爬虫的对外方法:
    POST /api/dlt/auth/send-code         发送验证码
    POST /api/dlt/auth/register           注册
    POST /api/dlt/auth/login              登录
    GET  /api/dlt/user/info               获取用户信息
    POST /api/dlt/user/set-contact        设置联系方式
    POST /api/dlt/user/set-mysign         设置个性签名
    POST /api/dlt/user/change-password    修改密码
    POST /api/dlt/user/sign-in            签到
    GET  /api/dlt/user/real-name-info     获取实名认证信息
    GET  /api/dlt/games                   获取全部游戏
    GET  /api/dlt/games/orders            按游戏获取订单列表
    GET  /api/dlt/search/orders           按关键词搜索订单（高度自定义）
    GET  /api/dlt/search/hot-words        获取某游戏热门搜索词
    POST /api/dlt/orders/receive          接收订单
    POST /api/dlt/orders/publish          发布订单（自定义发布）
    POST /api/dlt/orders/apply-cancel     申请撤销订单
    POST /api/dlt/orders/handle-cancel    处理撤销申请（同意/取消/申请平台介入）
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


def _get_int(params, name, default):
    """读取整数参数（未传 / 空串用默认值）。

    :param params: request.GET 或 request.POST（QueryDict）
    :return: (值, None) 或 (None, 错误响应)
    """
    raw = (params.get(name) or '').strip()
    if raw == '':
        return default, None
    try:
        return int(raw), None
    except ValueError:
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg=f"参数格式错误: {name} 必须为整数")


def _get_number(params, name, default):
    """读取数值参数（整数 / 小数；未传 / 空串用默认值）。

    :return: (值, None) 或 (None, 错误响应)
    """
    raw = (params.get(name) or '').strip()
    if raw == '':
        return default, None
    try:
        value = float(raw)
    except ValueError:
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg=f"参数格式错误: {name} 必须为数值")
    return (int(value) if value.is_integer() else value), None


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
        user_id (选填): 用户ID；不传则用后台「账号管理」的默认代练通账号
        token   (选填): 登录令牌；不传则用后台默认账号的令牌
    """
    user_id = request.GET.get("user_id", "").strip()
    token = request.GET.get("token", "").strip()

    ok, data = utils.get_user_info(user_id, token)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def set_contact_view(request):
    """设置联系方式

    参数:
        contact   (必填): 联系方式（QQ号或手机号）
        user_id   (选填): 用户ID；不传则用后台默认账号
        token     (选填): 登录令牌；不传则用后台默认账号的令牌
        set_type  (选填): qq(QQ号) / mobile(手机号)，默认 qq
    """
    contact = request.POST.get("contact", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    token = request.POST.get("token", "").strip()
    set_type = request.POST.get("set_type", "qq").strip()
    if not contact:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: contact(联系方式)")
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
        user_id (选填): 用户ID；不传则用后台默认账号
    """
    mysign = request.POST.get("mysign", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    if not mysign:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: mysign(个性签名)")

    ok, data = utils.set_mysign(mysign, user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def change_password_view(request):
    """修改密码

    参数:
        old_password (选填): 旧密码（为空时表示未设置过密码）
        new_password (必填): 新密码
        user_id      (选填): 用户ID；不传则用后台默认账号
        login_id     (必填): 登录ID
        uid          (必填): UID
        token        (选填): 登录令牌；不传则用后台默认账号的令牌
    """
    old = request.POST.get("old_password", "").strip()
    new = request.POST.get("new_password", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    login_id = request.POST.get("login_id", "").strip()
    uid = request.POST.get("uid", "").strip()
    token = request.POST.get("token", "").strip()

    if not new:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: new_password(新密码)")
    if not login_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: login_id(登录ID)")
    if not uid:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: uid")

    ok, data = utils.change_password(old, new, user_id, login_id, uid, token)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def sign_in_view(request):
    """签到得代币

    参数:
        user_id (选填): 用户ID；不传则用后台默认账号
    """
    user_id = request.POST.get("user_id", "").strip()

    ok, data = utils.sign_in(user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def real_name_info_view(request):
    """获取实名认证信息

    参数:
        user_id (选填): 用户ID；不传则用后台默认账号
    """
    user_id = request.GET.get("user_id", "").strip()

    ok, data = utils.get_real_name_info(user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 订单模块 ====================


@require_http_methods(["POST"])
def receive_order_view(request):
    """接收订单

    参数:
        order_id  (必填): 订单ID
        pay_pass  (必填): 支付密码
        uid       (必填): UID
        token     (选填): 登录令牌；不传则用后台默认账号的令牌
        user_id   (选填): 用户ID；不传则用后台默认账号
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

    ok, data = utils.receive_order(order_id, pay_pass, uid, token, user_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def delete_order_view(request):
    """删除订单

    参数:
        order_id (必填): 订单ID
        token    (选填): 登录令牌；不传则用后台默认账号的令牌
        user_id  (选填): 用户ID；不传则用后台默认账号
        reason   (选填): 删除原因，默认"不用了"
    """
    order_id = request.POST.get("order_id", "").strip()
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    reason = request.POST.get("reason", "不用了").strip()

    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.delete_order(order_id, token, user_id, reason=reason)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def apply_cancel_view(request):
    """申请撤销订单（发单者/接单者）

    参数:
        order_id       (必填): 订单ID（ODSerialNo）
        pay_pass       (必填): 支付密码（原密码；服务端按 md5(md5(pwd)+uid) 处理）
        uid            (必填): 账号 UID（USR 开头；支付密码哈希用）
        token          (选填): 登录令牌；不传则用后台默认账号的令牌
        user_id        (选填): 用户ID；不传则用后台默认账号
        flag           (选填): 0=申请撤销（默认）/1=取消撤销/2=同意撤销/3=申请平台介入
        desire         (选填): 撤销意愿 0=我愿意支付代练费 / 1=我要求赔偿保证金 / 2=仅要求退款（默认）
        progress       (选填): 账号进度：有进度/无进度/负进度/未开始代练（默认 无进度）
        comment        (选填): 补充描述
        pay_level_bal  (选填): 支付代练费金额（desire=0 时生效），默认 0
        rep_ensure_bal (选填): 赔偿保证金金额（desire=1 时生效），默认 0
        revoke_price   (选填): 撤销金额，默认 0
        image          (选填): 撤销凭证图片地址；撤销成功后自动以「撤销」留言上传

    返回 data 为上游 LevelOrderCancel 的返回（原样透传）。
    """
    order_id = request.POST.get("order_id", "").strip()
    pay_pass = request.POST.get("pay_pass", "").strip()
    uid = request.POST.get("uid", "").strip()
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    comment = request.POST.get("comment", "").strip()
    image = request.POST.get("image", "").strip()

    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")
    if not pay_pass:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: pay_pass(支付密码)")
    if not uid:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: uid(账号UID)")

    desire = request.POST.get("desire", "2").strip() or "2"
    if desire not in utils.CANCEL_DESIRE_OPTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg="参数值非法: desire 仅支持 0/1/2")
    progress = request.POST.get("progress", "无进度").strip() or "无进度"
    if progress not in utils.CANCEL_PROGRESS_OPTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f"参数值非法: progress 仅支持 {'/'.join(utils.CANCEL_PROGRESS_OPTIONS)}")

    flag, err = _get_int(request.POST, "flag", 0)
    if err:
        return err
    pay_level_bal, err = _get_number(request.POST, "pay_level_bal", 0)
    if err:
        return err
    rep_ensure_bal, err = _get_number(request.POST, "rep_ensure_bal", 0)
    if err:
        return err
    revoke_price, err = _get_number(request.POST, "revoke_price", 0)
    if err:
        return err

    ok, data = utils.apply_cancel_order(
        order_id, pay_pass, uid, token, user_id, flag=flag, desire=desire,
        progress=progress, comment=comment, pay_level_bal=pay_level_bal,
        rep_ensure_bal=rep_ensure_bal, revoke_price=revoke_price, image=image)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def handle_cancel_view(request):
    """处理撤销申请（同意撤销 / 取消撤销 / 申请平台介入）

    参数:
        order_id       (必填): 订单ID（ODSerialNo）
        action         (选填): agree=同意撤销（默认）/ cancel=取消撤销 / arbitration=申请平台介入
        pay_pass       (选填): 支付密码（agree / cancel 必填；arbitration 不需要）
        uid            (选填): 账号 UID（agree / cancel 必填；支付密码哈希用）
        pay_level_bal  (选填): 支付代练费金额（同意撤销时下发），默认 0
        rep_ensure_bal (选填): 赔偿保证金金额（同意撤销时下发），默认 0
        comment        (选填): 撤销说明，默认空
        image          (选填): 凭证图片地址；操作成功后自动以「撤销」留言上传
        token          (选填): 登录令牌；不传则用后台默认账号的令牌
        user_id        (选填): 用户ID；不传则用后台默认账号

    返回 data 为上游返回（原样透传）。
    """
    order_id = request.POST.get("order_id", "").strip()
    action = request.POST.get("action", "agree").strip() or "agree"
    pay_pass = request.POST.get("pay_pass", "").strip()
    uid = request.POST.get("uid", "").strip()
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    comment = request.POST.get("comment", "").strip()
    image = request.POST.get("image", "").strip()

    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")
    if action not in utils.HANDLE_CANCEL_ACTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f"参数值非法: action 仅支持 {'/'.join(utils.HANDLE_CANCEL_ACTIONS)}")
    if action in ('agree', 'cancel'):
        if not pay_pass:
            return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: pay_pass(支付密码)")
        if not uid:
            return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: uid(账号UID)")

    pay_level_bal, err = _get_number(request.POST, "pay_level_bal", 0)
    if err:
        return err
    rep_ensure_bal, err = _get_number(request.POST, "rep_ensure_bal", 0)
    if err:
        return err

    ok, data = utils.handle_cancel(
        order_id, action, pay_pass=pay_pass, uid=uid, token=token, user_id=user_id,
        pay_level_bal=pay_level_bal, rep_ensure_bal=rep_ensure_bal,
        comment=comment, image=image)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def my_orders_view(request):
    """获取我的订单（我发布的 / 我接的，可多条件筛选）

    参数:
        token         (选填): 登录令牌；不传则用后台默认账号的令牌
        user_id       (选填): 用户ID；不传则用后台默认账号
        publish       (选填): 1=我发布的（默认） / 0=我接的
        over_days     (选填): -99=进行中（默认） / 99=已完成
        status        (选填): 订单状态位，0=不限（默认）
        cancel_status (选填): 撤单状态位，0=不限（默认）
        game_id       (选填): 游戏ID筛选，0=全部（默认）
        search_str    (选填): 关键词，默认空
        game_mobile   (选填): 号主联系方式筛选，默认空
        with_tg       (选填): 是否含托管，默认 1
        state         (选填): 状态快捷筛选（中文名，如 待付款/未接手/正在代练/等待验收/订单异常/
                              锁定订单/申请撤销中/仲裁介入中/协商已处理/仲裁已处理/客服强制撤销/已结算/全部）；
                              等价于一次性设置 status/cancel_status/over_days，显式传这三者时以其为准
        page          (选填): 页码，默认 1
        page_size     (选填): 每页数量，默认 20，1-100

    返回 data 为分页对象（服务端分页）：items / total / page / page_size / total_pages。
    """
    user_id_raw = request.GET.get("user_id", "").strip()
    if user_id_raw and not user_id_raw.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: user_id 必须为数字")

    # state 预置一组 (Status, CancelStatus, OverDays)；显式传 status/cancel_status/over_days 时以其为准
    state = request.GET.get("state", "").strip()
    if state and state not in utils.MY_ORDER_STATES:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f"参数值非法: state 仅支持 {'/'.join(utils.MY_ORDER_STATES)}")
    status_default, cancel_default, over_days_default = utils.MY_ORDER_STATES.get(state, (0, 0, -99))

    int_params = {}
    for name, default in (('publish', 1), ('over_days', over_days_default), ('status', status_default),
                          ('cancel_status', cancel_default), ('game_id', 0), ('with_tg', 1),
                          ('page', 1), ('page_size', 20)):
        value, err = _get_int(request.GET, name, default)
        if err:
            return err
        int_params[name] = value

    if int_params['page'] < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page 必须大于 0")
    if int_params['page_size'] < 1 or int_params['page_size'] > 100:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page_size 必须在 1-100 之间")

    ok, data = utils.get_my_order(
        token=request.GET.get("token", "").strip(),
        user_id=int(user_id_raw) if user_id_raw else 0,
        search_str=request.GET.get("search_str", "").strip(),
        game_mobile=request.GET.get("game_mobile", "").strip(),
        **int_params,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["POST"])
def upload_image_view(request):
    """在订单留言中上传图片

    参数:
        token      (选填): 登录令牌；不传则用后台默认账号的令牌
        user_id    (选填): 用户ID；不传则用后台默认账号
        image_path (必填): 图片路径
        order_id   (必填): 订单ID
    """
    token = request.POST.get("token", "").strip()
    user_id = request.POST.get("user_id", "").strip()
    image_path = request.POST.get("image_path", "").strip()
    order_id = request.POST.get("order_id", "").strip()

    if not image_path:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image_path(图片路径)")
    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.upload_image_in_comment(token, user_id, image_path, order_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 号主信息 ====================


@require_http_methods(["GET"])
def owner_info_view(request):
    """获取订单的号主信息（游戏名称 / 客户端 / 游戏账号 / 密码 / 角色名 / 号主联系方式 / 剩余时间）

    参数:
        order_id (必填): 订单ID
        user_id  (选填): 用户ID；不传则用后台「账号管理」的默认代练通账号
        token    (选填): 登录令牌；不传则用后台默认账号的令牌

    说明：账号 / 密码 / 角色名只有**接单方**可见，故需先在代练通接单后再调用。
    """
    order_id = request.GET.get("order_id", "").strip()
    if not order_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: order_id(订单ID)")

    ok, data = utils.get_owner_info(order_id,
                                    request.GET.get("user_id", "").strip(),
                                    request.GET.get("token", "").strip())
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


# ==================== 头像模块 ====================


@require_http_methods(["POST"])
def upload_avatar_view(request):
    """上传头像（无需 token）

    参数:
        user_id    (选填): 用户ID；不传则用后台默认账号
        image_path (必填): 图片URL路径
    """
    user_id = request.POST.get("user_id", "").strip()
    image_path = request.POST.get("image_path", "").strip()
    if not image_path:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image_path(图片路径)")

    ok, data = utils.upload_avatar(user_id, image_path)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 游戏模块 ====================


@require_http_methods(["GET"])
def games_view(request):
    """获取全部游戏（含各自的公开订单数量）

    无需请求参数，服务端匿名调用上游；对外仍需项目签名。

    返回 data 为游戏数组（按订单数从多到少），每项含:
        game_id     - 游戏ID
        game_name   - 游戏名称
        order_count - 当前可接的公开订单数量
    """
    ok, data = utils.get_games()
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# 订单列表筛选项的允许取值（与代练通「筛选」面板对齐，供视图校验）
_TIER_VALUES = ('青铜', '白银', '黄金', '铂金', '钻石', '星耀', '王者')   # 段位（不限用空串）
_ORDER_TYPE_VALUES = ('10', '13', '15', '1920')                          # 订单类型（不限用空串）
_SORT_VALUES = ('Price_DESC', 'Price_ASC', 'SettleHour_ASC', 'Ensure_ASC',
                'TimeLimit_DESC', 'PubCancelRate_ASC')                   # 排序（不限用空串）


@require_http_methods(["GET"])
def games_orders_view(request):
    """按游戏ID获取该游戏的公开订单列表（分页 + 多条件筛选）

    参数:
        game_id     (必填): 游戏ID
        page        (选填): 页码，默认 1
        page_size   (选填): 每页数量，默认 20，1-100
        pg_type     (选填): 区服，0=全部 1=安卓 2=IOS，默认 0
        order_type  (选填): 订单类型，空=不限 / 10=5V5排位赛 / 13=巅峰赛 / 15=荣耀战力 / 1920=国标
        start_tier  (选填): 初始段位，空=不限 / 青铜/白银/黄金/铂金/钻石/星耀/王者
        end_tier    (选填): 目标段位，取值同 start_tier
        price_str   (选填): 价格区间（最低_最高，如 1_20），空=不限
        pub_cancel  (选填): 仲裁介入率上限(%)，0=不限 / 10 / 20 / 30 / 50，默认 0
        settle_hour (选填): 结算时间上限(小时)，0=不限 / 6 / 12 / 24 / 48，默认 0
        filter_type (选填): 只看本账号可接手的订单，1=是（默认） / 0=否
        sort_str    (选填): 排序，空=平台默认 / Price_DESC 价格最高 / Price_ASC 价格最低 /
                            SettleHour_ASC 验收最快 / Ensure_ASC 保证金最少 /
                            TimeLimit_DESC 总时限最长 / PubCancelRate_ASC 介入率最低
        search_str  (选填): 关键词；对王者荣耀等游戏即「指定英雄」（多个英雄名用空格分隔）
        user_id     (选填): 代练通账号ID；与 token 一起传才按登录态筛选；不传则用后台默认账号
        token       (选填): 代练通登录令牌；与 user_id 配对；不传则用后台默认账号的令牌

    返回 data 为分页对象，含 items / total / page / page_size / total_pages。
    说明：user_id / token 未同时提供时，自动回落到后台「账号管理」(/console/accounts/) 的默认代练通账号；
          都没有时按匿名调用 —— 此时仅 search_str（关键词/指定英雄）与 pg_type（区服）筛选生效，
          filter_type（只看可接手）与段位/订单类型等账号相关筛选需要登录态。
    """
    game_id = request.GET.get('game_id', '').strip()
    if not game_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: game_id(游戏ID)")
    if not game_id.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: game_id 必须为正整数")

    try:
        page = int(request.GET.get('page', '1'))
        page_size = int(request.GET.get('page_size', '20'))
        pg_type = int(request.GET.get('pg_type', '0'))
        filter_type = int(request.GET.get('filter_type', '1'))
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg="参数格式错误: page/page_size/pg_type/filter_type 必须为整数")

    if page < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page 必须大于 0")
    if page_size < 1 or page_size > 100:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page_size 必须在 1-100 之间")
    if pg_type not in (0, 1, 2):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: pg_type 仅支持 0/1/2")
    if filter_type not in (0, 1):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: filter_type 仅支持 0/1")

    pub_cancel, err = _get_int(request.GET, 'pub_cancel', 0)
    if err:
        return err
    settle_hour, err = _get_int(request.GET, 'settle_hour', 0)
    if err:
        return err

    # 枚举筛选（空串=不限；"不限" 归一为空串）
    enum_values = {}
    for name, allowed in (('order_type', _ORDER_TYPE_VALUES),
                          ('start_tier', _TIER_VALUES),
                          ('end_tier', _TIER_VALUES),
                          ('sort_str', _SORT_VALUES)):
        value = request.GET.get(name, '').strip()
        if value == '不限':
            value = ''
        if value and value not in allowed:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=f"参数值非法: {name} 取值不在允许范围")
        enum_values[name] = value

    user_id_raw = request.GET.get('user_id', '').strip()
    if user_id_raw and not user_id_raw.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: user_id 必须为数字")

    ok, data = utils.get_game_orders(
        game_id=int(game_id), page=page, page_size=page_size, pg_type=pg_type,
        order_type=enum_values['order_type'],
        start_tier=enum_values['start_tier'], end_tier=enum_values['end_tier'],
        price_str=request.GET.get('price_str', '').strip(),
        pub_cancel=pub_cancel, settle_hour=settle_hour,
        filter_type=filter_type, sort_str=enum_values['sort_str'],
        search_str=request.GET.get('search_str', '').strip(),
        user_id=int(user_id_raw) if user_id_raw else 0,
        token=request.GET.get('token', '').strip(),
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 搜索模块 ====================

# 搜索接口各整数参数的默认值（对齐官网「搜索」页：优选订单池 9 / 苹果 2 / FilterType 0）
_SEARCH_INT_DEFAULTS = (
    ('is_pub', 9), ('pg_type', 2), ('zone_id', 0), ('server_id', 0),
    ('pub_cancel', 0), ('settle_hour', 0), ('filter_type', 0), ('focused', -1),
    ('order_type', 0), ('pub_recommend', 0), ('score1', 0), ('score2', 0),
    ('page', 1), ('page_size', 20),
)


@require_http_methods(["GET"])
def search_orders_view(request):
    """按关键词搜索订单（参数对齐官网搜索页，可高度自定义）

    参数:
        game_id       (必填): 游戏ID
        search_str    (选填): 搜索关键词（如「马可波罗」「安琪拉」）
        is_pub        (选填): 订单池，默认 9（对齐官网搜索）
        pg_type       (选填): 区服，0=全部 1=安卓 2=IOS，默认 2
        zone_id       (选填): 大区ID，默认 0
        server_id     (选填): 服务器ID，默认 0
        level_type2   (选填): 订单类型（上游 LevelType2），空=不限
        stier         (选填): 初始段位，空=不限
        etier         (选填): 目标段位，空=不限
        price_str     (选填): 价格区间（最低_最高），空=不限
        pub_cancel    (选填): 仲裁介入率上限(%)，默认 0
        settle_hour   (选填): 结算时间上限(小时)，默认 0
        filter_type   (选填): 只看本账号可接手，1=是 0=否，默认 0
        sort_str      (选填): 排序，空=默认
        focused       (选填): 关注筛选，默认 -1
        order_type    (选填): 上游 OrderType，默认 0
        pub_recommend (选填): 上游 PubRecommend，默认 0
        score1/score2 (选填): 上游评分筛选位，默认 0
        page          (选填): 页码，默认 1
        page_size     (选填): 每页数量，默认 20，1-100
        user_id/token (选填): 登录态；不传则用后台「账号管理」的默认代练通账号

    返回 data 为分页对象，含 items / total / page / page_size / total_pages。
    """
    game_id = request.GET.get('game_id', '').strip()
    if not game_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: game_id(游戏ID)")
    if not game_id.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: game_id 必须为正整数")

    int_params = {}
    for name, default in _SEARCH_INT_DEFAULTS:
        value, err = _get_int(request.GET, name, default)
        if err:
            return err
        int_params[name] = value

    if int_params['page'] < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page 必须大于 0")
    if int_params['page_size'] < 1 or int_params['page_size'] > 100:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: page_size 必须在 1-100 之间")

    user_id_raw = request.GET.get('user_id', '').strip()
    if user_id_raw and not user_id_raw.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: user_id 必须为数字")

    ok, data = utils.search_orders(
        game_id=int(game_id),
        search_str=request.GET.get('search_str', '').strip(),
        level_type2=request.GET.get('level_type2', '').strip(),
        stier=request.GET.get('stier', '').strip(),
        etier=request.GET.get('etier', '').strip(),
        price_str=request.GET.get('price_str', '').strip(),
        sort_str=request.GET.get('sort_str', '').strip(),
        user_id=int(user_id_raw) if user_id_raw else 0,
        token=request.GET.get('token', '').strip(),
        **int_params,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


@require_http_methods(["GET"])
def hot_search_words_view(request):
    """获取某游戏的热门搜索词

    参数:
        game_id (必填): 游戏ID

    返回 data 为 {"words": [词...], "tip": 说明文字}。
    """
    game_id = request.GET.get('game_id', '').strip()
    if not game_id:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: game_id(游戏ID)")
    if not game_id.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: game_id 必须为正整数")

    ok, data = utils.get_hot_search_words(int(game_id))
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)


# ==================== 发布模块 ====================


@require_http_methods(["POST"])
def publish_order_view(request):
    """发布订单（自定义发布）

    参数:
        title            (必填): 订单标题（建议写明「指定单」等规则，避免私接）
        price            (必填): 订单价格（元）
        time_limit       (必填): 代练时限（小时）
        ensure1          (选填): 安全保证金（元），默认 0
        ensure2          (选填): 效率保证金（元），默认 0
        game_mobile      (必填): 号主联系方式
        game_account     (必填): 游戏账号
        game_password    (必填): 游戏密码
        game_author_name (必填): 游戏角色名
        requirements     (必填): 代练要求（写入订单详情）
        pay_pass         (选填): 支付密码（原密码；服务端按 md5(md5(pwd)+uid) 处理）
        uid              (选填): 账号 UID（USR 开头，支付密码哈希用）；不传则用后台默认账号
        game_id          (选填): 游戏ID；用于自动定位区服（如 107=王者荣耀）
        zone_type        (选填): 大区名（如 安卓QQ / 苹果微信 / 官服）；配合 game_id 自动定位区服
        zone_server_id   (选填): 区服ID（高级，直接指定）；留空则按 game_id + zone_type 自动定位
        level_type2      (选填): 订单类型（上游 LevelType2），默认 14
        game_extra       (选填): Actors 第 4 段；按游戏取默认（王者荣耀=铭文等级 150，三角洲行动=空）
        mobile / qq      (选填): 发单者联系方式
        insurance / max_claim_amount / order_type (选填): 上游字段（max_claim_amount 默认 20，含义见文档）
        user_id / token  (选填): 登录态；不传则用后台默认账号

    返回 data 为上游发布结果（含订单信息，字段由上游定义）。
    """
    required = {
        'title': '订单标题', 'game_mobile': '号主联系方式',
        'game_account': '游戏账号', 'game_password': '游戏密码',
        'game_author_name': '游戏角色名', 'requirements': '代练要求',
    }
    values = {}
    for name, label in required.items():
        value = (request.POST.get(name) or '').strip()
        if not value:
            return _json_response(StatusCode.PARAM_MISSING, msg=f"参数缺失: {name}({label})")
        values[name] = value

    price, err = _get_number(request.POST, 'price', None)
    if err:
        return err
    if price is None:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: price(订单价格)")
    time_limit, err = _get_number(request.POST, 'time_limit', None)
    if err:
        return err
    if time_limit is None:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: time_limit(代练时限)")

    ensure1, err = _get_number(request.POST, 'ensure1', 0)
    if err:
        return err
    ensure2, err = _get_number(request.POST, 'ensure2', 0)
    if err:
        return err
    insurance, err = _get_int(request.POST, 'insurance', 0)
    if err:
        return err
    max_claim_amount, err = _get_int(request.POST, 'max_claim_amount', 20)
    if err:
        return err
    order_type, err = _get_int(request.POST, 'order_type', 0)
    if err:
        return err
    game_id, err = _get_int(request.POST, 'game_id', 0)
    if err:
        return err

    user_id_raw = (request.POST.get('user_id') or '').strip()
    if user_id_raw and not user_id_raw.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: user_id 必须为数字")

    ok, data = utils.publish_order(
        title=values['title'], price=price, time_limit=time_limit,
        ensure1=ensure1, ensure2=ensure2, game_mobile=values['game_mobile'],
        game_account=values['game_account'], game_password=values['game_password'],
        game_author_name=values['game_author_name'], requirements=values['requirements'],
        pay_pass=(request.POST.get('pay_pass') or '').strip(),
        uid=(request.POST.get('uid') or '').strip(),
        game_id=game_id,
        zone_type=(request.POST.get('zone_type') or '').strip(),
        zone_server_id=(request.POST.get('zone_server_id') or '').strip(),
        level_type2=(request.POST.get('level_type2') or '').strip(),
        game_extra=(request.POST.get('game_extra') or '').strip(),
        mobile=(request.POST.get('mobile') or '').strip(),
        qq=(request.POST.get('qq') or '').strip(),
        insurance=insurance, max_claim_amount=max_claim_amount, order_type=order_type,
        user_id=int(user_id_raw) if user_id_raw else 0,
        token=(request.POST.get('token') or '').strip(),
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _spider_result(data)
