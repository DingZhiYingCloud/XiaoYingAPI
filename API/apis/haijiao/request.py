"""海角社区 API 请求处理视图

提供接口:
    GET    /api/haijiao/domain         今日域名（今日大陆可访问域名 / 备用 / 海外 / 影视站域名 + 客服邮箱）
    GET    /api/haijiao/topics         内容列表（tab 选模块：热帖/新闻/大事记/原创/精华/最新）
    GET    /api/haijiao/search         搜索（type 选范围，目前仅支持帖子）
    GET    /api/haijiao/topic/detail   帖子详情（正文 / 原图 / 视频附件 / 互动数据）
    GET    /api/haijiao/topic/comments 帖子评论列表（分页，可按「只看楼主」筛选）
    GET    /api/haijiao/comment/replies 二级评论列表（某条主评论下的子评论，分页）
    GET    /api/haijiao/topic/nodes    板块列表（发帖选板块用，含层级）
    GET    /api/haijiao/topic/tags     标签池（分页）
    POST   /api/haijiao/topic/upload   上传发帖媒体（图片 / 视频，multipart）
    POST   /api/haijiao/topic/create   发帖（标题 / 正文 / 板块 / 标签 / 媒体嵌入）
    GET    /api/haijiao/topic/mine     我的帖子（审核通过 / 审核中 / 审核失败）
    GET    /api/haijiao/gift/list      礼物列表（打赏挑礼物用：金币 / 钻石礼物）
    GET    /api/haijiao/topic/give     给帖子送金币（打赏，不传礼物则用最便宜的）
    GET    /api/haijiao/user/follow    关注 / 取消关注用户（个人主页的关注按钮）
    POST   /api/haijiao/user/follow/batch 批量关注 / 取关（让库内全部有 token 的账号都执行）
    GET    /api/haijiao/ranking        排行榜（粉丝 / 点赞 / 人气 × 总榜 / 月榜 / 周榜）
    GET    /api/haijiao/user/info      用户主页信息（昵称 / 头像 / 粉丝数 / 是否已关注）
    GET    /api/haijiao/user/wealth    当前账号余额（金币 / 钻石）
    GET    /api/haijiao/user/wealth/log 金币 / 钻石流水（分页）
    GET    /api/haijiao/user/following 我关注的人
    GET    /api/haijiao/user/fans      我的粉丝（分页）
    GET    /api/haijiao/topic/like/state 查询当前账号是否已点赞
    POST   /api/haijiao/topic/like     给帖子点赞 / 取消点赞
    POST   /api/haijiao/topic/like/batch 批量点赞 / 取关（让库内全部账号都执行）
    GET    /api/haijiao/topic/liked    我点赞过的帖子（分页）
    GET    /api/haijiao/favorite/folders 我的收藏夹列表（收藏页左侧）
    GET    /api/haijiao/favorite/topics  我收藏的帖子（分页，可按收藏夹筛选）
    POST   /api/haijiao/favorite/add     收藏帖子到收藏夹
    POST   /api/haijiao/favorite/delete  取消收藏帖子
    POST   /api/haijiao/favorite/delete/batch 批量取消收藏（逐条串行，单次最多 50 个）
    POST   /api/haijiao/favorite/folder/add 新建收藏夹
    POST   /api/haijiao/favorite/folder/rename 重命名收藏夹
    POST   /api/haijiao/favorite/folder/delete 删除收藏夹（要求夹内为空）
    GET    /api/haijiao/image          图片解码（返回真实图片二进制，可直接 <img> 引用）
    GET    /api/haijiao/video/m3u8     视频播放列表（m3u8 文本，已还原真密钥，可直接播放）
    POST   /api/haijiao/register/captcha  取注册验证码（两步式注册第一步，可选走代理）
    POST   /api/haijiao/register/credentials 生成一组注册账号凭据（一键填写 / 自行批量注册用）
    POST   /api/haijiao/register/batch    批量注册（凭据服务端自动生成，用户名统一 xy_ 前缀）
    POST   /api/haijiao/register          提交注册（两步式注册第二步，成功后账号入库）
    POST   /api/haijiao/login             账号登录（直传账号密码，或按 account_id 取库内账号）
    POST   /api/haijiao/sign-in           金币签到（按 account_id 取库内账号，或直传 user_id + user_token）
    POST   /api/haijiao/sign-in/batch     一键签到全部账号（账号表内所有有 token 的账号逐个签到）
    GET    /api/haijiao/accounts          账号列表（分页 / 关键词搜索 / 可选返回密码）
    POST   /api/haijiao/accounts          新增账号
    GET    /api/haijiao/accounts/<uuid>   账号详情（含 token，可选返回密码）
    PATCH  /api/haijiao/accounts/<uuid>   更新账号
    DELETE /api/haijiao/accounts/<uuid>   删除账号

签名参数（app_id/timestamp/nonce/sign）由 ApiAuthMiddleware 统一校验，视图不重复处理。
"""
import base64
import json
import re
import uuid

from django.http import HttpResponse, JsonResponse, QueryDict
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.common.url_safety import check_public_http_url
from . import utils

# 可选的内容模块（与源站首页栏目一一对应）
TABS = ('hot', 'news', 'events', 'original', 'essence', 'latest')

# 搜索范围（源站搜索页另有用户 / 标签 / 站内视频等范围，当前仅开放帖子搜索）
SEARCH_TYPES = {'1': '帖子'}

# 评论筛选（与源站评论区的「看全部 / 看楼主」两个 tab 一致）
COMMENT_SEARCH_TYPES = {'0': '全部', '1': '只看楼主'}

# 帖子类型（源站发帖表单的「普通 / 出售 / 悬赏」）
TOPIC_TYPES = (0, 1, 2)

# 我的帖子：审核状态（对外的语义化取值 -> 源站 status 码，取自源站 /post/release 页三个 tab）
MY_TOPIC_STATUSES = {'published': 3, 'pending': 2, 'rejected': 4}

# 打赏：礼物类型（源站礼物弹窗的两个 tab）与单次赠送数量上限（源站前端限制 1~99）
GIFT_KINDS = ('gold', 'diamond')
GIVE_MAX_QUANTITY = 99

# 关注动作（源站个人主页「关注」按钮只回状态，这里对外语义化为 follow / unfollow）
FOLLOW_ACTIONS = {'follow': True, 'unfollow': False}

# 点赞动作（源站 body 里收的是「点赞后的目标状态」status，这里对外语义化为 like / unlike）
LIKE_ACTIONS = {'like': True, 'unlike': False}

# 钱包流水类型（源站金币 / 钻石是两套流水接口）
WEALTH_KINDS = ('gold', 'diamond')

# 排行榜维度（对外的语义化取值 -> 名称）：源站首页榜单另有消费榜 consume，本服务未开放
RANKING_BOARDS = {'fans': '粉丝', 'liked': '点赞', 'wealth': '人气'}
# 排行榜周期（对外取值 -> (源站 type, 名称)）：源站用 all / 30 / 7 区分总榜 / 月榜 / 周榜
RANKING_PERIODS = {'all': ('all', '总榜'), 'month': (30, '月榜'), 'week': (7, '周榜')}

# 图片解码结果必须是 data URI（形如 data:image/jpeg;base64,...），否则视为非法
_DATA_URI_RE = re.compile(r'^data:(image/[\w.+-]+);base64,(.+)$', re.S)

# 布尔型表单参数取值
_TRUE_VALUES = ('true', '1', 'yes', 'y')
_FALSE_VALUES = ('false', '0', 'no', 'n')


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体
    :param code: 状态码(参见 StatusCode)
    :param data: 业务数据,默认为 None
    :param msg:  自定义消息,未传则使用状态码对应的默认描述
    """
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _require_int(raw, name, minimum=0):
    """解析必填整数参数

    :return: (值, 错误响应)；正常时错误响应为 None
    """
    if not raw:
        return None, _json_response(StatusCode.PARAM_MISSING, msg=f'参数缺失: {name}')
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg=f'参数格式错误: {name} 必须为整数')
    if minimum is not None and value < minimum:
        return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                    msg=f'参数值非法: {name} 必须 >= {minimum}')
    return value, None


def _parse_flag(raw, name, default=False):
    """解析布尔型参数（true/1/yes/y 为真，false/0/no/n 为假，不传取默认值）

    :return: (布尔值, 错误响应)；正常时错误响应为 None
    """
    value = (raw or '').strip().lower()
    if value == '':
        return default, None
    if value in _TRUE_VALUES:
        return True, None
    if value in _FALSE_VALUES:
        return False, None
    return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                msg=f'参数值非法: {name} 仅支持 true / false')


def _error_response(msg, fallback=StatusCode.PARAM_VALUE_INVALID):
    """按业务错误消息映射状态码（统一口径，见 StatusCode.from_message）"""
    return _json_response(StatusCode.from_message(msg, fallback=fallback), msg=msg)


def _parse_body(request):
    """解析 x-www-form-urlencoded 表单请求体

    注意：Django 的 request.POST 仅自动解析 POST 方法，PATCH 等需手动从 request.body 解析。
    :return: (参数字典, 错误信息)；正常时错误信息为 None
    """
    if request.method == 'POST':
        qd = request.POST
    elif request.body:
        try:
            qd = QueryDict(request.body.decode('utf-8'))
        except Exception as e:      # noqa: BLE001 - 解析失败按参数格式错误返回
            return None, f'表单解析失败: {e}'
    else:
        return {}, None
    return qd.dict(), None


def _parse_page(request):
    """解析 page 参数（可选，默认 1）

    :return: (page, 错误响应)；正常时错误响应为 None
    """
    raw = request.GET.get('page', '').strip()
    if not raw:
        return 1, None
    try:
        page = int(raw)
    except (TypeError, ValueError):
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg='参数格式错误: page 必须为整数')
    if page < 1:
        return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                    msg='参数值非法: page 必须 >= 1')
    return page, None


def _parse_folder_id(raw, default=None):
    """解析可选的 folder_id 参数（收藏夹 ID，不传取 default）

    :return: (值, 错误响应)；正常时错误响应为 None
    """
    raw = (raw or '').strip()
    if not raw:
        return default, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg='参数格式错误: folder_id 必须为整数')
    if value < 0:
        return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                    msg='参数值非法: folder_id 必须 >= 0')
    return value, None


def _parse_folder_name(raw):
    """解析收藏夹名称（必填；源站规则：1-12 位字符）

    :return: (名称, 错误响应)；正常时错误响应为 None
    """
    name = (raw or '').strip()
    if not name:
        return None, _json_response(StatusCode.PARAM_MISSING,
                                    msg='参数缺失: folder_name(收藏夹名称)')
    if len(name) > utils.FAVORITE_FOLDER_NAME_MAX:
        return None, _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: folder_name 最长为 {utils.FAVORITE_FOLDER_NAME_MAX} 位字符')
    return name, None


@require_http_methods(['GET'])
def domain_view(request):
    """
    获取今日域名配置。

    无参数：返回源站当日公布的可用域名与客服邮箱（源站首页弹窗「今日大陆直接访问网址为: xxx」
    提示的就是其中的 domain）。
    """
    ok, data = utils.get_domain_config()
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topics_view(request):
    """
    获取内容列表。

    查询参数:
        tab  (可选): 模块，hot 热帖 / news 新闻 / events 大事记 / original 原创 /
                     essence 精华 / latest 最新，默认 hot
        page (可选): 页码，从 1 开始，默认 1（源站每页 20 条）
    """
    tab = request.GET.get('tab', '').strip() or 'hot'
    if tab not in TABS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: tab 仅支持 {" / ".join(TABS)}')

    page, err = _parse_page(request)
    if err:
        return err

    ok, data = utils.get_topics(tab=tab, page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def search_view(request):
    """
    搜索帖子。

    查询参数:
        key     (必填): 搜索关键词
        type    (可选): 搜索范围，目前仅支持 1（帖子），默认 1
        node_id (可选): 板块 ID，0 表示不限板块，默认 0
        page    (可选): 页码，从 1 开始，默认 1（源站每页 20 条）
    """
    key = request.GET.get('key', '').strip()
    if not key:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: key(搜索关键词)')

    type_raw = request.GET.get('type', '').strip() or '1'
    if type_raw not in SEARCH_TYPES:
        supports = ' / '.join(f'{k}({v})' for k, v in SEARCH_TYPES.items())
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: type 仅支持 {supports}')

    node_id_raw = request.GET.get('node_id', '').strip()
    if node_id_raw:
        try:
            node_id = int(node_id_raw)
        except (TypeError, ValueError):
            return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                  msg='参数格式错误: node_id 必须为整数')
        if node_id < 0:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg='参数值非法: node_id 必须 >= 0')
    else:
        node_id = 0

    page, err = _parse_page(request)
    if err:
        return err

    ok, data = utils.search_topics(key, page=page, node_id=node_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_detail_view(request):
    """
    获取帖子详情。

    查询参数:
        topic_id   (必填): 帖子 ID（取自内容列表 results[].topic_id）
        user_id    (可选): 覆盖默认登录凭据的账号 ID，需与 user_token 成对提供
        user_token (可选): 覆盖默认登录凭据的登录 token
    """
    topic_id, err = _require_int(request.GET.get('topic_id', '').strip(),
                                 'topic_id(帖子ID，取自内容列表 results[].topic_id)')
    if err:
        return err

    # 可选的登录凭据覆盖（两者必须成对提交，避免半份凭据造成意料外的匿名/越权请求）
    user_id = request.GET.get('user_id', '').strip()
    user_token = request.GET.get('user_token', '').strip()
    if bool(user_id) != bool(user_token):
        return _json_response(StatusCode.PARAM_MISSING,
                              msg='参数缺失: user_id 与 user_token 必须成对提供')

    ok, data = utils.get_topic_detail(topic_id, user_id=user_id or None,
                                      user_token=user_token or None)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    # 附带可直接喂给 HLS 播放器的播放列表地址（真密钥由服务端还原，见 video_m3u8_view）
    for video in data['videos']:
        video['play_url'] = (f'/api/haijiao/video/m3u8'
                             f'?topic_id={data["topic_id"]}&attachment_id={video["id"]}')
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_comments_view(request):
    """
    获取帖子评论列表（分页）。

    查询参数:
        topic_id    (必填): 帖子 ID（取自内容列表 results[].topic_id）
        page        (可选): 页码，从 1 开始，默认 1（源站每页 20 条）
        search_type (可选): 0=全部（默认）/ 1=只看楼主
    """
    topic_id, err = _require_int(request.GET.get('topic_id', '').strip(),
                                 'topic_id(帖子ID，取自内容列表 results[].topic_id)')
    if err:
        return err

    page, err = _parse_page(request)
    if err:
        return err

    search_type = request.GET.get('search_type', '').strip() or '0'
    if search_type not in COMMENT_SEARCH_TYPES:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: search_type 仅支持 {" / ".join(sorted(COMMENT_SEARCH_TYPES))}')

    ok, data = utils.get_topic_comments(topic_id, page=page, search_type=int(search_type))
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def comment_replies_view(request):
    """
    获取某条主评论下的二级评论（子评论）列表。

    查询参数:
        comment_id (必填): 主评论 ID（评论列表 results[].comment_id）
        page       (可选): 页码，从 1 开始，默认 1（源站每页 20 条）
    """
    comment_id, err = _require_int(request.GET.get('comment_id', '').strip(),
                                   'comment_id(主评论ID，取自评论列表 results[].comment_id)')
    if err:
        return err

    page, err = _parse_page(request)
    if err:
        return err

    ok, data = utils.get_comment_replies(comment_id, page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_nodes_view(request):
    """
    获取板块列表（发帖选板块用，含层级 children）。

    无查询参数。返回 data.list 为顶层板块数组，每个板块含 node_id / name / children 等。
    """
    ok, data = utils.get_topic_nodes()
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_tags_view(request):
    """
    获取标签池（分页）。

    查询参数:
        page (可选): 页码，从 1 开始，默认 1（源站每页 20 条）

    注：源站该接口不支持关键词搜索，调用方可在本页结果里本地过滤。
    """
    page, err = _parse_page(request)
    if err:
        return err
    ok, data = utils.get_topic_tags(page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def topic_media_upload_view(request):
    """
    上传发帖用的图片 / 视频（multipart/form-data）。

    表单参数:
        file        (必填): 媒体文件（图片 png/jpg/jpeg/gif/bmp，单张 ≤10MB；视频 mp4）
        account_id  (可选): 库内账号 ID（与 user_id + user_token 二选一）
        user_id     (可选): 源站用户 ID
        user_token  (可选): 源站登录 token

    返回 data.attachment_id / data.category / data.url / data.html：
    html 是可直接拼接进发帖 content 的片段（图片为 <img>、视频为 <video> 占位）。
    """
    upload = request.FILES.get('file')
    if upload is None:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: file(媒体文件)')

    ok, data = utils.upload_topic_media(
        upload.name, upload.read(), upload.content_type,
        account_id=request.POST.get('account_id', '').strip() or None,
        user_id=request.POST.get('user_id', '').strip() or None,
        user_token=request.POST.get('user_token', '').strip() or None)
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='上传成功')


@require_http_methods(['POST'])
def topic_create_view(request):
    """
    发帖。

    表单参数:
        node_id      (必填): 板块 ID（取自「板块列表」叶子节点的 node_id）
        title        (必填): 标题（源站上限 36 字）
        content      (必填): 正文 HTML；图片 / 视频片段用「上传发帖媒体」返回的 data.html 拼接
        tags         (必填): 标签名，多个用逗号分隔（源站按名称关联，不存在的名称会被当作新标签）
        type         (可选): 0=普通（默认）1=出售 2=悬赏
        money_type   (可选): 0=金币（默认）1=钻石（仅出售 / 悬赏有意义）
        amount       (可选): 出售价格 / 悬赏金额，默认 0
        reward_hours (可选): 悬赏时长，72-240 的整数（仅悬赏）
        account_id   (可选): 库内账号 ID（与 user_id + user_token 二选一）
        user_id      (可选): 源站用户 ID
        user_token   (可选): 源站登录 token

    返回 data.topic_id（源站判定待审核时为空）与 data.pending。
    """
    body, err = _parse_body(request)
    if err:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
    if not body:
        return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')

    node_id, err = _require_int(str(body.get('node_id', '')).strip(),
                                'node_id(板块ID，取自板块列表)')
    if err:
        return err

    title = (body.get('title') or '').strip()
    content = (body.get('content') or '').strip()
    tags = [t.strip() for t in (body.get('tags') or '').replace('，', ',').split(',') if t.strip()]
    for name, value in (('title(标题)', title), ('content(正文)', content)):
        if not value:
            return _json_response(StatusCode.PARAM_MISSING, msg=f'参数缺失: {name}')
    if not tags:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: tags(标签名，多个用逗号分隔)')
    if len(title) > 36:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: title 最长为 36 字')

    topic_type, err = _require_int(str(body.get('type', '') or '0').strip(),
                                   'type(0=普通 1=出售 2=悬赏)')
    if err:
        return err
    if topic_type not in TOPIC_TYPES:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: type 仅支持 '
                                  + ' / '.join(str(t) for t in TOPIC_TYPES))

    money_type, err = _require_int(str(body.get('money_type', '') or '0').strip(),
                                   'money_type(0=金币 1=钻石)')
    if err:
        return err
    if money_type not in (0, 1):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: money_type 仅支持 0 / 1')

    amount, err = _require_int(str(body.get('amount', '') or '0').strip(), 'amount(价格/悬赏金额)')
    if err:
        return err

    reward_hours, err = _require_int(str(body.get('reward_hours', '') or '0').strip(),
                                     'reward_hours(悬赏时长)')
    if err:
        return err
    if reward_hours and not 72 <= reward_hours <= 240:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: reward_hours 需为 72-240 的整数')

    ok, data = utils.create_topic(
        node_id, title, content, tags,
        topic_type=topic_type, money_type=money_type, amount=amount, reward_hours=reward_hours,
        account_id=(body.get('account_id') or '').strip() or None,
        user_id=(body.get('user_id') or '').strip() or None,
        user_token=(body.get('user_token') or '').strip() or None)
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    msg = '发布成功，待审核通过后即可查看' if data['pending'] else f'发帖成功，帖子 ID: {data["topic_id"]}'
    return _json_response(StatusCode.SUCCESS, data=data, msg=msg)


@require_http_methods(['GET'])
def topic_mine_view(request):
    """
    我的帖子（查看自己账号「发布成功 / 审核中 / 审核失败」的帖子）。

    查询参数:
        status     (可选): published=审核通过（默认）/ pending=审核中 / rejected=审核失败
        page       (可选): 页码，从 1 开始，默认 1（源站每页 10 条）
        account_id (可选): 库内账号 ID（与 user_id + user_token 二选一）
        user_id    (可选): 源站用户 ID
        user_token (可选): 源站登录 token

    返回 data.status（与请求一致的语义化取值）、data.pagination 与 data.results。
    审核通过 / 审核中的条目才有 topic_id；审核失败的有 pending_id 与失败原因 remarks。
    """
    status = request.GET.get('status', '').strip() or 'published'
    if status not in MY_TOPIC_STATUSES:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: status 仅支持 ' + ' / '.join(MY_TOPIC_STATUSES))

    page, err = _parse_page(request)
    if err:
        return err

    ok, data = utils.get_my_topics(
        MY_TOPIC_STATUSES[status], page=page,
        account_id=request.GET.get('account_id', '').strip() or None,
        user_id=request.GET.get('user_id', '').strip() or None,
        user_token=request.GET.get('user_token', '').strip() or None)
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    data['status'] = status
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def gift_list_view(request):
    """
    礼物列表（打赏时挑礼物用）。

    查询参数:
        kind (可选): gold=金币礼物（默认）/ diamond=钻石礼物
        page (可选): 页码，从 1 开始，默认 1

    返回 data.results[]：item_id（礼物 ID，打赏时传它）、name、desc、kind、
    money_type（1=金币 2=钻石）、price（原价）、sale_price（实际单价）、img 等。
    """
    kind = request.GET.get('kind', '').strip() or 'gold'
    if kind not in GIFT_KINDS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: kind 仅支持 ' + ' / '.join(GIFT_KINDS))

    page, err = _parse_page(request)
    if err:
        return err

    ok, data = utils.get_gift_list(kind=kind, page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_give_view(request):
    """
    给帖子送金币（打赏）：给帖子作者赠送一份礼物，不传礼物则用该类型里最便宜的。

    查询参数:
        topic_id   (必填): 帖子 ID
        item_id    (可选): 礼物 ID（取自「礼物列表」的 item_id），不传则自动选最便宜的礼物
        quantity   (可选): 赠送数量，默认 1（源站限制 1~99）
        kind       (可选): gold=金币礼物（默认）/ diamond=钻石礼物
        account_id (可选): 库内账号 ID（与 user_id + user_token 二选一）
        user_id    (可选): 源站用户 ID
        user_token (可选): 源站登录 token

    返回 data：topic_id / item（所赠礼物）/ quantity / total_cost（本次花费）/
    receiver（收礼的帖子作者）/ money（赠送后余额）。
    """
    topic_id, err = _require_int(request.GET.get('topic_id', '').strip(), 'topic_id(帖子ID)')
    if err:
        return err

    item_id = None
    raw_item_id = request.GET.get('item_id', '').strip()
    if raw_item_id:
        item_id, err = _require_int(raw_item_id, 'item_id(礼物ID)')
        if err:
            return err

    quantity = 1
    raw_quantity = request.GET.get('quantity', '').strip()
    if raw_quantity:
        quantity, err = _require_int(raw_quantity, 'quantity(赠送数量)', minimum=1)
        if err:
            return err
        if quantity > GIVE_MAX_QUANTITY:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg=f'参数值非法: quantity 必须 <= {GIVE_MAX_QUANTITY}')

    kind = request.GET.get('kind', '').strip() or 'gold'
    if kind not in GIFT_KINDS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: kind 仅支持 ' + ' / '.join(GIFT_KINDS))

    ok, data = utils.give_topic_gift(
        topic_id, item_id=item_id, quantity=quantity, kind=kind,
        account_id=request.GET.get('account_id', '').strip() or None,
        user_id=request.GET.get('user_id', '').strip() or None,
        user_token=request.GET.get('user_token', '').strip() or None)
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    unit = '金币' if kind == 'gold' else '钻石'
    return _json_response(
        StatusCode.SUCCESS, data=data,
        msg=f'打赏成功：{data["item"]["name"]} ×{data["quantity"]}，花费 {data["total_cost"]} {unit}')


@require_http_methods(['GET'])
def user_follow_view(request):
    """
    关注 / 取消关注某个用户（源站个人主页的「关注」按钮）。

    查询参数:
        target_user_id (必填): 目标用户 ID（个人主页 /homepage/<user_id> 里的那段数字）
        action         (可选): follow=关注（默认）/ unfollow=取消关注
        account_id     (可选): 库内账号 ID（与 user_id + user_token 二选一）
        user_id        (可选): 源站用户 ID（发起关注的那个账号）
        user_token     (可选): 源站登录 token

    返回 data：target_user_id / action / followed（操作后的关注状态）。
    """
    target_user_id, err = _require_int(request.GET.get('target_user_id', '').strip(),
                                       'target_user_id(目标用户ID)', minimum=1)
    if err:
        return err

    action = request.GET.get('action', '').strip() or 'follow'
    if action not in FOLLOW_ACTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: action 仅支持 ' + ' / '.join(FOLLOW_ACTIONS))

    ok, data = utils.set_follow(
        target_user_id, follow=FOLLOW_ACTIONS[action],
        account_id=request.GET.get('account_id', '').strip() or None,
        user_id=request.GET.get('user_id', '').strip() or None,
        user_token=request.GET.get('user_token', '').strip() or None)
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data,
                          msg='关注成功' if data['followed'] else '已取消关注')


@require_http_methods(['POST'])
def follow_batch_view(request):
    """
    批量关注 / 取消关注：让账号库里**全部有 token 的账号**都去关注（或取关）同一个目标用户。

    表单参数:
        target_user_id (必填): 目标用户 ID（个人主页 /homepage/<user_id> 里的那段数字）
        action         (可选): follow=关注（默认）/ unfollow=取消关注

    串行逐个执行（避免瞬时并发触发源站风控），单个账号失败不影响其它账号：
    成功计入 success_count、已是目标状态计入 already_count、目标就是账号自己的计入
    skipped_count、其余计入 failed_count，逐账号明细见 data.items。
    """
    target_user_id, err = _require_int(request.POST.get('target_user_id', '').strip(),
                                       'target_user_id(目标用户ID)', minimum=1)
    if err:
        return err

    action = request.POST.get('action', '').strip() or 'follow'
    if action not in FOLLOW_ACTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: action 仅支持 ' + ' / '.join(FOLLOW_ACTIONS))

    ok, data = utils.set_follow_batch(target_user_id, follow=FOLLOW_ACTIONS[action])
    if not ok:
        return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
    return _json_response(
        StatusCode.SUCCESS, data=data,
        msg=f'批量{"关注" if data["action"] == "follow" else "取关"}完成：'
            f'成功 {data["success_count"]} / 无需操作 {data["already_count"]}'
            f' / 跳过 {data["skipped_count"]} / 失败 {data["failed_count"]}'
            f' / 共 {data["total"]} 个账号')


@require_http_methods(['GET'])
def ranking_view(request):
    """
    排行榜（源站首页「排行榜」模块）：粉丝榜 / 点赞榜 / 人气榜，各含总榜 / 月榜 / 周榜。

    查询参数:
        board  (可选): fans=粉丝（默认）/ liked=点赞 / wealth=人气
        period (可选): all=总榜（默认）/ month=月榜 / week=周榜

    源站一次返回整张榜单（不翻页），返回 data：board / board_label / period / period_label /
    total / results（results[].value 为该榜单的数值：粉丝数 / 点赞数 / 人气值）。
    """
    board = request.GET.get('board', '').strip() or 'fans'
    if board not in RANKING_BOARDS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: board 仅支持 ' + ' / '.join(RANKING_BOARDS))

    period = request.GET.get('period', '').strip() or 'all'
    if period not in RANKING_PERIODS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: period 仅支持 ' + ' / '.join(RANKING_PERIODS))

    source_type, period_label = RANKING_PERIODS[period]
    ok, data = utils.get_ranking(key=board, type_value=source_type)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data={
        'board': board,
        'board_label': RANKING_BOARDS[board],
        'period': period,
        'period_label': period_label,
        'total': data['total'],
        'results': data['results'],
    })


def _credentials(params):
    """从查询串 / 表单里取登录凭据（account_id，或 user_id + user_token 成对）"""
    return {
        'account_id': params.get('account_id', '').strip() or None,
        'user_id': params.get('user_id', '').strip() or None,
        'user_token': params.get('user_token', '').strip() or None,
    }


@require_http_methods(['GET'])
def user_info_view(request):
    """
    用户主页信息（谁？多少人关注？我关注了没？）。

    查询参数:
        target_user_id (必填): 目标用户 ID（个人主页 /homepage/<user_id> 里的数字）
        account_id / user_id + user_token (可选): 带上才能正确返回 is_followed（我是否已关注 TA）

    返回 data：user_id / nickname / avatar / avatar_encrypted / description / fans_count /
    vip / famous / certified / is_followed / topic_count / video_count / comment_count /
    favorite_count / like_count。
    """
    target_user_id, err = _require_int(request.GET.get('target_user_id', '').strip(),
                                       'target_user_id(目标用户ID)', minimum=1)
    if err:
        return err
    ok, data = utils.get_user_info(target_user_id, **_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def user_wealth_view(request):
    """
    当前账号余额（金币 / 钻石）。

    查询参数: account_id / user_id + user_token（二选一，必填）
    返回 data：gold / diamond。
    """
    ok, data = utils.get_wealth(**_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def user_wealth_log_view(request):
    """
    金币 / 钻石流水（分页，最新在前）。

    查询参数:
        kind (可选): gold=金币（默认）/ diamond=钻石
        page (可选): 页码，从 1 开始，默认 1
        account_id / user_id + user_token（二选一，必填）

    返回 data.results[]：amount（正负表示收入 / 支出）、balance_after（变动后余额）、
    time、description。
    """
    kind = request.GET.get('kind', '').strip() or 'gold'
    if kind not in WEALTH_KINDS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: kind 仅支持 ' + ' / '.join(WEALTH_KINDS))
    page, err = _parse_page(request)
    if err:
        return err
    ok, data = utils.get_wealth_log(kind=kind, page=page, **_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def user_following_view(request):
    """
    我关注的人（源站一次返回全部、不翻页）。

    查询参数: account_id / user_id + user_token（二选一，必填）
    返回 data：total / results（用户名片数组，字段同「用户主页信息」）。
    """
    ok, data = utils.get_following(**_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def user_fans_view(request):
    """
    我的粉丝（分页）。

    查询参数:
        page (可选): 页码，从 1 开始，默认 1
        account_id / user_id + user_token（二选一，必填）

    返回 data：pagination / results（用户名片数组，字段同「用户主页信息」）。
    """
    page, err = _parse_page(request)
    if err:
        return err
    ok, data = utils.get_fans(page=page, **_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_like_state_view(request):
    """
    查询当前账号是否已给某帖子点赞（点赞前先查，避免重复提交）。

    查询参数:
        topic_id (必填): 帖子 ID
        account_id / user_id + user_token（二选一，必填）

    返回 data：topic_id / liked。
    """
    topic_id, err = _require_int(request.GET.get('topic_id', '').strip(), 'topic_id(帖子ID)')
    if err:
        return err
    ok, data = utils.get_like_state(topic_id, **_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def topic_like_view(request):
    """
    给帖子点赞 / 取消点赞（源站只在 body 里收「点赞后的目标状态」，故 action 是明确的动作）。

    表单参数:
        topic_id (必填): 帖子 ID
        action   (可选): like=点赞（默认）/ unlike=取消点赞
        account_id / user_id + user_token（二选一，必填）

    返回 data：topic_id / action / liked（操作后的状态）。
    """
    topic_id, err = _require_int(request.POST.get('topic_id', '').strip(), 'topic_id(帖子ID)')
    if err:
        return err
    action = request.POST.get('action', '').strip() or 'like'
    if action not in LIKE_ACTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: action 仅支持 ' + ' / '.join(LIKE_ACTIONS))
    ok, data = utils.set_topic_like(topic_id, like=LIKE_ACTIONS[action],
                                    **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data,
                          msg='点赞成功' if data['liked'] else '已取消点赞')


@require_http_methods(['POST'])
def like_batch_view(request):
    """
    批量点赞 / 取消点赞：让账号库里**全部账号**都给同一篇帖子点赞（或取消）。

    表单参数:
        topic_id (必填): 帖子 ID
        action   (可选): like=点赞（默认）/ unlike=取消点赞

    串行逐个执行（避免瞬时并发触发源站风控），单个账号失败不影响其它账号：
    成功计入 success_count、已是目标状态计入 already_count、账号没有 token 的计入
    skipped_count、其余计入 failed_count，逐账号明细见 data.items。
    """
    topic_id, err = _require_int(request.POST.get('topic_id', '').strip(), 'topic_id(帖子ID)')
    if err:
        return err
    action = request.POST.get('action', '').strip() or 'like'
    if action not in LIKE_ACTIONS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: action 仅支持 ' + ' / '.join(LIKE_ACTIONS))
    ok, data = utils.set_like_batch(topic_id, like=LIKE_ACTIONS[action])
    if not ok:
        return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
    return _json_response(
        StatusCode.SUCCESS, data=data,
        msg=f'批量{"点赞" if data["action"] == "like" else "取消点赞"}完成：'
            f'成功 {data["success_count"]} / 无需操作 {data["already_count"]}'
            f' / 跳过 {data["skipped_count"]} / 失败 {data["failed_count"]}'
            f' / 共 {data["total"]} 个账号')


@require_http_methods(['GET'])
def topic_liked_view(request):
    """
    我点赞过的帖子（分页）。

    查询参数:
        page (可选): 页码，从 1 开始，默认 1
        account_id / user_id + user_token（二选一，必填）

    返回 data：pagination / results（帖子数组，字段同「内容列表」）。
    """
    page, err = _parse_page(request)
    if err:
        return err
    ok, data = utils.get_liked_topics(page=page, **_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_favorite_folders_view(request):
    """
    我的收藏夹列表（「我的收藏」页左侧的收藏夹）。

    查询参数:
        account_id / user_id + user_token（二选一，必填）

    返回 data：total / results（folder_id / name / count）。
    """
    ok, data = utils.get_favorite_folders(**_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def topic_favorite_view(request):
    """
    我收藏的帖子（分页，可按收藏夹筛选）。

    查询参数:
        page      (可选): 页码，从 1 开始，默认 1
        folder_id (可选): 收藏夹 ID（取自「我的收藏夹」）；不传或传 0 = 全部收藏
        account_id / user_id + user_token（二选一，必填）

    返回 data：pagination / results（帖子数组，字段同「内容列表」）。
    """
    page, err = _parse_page(request)
    if err:
        return err

    folder_id, err = _parse_folder_id(request.GET.get('folder_id'),
                                      default=utils.FAVORITE_ALL_FOLDERS)
    if err:
        return err

    ok, data = utils.get_favorite_topics(page=page, folder_id=folder_id,
                                         **_credentials(request.GET))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def topic_favorite_add_view(request):
    """
    收藏帖子到收藏夹。

    表单参数:
        topic_id  (必填): 帖子 ID（取自内容列表 results[].topic_id）
        folder_id (可选): 目标收藏夹 ID（取自「我的收藏夹」）；不传或传 0 = 默认收藏夹
        account_id / user_id + user_token（二选一，必填）

    返回 data：topic_id / folder_id / action（add）。
    """
    topic_id, err = _require_int(request.POST.get('topic_id', '').strip(),
                                 'topic_id(帖子ID)', minimum=1)
    if err:
        return err
    folder_id, err = _parse_folder_id(request.POST.get('folder_id'),
                                      default=utils.FAVORITE_ALL_FOLDERS)
    if err:
        return err

    ok, data = utils.add_favorite(topic_id, folder_id=folder_id,
                                  **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='收藏成功')


@require_http_methods(['POST'])
def topic_favorite_delete_view(request):
    """
    取消收藏帖子。

    表单参数:
        topic_id (必填): 帖子 ID
        account_id / user_id + user_token（二选一，必填）

    返回 data：topic_id / action（remove）。
    """
    topic_id, err = _require_int(request.POST.get('topic_id', '').strip(),
                                 'topic_id(帖子ID)', minimum=1)
    if err:
        return err

    ok, data = utils.remove_favorite(topic_id, **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='已取消收藏')


@require_http_methods(['POST'])
def favorite_folder_create_view(request):
    """
    新建收藏夹。

    表单参数:
        folder_name (必填): 收藏夹名称（源站规则：1-12 位字符，同名会拒绝）
        account_id / user_id + user_token（二选一，必填）

    返回 data：folder_id / name / count（新建出来的收藏夹）。
    """
    folder_name, err = _parse_folder_name(request.POST.get('folder_name'))
    if err:
        return err

    ok, data = utils.create_favorite_folder(folder_name, **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='收藏夹已创建')


@require_http_methods(['POST'])
def favorite_folder_rename_view(request):
    """
    重命名收藏夹。

    表单参数:
        folder_id   (必填): 要重命名的收藏夹 ID（取自「我的收藏夹」）
        folder_name (必填): 新名称（源站规则：1-12 位字符，不可与已有收藏夹同名）
        account_id / user_id + user_token（二选一，必填）

    返回 data：folder_id / name / action（rename）。
    """
    folder_id, err = _require_int(request.POST.get('folder_id', '').strip(),
                                  'folder_id(收藏夹ID)', minimum=1)
    if err:
        return err
    folder_name, err = _parse_folder_name(request.POST.get('folder_name'))
    if err:
        return err

    ok, data = utils.rename_favorite_folder(folder_id, folder_name,
                                            **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='收藏夹已重命名')


@require_http_methods(['POST'])
def topic_favorite_delete_batch_view(request):
    """
    批量取消收藏（对同一账号逐条串行取消）。

    表单参数:
        topic_ids (必填): 帖子 ID，多个用逗号分隔（自动去重，单次最多 FAVORITE_BATCH_MAX 个）
        account_id / user_id + user_token（二选一，必填）

    返回 data：total / success_count / skipped_count / failed_count / items
    （items[].state: done=已取消 / skipped=本来就没收藏 / failed=失败）。
    """
    raw = (request.POST.get('topic_ids') or '').strip()
    if not raw:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg='参数缺失: topic_ids(帖子ID，多个用逗号分隔)')

    topic_ids, seen = [], set()
    for part in raw.replace('，', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except (TypeError, ValueError):
            return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                  msg=f'参数格式错误: topic_ids 含非整数项 {part}')
        if value < 1:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg=f'参数值非法: topic_ids 的每项必须 >= 1（收到 {value}）')
        if value not in seen:
            seen.add(value)
            topic_ids.append(value)

    if not topic_ids:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg='参数缺失: topic_ids(帖子ID，多个用逗号分隔)')
    if len(topic_ids) > utils.FAVORITE_BATCH_MAX:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: topic_ids 单次最多 {utils.FAVORITE_BATCH_MAX} 个')

    ok, data = utils.remove_favorite_batch(topic_ids, **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(
        StatusCode.SUCCESS, data=data,
        msg=f'批量取消收藏完成：成功 {data["success_count"]} / 本来就没收藏 '
            f'{data["skipped_count"]} / 失败 {data["failed_count"]}')


@require_http_methods(['POST'])
def favorite_folder_delete_view(request):
    """
    删除收藏夹（源站要求夹内为空，非空会拒绝）。

    表单参数:
        folder_id (必填): 收藏夹 ID（取自「我的收藏夹」）
        account_id / user_id + user_token（二选一，必填）

    返回 data：folder_id / action（delete）。
    """
    folder_id, err = _require_int(request.POST.get('folder_id', '').strip(),
                                  'folder_id(收藏夹ID)', minimum=1)
    if err:
        return err

    ok, data = utils.delete_favorite_folder(folder_id, **_credentials(request.POST))
    if not ok:
        return _error_response(data, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='收藏夹已删除')


@require_http_methods(['GET'])
def video_m3u8_view(request):
    """
    获取可直接播放的视频播放列表（m3u8 文本）。

    源站清单里的密钥是假的（标准播放器解不开分片），本接口按源站播放器同一套逻辑还原
    真密钥，并返回自包含密钥的改写清单，客户端用普通 HLS 播放器（如 hls.js）即可播放。

    查询参数:
        topic_id      (必填): 帖子 ID
        attachment_id (必填): 视频附件 ID（取自详情接口 videos[].id）
    """
    topic_id, err = _require_int(request.GET.get('topic_id', '').strip(), 'topic_id(帖子ID)')
    if err:
        return err
    attachment_id, err = _require_int(request.GET.get('attachment_id', '').strip(),
                                      'attachment_id(视频附件ID)')
    if err:
        return err

    ok, data = utils.get_video_playlist(topic_id, attachment_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return HttpResponse(data, content_type='application/vnd.apple.mpegurl')


@require_http_methods(['GET'])
def image_view(request):
    """
    加载并解码混淆图片，返回真实图片二进制（可直接用于 <img src>）。

    源站帖内图片是混淆地址（形如 .../<hash>_mini.jpg.txt），直接访问得到的是文本而非图片；
    本接口按源站规则解码后把图片原样返回。

    查询参数:
        url (必填): 加密图片地址（http/https 公网地址）
    """
    url = request.GET.get('url', '').strip()
    if not url:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: url(加密图片地址)')

    # 代理外部 URL 必须做安全性校验（协议白名单 + 拒绝内网/回环/保留地址，S-09）
    ok, reason = check_public_http_url(url)
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=f'参数值非法: {reason}')

    ok, data = utils.fetch_image(url)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    # 只接受解码出的 data URI 图片，避免该端点被当作通用代理使用
    matched = _DATA_URI_RE.match(data or '')
    if not matched:
        return _json_response(StatusCode.EXTERNAL_API_FAILED,
                              msg='解码失败: 该地址不是有效的加密图片地址')
    return HttpResponse(base64.b64decode(matched.group(2)), content_type=matched.group(1))


@require_http_methods(['POST'])
def register_captcha_view(request):
    """
    取注册验证码（两步式注册的第一步）。

    源站注册需图形验证码且对注册有 IP 限制，故验证码图片直接返回给调用方人工识别
    （后续接入验证码识别后即可自动化）。

    表单参数:
        use_proxy (可选): true=经 51代理 请求，false/不传=直连（默认 false）
    """
    use_proxy_raw = request.POST.get('use_proxy', '').strip().lower()
    if use_proxy_raw in ('',) + _FALSE_VALUES:
        use_proxy = False
    elif use_proxy_raw in _TRUE_VALUES:
        use_proxy = True
    else:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: use_proxy 仅支持 true / false')

    ok, data = utils.create_register_captcha(use_proxy=use_proxy)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def register_view(request):
    """
    提交注册（两步式注册的第二步）。

    表单参数:
        captcha_token (必填): 取验证码时返回的会话 token（决定复用哪次出口 IP）
        captcha_code  (必填): 人工识别的验证码
        username      (必填): 用户名
        password      (必填): 密码（源站要求 ≥ 6 位）
        email         (必填): 邮箱（源站要求合法邮箱格式）
    """
    captcha_token = request.POST.get('captcha_token', '').strip()
    captcha_code = request.POST.get('captcha_code', '').strip()
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    email = request.POST.get('email', '').strip()
    for name, value in (('captcha_token', captcha_token), ('captcha_code', captcha_code),
                        ('username', username), ('password', password), ('email', email)):
        if not value:
            return _json_response(StatusCode.PARAM_MISSING, msg=f'参数缺失: {name}')

    if len(password) < 6:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: password 长度需 ≥ 6 位')

    ok, data = utils.submit_register(captcha_token, captcha_code, username, password, email)
    if not ok:
        # 源站拒绝多为业务校验不通过（验证码错误等）→ 20003；
        # 「已存在 / 已被注册」等按消息映射为对应状态码，见 StatusCode.from_message
        return _json_response(StatusCode.from_message(data), msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def register_credentials_view(request):
    """
    生成一组注册用账号凭据（不入库、不注册）。

    供「一键填写」以及调用方自行批量注册时使用；规则见 utils.generate_credentials：
    用户名 = xy_ + 9 位随机（合计 12 位，符合源站用户名长度上限）。
    """
    return _json_response(StatusCode.SUCCESS, data=utils.generate_credentials(), msg='生成成功')


@require_http_methods(['POST'])
def register_batch_view(request):
    """
    批量注册（用户名 / 密码 / 邮箱默认由服务端自动生成，用户名统一 xy_ 前缀）。

    表单参数:
        items (必填): JSON 数组字符串，每项 {"captcha_token": "...", "captcha_code": "1234"}；
                      可另带 username / password / email 覆盖自动生成值；单次上限 20 项。
    """
    raw = request.POST.get('items', '').strip()
    if not raw:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: items(JSON 数组字符串)')
    try:
        items = json.loads(raw)
    except Exception as e:      # noqa: BLE001 - 解析失败按参数格式错误返回
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg=f'参数格式错误: items 需为 JSON 数组（{e}）')
    if not isinstance(items, list) or not items:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: items 需为非空 JSON 数组')
    if len(items) > utils.MAX_BATCH_SIZE:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: 单次批量注册上限 {utils.MAX_BATCH_SIZE} 项')
    if not all(isinstance(item, dict) for item in items):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: items 每项需为 JSON 对象')

    ok, data = utils.register_batch(items)
    if not ok:
        return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data,
                          msg=f'批量注册完成：成功 {data["success_count"]} / 共 {data["total"]} 条')


@require_http_methods(['POST'])
def login_view(request):
    """
    账号登录（源站 POST /api/login/signin）。

    表单参数（两种用法二选一）:
        username + password : 直传账号密码登录
        account_id          : 传库内账号 ID，从账号表取凭据登录，成功后回写最新 token
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    account_id = request.POST.get('account_id', '').strip() or None

    ok, data = utils.login(username=username or None, password=password or None,
                           account_id=account_id)
    if not ok:
        return _error_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='登录成功')


@require_http_methods(['POST'])
def sign_in_view(request):
    """
    金币签到（源站 POST /api/user/user_sign_in，无请求体，靠登录态鉴权）。

    表单参数（两种用法二选一）:
        account_id           : 传库内账号 ID，用该账号的登录凭据签到
        user_id + user_token : 直传账号 ID 与登录 token 签到（不入库）

    返回 data.state: signed=本次签到成功 / already=今天已签到 / closed=任务未开放
    """
    account_id = request.POST.get('account_id', '').strip() or None
    user_id = request.POST.get('user_id', '').strip() or None
    user_token = request.POST.get('user_token', '').strip() or None

    ok, data = utils.sign_in(account_id=account_id, user_id=user_id, user_token=user_token)
    if not ok:
        return _error_response(data)
    if data['state'] == 'signed':
        return _json_response(StatusCode.SUCCESS, data=data,
                              msg=f'签到成功，获得 {data["amount"]} 金币')
    if data['state'] == 'already':
        return _json_response(StatusCode.SUCCESS, data=data, msg='今天已签到')
    return _json_response(StatusCode.SUCCESS, data=data, msg=data['message'] or '签到任务未开放')


@require_http_methods(['POST'])
def sign_in_all_view(request):
    """
    一键签到全部账号：对账号表里所有已存 token 的账号逐个签到（无表单参数）。

    逐个串行执行避免触发源站风控；今天已签到的账号按 already 计入，不算失败。
    """
    ok, data = utils.sign_in_all()
    if not ok:
        return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
    return _json_response(
        StatusCode.SUCCESS, data=data,
        msg=f'签到完成：新签 {data["success_count"]} / 已签 {data["already_count"]}'
            f' / 共 {data["total"]} 个账号')


@require_http_methods(['GET', 'POST'])
def accounts_view(request):
    """账号列表（GET）/ 新增账号（POST）

    GET 查询参数:
        keyword       (可选): 匹配 用户名 / 邮箱 / 昵称 / 源站用户ID
        page          (可选): 页码，从 1 开始，默认 1
        page_size     (可选): 每页条数，1-100，默认 10
        with_password (可选): true=列表项携带密码明文，默认 false（不返回）
    POST 表单参数:
        user_id(必填), username(必填), password(必填), email, nickname, token, remark
    """
    if request.method == 'GET':
        keyword = request.GET.get('keyword', '').strip()
        page, err = _require_int(request.GET.get('page', '').strip() or '1', 'page', minimum=1)
        if err:
            return err
        page_size, err = _require_int(request.GET.get('page_size', '').strip() or '10',
                                      'page_size', minimum=1)
        if err:
            return err
        if page_size > 100:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: page_size 最大为 100')
        with_password, err = _parse_flag(request.GET.get('with_password', ''), 'with_password')
        if err:
            return err

        ok, data = utils.list_accounts(keyword=keyword, page=page, page_size=page_size,
                                       with_password=with_password)
        if not ok:
            return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg=f'查询成功，共 {data["total"]} 条')

    body, err = _parse_body(request)
    if err:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
    if not body:
        return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')

    ok, data = utils.create_account(body)
    if not ok:
        return _error_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='创建成功')


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def account_detail_view(request, account_id: uuid.UUID):
    """账号详情（GET）/ 更新（PATCH）/ 删除（DELETE）

    GET 查询参数:
        with_password (可选): true=返回中携带密码明文，默认 false（不返回）
    PATCH 表单参数（部分字段，至少传一个）:
        username, password, email, nickname, token, remark
        注：user_id 是源站身份标识，不可修改；username / password 不允许置空。
    """
    if request.method == 'GET':
        with_password, err = _parse_flag(request.GET.get('with_password', ''), 'with_password')
        if err:
            return err
        ok, data = utils.get_account(account_id, with_password=with_password)
        if not ok:
            return _json_response(StatusCode.NOT_FOUND, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')

    if request.method == 'PATCH':
        body, err = _parse_body(request)
        if err:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
        if not body:
            return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')
        ok, data = utils.update_account(account_id, body)
        if not ok:
            return _error_response(data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='更新成功')

    ok, msg = utils.delete_account(account_id)
    if not ok:
        return _json_response(StatusCode.NOT_FOUND, msg=msg)
    return _json_response(StatusCode.SUCCESS, data=None, msg='删除成功')
