"""代练丸子服务 - 接口文档与在线调试数据

数据与 API/apis/DaiLianWanZi/ 实际实现对齐（服务策略 /api/dlwz/ 默认需签名）：
- 代练丸子分两条线路：打手版（建设中）/ 商家版（认证、用户资料、余额、我的订单）。
注意：多数接口的 authorization 为选填（形如 "Bearer xxx"），不传则用后台托管默认账号。

响应说明：本服务是把代练丸子（llwanzi.com）上游接口原样透传封装（见 API/apis/DaiLianWanZi/
与 SpiderServices/DaiLianWanZi/），data 即上游完整响应对象、结构由上游决定且可能随时变化，
故不逐个承诺字段，统一说明其构成方式。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

# 全部接口均为上游透传：data 由上游决定、可能随时变化，不承诺具体字段，故抽为常量复用
_UPSTREAM_NOTE = 'data 为上游接口返回的完整响应对象（原样透传，含上游自身的 code / message / data），字段由上游定义。'


def _auth(desc='选填：平台登录令牌，形如 "Bearer xxx"；不传则用后台「账号管理」的默认代练丸子账号'):
    return ParamSpec('authorization', '登录令牌(authorization)', kind='password', required=False, desc=desc)


SERVICE = ServiceSpec(
    slug='dlwz',
    name='代练丸子',
    prefix='/api/dlwz/',
    summary='代练丸子平台能力：验证码登录、用户资料/头像/实名/签到、余额查询；商家版「我的订单」（分类与列表）与「发布订单」（发单选项 / 一键发单）。',
    keywords='代练丸子API,代练订单接口,代练丸子发单',
    intro=[
        '代练丸子分**打手版**与**商家版**两条线路：打手版接口正在建设中；'
        '商家版提供验证码登录（服务端自动完成图形验证码识别）、用户资料与头像维护、'
        '实名查询、每日签到、余额查询，「我的订单」（订单分类与订单列表），'
        '以及**发布订单**（发单选项查询 + 一键发单）。',
        '验证码登录对未注册手机号会自动注册，适合需要批量接入账号的场景；'
        '登录后使用返回的授权信息继续调用后续接口。',
        '本服务需项目签名；`authorization` 为**选填**——不传时自动使用本站「账号管理」里'
        '维护的默认代练丸子账号，与代练通口径一致。',
    ],
    channels=[
        # ---------- 打手版（建设中） ----------
        ChannelSpec(
            slug='player',
            name='打手版',
            provider='代练丸子（llwanzi.com）打手版接口',
            auth_note='auth',
            note='打手版接口正在建设中，暂不可用。',
            endpoints=[
                EndpointSpec('player_coming_soon', '打手版接口（建设中）', 'GET', '/api/dlwz/player',
                             summary='打手版接口正在建设中，暂不可用。',
                             response_note='该线路尚未接入，统一返回 50002 服务建设中（data 为 null）。'),
            ],
        ),
        # ---------- 商家版 ----------
        ChannelSpec(
            slug='business',
            name='商家版',
            provider='代练丸子（llwanzi.com）商家版接口封装',
            auth_note='auth',
            note='本项目侧需项目签名；业务侧 authorization 选填——不传则用后台「账号管理」的默认代练丸子账号。',
            endpoints=[
                # ---------- 认证 ----------
                EndpointSpec('auth_send_code', '发送验证码', 'POST', '/api/dlwz/auth/send-code',
                             summary='发送登录验证码（内部自动完成图形验证码识别）。',
                             params=[ParamSpec('phone', '手机号', kind='text', required=True, placeholder='13800138000')],
                             response_note=_UPSTREAM_NOTE),
                EndpointSpec('auth_login', '登录', 'POST', '/api/dlwz/auth/login',
                             summary='验证码或密码登录；未注册手机号用验证码登录会自动注册。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True),
                                 ParamSpec('code', '验证码或密码', kind='password', required=True),
                                 ParamSpec('code_type', '登录方式', kind='select',
                                           options=[{'value': 'VerificationCode', 'label': 'VerificationCode（验证码，默认）'},
                                                    {'value': 'Password', 'label': 'Password（密码）'}],
                                           default='VerificationCode'),
                             ],
                             response_note=_UPSTREAM_NOTE),
                # ---------- 用户 ----------
                EndpointSpec('user_info', '用户信息', 'GET', '/api/dlwz/user/info',
                             summary='获取当前登录用户信息。', params=[_auth()],
                             response_note=_UPSTREAM_NOTE),
                EndpointSpec('user_upload_avatar', '上传头像', 'POST', '/api/dlwz/user/upload-avatar',
                             summary='设置头像（传图片 URL）。',
                             params=[_auth(),
                                     ParamSpec('image', '头像图片URL', kind='text', required=True,
                                               placeholder='https://…/avatar.png')],
                             response_note=_UPSTREAM_NOTE),
                EndpointSpec('user_set_profile', '设置个性信息', 'POST', '/api/dlwz/user/set-profile',
                             summary='设置用户名/签名/QQ（username 必填，其它按需传）。',
                             params=[
                                 _auth(),
                                 ParamSpec('username', '用户名', kind='text', required=True),
                                 ParamSpec('signature', '个性签名', kind='text'),
                                 ParamSpec('qq', 'QQ号', kind='text'),
                             ],
                             response_note=_UPSTREAM_NOTE),
                EndpointSpec('user_real_name', '实名认证信息', 'GET', '/api/dlwz/user/real-name',
                             summary='查询实名认证信息。', params=[_auth()],
                             response_note=_UPSTREAM_NOTE),
                EndpointSpec('user_sign_in', '签到', 'POST', '/api/dlwz/user/sign-in',
                             summary='每日签到。', params=[_auth()],
                             response_note=_UPSTREAM_NOTE),
                # ---------- 财务 ----------
                EndpointSpec('user_balance', '我的余额', 'GET', '/api/dlwz/user/balance',
                             summary='查询账号余额（不传 authorization 时用后台默认账号）。',
                             params=[_auth()],
                             response_note=_UPSTREAM_NOTE),
                # ---------- 发单 ----------
                EndpointSpec('business_games', '获取全部游戏', 'GET', '/api/dlwz/business/games',
                             summary='商家版发单用：全部游戏（仅 id + 名称，代练丸子没有「每个游戏的订单数」）。',
                             params=[_auth()],
                             response_note='data 为游戏数组 [{game_id, game_name}]，热门游戏在前（如 1=王者 / 134=三角洲行动）。',
                             response_fields=[
                                 ResponseFieldSpec('game_id', 'int', '游戏ID'),
                                 ResponseFieldSpec('game_name', 'string', '游戏名称'),
                             ]),
                EndpointSpec('business_order_options', '获取发单选项', 'GET', '/api/dlwz/business/order-options',
                             summary='商家版发单用：大区 + 代练类型 +（指定代练类型时）子类型字段（段位 / 数量等）。',
                             notes=['【怎么用】先调「获取全部游戏」拿 `game_id` → 调本接口拿 `regions` 与 `leveling_types` '
                                    '→ 想发某个代练类型时，再把该类型的 `leveling_type_id` 传进来，拿到它的字段与可选值。',
                                    '【字段类型】`fields[].type`：1=单选（带 `options`）、5=数字（带 `min_val/max_val`）、'
                                    '6=段位区间（带 `levels`，如「青铜3段0星」「王者50星」）。'],
                             params=[
                                 ParamSpec('game_id', '游戏ID', kind='number', required=True,
                                           desc='必填：游戏ID（由「获取全部游戏」取到）'),
                                 ParamSpec('leveling_type_id', '代练类型ID', kind='number',
                                           desc='选填：代练类型ID；传了才返回该类型的子类型字段（段位/数量等）'),
                                 _auth(),
                             ],
                             response_note='data 含 `regions`（大区，server 为默认服）、`leveling_types`（代练类型）、'
                                           '`fields`（子类型字段：下拉类带 options、段位类带 levels、数字类带 min_val/max_val）。'),
                EndpointSpec('business_orders_publish', '发布订单', 'POST', '/api/dlwz/business/orders/publish',
                             summary='商家版发布订单（真实下单）：用上方「发单选项」面板选游戏/大区/代练类型与任务字段即可，免填 JSON。',
                             dlwz_publish=True,
                             notes=['【怎么填】用上方「发单选项」面板：选游戏 → 大区 → 代练类型，任务字段'
                                    '（段位 / 数量 / 下拉）会自动出现并按预设预填；面板会把 `game_id` / `region_name` / '
                                    '`leveling_type_name` / `tasks` 一并带给接口（**不用手写 JSON**）。'
                                    '选王者只显示王者的字段，选三角洲只显示三角洲的字段。',
                                    '【会真实下单】按传入价格从商家余额扣款；取消用「取消订单」接口（金额原路退回）。',
                                    '【不传也能发】`game_id`=1（王者）/ 134（三角洲）有内置预设'
                                    '（王者=排位/安卓QQ/青铜3段0星→王者50星/铭文150/英雄170；'
                                    '三角洲=哈夫币代刷/手机QQ/哈夫币100万/代肝/保险箱2格），面板已按此预填。',
                                    '【上号方式】`login_method`=2 账密上号（配 `game_account/game_password/game_role`）；'
                                    '1 扫码上号（账号字段自动填「扫码上号」）。',
                                    '【加急服务包】默认不加（不会带 `insuranceProductId`）。',
                                    '【标题】不传 `title` 时按上游规则自动生成，并追加默认提示'
                                    '「私单勿接，指定单，接了扣除双金」。'],
                             params=[
                                 ParamSpec('amount', '订单价格(元)', kind='number', default='2'),
                                 ParamSpec('hour', '代练时长(小时)', kind='number', default='3'),
                                 ParamSpec('security_deposit', '安全保证金(元)', kind='number', default='2'),
                                 ParamSpec('efficiency_deposit', '效率保证金(元)', kind='number', default='2'),
                                 ParamSpec('login_method', '上号方式', kind='select', default='2',
                                           options=[{'value': '2', 'label': '2=账密上号（默认）'},
                                                    {'value': '1', 'label': '1=扫码上号'}]),
                                 ParamSpec('game_account', '游戏账号', kind='text'),
                                 ParamSpec('game_password', '游戏密码', kind='password'),
                                 ParamSpec('game_role', '游戏角色名', kind='text'),
                                 ParamSpec('player_phone', '号主手机', kind='text'),
                                 ParamSpec('contact_phone', '发单方联系方式', kind='text'),
                                 ParamSpec('contact_qq', '其它联系方式', kind='text'),
                                 ParamSpec('title', '订单标题', kind='text',
                                           desc='选填：留空则按上游规则自动生成（并追加默认提示）'),
                                 ParamSpec('subtitle', '副标题', kind='text',
                                           desc='选填：会拼进标题（ 备注：…）'),
                                 ParamSpec('explain', '代练说明', kind='textarea',
                                           desc='选填：留空取上游默认文案'),
                                 ParamSpec('requirement', '代练要求', kind='textarea',
                                           desc='选填：留空取上游默认文案'),
                                 ParamSpec('take_password', '接单密码', kind='password',
                                           desc='选填：仅指定打手可接时使用'),
                                 _auth(),
                             ],
                             response_note='data 为 {"trade_no": 订单号, "status": 状态}。注意：会真实发布订单。',
                             response_fields=[
                                 ResponseFieldSpec('trade_no', 'string', '订单号（如 WZ20261004121317927440）'),
                                 ResponseFieldSpec('status', 'int', '订单状态（2=待付待接）'),
                             ]),
                # ---------- 我的订单 ----------
                EndpointSpec('business_order_tabs', '订单分类', 'GET', '/api/dlwz/business/order-tabs',
                             summary='商家版「我的订单」页顶部分类（含各分类订单数量），分类值传给「我的订单」做筛选。',
                             params=[_auth()],
                             response_note='data 为上游完整响应对象（原样透传）：分类数组在上游 data.tableList，'
                                           '每项含 table_type / table_name / count；常见取值：0=全部、101=待付待接、'
                                           '102=代练中、103=待验收、104=撤销中、105=仲裁中、106=已撤销、107=已仲裁、'
                                           '108=已结算、109=异常中、110=锁定中、111=已取消。'),
                EndpointSpec('business_orders', '我的订单', 'GET', '/api/dlwz/business/orders',
                             summary='商家版我的订单：按分类筛选 + 关键词搜索 + 分页。',
                             notes=['【分类怎么取】先调「订单分类」接口拿到 table_type（0=全部 / 101=待付待接 …），'
                                    '再作为本接口的 table_type 参数传入。'],
                             params=[
                                 ParamSpec('table_type', '订单分类', kind='number', default='0',
                                           desc='订单分类，默认 0=全部；取值来自「订单分类」接口的 table_type'),
                                 ParamSpec('keyword', '搜索关键词', kind='text',
                                           desc='按标题 / 角色名 / 订单号 / 号主手机搜索，默认空'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='从 1 开始，默认 1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20',
                                           desc='1-100，默认 20'),
                                 _auth(),
                             ],
                             response_note='data 为上游完整响应对象（原样透传）：分页在上游 data.page'
                                           '（pageNo / pageSize / totalPage / totalCount），'
                                           '订单数组在上游 data.ordersList。'),
                EndpointSpec('business_orders_cancel', '取消订单', 'POST', '/api/dlwz/business/orders/cancel',
                             summary='商家版取消已发布的订单（待付待接等可取消状态）。',
                             notes=['【会真实改变订单状态】仅「待付待接」等可取消状态可取消；'
                                    '取消后订单金额**原路退回**商家余额（实测 2 元订单取消后余额 +2）。'],
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True,
                                           desc='必填：订单号（「发布订单」返回的 trade_no，如 WZ20261004121328255441）'),
                                 _auth(),
                             ],
                             response_note='data 为上游完整响应对象（原样透传）。'),
                EndpointSpec('business_hall_search', '搜索订单（接单大厅）', 'GET',
                             '/api/dlwz/business/hall/search',
                             summary='搜索接单大厅的订单：关键词 / 游戏筛选 + 分页。',
                             notes=['【用途】接单前找单：拿到 `trade_no` 后可用「大厅订单详情」核对，'
                                    '再调「接单」接手。',
                                    '【分页】上游用 `pageNo`/`pageSize`（对外仍是 `page`/`page_size`）。',
                                    '【热搜词】搜索框推荐词见「大厅热搜词」接口。'],
                             params=[
                                 ParamSpec('keyword', '搜索关键词', kind='text', placeholder='王者',
                                           desc='选填：标题 / 角色名 / 段位等；不传按默认顺序返回'),
                                 ParamSpec('game_id', '游戏ID', kind='number',
                                           desc='选填：按游戏筛选（见「获取全部游戏」）'),
                                 ParamSpec('page', '页码', kind='number', default='1', desc='默认 1'),
                                 ParamSpec('page_size', '每页数量', kind='number', default='20',
                                           desc='1-100，默认 20'),
                                 _auth(),
                             ],
                             response_note='data 为上游完整响应对象：分页在 data.page'
                                           '（pageNo / pageSize / totalPage / totalCount），'
                                           '订单数组在 data.ordersList。'),
                EndpointSpec('business_hall_words', '大厅热搜词', 'GET', '/api/dlwz/business/hall/words',
                             summary='接单大厅搜索框的推荐热词。',
                             params=[_auth()],
                             response_note='data.wordList 为热词数组。'),
                EndpointSpec('business_hall_detail', '大厅订单详情', 'GET', '/api/dlwz/business/hall/detail',
                             summary='按订单号查看大厅订单详情（接单前核对金额 / 双金 / 区服 / 代练要求）。',
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True,
                                           desc='必填：订单号（「搜索订单」返回的 tradeNo）'),
                                 _auth(),
                             ],
                             response_note='data 为上游订单对象：amount / hour / securityDeposit / '
                                           'efficiencyDeposit / totalDeposit / title / gameRegionName 等。'),
                EndpointSpec('business_take_password_check', '接单密码校验', 'POST',
                             '/api/dlwz/business/orders/take-password-check',
                             summary='指定单接单前校验「接单密码」。',
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True),
                                 ParamSpec('take_password', '接单密码', kind='text', required=True),
                                 _auth(),
                             ],
                             response_note='密码正确返回 code=10000。'),
                EndpointSpec('business_take_order', '接单', 'POST', '/api/dlwz/business/orders/take',
                             summary='接单（真实接手，双金从接单方余额冻结）。',
                             notes=['【会真实接单】成功后订单进入「代练中」，并按 安全保证金 + 效率保证金'
                                    '从**接单方余额**冻结双金（实测 2 元订单双金 2+2=4 元）。',
                                    '【支付密码必填】缺 `pay_password` 会被上游拒绝（接单流程处理异常）。',
                                    '【指定单】需要「接单密码」，可先用「接单密码校验」确认。',
                                    '【重复接单】已被接手的单上游返回「该订单已被接手」，本接口映射为 40001。'],
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True,
                                           desc='必填：订单号（「搜索订单」/「大厅订单详情」得到）'),
                                 ParamSpec('pay_password', '支付密码', kind='text', required=True,
                                           desc='必填：本账号支付密码，用于冻结双金'),
                                 ParamSpec('take_password', '接单密码', kind='text',
                                           desc='选填：指定单才需要（可先用「接单密码校验」）'),
                                 _auth(),
                             ],
                             response_note='data 为上游响应对象，含 noneBalanceEnough / noneSetPayPwd / '
                                           'noneRealNameAuth 等校验标记。'),
                EndpointSpec('business_apply_revocation', '申请撤销', 'POST',
                             '/api/dlwz/business/orders/revoke',
                             summary='申请撤销（提前终止代练），需对方同意才生效。',
                             notes=['【流程】申请后订单进入「撤销中」(status=5)，对方「同意撤销」后按资金分配方案结算。',
                                    '【凭证图片必填】上游强制要求先关联凭证图片，缺 `images` 会被拒（「请补充传图」）。',
                                    '【资金分配】`pay_amount` = 我愿支付的代练费（打手未开始代练填 0）；'
                                    '`deposit` = 对方需赔付的保证金（对方无违规填 0）。',
                                    '【initiator】1=发单方 / 2=接单方（本方身份）。',
                                    '【原因必填】`reason` 写清订单进度 + 撤销理由，客服据此处理。'],
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True),
                                 ParamSpec('initiator', '发起方', kind='select', required=True, default='1',
                                           options=[{'value': '1', 'label': '1 = 发单方'},
                                                    {'value': '2', 'label': '2 = 接单方'}]),
                                 ParamSpec('reason', '撤销理由', kind='text', required=True,
                                           placeholder='未开始代练，双方无违规，资金分配填 0'),
                                 ParamSpec('images', '凭证图片', kind='textarea', required=True,
                                           placeholder='["https://example.com/a.png"]',
                                           desc='必填：凭证图片URL列表（JSON 字符串数组，至少一张）'),
                                 ParamSpec('deposit', '对方赔付保证金(元)', kind='number', default='0',
                                           desc='选填：对方无违规填 0'),
                                 ParamSpec('pay_amount', '我愿支付代练费(元)', kind='number', default='0',
                                           desc='选填：打手未开始代练填 0'),
                                 ParamSpec('if_auto_arbitrate', '超时自动仲裁', kind='select', default='0',
                                           options=[{'value': '0', 'label': '否'}, {'value': '1', 'label': '是'}],
                                           desc='选填：对方超时未处理是否自动转仲裁（接单方发起时可用）'),
                                 _auth(),
                             ],
                             response_note='成功返回 code=10000。'),
                EndpointSpec('business_agree_revocation', '同意撤销', 'POST',
                             '/api/dlwz/business/orders/revoke/agree',
                             summary='同意对方的撤销申请（生效后按申请单的资金分配方案结算）。',
                             notes=['【会真实结算】同意后订单变为「已完结」，双金 / 代练金按申请单释放'
                                    '（实测：双方都填 0 时，接单方 4 元双金原路退回）。',
                                    '【支付密码】发单方同意时上游要求 `pay_password` 必填；接单方可省略。'],
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True),
                                 ParamSpec('pay_password', '支付密码', kind='password',
                                           desc='选填：发单方同意时必填；接单方可省略'),
                                 _auth(),
                             ],
                             response_note='data 含 revocationsDataBean（撤销单详情）。'),
                EndpointSpec('business_cancel_revocation', '取消撤销', 'POST',
                             '/api/dlwz/business/orders/revoke/cancel',
                             summary='撤回已提交的撤销申请。',
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True),
                                 _auth(),
                             ],
                             response_note='订单状态已变更等场景返回 40001。'),
                EndpointSpec('business_apply_arbitration', '申请仲裁', 'POST',
                             '/api/dlwz/business/orders/arbitrate',
                             summary='申请平台仲裁（订单产生争议时）。',
                             notes=['【凭证图片必填】上游强制要求先关联举证图片，缺 `images` 会被拒。',
                                    '【不可撤销】仲裁发起后只能等待平台处理（预计 48 小时内）。'],
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True),
                                 ParamSpec('initiator', '操作方', kind='select', required=True, default='1',
                                           options=[{'value': '1', 'label': '1 = 发单方'},
                                                    {'value': '2', 'label': '2 = 接单方'}]),
                                 ParamSpec('reason', '仲裁理由', kind='text', required=True),
                                 ParamSpec('images', '举证图片', kind='textarea', required=True,
                                           placeholder='["https://example.com/a.png"]',
                                           desc='必填：举证图片URL列表（JSON 字符串数组，至少一张）'),
                                 ParamSpec('amount', '争议代练费(元)', kind='number', default='0'),
                                 ParamSpec('deposit', '争议保证金(元)', kind='number', default='0'),
                                 ParamSpec('opera_type', '操作类型', kind='select', default='0',
                                           options=[{'value': '0', 'label': '0'}, {'value': '1', 'label': '1'}]),
                                 _auth(),
                             ],
                             response_note='成功返回 code=10000。'),
                EndpointSpec('business_accept_completion', '同意验收并结账', 'POST',
                             '/api/dlwz/business/orders/accept-completion',
                             summary='同意打手的完单申请，订单结算、款项放给打手。',
                             notes=['【会真实结算】同意后订单变为「已结算」，代练金结算给打手、双金解冻。',
                                    '【支付密码】不传 `pay_password` 时，自动用后台「账号管理」丸子凭据里的 '
                                    '`pay_password`；两处都没有则报错。',
                                    '【前置条件】丸子订单需处于「待验收」（打手已提交完单图）状态。'],
                             params=[
                                 ParamSpec('trade_no', '订单号', kind='text', required=True),
                                 ParamSpec('pay_password', '支付密码', kind='password',
                                           desc='选填：不传则用后台账号凭据里的 pay_password'),
                                 _auth(),
                             ],
                             response_note='成功返回 code=10000。'),
            ],
        ),
    ],
)
