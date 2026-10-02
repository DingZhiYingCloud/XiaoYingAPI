"""支付渠道抽象基类

新增一个支付渠道 = 写一个继承 `BasePayProvider` 的类（实现下面 5 个方法）+ 在
`providers/registry.py` 里登记一行。上层（`service.py` / 视图 / 后台）只认这一套
归一化的入参出参，因此换渠道、加渠道都不需要改业务代码。

统一契约（金额一律「元」的 Decimal；时间戳由各渠道内部处理）：

    create_order(...) -> {'trade_no': str, 'pay_type': str, 'pay_info': str, 'raw': dict}
    query_order(...)  -> {'state': str, 'trade_no': str, 'out_trade_no': str,
                          'money': str, 'raw': dict}
                          state ∈ pending / paid / refunded / frozen / authorized / closed
    refund(...)       -> {'refund_no': str, 'out_refund_no': str, 'money': str, 'raw': dict}
    verify_notify(params) -> bool          # 用平台公钥验签
    parse_notify(params)  -> dict          # 归一化：out_trade_no / trade_no / state / money / pay_type

失败一律抛 `PayError(msg)`（msg 可直接给用户看）。
"""
from abc import ABC, abstractmethod


class PayError(Exception):
    """支付渠道调用失败（平台返回非成功码 / 网络异常 / 应答无法解析）"""


class BasePayProvider(ABC):
    """支付渠道基类（子类只需声明 code/name/default_gateway 并实现 5 个方法）"""

    #: 渠道标识（与 PayProvider.code 对应）
    code = ''
    #: 渠道展示名
    name = ''
    #: 默认网关地址（PayProvider.gateway 留空时用它）
    default_gateway = ''
    #: 该渠道支持的支付方式（值 -> 展示名），供后台勾选；留空 = 不做限制
    pay_types = {}
    #: 支持的调用方式（值 -> 展示名），见渠道文档的「接口类型列表」
    methods = {}
    #: 支持的设备类型（值 -> 展示名），见渠道文档的「设备类型列表」
    devices = {}

    def __init__(self, config):
        """config 是 `API.models.Payment.provider.PayProvider` 实例（含 pid 与两把密钥）"""
        self.config = config

    @property
    def gateway(self) -> str:
        return (self.config.gateway or self.default_gateway).rstrip('/')

    @property
    def merchant_id(self) -> str:
        return (self.config.merchant_id or '').strip()

    # ---------- 子类必须实现 ----------

    @abstractmethod
    def create_order(self, *, out_trade_no, amount, subject, pay_type,
                     client_ip, notify_url, return_url, param='',
                     method='web', device='pc') -> dict:
        """统一下单：返回支付参数

        :param method: 调用方式（web / jump / app / jsapi …），见各渠道的 `methods`
        :param device: 设备类型（pc / mobile / wechat / alipay …），见各渠道的 `devices`
        —— 网页端用默认的 web+pc；**移动端 App 建议传 method=jump + device=mobile**，
        平台会返回收单台跳转地址，WebView / 系统浏览器打开即可拉起支付。
        """

    @abstractmethod
    def query_order(self, *, out_trade_no=None, trade_no=None) -> dict:
        """主动查单（通知可能丢，查单是兜底同时也是对账口径）"""

    @abstractmethod
    def refund(self, *, amount, out_trade_no=None, trade_no=None, out_refund_no='') -> dict:
        """订单退款（金额单位为元；平台可能不支持部分退款）"""

    @abstractmethod
    def verify_notify(self, params: dict) -> bool:
        """校验异步通知签名（用平台公钥）"""

    @abstractmethod
    def parse_notify(self, params: dict) -> dict:
        """把通知参数归一化成统一结构（不负责验签，验签单独调 verify_notify）"""

    # ---------- 公共校验 ----------

    def ensure_configured(self):
        """下单/查单/退款前的配置自检：缺商户ID或私钥就早失败，别等平台回报签名错"""
        if not self.merchant_id:
            raise PayError(f'{self.name} 未配置商户ID')
        if not self.config.private_key:
            raise PayError(f'{self.name} 未配置商户私钥')

    def ensure_verifiable(self):
        """验签前自检：缺平台公钥时明确报错（否则会静默把所有回调判成验签失败）"""
        if not self.config.platform_public_key:
            raise PayError(f'{self.name} 未配置平台公钥，无法校验回调签名')
