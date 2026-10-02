"""代练通服务 - 接口文档与在线调试数据

数据与 API/apis/DaiLianTong/ 实际实现对齐（服务策略 /api/dlt/ 默认需签名）：
- 代练通（dlt.com）订单/用户操作封装：认证、用户资料、公共/个人订单查询与操作。
注意：多数接口需要「代练通平台账号」登录后拿到的 user_id / token；
涉及下单、接收订单、改密、上传等操作会产生真实影响，请在真实账号下谨慎调试。

响应说明：本服务是把代练通（dlt.com）上游接口原样透传封装（见 API/apis/DaiLianTong/ 与
SpiderServices/DaiLianTong/），data 结构由上游决定、随时可能变化，故大多不逐个承诺字段，
只说明 data 的构成方式；仅订单列表的敏感词过滤分支由本项目自己拼装，才写结构化字段表。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

_AUTH_DESC = '必填：平台登录令牌（代练通登录后返回）'
_UID_DESC = '必填：平台用户 ID（代练通登录/注册后返回）'
# 只回执行结果、data 恒为 null 的接口（设置个性签名 / 上传头像）共用同一说明
_NULL_DATA_NOTE = '执行结果由外层 code / msg 表达；data 为 null，不含业务数据。'


def _t_uid():
    return ParamSpec('user_id', '用户ID', kind='text', required=True, desc=_UID_DESC)


def _t_token():
    return ParamSpec('token', '登录令牌', kind='password', required=True, desc=_AUTH_DESC)


SERVICE = ServiceSpec(
    slug='dlt',
    name='代练通',
    prefix='/api/dlt/',
    summary='代练通平台能力：验证码登录注册、用户资料、公共/个人代练订单查询与操作（接收/发布/删除）、图片上传。',
    keywords='代练通API,代练订单接口,代练通数据',
    intro=[
        '代练通服务封装代练通平台的数据接口，覆盖验证码登录注册、用户资料与联系方式维护、'
        '头像与留言图片上传，以及公共订单、个人订单的查询与操作（发布、接收、删除）。',
        '调用链路上，登录成功后需携带返回的 user_id 与 token 继续调用后续接口；'
        '部分操作（如接收订单、发布订单）还需额外的支付密码或保证金等信息，请按参数说明谨慎传参。',
        '本服务需项目签名。发布、接收、删除等接口会真实作用于第三方平台的订单数据，'
        '调试时请避免在正式环境误操作。',
    ],
    channels=[
        ChannelSpec(
            slug='dlt',
            name='代练通订单平台',
            provider='代练通（dlt.com）网页接口封装',
            auth_note='auth',
            note='本项目侧需项目签名；业务侧还需先登录代练通取得 user_id / token。'
                 '含资金/下单等高风险操作，调试请务必使用自己的真实小号并谨慎操作。',
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
                # ---------- 订单 ----------
                EndpointSpec('orders_public', '公共订单列表', 'GET', '/api/dlt/orders/public',
                             summary='查询大厅公共代练订单（默认王者荣耀）。',
                             params=[
                                 _t_uid(), _t_token(),
                                 ParamSpec('page_index', '页码', kind='number', default='1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20'),
                                 ParamSpec('game_id', '游戏ID', kind='number', default='107',
                                           desc='默认 107=王者荣耀'),
                                 ParamSpec('price_str', '价格范围', kind='text', default='10_20',
                                           desc='格式 最低_最高，默认 10_20'),
                                 ParamSpec('is_pub', '是否公共', kind='text', default='1'),
                                 ParamSpec('search_str', '搜索关键词', kind='text'),
                                 ParamSpec('pg_type', '区服', kind='select',
                                           options=[{'value': '0', 'label': '0=全部（默认）'},
                                                    {'value': '1', 'label': '1=安卓'},
                                                    {'value': '2', 'label': '2=IOS'}]),
                                 ParamSpec('filter_sensitive', '过滤敏感词', kind='select',
                                           options=[{'value': 'false', 'label': 'false（默认）'},
                                                    {'value': 'true', 'label': 'true'}]),
                             ],
                             response_note='默认 data 为上游订单数组（字段由上游定义）；当 filter_sensitive=true 时，data 变为下列含过滤统计的对象。',
                             response_fields=[
                                 ResponseFieldSpec('orders', 'array', '过滤后保留的订单数组'),
                                 ResponseFieldSpec('total_count', 'int', '过滤前的订单总数'),
                                 ResponseFieldSpec('filtered_count', 'int', '被过滤的订单数'),
                                 ResponseFieldSpec('remaining_count', 'int', '过滤后剩余的订单数'),
                                 ResponseFieldSpec('filtered_reasons', 'array', '被过滤订单及命中的敏感词'),
                                 ResponseFieldSpec('filtered_reasons[].order_id', 'string', '被过滤的订单号'),
                                 ResponseFieldSpec('filtered_reasons[].title', 'string', '被过滤的订单标题'),
                                 ResponseFieldSpec('filtered_reasons[].matched_words', 'array', '命中该订单的敏感词'),
                             ]),
                EndpointSpec('orders_detail', '订单详情', 'GET', '/api/dlt/orders/detail',
                             summary='查询单个代练订单详情。',
                             params=[_t_uid(), _t_token(),
                                     ParamSpec('order_id', '订单ID', kind='text', required=True)],
                             response_note='data 为代练通订单详情接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('orders_receive', '接收订单', 'POST', '/api/dlt/orders/receive',
                             summary='接收（抢）一笔订单，需支付密码与 uid。',
                             params=[
                                 ParamSpec('order_id', '订单ID', kind='text', required=True),
                                 ParamSpec('pay_pass', '支付密码', kind='password', required=True),
                                 ParamSpec('uid', 'UID', kind='text', required=True),
                                 _t_token(), _t_uid(),
                             ],
                             response_note='data 为代练通接收订单接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('orders_publish', '发布订单', 'POST', '/api/dlt/orders/publish',
                             summary='发布一笔代练订单（需较多游戏/保证金/支付信息，含真实下单）。',
                             params=[
                                 ParamSpec('title', '订单标题', kind='text', required=True),
                                 ParamSpec('uid', 'UID', kind='text', required=True),
                                 ParamSpec('price', '价格', kind='text', required=True),
                                 ParamSpec('time_limit', '代练时长', kind='text', required=True),
                                 _t_token(), _t_uid(),
                                 ParamSpec('ensure1', '安全保证金', kind='text', required=True),
                                 ParamSpec('ensure2', '效率保证金', kind='text', required=True),
                                 ParamSpec('game_mobile', '号主联系方式', kind='text', required=True),
                                 ParamSpec('pay_pass', '支付密码', kind='password', required=True),
                                 ParamSpec('game_account', '游戏账号', kind='text', required=True),
                                 ParamSpec('game_password', '游戏密码', kind='password', required=True),
                                 ParamSpec('game_author_name', '游戏角色名', kind='text', required=True),
                                 ParamSpec('hero_count', '英雄数量', kind='number', default='10'),
                                 ParamSpec('requirements', '代练要求', kind='textarea',
                                           desc='选填：默认提供平台通用要求文案'),
                                 ParamSpec('zone_server_id', '游戏区服ID', kind='text',
                                           default='107103017095500', desc='默认王者荣耀区服'),
                             ],
                             response_note='data 为代练通发布订单接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('orders_delete', '删除订单', 'POST', '/api/dlt/orders/delete',
                             summary='删除自己的订单（默认原因“不用了”）。',
                             params=[ParamSpec('order_id', '订单ID', kind='text', required=True),
                                     _t_token(), _t_uid(),
                                     ParamSpec('reason', '删除原因', kind='text', default='不用了')],
                             response_note='data 为代练通删除订单接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
                EndpointSpec('orders_my', '我的订单', 'GET', '/api/dlt/orders/my',
                             summary='查询我的代练订单（进行中/已完成）。',
                             params=[
                                 _t_token(), _t_uid(),
                                 ParamSpec('page_index', '页码', kind='number', default='1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20'),
                                 ParamSpec('over_days', '状态', kind='text', default='-99',
                                           desc='-99=正在进行（默认），99=已完成'),
                                 ParamSpec('search_str', '搜索关键词', kind='text'),
                             ],
                             response_note='data 为上游「我的订单」接口 LevelOrderList 字段的订单数组（原样透传），每项字段由上游定义。'),
                EndpointSpec('orders_upload_image', '订单留言传图', 'POST', '/api/dlt/orders/upload-image',
                             summary='向订单留言上传图片（传图片 URL/路径）。',
                             params=[
                                 _t_token(), _t_uid(),
                                 ParamSpec('image_path', '图片路径/URL', kind='text', required=True),
                                 ParamSpec('order_id', '订单ID', kind='text', required=True),
                             ],
                             response_note='data 为代练通订单留言接口返回的原始 JSON 对象（原样透传），字段由上游定义。'),
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
