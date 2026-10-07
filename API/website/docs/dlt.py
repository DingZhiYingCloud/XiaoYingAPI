"""代练通服务 - 接口文档与在线调试数据

数据与 API/apis/DaiLianTong/ 实际实现对齐（服务策略 /api/dlt/ 默认需签名）：
- 代练通（dlt.com）订单/用户操作封装：认证、用户资料、个人订单查询与操作。
注意：多数接口需要「代练通平台账号」登录后拿到的 user_id / token；
涉及接收订单、改密、上传等操作会产生真实影响，请在真实账号下谨慎调试。

响应说明：本服务是把代练通（dlt.com）上游接口原样透传封装（见 API/apis/DaiLianTong/ 与
SpiderServices/DaiLianTong/），data 结构由上游决定、随时可能变化，故不逐个承诺字段，
只说明 data 的构成方式。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

_AUTH_DESC = '选填：平台登录令牌（代练通登录后返回）；不传则用后台「账号管理」的默认代练通账号'
_UID_DESC = '选填：平台用户 ID（登录/注册后返回）；不传则用后台「账号管理」的默认代练通账号'
# 只回执行结果、data 恒为 null 的接口（设置个性签名 / 上传头像）共用同一说明
_NULL_DATA_NOTE = '执行结果由外层 code / msg 表达；data 为 null，不含业务数据。'


def _t_uid():
    return ParamSpec('user_id', '用户ID', kind='text', required=False, desc=_UID_DESC)


def _t_token():
    return ParamSpec('token', '登录令牌', kind='password', required=False, desc=_AUTH_DESC)


def _tier_options():
    """段位下拉选项（不限 + 7 个段位），初始段位 / 目标段位共用"""
    return [{'value': '', 'label': '不限（默认）'}] + [
        {'value': t, 'label': t} for t in ('青铜', '白银', '黄金', '铂金', '钻石', '星耀', '王者')
    ]


def _my_order_state_options():
    """「我的订单」状态快捷筛选的下拉选项（取自服务层，避免两处漂移）"""
    from API.apis.DaiLianTong.utils import MY_ORDER_STATES
    return [{'value': '', 'label': '不按状态筛选（默认）'}] + [
        {'value': name, 'label': name} for name in MY_ORDER_STATES
    ]


def _dlt_game_options():
    """发布订单：已支持的游戏下拉（目前仅 王者荣耀 / 三角洲行动，逐个接入）"""
    from API.apis.DaiLianTong.utils import supported_game_options
    return supported_game_options()


# 代练时限的「时间表」档位：2~24 每小时一档，再接 48 / 72 小时（2 天 / 3 天）。
# 最低 2 小时起步；用户也可切到「手动输入」面板自由填写。
_TIME_LIMIT_DAY_HINT = {24: '（1 天）', 48: '（2 天）', 72: '（3 天）'}


def _time_limit_options():
    return [{'value': str(h), 'label': f'{h} 小时{_TIME_LIMIT_DAY_HINT.get(h, "")}'}
            for h in list(range(2, 25)) + [48, 72]]


def _order_response_fields():
    """订单对象 + 分页字段说明（「按游戏获取订单列表」与「搜索订单」共用）"""
    return [
        ResponseFieldSpec('items', 'array', '订单数组，每项字段见下方 items[].*'),
        ResponseFieldSpec('items[].SerialNo', 'string', '订单编号'),
        ResponseFieldSpec('items[].Title', 'string', '订单标题（代练要求摘要）'),
        ResponseFieldSpec('items[].Price', 'float', '订单金额（元）'),
        ResponseFieldSpec('items[].Ensure', 'float', '总保证金（元）'),
        ResponseFieldSpec('items[].Ensure1', 'float', '安全保证金（元）'),
        ResponseFieldSpec('items[].Ensure2', 'float', '效率保证金（元）'),
        ResponseFieldSpec('items[].TimeLimit', 'int', '代练时限（小时）'),
        ResponseFieldSpec('items[].Game', 'string', '游戏名称'),
        ResponseFieldSpec('items[].Zone', 'string', '大区（如 苹果QQ / 苹果WX）'),
        ResponseFieldSpec('items[].Server', 'string', '服务器（如 默认服）'),
        ResponseFieldSpec('items[].ZoneServerID', 'string', '区服ID'),
        ResponseFieldSpec('items[].Create', 'string', '发单者昵称'),
        ResponseFieldSpec('items[].IsPub', 'int', '是否公开订单（1=公开）'),
        ResponseFieldSpec('items[].InGoodPrice', 'int', '是否优选（好价）订单（1=是）'),
        ResponseFieldSpec('items[].OrderType', 'int', '上游订单类型标识（0=普通 等，由上游定义）'),
        ResponseFieldSpec('items[].SameCity', 'string', '同城信息，无则为空'),
        ResponseFieldSpec('items[].Stamp', 'int', '上游时间标记（本接口通常为 0）'),
        ResponseFieldSpec('items[].PriPartner', 'int', '上游合作商标记（由上游定义）'),
        ResponseFieldSpec('items[].IsShare', 'int', '上游分享标记（由上游定义）'),
        ResponseFieldSpec('total', 'int', '筛选后的订单总数'),
        ResponseFieldSpec('page', 'int', '当前页码'),
        ResponseFieldSpec('page_size', 'int', '每页数量'),
        ResponseFieldSpec('total_pages', 'int', '总页数'),
    ]


SERVICE = ServiceSpec(
    slug='dlt',
    name='代练通',
    prefix='/api/dlt/',
    summary='代练通平台能力：验证码登录注册、用户资料、各游戏公开订单数统计、个人代练订单查询与操作（接收/删除）、图片上传。',
    keywords='代练通API,代练订单接口,代练通数据',
    intro=[
        '代练通服务封装代练通平台的数据接口，覆盖验证码登录注册、用户资料与联系方式维护、'
        '头像与留言图片上传、各游戏的公开订单数统计，以及个人订单的查询与操作（接收、删除）。',
        '调用链路上，登录成功后需携带返回的 user_id 与 token 继续调用后续接口；'
        '部分操作（如接收订单）还需额外的支付密码等信息，请按参数说明谨慎传参。',
        '本服务需项目签名。接收、删除等接口会真实作用于第三方平台的订单数据，'
        '调试时请避免在正式环境误操作。',
    ],
    channels=[
        ChannelSpec(
            slug='dlt',
            name='代练通订单平台',
            provider='代练通（dlt.com）网页接口封装',
            auth_note='auth',
            note='本项目侧需项目签名；业务侧还需先登录代练通取得 user_id / token。'
                 '含资金/接收订单等高风险操作，调试请务必使用自己的真实小号并谨慎操作。',
            endpoints=[
                # ---------- 认证 ----------
                EndpointSpec('auth_send_code', '发送验证码', 'POST', '/api/dlt/auth/send-code',
                             summary='向手机号发送注册/登录验证码。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True, placeholder='13800138000'),
                                 ParamSpec('use_type', '验证码类型', kind='select',
                                           options=[{'value': '17', 'label': '17=注册（默认）'},
                                                    {'value': '12', 'label': '12=登录'}],
                                           default='17'),
                             ],
                             response_note='data 为代练通短信接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('auth_register', '注册', 'POST', '/api/dlt/auth/register',
                             summary='用手机号+验证码注册代练通账号。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                             ],
                             response_note='data 为代练通注册接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('auth_login', '登录', 'POST', '/api/dlt/auth/login',
                             summary='验证码或密码登录，返回 user_id / token。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True),
                                 ParamSpec('code', '验证码或密码', kind='password', required=True),
                                 ParamSpec('code_type', '登录方式', kind='select',
                                           options=[{'value': 'VerificationCode', 'label': 'VerificationCode（验证码，默认）'},
                                                    {'value': 'Password', 'label': 'Password（密码）'}],
                                           default='VerificationCode'),
                             ],
                             response_note='data 为代练通登录接口返回的原始 JSON 对象（原样透传），含上游下发的登录态信息，字段由上游定义。'),
                # ---------- 用户 ----------
                EndpointSpec('user_info', '获取用户信息', 'GET', '/api/dlt/user/info',
                             summary='按 user_id + token 查询代练通用户信息。',
                             params=[_t_uid(), _t_token()],
                             response_note='data 为代练通用户信息接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('user_set_contact', '设置联系方式', 'POST', '/api/dlt/user/set-contact',
                             summary='设置 QQ 或手机号联系方式。',
                             params=[
                                 ParamSpec('contact', '联系方式', kind='text', required=True,
                                           desc='必填：QQ 号或手机号'),
                                 _t_uid(), _t_token(),
                                 ParamSpec('set_type', '类型', kind='select',
                                           options=[{'value': 'qq', 'label': 'qq（默认）'},
                                                    {'value': 'mobile', 'label': 'mobile'}],
                                           default='qq'),
                             ],
                             response_note='data 为代练通用户信息更新接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('user_set_mysign', '设置个性签名', 'POST', '/api/dlt/user/set-mysign',
                             summary='设置个性签名（无需 token）。',
                             params=[
                                 ParamSpec('mysign', '个性签名', kind='text', required=True),
                                 _t_uid(),
                             ],
                             response_note=_NULL_DATA_NOTE),
                EndpointSpec('user_change_password', '修改密码', 'POST', '/api/dlt/user/change-password',
                             summary='修改代练通登录密码（需登录上下文与旧密码）。',
                             params=[
                                 ParamSpec('old_password', '旧密码', kind='password', required=True,
                                           desc='必填：旧密码（为空表示未设置过密码，传空字符串）'),
                                 ParamSpec('new_password', '新密码', kind='password', required=True),
                                 _t_uid(),
                                 ParamSpec('login_id', '登录ID', kind='text', required=True, desc='必填：登录返回的 login_id'),
                                 ParamSpec('uid', 'UID', kind='text', required=True),
                                 _t_token(),
                             ],
                             response_note='data 为代练通改密接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('user_sign_in', '签到得代币', 'POST', '/api/dlt/user/sign-in',
                             summary='每日签到领取代练币。', params=[_t_uid()],
                             response_note='data 为上游签到接口 Result1 字段的内容（原样透传），字段由上游定义。'),
                EndpointSpec('user_real_name_info', '实名认证信息', 'GET', '/api/dlt/user/real-name-info',
                             summary='查询账号实名认证信息。', params=[_t_uid()],
                             response_note='data 为上游实名认证接口 Result 字段的内容（数组或对象，原样透传），字段由上游定义。'),
                # ---------- 游戏 ----------
                EndpointSpec('games', '获取全部游戏', 'GET', '/api/dlt/games',
                             summary='列出当前有公开订单的游戏及各自的订单数量（按订单数降序）。',
                             params=[],
                             response_note='data 为游戏数组，按订单数从多到少排序；仅包含当前有公开订单的游戏，'
                                           '由上游游戏清单与各游戏订单数合并而成。',
                             response_fields=[
                                 ResponseFieldSpec('game_id', 'int', '游戏ID'),
                                 ResponseFieldSpec('game_name', 'string', '游戏名称'),
                                 ResponseFieldSpec('order_count', 'int', '当前可接的公开订单数量'),
                             ]),
                EndpointSpec('games_orders', '按游戏获取订单列表', 'GET', '/api/dlt/games/orders',
                             summary='按游戏ID查询该游戏的公开订单列表：支持分页与区服/订单类型/段位/价格/'
                                     '仲裁介入/结算时间/排序/关键词（指定英雄）等筛选。',
                             params=[
                                 ParamSpec('game_id', '游戏ID', kind='number', required=True,
                                           desc='必填：游戏ID；可由「获取全部游戏」接口取到'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='从 1 开始，默认 1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20',
                                           desc='1-100，默认 20'),
                                 ParamSpec('pg_type', '区服', kind='select',
                                           desc='按游戏区服筛选；默认 0=全部',
                                           options=[{'value': '0', 'label': '0=全部（默认）'},
                                                    {'value': '1', 'label': '1=安卓'},
                                                    {'value': '2', 'label': '2=IOS'}]),
                                 ParamSpec('order_type', '订单类型', kind='select',
                                           desc='按订单玩法类型筛选；默认不限',
                                           options=[{'value': '', 'label': '不限（默认）'},
                                                    {'value': '10', 'label': '10=5V5排位赛'},
                                                    {'value': '13', 'label': '13=巅峰赛'},
                                                    {'value': '15', 'label': '15=荣耀战力'},
                                                    {'value': '1920', 'label': '1920=国标'}]),
                                 ParamSpec('start_tier', '初始段位', kind='select',
                                           desc='按订单要求的初始段位筛选；默认不限',
                                           options=_tier_options()),
                                 ParamSpec('end_tier', '目标段位', kind='select',
                                           desc='按订单的目标段位筛选；默认不限',
                                           options=_tier_options()),
                                 ParamSpec('price_str', '价格区间', kind='text',
                                           desc='格式「最低_最高」，如 1_20；默认不限。'
                                                '常用值：1_20 / 21_50 / 51_100 / 101_300 / 301_10000'),
                                 ParamSpec('pub_cancel', '仲裁介入率上限', kind='select',
                                           desc='只显示发单者仲裁介入率不超过该百分比的订单；默认 0=不限',
                                           options=[{'value': '0', 'label': '0=不限（默认）'},
                                                    {'value': '10', 'label': '10%'},
                                                    {'value': '20', 'label': '20%'},
                                                    {'value': '30', 'label': '30%'},
                                                    {'value': '50', 'label': '50%'}]),
                                 ParamSpec('settle_hour', '结算时间上限', kind='select',
                                           desc='只显示结算时间不超过该小时数的发单者订单；默认 0=不限',
                                           options=[{'value': '0', 'label': '0=不限（默认）'},
                                                    {'value': '6', 'label': '6小时'},
                                                    {'value': '12', 'label': '12小时'},
                                                    {'value': '24', 'label': '24小时'},
                                                    {'value': '48', 'label': '48小时'}]),
                                 ParamSpec('filter_type', '只看可接手', kind='select',
                                           desc='是否只返回本账号可接手的订单；默认 1=只看可接手',
                                           options=[{'value': '1', 'label': '1=只看可接手（默认）'},
                                                    {'value': '0', 'label': '0=不限'}]),
                                 ParamSpec('sort_str', '排序', kind='select',
                                           desc='结果排序方式；默认按平台推荐排序',
                                           options=[{'value': '', 'label': '默认排序'},
                                                    {'value': 'Price_DESC', 'label': '价格最高'},
                                                    {'value': 'Price_ASC', 'label': '价格最低'},
                                                    {'value': 'SettleHour_ASC', 'label': '验收最快'},
                                                    {'value': 'Ensure_ASC', 'label': '保证金最少'},
                                                    {'value': 'TimeLimit_DESC', 'label': '总时限最长'},
                                                    {'value': 'PubCancelRate_ASC', 'label': '介入率最低'}]),
                                 ParamSpec('search_str', '关键词 / 指定英雄', kind='text',
                                           desc='关键词筛选。对王者荣耀等游戏，「指定英雄」即在此填英雄名，'
                                                '多个英雄用空格分隔（如「澜 镜」）'),
                                 ParamSpec('user_id', '用户ID（选填）', kind='text',
                                           desc='代练通账号ID（登录后返回）。与 token 一起传时按登录态筛选；'
                                                '不传则用后台「账号管理」的默认代练通账号；都没有=匿名'),
                                 ParamSpec('token', '登录令牌（选填）', kind='password',
                                           desc='代练通登录令牌，与 user_id 配对。不传则用后台默认账号的令牌；'
                                                '都没有=匿名（匿名下仅关键词与区服筛选生效）'),
                             ],
                             response_note='data 为分页对象；上游一次性返回全部匹配订单，本接口按 '
                                           'page/page_size 切片分页。items 内每个订单字段见下表（由上游定义）。',
                             response_fields=_order_response_fields()),
                # ---------- 搜索 ----------
                EndpointSpec('search_orders', '搜索订单', 'GET', '/api/dlt/search/orders',
                             summary='按关键词搜索订单（如「马可波罗」「安琪拉」）；参数对齐官网搜索页，'
                                     '上游大部分字段都可自定义。',
                             params=[
                                 ParamSpec('game_id', '游戏ID', kind='number', required=True,
                                           desc='必填：游戏ID；可由「获取全部游戏」取到'),
                                 ParamSpec('search_str', '搜索关键词', kind='text',
                                           desc='搜索关键词，如「马可波罗」「安琪拉」「巅峰赛」「五排」'),
                                 ParamSpec('is_pub', '订单池', kind='number', default='9',
                                           desc='上游订单池标识 IsPub；默认 9（对齐官网搜索页）'),
                                 ParamSpec('pg_type', '区服', kind='select', default='2',
                                           desc='按区服筛选；官网搜索页默认 2=苹果',
                                           options=[{'value': '0', 'label': '0=全部'},
                                                    {'value': '1', 'label': '1=安卓'},
                                                    {'value': '2', 'label': '2=IOS（默认）'}]),
                                 ParamSpec('zone_id', '大区ID', kind='number', default='0',
                                           desc='上游大区ID ZoneID，默认 0'),
                                 ParamSpec('server_id', '服务器ID', kind='number', default='0',
                                           desc='上游服务器ID ServerID，默认 0'),
                                 ParamSpec('level_type2', '订单类型', kind='select',
                                           desc='上游 LevelType2（订单玩法类型）；默认不限',
                                           options=[{'value': '', 'label': '不限（默认）'},
                                                    {'value': '10', 'label': '10=5V5排位赛'},
                                                    {'value': '13', 'label': '13=巅峰赛'},
                                                    {'value': '15', 'label': '15=荣耀战力'},
                                                    {'value': '1920', 'label': '1920=国标'}]),
                                 ParamSpec('stier', '初始段位', kind='select',
                                           desc='初始段位 STier；默认不限', options=_tier_options()),
                                 ParamSpec('etier', '目标段位', kind='select',
                                           desc='目标段位 ETier；默认不限', options=_tier_options()),
                                 ParamSpec('price_str', '价格区间', kind='text',
                                           desc='格式「最低_最高」，如 1_20；默认不限'),
                                 ParamSpec('pub_cancel', '仲裁介入率上限', kind='select', default='0',
                                           desc='只显示发单者仲裁介入率不超过该百分比的订单；默认 0=不限',
                                           options=[{'value': '0', 'label': '0=不限（默认）'},
                                                    {'value': '10', 'label': '10%'},
                                                    {'value': '20', 'label': '20%'},
                                                    {'value': '30', 'label': '30%'},
                                                    {'value': '50', 'label': '50%'}]),
                                 ParamSpec('settle_hour', '结算时间上限', kind='select', default='0',
                                           desc='只显示结算时间不超过该小时数的发单者订单；默认 0=不限',
                                           options=[{'value': '0', 'label': '0=不限（默认）'},
                                                    {'value': '6', 'label': '6小时'},
                                                    {'value': '12', 'label': '12小时'},
                                                    {'value': '24', 'label': '24小时'},
                                                    {'value': '48', 'label': '48小时'}]),
                                 ParamSpec('filter_type', '只看可接手', kind='select', default='0',
                                           desc='1=只看本账号可接手的订单；官网搜索页默认 0',
                                           options=[{'value': '0', 'label': '0=不限（默认）'},
                                                    {'value': '1', 'label': '1=只看可接手'}]),
                                 ParamSpec('sort_str', '排序', kind='select',
                                           desc='结果排序方式；默认按平台推荐排序',
                                           options=[{'value': '', 'label': '默认排序'},
                                                    {'value': 'Price_DESC', 'label': '价格最高'},
                                                    {'value': 'Price_ASC', 'label': '价格最低'},
                                                    {'value': 'SettleHour_ASC', 'label': '验收最快'},
                                                    {'value': 'Ensure_ASC', 'label': '保证金最少'},
                                                    {'value': 'TimeLimit_DESC', 'label': '总时限最长'},
                                                    {'value': 'PubCancelRate_ASC', 'label': '介入率最低'}]),
                                 ParamSpec('focused', '关注筛选', kind='number', default='-1',
                                           desc='上游 Focused，默认 -1'),
                                 ParamSpec('order_type', '上游 OrderType', kind='number', default='0',
                                           desc='上游 OrderType（与「订单类型 LevelType2」不同），默认 0'),
                                 ParamSpec('pub_recommend', '上游 PubRecommend', kind='number', default='0',
                                           desc='上游 PubRecommend，默认 0'),
                                 ParamSpec('score1', '上游 Score1', kind='number', default='0',
                                           desc='上游评分筛选位 Score1，默认 0'),
                                 ParamSpec('score2', '上游 Score2', kind='number', default='0',
                                           desc='上游评分筛选位 Score2，默认 0'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='从 1 开始，默认 1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20',
                                           desc='1-100，默认 20'),
                                 _t_uid(),
                                 _t_token(),
                             ],
                             response_note='data 为分页对象；上游一次性返回全部匹配订单，本接口按 page/page_size '
                                           '切片分页。默认口径对齐官网「搜索」页（优选订单池 IsPub=9）。',
                             response_fields=_order_response_fields()),
                EndpointSpec('hot_search_words', '热门搜索词', 'GET', '/api/dlt/search/hot-words',
                             summary='获取某游戏的热门搜索词（官网搜索页的推荐词）。',
                             params=[ParamSpec('game_id', '游戏ID', kind='number', required=True,
                                               desc='必填：游戏ID')],
                             response_note='data 为 {words, tip}：words 为热门搜索词数组，tip 为一句说明文字。',
                             response_fields=[
                                 ResponseFieldSpec('words', 'array', '热门搜索词数组'),
                                 ResponseFieldSpec('tip', 'string', '说明文字'),
                             ]),
                # ---------- 订单 ----------
                EndpointSpec('orders_receive', '接收订单', 'POST', '/api/dlt/orders/receive',
                             summary='接收（抢）一笔订单，需支付密码与 uid。',
                             params=[
                                 ParamSpec('order_id', '订单ID', kind='text', required=True),
                                 ParamSpec('pay_pass', '支付密码', kind='password', required=True),
                                 ParamSpec('uid', 'UID', kind='text', required=True),
                                 _t_token(), _t_uid(),
                             ],
                             response_note='data 为代练通接收订单接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                # ---------- 发布 ----------
                EndpointSpec('orders_publish', '发布订单', 'POST', '/api/dlt/orders/publish',
                             summary='发布代练订单（自定义发布）：填订单信息与游戏账号，服务端按官网发单参数提交。',
                             notes=['【怎么选游戏/区服】三步：①「选择游戏」下拉 → ②「选择客户端/大区」'
                                    '（安卓QQ / 苹果微信 / 官服…）→ ③服务端自动定位到具体区服ID，'
                                    '一般无需手填 zone_server_id。',
                                    '【区服ID 是什么】上游用 ZoneServerID 标识「游戏+大区+服务器」，'
                                    '形如 107103017095500（王者荣耀·安卓QQ·默认服）；确需精确指定时用「区服ID（高级）」填。',
                                    '【真实下单】本接口会真实发布订单并占用 / 扣减账号资金；'
                                    '测试完请用「删除订单」接口撤销，避免连续多次撤销触发风控。',
                                    '【标题与要求】务必写明「指定单」等规则（如「私接扣除全部保证金」），'
                                    '否则容易被私接、扣保证金。',
                                    '【已固定、不在表单暴露的字段】level_type2（订单类型）与 '
                                    'max_claim_amount（最大索赔额）由「自定义发单」固定，无需也无需修改。',
                                    '【游戏账号】按表单选择的登录方式填写；账号密码方式即填 游戏账号/密码/角色名。'],
                             params=[
                                 ParamSpec('game_id', '选择游戏', kind='select', default='107',
                                           dynamic_options='dlt_games',
                                           cascade='dlt-zones', cascade_role='game',
                                           desc='当前已支持：王者荣耀 / 三角洲行动；选完会自动刷新该游戏的大区'),
                                 ParamSpec('zone_type', '选择客户端/大区', kind='select',
                                           cascade='dlt-zones', cascade_role='zone',
                                           options=[{'value': '', 'label': '默认（安卓QQ）'}],
                                           desc='如 安卓QQ / 苹果微信 / 官服；选完会自动刷新出该大区下的区服'),
                                 ParamSpec('zone_server_id', '选择区服', kind='select',
                                           cascade='dlt-zones', cascade_role='server',
                                           options=[{'value': '', 'label': '默认（自动定位）'}],
                                           desc='游戏+大区+服务器（上游 ZoneServerID）；一般留空由「游戏+大区」自动定位'),
                                 ParamSpec('title', '订单标题', kind='text', required=True,
                                           desc='必填：订单标题（建议含「指定单」字样）'),
                                 ParamSpec('price', '价格（元）', kind='number', required=True,
                                           desc='必填：订单价格'),
                                 ParamSpec('time_limit', '时限（小时）', kind='select', required=True, default='2',
                                           options=_time_limit_options(),
                                           alt_kind='number', alt_default='',
                                           primary_label='时间表', alt_label='手动输入',
                                           desc='必填：代练时限（小时）。默认用「时间表」下拉（2~24 小时，'
                                                '再接 48/72）；需要特殊时长可切到「手动输入」自行填写，最低 2 小时'),
                                 ParamSpec('ensure1', '安全保证金', kind='number', default='0',
                                           desc='安全保证金（元），默认 0'),
                                 ParamSpec('ensure2', '效率保证金', kind='number', default='0',
                                           desc='效率保证金（元），默认 0'),
                                 ParamSpec('game_mobile', '号主联系方式', kind='text', required=True,
                                           desc='必填：号主联系方式'),
                                 ParamSpec('mobile', '发单者手机号', kind='text',
                                           desc='发单者联系方式（可选）'),
                                 ParamSpec('qq', '发单者QQ', kind='text', desc='发单者 QQ（可选）'),
                                 ParamSpec('game_account', '游戏账号', kind='text', required=True),
                                 ParamSpec('game_password', '游戏密码', kind='password', required=True),
                                 ParamSpec('game_author_name', '游戏角色名', kind='text', required=True),
                                 ParamSpec('game_extra', '铭文', kind='text', default='150',
                                           games=['107'],
                                           desc='仅王者荣耀需要：铭文等级（如 150），默认 150；'
                                                '其它游戏没有该项，切到别的游戏会自动隐藏'),
                                 ParamSpec('requirements', '代练要求', kind='textarea', required=True,
                                           desc='必填：写入订单详情；建议写明「指定单，私接扣除全部保证金」等规则'),
                                 ParamSpec('pay_pass', '支付密码', kind='password',
                                           desc='支付密码（原密码）；需要支付时填，服务端按 md5(md5(pwd)+uid) 处理'),
                                 ParamSpec('order_type', '订单玩法', kind='select', default='0',
                                           games=['107'],
                                           options=[{'value': '0', 'label': '普通订单'},
                                                    {'value': '1', 'label': '全胜订单'},
                                                    {'value': '2', 'label': '限时订单'}],
                                           desc='仅王者荣耀有（上游 OrderType：0=普通 / 1=全胜 / 2=限时）；'
                                                '三角洲行动没有该项，切过去会自动隐藏'),
                                 ParamSpec('insurance', '保险', kind='number', default='0',
                                           desc='上游 Insurance（保险设置），默认 0'),
                                 ParamSpec('uid', '账号UID', kind='text',
                                           desc='USR 开头（支付密码哈希用）；不传则用后台默认账号'),
                                 _t_uid(), _t_token(),
                             ],
                             response_note='data 为上游 LevelOrderAdd 的返回（原样透传），字段由上游定义。'),
                EndpointSpec('orders_apply_cancel', '申请撤销订单', 'POST', '/api/dlt/orders/apply-cancel',
                             summary='撤销订单（发单者不想让打手继续代练）：按官网「申请撤销」提交撤销意愿、账号进度、'
                                     '补充描述与凭证图片（上游 LevelOrderCancel）。',
                             notes=['【谁在用】发单者「我发布的订单」里点「申请撤销」；也可由接单者申请（Flag=0 时'
                                    '按登录账号身份判定）。',
                                    '【撤销意愿 desire】0=我愿意支付代练费（把金额填 pay_level_bal）/ '
                                    '1=我要求赔偿保证金（把金额填 rep_ensure_bal）/ 2=仅要求退款（默认，双方都不支出）。',
                                    '【账号进度 progress】上游页面选项：有进度 / 无进度 / 负进度 / 未开始代练。',
                                    '【会真实改变订单状态】申请后订单进入「申请撤销中」，对方需同意或走平台介入；'
                                    '可能涉及资金，请谨慎调用。',
                                    '【凭证图片 image】撤销成功后自动以「撤销」留言上传（LevelOrderProgressAdd）；'
                                    '上传失败不会回滚撤销结果，仅在返回 msg 里提示。',
                                    '【本接口只做提交，不含页面那层预检】撤销原因、进度赔偿金、预计撤销金额等'
                                    '由官网的预检接口（SelectOrderRevoke / SelectOrderDamages / SelectRevokeExtend）计算，'
                                    '如需精确金额请先把算出结果通过 pay_level_bal / rep_ensure_bal / revoke_price 传入。'],
                             params=[ParamSpec('order_id', '订单ID', kind='text', required=True,
                                               desc='必填：订单编号（上游 ODSerialNo，如 10717695025313439830）'),
                                     ParamSpec('pay_pass', '支付密码', kind='password', required=True,
                                               desc='必填：支付密码（原密码）；服务端按 md5(md5(pwd)+uid) 处理'),
                                     ParamSpec('uid', '账号UID', kind='text', required=True,
                                               desc='必填：账号 UID（USR 开头，如 USR2025112802644）；支付密码哈希用'),
                                     ParamSpec('flag', '撤销动作', kind='select', default='0',
                                               desc='上游 Flag：0=申请撤销（默认）/ 1=取消撤销 / 2=同意撤销（对方申请后）/ '
                                                    '3=申请平台介入',
                                               options=[{'value': '0', 'label': '0=申请撤销（默认）'},
                                                        {'value': '1', 'label': '1=取消撤销'},
                                                        {'value': '2', 'label': '2=同意撤销'},
                                                        {'value': '3', 'label': '3=申请平台介入'}]),
                                     ParamSpec('desire', '撤销意愿', kind='select', default='2',
                                               desc='撤销意愿（写入撤销说明）：0=我愿意支付代练费（金额取 pay_level_bal）/ '
                                                    '1=我要求赔偿保证金（金额取 rep_ensure_bal）/ 2=仅要求退款（默认）',
                                               options=[{'value': '0', 'label': '0=我愿意支付代练费'},
                                                        {'value': '1', 'label': '1=我要求赔偿保证金'},
                                                        {'value': '2', 'label': '2=仅要求退款（默认）'}]),
                                     ParamSpec('progress', '账号进度', kind='select', default='无进度',
                                               desc='账号进度情况（写入撤销说明）：有进度 / 无进度（默认）/ 负进度 / 未开始代练',
                                               options=[{'value': '有进度', 'label': '有进度'},
                                                        {'value': '无进度', 'label': '无进度（默认）'},
                                                        {'value': '负进度', 'label': '负进度'},
                                                        {'value': '未开始代练', 'label': '未开始代练'}]),
                                     ParamSpec('comment', '补充描述', kind='textarea',
                                               desc='补充描述（写入撤销说明，建议写清撤销原因，便于协商/仲裁）'),
                                     ParamSpec('pay_level_bal', '支付代练费金额', kind='number', default='0',
                                               desc='撤销意愿=0（我愿意支付代练费）时下发的金额（元），默认 0'),
                                     ParamSpec('rep_ensure_bal', '赔偿保证金金额', kind='number', default='0',
                                               desc='撤销意愿=1（我要求赔偿保证金）时下发的金额（元），默认 0'),
                                     ParamSpec('revoke_price', '撤销金额', kind='number', default='0',
                                               desc='上游 RevokePrice（预计撤销金额，元），默认 0'),
                                     ParamSpec('image', '凭证图片', kind='text',
                                               desc='可选：撤销凭证图片地址（先上传到图床再填 URL）；'
                                                    '撤销成功后自动以「撤销」留言上传'),
                                     _t_uid(), _t_token()],
                             response_note='data 为上游 LevelOrderCancel 的返回（原样透传），字段由上游定义。'),
                EndpointSpec('orders_handle_cancel', '处理撤销申请', 'POST', '/api/dlt/orders/handle-cancel',
                             summary='订单「撤销详情」页的处置动作：同意撤销 / 取消撤销 / 申请平台介入'
                                     '（接单者或发单者均可调用，按登录账号身份判定）。',
                             notes=['【页面 3 种方式】「联系发单者协商继续代练」是站内聊天、没有接口；'
                                    '「同意撤销」=LevelOrderCancel(Flag=2)；「申请仲裁介入」=LevelOrderRequestArbitration，'
                                    '本接口用 action 区分，默认 action=agree（同意撤销）。',
                                    '【agree 同意撤销】对方申请撤销后，您认可即可同意；默认下发 PayLevelBal/RepEnsureBal'
                                    '（来自对方申请时的金额，可用参数覆盖）。',
                                    '【cancel 取消撤销】撤销方自己想撤回申请时用（等价申请撤销接口的 flag=1）。',
                                    '【arbitration 申请平台介入】双方协商不成时申请；上游要求订单进入「撤销中」满一定时长'
                                    '（王者荣耀 1 小时）后才可申请，否则上游会报错。此动作不需要支付密码。',
                                    '【会真实改变订单状态/资金】同意撤销后订单终止并按撤销意愿结算，请谨慎调用。',
                                    '【凭证图片 image】操作成功后自动以「撤销」留言上传；上传失败不回滚，仅在返回 msg 提示。'],
                             params=[ParamSpec('order_id', '订单ID', kind='text', required=True,
                                               desc='必填：订单编号（上游 ODSerialNo）'),
                                     ParamSpec('action', '处理方式', kind='select', default='agree',
                                               desc='页面「撤销详情」的处置方式，默认 同意撤销',
                                               options=[{'value': 'agree', 'label': 'agree=同意撤销（默认）'},
                                                        {'value': 'cancel', 'label': 'cancel=取消撤销'},
                                                        {'value': 'arbitration', 'label': 'arbitration=申请平台介入'}]),
                                     ParamSpec('pay_pass', '支付密码', kind='password',
                                               desc='agree / cancel 必填；arbitration 不需要。服务端按 md5(md5(pwd)+uid) 处理'),
                                     ParamSpec('uid', '账号UID', kind='text',
                                               desc='agree / cancel 必填：账号 UID（USR 开头，如 USR2025111906640）；支付密码哈希用'),
                                     ParamSpec('pay_level_bal', '支付代练费金额', kind='number', default='0',
                                               desc='同意撤销时下发的支付代练费金额（元），默认 0；一般取对方申请时的金额'),
                                     ParamSpec('rep_ensure_bal', '赔偿保证金金额', kind='number', default='0',
                                               desc='同意撤销时下发的赔偿保证金金额（元），默认 0；一般取对方申请时的金额'),
                                     ParamSpec('comment', '撤销说明', kind='textarea',
                                               desc='可选：撤销说明（上游 Comment），默认空'),
                                     ParamSpec('image', '凭证图片', kind='text',
                                               desc='可选：凭证图片地址（先上传到图床再填 URL）；操作成功后自动以「撤销」留言上传'),
                                     _t_uid(), _t_token()],
                             response_note='data 为上游 LevelOrderCancel / LevelOrderRequestArbitration 的返回'
                                           '（原样透传），字段由上游定义。'),
                EndpointSpec('orders_delete', '删除订单', 'POST', '/api/dlt/orders/delete',
                             summary='删除自己的订单（默认原因“不用了”）。',
                             params=[ParamSpec('order_id', '订单ID', kind='text', required=True),
                                     _t_token(), _t_uid(),
                                     ParamSpec('reason', '删除原因', kind='text', default='不用了')],
                             response_note='data 为代练通删除订单接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('orders_my', '我的订单', 'GET', '/api/dlt/orders/my',
                             summary='查询我发布的 / 我接的订单，支持订单范围、进度、状态、游戏、关键词等筛选（服务端分页）。',
                             params=[
                                 _t_uid(), _t_token(),
                                 ParamSpec('publish', '订单范围', kind='select', default='1',
                                           desc='查我发布还是我接的订单',
                                           options=[{'value': '1', 'label': '1=我发布的（默认）'},
                                                    {'value': '0', 'label': '0=我接的'}]),
                                 ParamSpec('over_days', '订单进度', kind='select', default='-99',
                                           desc='进行中 / 已完成',
                                           options=[{'value': '-99', 'label': '-99=进行中（默认）'},
                                                    {'value': '99', 'label': '99=已完成'}]),
                                 ParamSpec('status', '订单状态', kind='number', default='0',
                                           desc='上游订单状态位；0=不限（默认），具体取值由上游定义'),
                                 ParamSpec('cancel_status', '撤单状态', kind='number', default='0',
                                           desc='上游撤单状态位；0=不限（默认），具体取值由上游定义'),
                                 ParamSpec('game_id', '游戏ID', kind='number', default='0',
                                           desc='按游戏筛选；0=全部（默认）'),
                                 ParamSpec('search_str', '搜索关键词', kind='text',
                                           desc='按关键词筛选，默认空'),
                                 ParamSpec('game_mobile', '号主联系方式', kind='text',
                                           desc='按号主联系方式筛选，默认空'),
                                 ParamSpec('with_tg', '含托管', kind='select', default='1',
                                           desc='1=含托管（默认） / 0=不含',
                                           options=[{'value': '1', 'label': '1=含托管（默认）'},
                                                    {'value': '0', 'label': '0=不含'}]),
                                 ParamSpec('state', '状态快捷筛选', kind='select',
                                           desc='中文名一键筛选常用状态；等价于设置 status/cancel_status/over_days，'
                                                '显式传这三者时以其为准。对应上游：待付款=Status19、未接手=11、'
                                                '正在代练=12、等待验收=13、订单异常=14、锁定订单=15、'
                                                '申请撤销中=Status16+Cancel11、仲裁介入中=Cancel14、'
                                                '协商已处理=Cancel12、仲裁已处理=Cancel15、客服强制撤销=Cancel16、'
                                                '已结算=Status17；其中协商/仲裁/客服强制撤销/已结算 按已结束'
                                                '(OverDays=99)，其余按进行中(OverDays=-99)',
                                           options=_my_order_state_options()),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='从 1 开始，默认 1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20',
                                           desc='1-100，默认 20'),
                             ],
                             response_note='data 为分页对象（上游服务端分页）：items（订单数组，字段由上游定义，'
                                           '含 Status / CancelStatus / AcceptCount / LevelType2 等）/ total / '
                                           'page / page_size / total_pages。',
                             response_fields=[
                                 ResponseFieldSpec('items', 'array', '订单数组（字段由上游定义）'),
                                 ResponseFieldSpec('items[].SerialNo', 'string', '订单编号'),
                                 ResponseFieldSpec('items[].Title', 'string', '订单标题'),
                                 ResponseFieldSpec('items[].Status', 'int', '订单状态位（取值由上游定义）'),
                                 ResponseFieldSpec('items[].CancelStatus', 'int', '撤单状态位（取值由上游定义）'),
                                 ResponseFieldSpec('items[].Price', 'float', '订单金额（元）'),
                                 ResponseFieldSpec('items[].CreateDate', 'string', '发单时间'),
                                 ResponseFieldSpec('items[].Game', 'string', '游戏名称'),
                                 ResponseFieldSpec('items[].AcceptCount', 'string', '接单人数'),
                                 ResponseFieldSpec('total', 'int', '订单总数'),
                                 ResponseFieldSpec('page', 'int', '当前页码'),
                                 ResponseFieldSpec('page_size', 'int', '每页数量'),
                                 ResponseFieldSpec('total_pages', 'int', '总页数'),
                             ]),
                EndpointSpec('orders_owner_info', '号主信息', 'GET', '/api/dlt/orders/owner-info',
                             summary='获取订单的号主信息（游戏名称 / 客户端 / 游戏账号 / 密码 / 角色名 / 号主联系方式 / 剩余时间）。',
                             notes=['【前提】账号 / 密码 / 角色名只有**接单方**可见，需先在代练通接单后再调用；'
                                    '未接单时这些字段为空。'],
                             params=[
                                 ParamSpec('order_id', '订单ID', kind='text', required=True,
                                           desc='必填：订单号（SerialNo）'),
                                 _t_uid(), _t_token(),
                             ],
                             response_note='data 为号主信息对象（中文键）。',
                             response_fields=[
                                 ResponseFieldSpec('游戏名称', 'string', '游戏名称（如 王者荣耀）'),
                                 ResponseFieldSpec('客户端', 'string', '客户端 / 大区（如 安卓QQ、苹果微信）'),
                                 ResponseFieldSpec('游戏账号', 'string', '号主的游戏账号'),
                                 ResponseFieldSpec('密码', 'string', '号主的游戏密码'),
                                 ResponseFieldSpec('角色名', 'string', '游戏角色名'),
                                 ResponseFieldSpec('号主联系方式', 'string', '号主联系方式（手机号）'),
                                 ResponseFieldSpec('剩余时间', 'string', '订单剩余时间'),
                             ]),
                EndpointSpec('orders_upload_image', '订单留言传图', 'POST', '/api/dlt/orders/upload-image',
                             summary='向订单留言上传图片（传图片 URL/路径）。',
                             params=[
                                 _t_token(), _t_uid(),
                                 ParamSpec('image_path', '图片路径/URL', kind='text', required=True),
                                 ParamSpec('order_id', '订单ID', kind='text', required=True),
                             ],
                             response_note='data 为代练通订单留言接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('orders_upload_first_image', '上传首图', 'POST',
                             '/api/dlt/orders/upload-first-image',
                             summary='上传订单首图（接单后须在规定时间内上传；王者荣耀一般 2 张：好友天梯图 + 物品图）。',
                             notes=['服务端会先把图片转存到代练通图片存储，再逐张以「首图」留言挂到订单上'
                                    '（每张调一次上游接口）。',
                                    '失败时 msg 会指明是第几张出错，此前已挂上的图片仍然有效。'],
                             params=[
                                 ParamSpec('order_id', '订单ID', kind='text', required=True),
                                 ParamSpec('image_url_1', '第1张图片地址', kind='text', required=True,
                                           desc='必填：可访问的 http/https 图片链接（王者荣耀＝好友天梯图）'),
                                 ParamSpec('image_url_2', '第2张图片地址', kind='text', required=False,
                                           desc='选填：可访问的 http/https 图片链接（王者荣耀＝物品图）'),
                                 _t_uid(), _t_token(),
                             ],
                             response_note='data 含 images（已成功挂到订单上的图片地址）与 results（每张挂单的上游返回）。'),
                EndpointSpec('orders_upload_end_image', '上传完单图', 'POST',
                             '/api/dlt/orders/upload-end-image',
                             summary='上传订单完单图并申请完单（接单方上传完成凭证后，订单进入「等待验收」）。',
                             notes=['服务端会先把图片转存到代练通图片存储，再逐张以「完单图」留言挂到订单上'
                                    '（每张调一次上游接口）。',
                                    '全部图片挂完后自动发起「申请完单」，之后发单方即可验收。',
                                    '失败时 msg 会指明是第几张出错，此前已挂上的图片仍然有效。'],
                             params=[
                                 ParamSpec('order_id', '订单ID', kind='text', required=True),
                                 ParamSpec('image_url_1', '第1张完单图地址', kind='text', required=True,
                                           desc='必填：可访问的 http/https 图片链接'),
                                 ParamSpec('image_url_2', '第2张完单图地址', kind='text', required=False,
                                           desc='选填：可访问的 http/https 图片链接'),
                                 _t_uid(), _t_token(),
                             ],
                             response_note='data 含 images（已成功挂到订单上的图片地址）、results（每张挂单的上游返回）'
                                           '与 over（申请完单的上游返回）。'),
                # ---------- 头像 ----------
                EndpointSpec('avatar_upload', '上传头像', 'POST', '/api/dlt/avatar/upload',
                             summary='上传代练通头像（传图片 URL/路径，无需 token）。',
                             params=[_t_uid(),
                                     ParamSpec('image_path', '图片路径/URL', kind='text', required=True)],
                             response_note=_NULL_DATA_NOTE),
            ],
        ),
    ],
)
