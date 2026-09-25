"""
巨量代理 - 辅助工具模块

提供巨量代理（juliangip.com）「独享代理」提取接口的默认配置与签名工具。
业务编号 / API Key / 代理账密默认从 .env 读取
（PROXY_JULIANG_TRADE_NO / PROXY_JULIANG_KEY / PROXY_JULIANG_USERNAME / PROXY_JULIANG_PASSWORD），
禁止硬编码；调用方传参时以调用方为准。
提取接口地址也可由 .env 的 PROXY_JULIANG_API_BASE 覆盖（默认直连官方，
海外部署需指向国内中转，见下方 API_BASE 说明）。

签名规则（官方 https://www.juliangip.com/help/api/sign/）：
    去掉 sign → 参数名按 ASCII 升序 → 拼成 key=value&key=value →
    MD5(拼接串 + "&key=" + 业务密钥)，取 32 位小写。
"""
import hashlib
import os

from dotenv import load_dotenv

load_dotenv()

# 提取接口（独享代理产品）。
# 巨量对「提取」会校验调用方 IP 的地区：海外 IP 会被直接拒绝
#（"暂不支持向您添加的IP：xxx所属地区提供服务"），此时可用 .env 的
# PROXY_JULIANG_API_BASE 指向国内中转（如 nginx 反代），路径与参数保持不变。
# 该地址只允许平台侧配置，不开放给调用方（避免被当作任意请求跳板 / SSRF）。
API_BASE = ((os.getenv("PROXY_JULIANG_API_BASE", "") or "").strip()
            or "http://v2.api.juliangip.com").rstrip("/")
API_PATH = "/unlimited/getips"
API_URL = f"{API_BASE}{API_PATH}"

# 平台默认凭据（从 .env 读取；调用方传参时以调用方为准）
DEFAULT_TRADE_NO = (os.getenv("PROXY_JULIANG_TRADE_NO", "") or "").strip()
DEFAULT_KEY = (os.getenv("PROXY_JULIANG_KEY", "") or "").strip()
DEFAULT_USERNAME = (os.getenv("PROXY_JULIANG_USERNAME", "") or "").strip()
DEFAULT_PASSWORD = (os.getenv("PROXY_JULIANG_PASSWORD", "") or "").strip()

# 单次最大提取数量（官方上限 100）
MAX_NUM = 100

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# 代理协议与归属说明（写入返回的代理条目）
PROTOCOL_HTTP = "HTTP"
PROTOCOL_SOCKS = "SOCKS5"
REGION = "国内动态"

# 可透传的业务参数：{参数名: 允许取值}（只发送调用方显式传入的参数）
# result_type 只开放 json/text：本线路需要解析出 ip:port，xml 无法解析
PASSTHROUGH_ENUM = {
    'pt': ('1', '2'),
    'result_type': ('json', 'text'),
    'split': ('1', '2', '3', '4'),
    'auto_white': ('0', '1'),
    'city_name': ('0', '1'),
    'city_code': ('0', '1'),
    'ip_remain': ('0', '1'),
    'auth_info': ('0', '1'),
    'filter': ('0', '1'),
}

# 可透传的业务参数（自由文本，如地区 / 运营商，多个用英文逗号分隔）
PASSTHROUGH_TEXT = ('area', 'isp')


def build_sign(params: dict, key: str) -> str:
    """按官方规则计算签名

    :param params: 业务参数（含 trade_no / num 等，不应含 sign）
    :param key: 业务密钥（API Key）
    :return: 32 位小写 MD5 签名
    """
    items = {k: str(v) for k, v in params.items() if k != 'sign' and str(v) != ''}
    raw = '&'.join(f'{k}={items[k]}' for k in sorted(items))
    return hashlib.md5(f'{raw}&key={key}'.encode('utf-8')).hexdigest()
