"""易支付（EZFP）V2 渠道实现

文档：https://www.ezfp.cn/doc/index.html
网关：POST 表单（application/x-www-form-urlencoded），返回 JSON，`code == 0` 为成功。

    POST /api/pay/create   统一下单   → trade_no / pay_type / pay_info
    POST /api/pay/query    订单查询   → status(0未支付 1已支付 2已退款 3已冻结 4预授权) / money
    POST /api/pay/refund   订单退款   → refund_no / out_refund_no / money

本实现的约定（**已用真实网关实测**，pid 6681）：
    · 下单固定 `method=web` + `device=pc`。实测该组合下：
        - `type=wxpay` → **`pay_type=qrcode`**，`pay_info` 是原生微信支付二维码链接
          （`weixin://wxpay/bizpayurl?…`，手机微信扫码即可付）；
        - `type=alipay` → `pay_type=jump`，`pay_info` 是平台收银台地址（PC 打开后页面自带二维码）。
      因此**统一按返回的 `pay_type` 渲染**：`qrcode` 直接出二维码，`jump`/`html` 走跳转或把地址做成二维码，
      不硬编码某一种。
    · 应答与通知都用**平台公钥**验签；实测应答验签与请求签名同一套字段口径，无需特殊处理。
"""
import logging
import time

import requests

from API.apis.pay.utils import format_money
from API.apis.pay.providers.base import BasePayProvider, PayError
from API.apis.pay.providers.sign import build_sign_content, sign_content, verify_content

logger = logging.getLogger('api.pay')

#: 单次网关调用超时（秒）——支付接口不能挂太久，超时由上层提示用户重试
REQUEST_TIMEOUT = 15

#: 平台订单状态 → 归一化状态
_STATUS_MAP = {
    0: 'pending',
    1: 'paid',
    2: 'refunded',
    3: 'frozen',
    4: 'authorized',
}


class EzfpProvider(BasePayProvider):
    """易支付 V2（RSA 签名）"""

    code = 'ezfp'
    name = '易支付'
    default_gateway = 'https://www.ezfp.cn'

    # 支付方式取值见文档 https://www.ezfp.cn/doc/paytype.html（实际可用以商户用户组启用的为准）
    pay_types = {
        'alipay': '支付宝',
        'wxpay': '微信支付',
        'qqpay': 'QQ钱包',
        'bank': '网银支付',
        'jdpay': '京东支付',
        'paypal': 'PayPal',
        'usdt': '泰达币（USDT-TRC20）',
        'stripepay': '银行卡/钱包（Stripe）',
        'stripealipay': 'Stripe 支付宝',
        'stripewxpay': 'Stripe 微信支付',
    }

    # 调用方式 / 设备类型（见文档「接口类型列表」「设备类型列表」）
    methods = {
        'web': '通用网页支付（按 device 自动返回跳转/二维码）',
        'jump': '跳转支付（只返回跳转 url）',
        'jsapi': '小程序内支付（需传 sub_openid / sub_appid）',
        'app': 'APP 支付（iOS/安卓 APP 内发起）',
        'scan': '付款码支付（需传 auth_code）',
        'applet': '小程序支付（微信小程序内）',
    }
    devices = {
        'pc': '电脑浏览器',
        'mobile': '手机浏览器',
        'qq': '手机 QQ 内浏览器',
        'wechat': '微信内浏览器',
        'alipay': '支付宝客户端',
    }

    # ---------- 统一请求 ----------

    def _post(self, path: str, params: dict) -> dict:
        """带签名的 POST（自动补 pid / timestamp / sign_type / sign）"""
        self.ensure_configured()
        body = dict(params)
        body['pid'] = self.merchant_id
        body['timestamp'] = str(int(time.time()))
        body['sign_type'] = 'RSA'
        body['sign'] = sign_content(build_sign_content(body), self.config.private_key)

        url = f'{self.gateway}{path}'
        try:
            resp = requests.post(url, data=body, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise PayError(f'{self.name} 网关请求失败：{exc}') from exc
        except ValueError as exc:
            raise PayError(f'{self.name} 网关返回不是 JSON，无法解析') from exc

        code = payload.get('code')
        if str(code) != '0':
            msg = payload.get('msg') or f'返回码 {code}'
            raise PayError(f'{self.name}：{msg}')
        self._verify_response(payload)
        return payload

    def _verify_response(self, payload: dict) -> None:
        """校验平台应答签名（有 sign 且配了平台公钥才校验）"""
        sign = payload.get('sign')
        if not sign or not self.config.platform_public_key:
            return
        if not verify_content(build_sign_content(payload), sign, self.config.platform_public_key):
            raise PayError(f'{self.name} 应答验签失败：平台公钥与商户不匹配，或应答签名口径需调整')

    # ---------- 5 个契约方法 ----------

    def create_order(self, *, out_trade_no, amount, subject, pay_type,
                     client_ip, notify_url, return_url, param='',
                     method='web', device='pc') -> dict:
        if method not in self.methods:
            raise PayError(f'{self.name} 不支持调用方式：{method}')
        if device not in self.devices:
            raise PayError(f'{self.name} 不支持设备类型：{device}')
        payload = self._post('/api/pay/create', {
            'method': method,
            'device': device,
            'type': pay_type,
            'out_trade_no': out_trade_no,
            'notify_url': notify_url,
            'return_url': return_url,
            'name': subject,
            'money': format_money(amount),
            'clientip': client_ip or '127.0.0.1',
            'param': param,
        })
        return {
            'trade_no': str(payload.get('trade_no') or ''),
            'pay_type': str(payload.get('pay_type') or ''),
            'pay_info': str(payload.get('pay_info') or ''),
            'raw': payload,
        }

    def query_order(self, *, out_trade_no=None, trade_no=None) -> dict:
        params = {}
        if trade_no:
            params['trade_no'] = trade_no
        if out_trade_no:
            params['out_trade_no'] = out_trade_no
        if not params:
            raise PayError('查单必须提供平台订单号或商户订单号')
        payload = self._post('/api/pay/query', params)
        return {
            'state': _STATUS_MAP.get(int(payload.get('status', 0)), 'pending'),
            'trade_no': str(payload.get('trade_no') or ''),
            'out_trade_no': str(payload.get('out_trade_no') or ''),
            'money': str(payload.get('money') or ''),
            'raw': payload,
        }

    def refund(self, *, amount, out_trade_no=None, trade_no=None, out_refund_no='') -> dict:
        params = {'money': format_money(amount)}
        if trade_no:
            params['trade_no'] = trade_no
        if out_trade_no:
            params['out_trade_no'] = out_trade_no
        if out_refund_no:
            params['out_refund_no'] = out_refund_no
        payload = self._post('/api/pay/refund', params)
        return {
            'refund_no': str(payload.get('refund_no') or ''),
            'out_refund_no': str(payload.get('out_refund_no') or ''),
            'money': str(payload.get('money') or ''),
            'raw': payload,
        }

    def verify_notify(self, params: dict) -> bool:
        """用平台公钥校验异步通知签名"""
        self.ensure_verifiable()
        return verify_content(build_sign_content(params),
                              params.get('sign', ''),
                              self.config.platform_public_key)

    def parse_notify(self, params: dict) -> dict:
        """归一化通知参数

        平台只在支付成功时通知，`trade_status` 固定为 `TRADE_SUCCESS`；
        这里仍把状态映射出来，便于 service 层统一判断。
        """
        trade_status = (params.get('trade_status') or '').strip()
        return {
            'out_trade_no': (params.get('out_trade_no') or '').strip(),
            'trade_no': (params.get('trade_no') or '').strip(),
            'state': 'paid' if trade_status == 'TRADE_SUCCESS' else 'pending',
            'money': (params.get('money') or '').strip(),
            'pay_type': (params.get('type') or '').strip(),
            'buyer': (params.get('buyer') or '').strip(),
            'trade_status': trade_status,
        }
