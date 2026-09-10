"""代练丸子服务 - 接口文档与在线调试数据

数据与 API/apis/DaiLianWanZi/ 实际实现对齐（分类树 /api/dlwz/ 需项目签名）：
- 代练丸子（llwanzi.com）能力封装：认证、用户资料、公共/个人订单查询与发布取消、余额。
注意：多数接口需要代练丸子平台登录后的 authorization（形如 "Bearer xxx"）；
发布/取消订单等操作会真实作用于账号，请用小号谨慎调试。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec


def _auth(desc='必填：平台登录令牌，形如 "Bearer xxx"'):
    return ParamSpec('authorization', '登录令牌(authorization)', kind='password', required=True, desc=desc)


def _int_opt(name, label, default, desc=''):
    return ParamSpec(name, label, kind='number', default=str(default), desc=desc or '选填')


SERVICE = ServiceSpec(
    slug='dlwz',
    name='代练丸子',
    prefix='/api/dlwz/',
    summary='代练丸子平台能力：验证码登录、用户资料/头像/实名/签到、公共与搜索订单、发布/取消订单、余额查询。',
    channels=[
        ChannelSpec(
            slug='dlwz',
            name='代练丸子平台',
            provider='代练丸子（llwanzi.com）网页接口封装',
            auth_note='auth',
            note='本项目侧需项目签名；业务侧需先登录取得 authorization。发布/取消订单等操作会产生真实影响，请谨慎。',
            endpoints=[
                # ---------- 认证 ----------
                EndpointSpec('auth_send_code', '发送验证码', 'POST', '/api/dlwz/auth/send-code',
                             summary='发送登录验证码（内部自动完成图形验证码识别）。',
                             params=[ParamSpec('phone', '手机号', kind='text', required=True, placeholder='13800138000')]),
                EndpointSpec('auth_login', '登录', 'POST', '/api/dlwz/auth/login',
                             summary='验证码或密码登录；未注册手机号用验证码登录会自动注册。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True),
                                 ParamSpec('code', '验证码或密码', kind='password', required=True),
                                 ParamSpec('code_type', '登录方式', kind='select',
                                           options=[{'value': 'VerificationCode', 'label': 'VerificationCode（验证码，默认）'},
                                                    {'value': 'Password', 'label': 'Password（密码）'}],
                                           default='VerificationCode'),
                             ]),
                # ---------- 用户 ----------
                EndpointSpec('user_info', '用户信息', 'GET', '/api/dlwz/user/info',
                             summary='获取当前登录用户信息。', params=[_auth()]),
                EndpointSpec('user_upload_avatar', '上传头像', 'POST', '/api/dlwz/user/upload-avatar',
                             summary='设置头像（传图片 URL）。',
                             params=[_auth(),
                                     ParamSpec('image', '头像图片URL', kind='text', required=True,
                                               placeholder='https://…/avatar.png')]),
                EndpointSpec('user_set_profile', '设置个性信息', 'POST', '/api/dlwz/user/set-profile',
                             summary='设置用户名/签名/QQ（username 必填，其它按需传）。',
                             params=[
                                 _auth(),
                                 ParamSpec('username', '用户名', kind='text', required=True),
                                 ParamSpec('signature', '个性签名', kind='text'),
                                 ParamSpec('qq', 'QQ号', kind='text'),
                             ]),
                EndpointSpec('user_real_name', '实名认证信息', 'GET', '/api/dlwz/user/real-name',
                             summary='查询实名认证信息。', params=[_auth()]),
                EndpointSpec('user_sign_in', '签到', 'POST', '/api/dlwz/user/sign-in',
                             summary='每日签到。', params=[_auth()]),
                # ---------- 订单 ----------
                EndpointSpec('orders_public', '公共订单列表', 'GET', '/api/dlwz/orders/public',
                             summary='大厅公共订单（默认王者、价格 10-50）。',
                             params=[
                                 _auth(),
                                 _int_opt('price_gt', '最低价格', 10),
                                 _int_opt('price_lt', '最高价格', 50),
                                 _int_opt('page_no', '页码', 1),
                                 _int_opt('page_size', '每页数量', 30),
                                 ParamSpec('game_id', '游戏ID', kind='number', default='1', desc='1=王者（默认）'),
                             ]),
                EndpointSpec('orders_search', '搜索订单', 'GET', '/api/dlwz/orders/search',
                             summary='按关键词搜索订单。',
                             params=[_auth(),
                                     ParamSpec('keyword', '关键词', kind='text', required=True),
                                     _int_opt('page_no', '页码', 1),
                                     _int_opt('page_size', '每页数量', 10)]),
                EndpointSpec('orders_detail', '订单详情', 'GET', '/api/dlwz/orders/detail',
                             summary='查询单个订单详情。',
                             params=[_auth(),
                                     ParamSpec('order_id', '订单ID', kind='text', required=True)]),
                EndpointSpec('orders_publish', '发布订单', 'POST', '/api/dlwz/orders/publish',
                             summary='发布一笔代练订单（默认王者/排位/安卓QQ，真实下单）。',
                             params=[
                                 _auth(),
                                 ParamSpec('title', '订单标题', kind='text', required=True),
                                 ParamSpec('amount', '订单金额(元)', kind='text', required=True),
                                 ParamSpec('hour', '代练时长(小时)', kind='number', required=True),
                                 ParamSpec('security_deposit', '安全保证金', kind='text', required=True),
                                 ParamSpec('efficiency_deposit', '效率保证金', kind='text', required=True),
                                 ParamSpec('player_phone', '号主手机号', kind='text', default='3837190115'),
                                 ParamSpec('contact_phone', '发单方联系方式', kind='text', default='3837190115'),
                                 ParamSpec('game_region_name', '游戏区域', kind='select',
                                           options=[{'value': '安卓QQ', 'label': '安卓QQ（默认）'},
                                                    {'value': '安卓微信', 'label': '安卓微信'},
                                                    {'value': '苹果QQ', 'label': '苹果QQ'},
                                                    {'value': '苹果微信', 'label': '苹果微信'}],
                                           default='安卓QQ'),
                                 ParamSpec('hero_number', '英雄数量', kind='number'),
                                 ParamSpec('requirement', '代练要求', kind='textarea', default='代练要求'),
                                 ParamSpec('explain_text', '订单说明', kind='textarea', default='代练说明'),
                                 ParamSpec('game_account', '游戏账号', kind='text', default='扫码上号'),
                                 ParamSpec('game_password', '游戏密码', kind='password', default='扫码上号'),
                                 ParamSpec('contact_qq', '其他联系方式', kind='text', default='扫码上号'),
                                 ParamSpec('game_role', '游戏角色', kind='text', default='扫码上号'),
                                 _int_opt('game_id', '游戏ID', 1, '1=王者'),
                                 _int_opt('game_server_id', '服务器ID', 122, '122=安卓QQ'),
                                 _int_opt('game_region_id', '区域ID', 2, '2=安卓QQ'),
                                 ParamSpec('game_icon', '游戏图标URL', kind='text',
                                           desc='选填：默认平台图标'),
                                 ParamSpec('game_name', '游戏名称', kind='text', default='王者'),
                                 ParamSpec('game_leveling_type_name', '代练类型', kind='text', default='排位'),
                             ]),
                EndpointSpec('orders_cancel', '取消订单', 'POST', '/api/dlwz/orders/cancel',
                             summary='取消订单。',
                             params=[ParamSpec('order_id', '订单ID', kind='text', required=True),
                                     _auth(desc='选填：平台登录令牌')]),
                # ---------- 财务 ----------
                EndpointSpec('user_balance', '我的余额', 'GET', '/api/dlwz/user/balance',
                             summary='查询账号余额（authorization 选填）。',
                             params=[_auth(desc='选填：平台登录令牌')]),
            ],
        ),
    ],
)
