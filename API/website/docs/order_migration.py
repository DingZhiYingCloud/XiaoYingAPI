"""代练搬单服务 - 接口文档与在线调试数据

数据与 API/apis/order_migration/ 实际实现对齐（服务策略 /api/order_migration/ 默认需签名）。
本服务只做「代练通订单 → 代练丸子发单参数」的映射换算，不触发真实发单。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

_ZONE_OPTIONS = [{'value': z, 'label': z} for z in ('安卓QQ', '苹果QQ', '安卓WX', '苹果WX')]


SERVICE = ServiceSpec(
    slug='order_migration',
    name='代练搬单',
    prefix='/api/order_migration/',
    summary='代练搬单：把代练通王者荣耀公开订单映射为代练丸子商家版发单参数（区服 / 标题 / 价格 / 双金），仅做映射预览，不真实发单。',
    keywords='代练搬单,代练通转代练丸子,代练订单搬运',
    intro=[
        '本服务把「代练通」的王者荣耀公开订单搬运到「代练丸子」：按固定规则把订单标题、'
        '区服、价格、时限换算成丸子商家版的发单参数。',
        '映射口径：丸子固定发「王者荣耀 / 排位」；区服以代练通订单的 Zone 为准（安卓 / 苹果 × QQ / 微信）；'
        '标题**原样照搬**代练通订单标题、不做解析；发布价 =(代练通价 − 代练通手续费) × 80%；'
        '双金（安全 / 效率保证金合计）= 发布价 × 双金倍数（后台可配 0-5，默认 2），两项均分。',
        '当前仅提供「预览映射」接口，不会真实发单；接单 / 监控 / 落库等能力后续在本服务内扩展。'
        '本服务需项目签名。',
    ],
    channels=[
        ChannelSpec(
            slug='mapping',
            name='订单映射',
            provider='代练通 → 代练丸子 参数映射',
            auth_note='auth',
            note='本项目侧需项目签名；本服务不直接调用第三方，只做参数换算。',
            endpoints=[
                EndpointSpec('order_migration_preview', '预览发单映射', 'POST',
                             '/api/order_migration/preview',
                             summary='把一笔代练通王者订单映射为代练丸子发单参数（不真实发单）。',
                             notes=['【用途】核对一笔代练通订单搬运到丸子后的发单参数是否正确。',
                                    '【成本口径】代练通王者·代练区·公共频道阶梯手续费：'
                                    '<20 元收 1；[20,50) 收 4；≥50 每 +50 元 +1（5 起），封顶 20。'],
                             params=[
                                 ParamSpec('title', '订单标题', kind='text', required=True,
                                           placeholder='星耀5 1星-星耀3 1星 铭文150级',
                                           desc='代练通订单标题，原样照搬为丸子订单标题'),
                                 ParamSpec('price', '订单金额(元)', kind='number', required=True,
                                           placeholder='43', desc='代练通订单金额'),
                                 ParamSpec('zone', '大区', kind='select', required=True,
                                           options=_ZONE_OPTIONS, default='安卓QQ',
                                           desc='代练通订单大区；WX 会自动映射为丸子的「微信」'),
                                 ParamSpec('time_limit', '时限(小时)', kind='number', required=True,
                                           placeholder='5', desc='代练通订单时限'),
                             ],
                             response_note='data 为映射后的代练丸子发单业务参数。',
                             response_fields=[
                                 ResponseFieldSpec('game_id', 'string', '游戏ID（固定 1=王者荣耀）'),
                                 ResponseFieldSpec('leveling_type_name', 'string', '代练类型（固定 排位）'),
                                 ResponseFieldSpec('region_name', 'string', '丸子区服（由代练通 Zone 映射）'),
                                 ResponseFieldSpec('title', 'string', '订单标题（照搬代练通原文）'),
                                 ResponseFieldSpec('hour', 'int', '代练时长（小时）'),
                                 ResponseFieldSpec('amount', 'float', '丸子发布价(元) =(代练通价 − 手续费) × 80%'),
                                 ResponseFieldSpec('security_deposit', 'float', '安全保证金(元) = 发布价 × 双金倍数 ÷ 2'),
                                 ResponseFieldSpec('efficiency_deposit', 'float', '效率保证金(元) = 发布价 × 双金倍数 ÷ 2'),
                                 ResponseFieldSpec('dlt_price', 'float', '代练通原价(元)，计算依据'),
                                 ResponseFieldSpec('dlt_cost', 'int', '代练通手续费(元)，计算依据'),
                             ]),
            ],
        ),
    ],
)
