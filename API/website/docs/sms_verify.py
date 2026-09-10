"""短信验证服务 - 接口文档与在线调试数据

数据与 API/apis/sms_verify/ 实际实现对齐（分类树 /api/sms_verify/ 为需签名）：
- 阿里云 aliyun：阿里云号码认证（Dypnsapi）发送/核验短信验证码，两个 POST 接口。
后续接入更多短信渠道（如三网、国际短信等）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

# 重复发送处理：覆盖旧码 / 保留旧码
_DUP_POLICY = [
    {'value': '1', 'label': '1（覆盖旧码，默认）'},
    {'value': '2', 'label': '2（保留旧码）'},
]
# 大小写核验策略
_CASE_POLICY = [
    {'value': '1', 'label': '1（不区分大小写，默认）'},
    {'value': '2', 'label': '2（区分大小写）'},
]
# 是否返回验证码
_RETURN_CODE = [
    {'value': 'false', 'label': 'false（不返回，默认）'},
    {'value': 'true', 'label': 'true（返回验证码，仅测试场景建议开启）'},
]


def _phone_param(required=True):
    return ParamSpec('phone', '手机号', kind='text', required=required,
                     placeholder='13800138000', desc='11 位手机号（必填）')


def _out_id_param():
    return ParamSpec('out_id', '外部流水号', kind='text',
                     desc='选填：外部流水号（透传返回）')


SERVICE = ServiceSpec(
    slug='sms_verify',
    name='短信验证',
    prefix='/api/sms_verify/',
    summary='短信验证码能力：阿里云号码认证发送与核验，服务端生成/校验验证码，防短信轰炸。当前接入阿里云线路。',
    channels=[
        ChannelSpec(
            slug='aliyun',
            name='阿里云短信验证码',
            provider='阿里云号码认证服务（Dypnsapi）',
            auth_note='auth',
            note='发送验证码由阿里云系统动态生成并完成核验；全部接口需接入项目签名，防短信被滥用。',
            endpoints=[
                EndpointSpec('send', '发送短信验证码', 'POST', '/api/sms_verify/aliyun/send',
                             summary='向指定手机号发送短信验证码；验证码有效期、频控间隔等可配。',
                             params=[
                                 _phone_param(),
                                 ParamSpec('code_length', '验证码长度', kind='number', default='4',
                                           desc='选填：4-8，默认 4'),
                                 ParamSpec('valid_time', '有效时长(秒)', kind='number', default='300',
                                           desc='选填：验证码有效时长，默认 300 秒（5 分钟）'),
                                 ParamSpec('duplicate_policy', '重复发送处理', kind='select',
                                           options=_DUP_POLICY, default='1',
                                           desc='选填：默认 1（覆盖旧码）'),
                                 ParamSpec('interval', '发送间隔(秒)', kind='number', default='60',
                                           desc='选填：频控间隔，默认 60 秒（防短信轰炸）'),
                                 ParamSpec('code_type', '验证码类型', kind='number', default='1',
                                           desc='选填：1-7（1=纯数字），默认 1'),
                                 ParamSpec('return_verify_code', '响应返回验证码', kind='select',
                                           options=_RETURN_CODE, default='false',
                                           desc='选填：仅测试场景建议开启 true，便于直接取码核验'),
                                 ParamSpec('scheme_name', '方案名称', kind='text',
                                           desc='选填：留空使用阿里云默认方案'),
                                 _out_id_param(),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；本服务需项目签名（app_id/timestamp/nonce/sign）。',
                                    '发送成功即返回 code=10000；频控触发时提示等待（interval 秒）后再试。']),
                EndpointSpec('check', '核验短信验证码', 'POST', '/api/sms_verify/aliyun/check',
                             summary='核验用户输入的验证码是否正确/是否过期。',
                             params=[
                                 _phone_param(),
                                 ParamSpec('verify_code', '验证码', kind='text', required=True,
                                           placeholder='如：1234', desc='手机收到的验证码（必填）'),
                                 ParamSpec('case_auth_policy', '大小写核验策略', kind='select',
                                           options=_CASE_POLICY, default='1',
                                           desc='选填：默认 1（不区分大小写）'),
                                 ParamSpec('scheme_name', '方案名称', kind='text',
                                           desc='选填：须与发送验证码时一致，留空使用默认方案'),
                                 _out_id_param(),
                             ],
                             notes=['接口请求成功统一返回 code=10000；业务结果以 data.verify_result 判断：',
                                    'PASS=核验成功，UNKNOWN=核验失败（验证码错误或已过期）。']),
            ],
        ),
    ],
)
