"""
51代理 - 辅助工具模块

提供 51代理（51daili.com）动态代理提取接口（不限量套餐 `/unlimitedip/getip`）的默认配置。
账号凭据与套餐标识默认从 .env 读取
（PROXY_51DAILI_UID / PROXY_51DAILI_ACCESS_NAME / PROXY_51DAILI_ACCESS_PASSWORD /
  PROXY_51DAILI_PACKID / PROXY_51DAILI_RID / PROXY_51DAILI_PID），禁止硬编码；
调用方传参时以调用方为准。
提取接口地址也可由 .env 的 PROXY_51DAILI_API_BASE 覆盖
（该地址只允许平台侧配置，不开放给调用方，避免被当作任意请求跳板 / SSRF）。

接口文档: https://m.51daili.com/wap/api/apinote.html
"""
import os

from dotenv import load_dotenv

load_dotenv()

# 提取接口（不限量套餐 `/unlimitedip/getip`）。
# 2026-10-02 由旧的 `/getapi2` 换成此路径：账号换了「不限量」套餐后，旧路径对新的
# packid 一律回 `{"code":7,"msg":"套餐类型不存在"}`，且新路径**多一个必填参数 pid**
#（缺了回 `{"code":7,"msg":"不限量套餐id不能为空"}`）；响应结构（code/success/data[]）
# 与字段名（ip / expireTime / ipaddress / IpAddressName / isp）与旧接口完全一致，解析无需改动。
# 51代理对「提取」会校验调用方 IP 的地区：海外 IP 会被直接拒绝
#（{"code":501,"message":"当前ip:xxx,地区为美国,请更换为内地ip"}），
# 此时可用 .env 的 PROXY_51DAILI_API_BASE 指向国内中转（如 nginx 反代），路径与参数保持不变。
# 该地址只允许平台侧配置，不开放给调用方（避免被当作任意请求跳板 / SSRF）。
API_BASE = ((os.getenv('PROXY_51DAILI_API_BASE', '') or '').strip()
            or 'http://bapi.51daili.com').rstrip('/')
API_PATH = '/unlimitedip/getip'
API_URL = f'{API_BASE}{API_PATH}'

# 平台默认凭据 / 套餐标识（从 .env 读取；调用方传参时以调用方为准）
# uid / accessName / accessPassword 是账号三件套，packid（套餐ID）、pid（不限量套餐 ID）
# 与 rid（提取链接上的标识）都随该账号走，属账号级配置，故与凭据一并从 .env 取，
# 不硬编码进代码库。
DEFAULT_UID = (os.getenv('PROXY_51DAILI_UID', '') or '').strip()
DEFAULT_ACCESS_NAME = (os.getenv('PROXY_51DAILI_ACCESS_NAME', '') or '').strip()
DEFAULT_ACCESS_PASSWORD = (os.getenv('PROXY_51DAILI_ACCESS_PASSWORD', '') or '').strip()
DEFAULT_PACKID = (os.getenv('PROXY_51DAILI_PACKID', '') or '').strip()
DEFAULT_RID = (os.getenv('PROXY_51DAILI_RID', '') or '').strip()
DEFAULT_PID = (os.getenv('PROXY_51DAILI_PID', '') or '').strip()

# 账号级参数的字段名（成组使用：要么调用方全传，要么整组回退 .env）
# pid 与 packid 同性质（都标识「用哪个套餐」），混用两个账号的套餐凭据没有意义，
# 故一并放进这一组：只传一部分会被明确拒绝，而不是把我们的 pid 配别人的 packid
# 发给上游、换来一句看不懂的「套餐类型不存在」。
CRED_FIELDS = ('uid', 'accessName', 'accessPassword', 'packid', 'pid')

# 非凭据参数的默认值（写在代码常量里，调用方传参即覆盖）
DEFAULT_TIME = '2'                                         # 稳定使用时长（照抄新套餐控制台提取链接）
DEFAULT_QTY = 1                                            # 单次提取数量
DEFAULT_PORT = '1'                                         # 代理协议 1=HTTP/HTTPS 2=Socks5
DEFAULT_FORMAT = 'json'                                    # 返回格式
DEFAULT_FIELD = 'ipport,expiretime,regioncode,isptype'     # 返回字段
DEFAULT_LINE_POOL_INDEX = '-1'                             # 线路池索引，-1=不限

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# 单次提取数量上限：官方未公布硬上限，这里设一道防滥用护栏（上游自身限制仍会生效）
MAX_QTY = 100

# 代理协议：上游 port 参数 → 写入返回条目的 protocol
PROTOCOL_MAP = {'1': 'HTTP', '2': 'SOCKS5'}

# 返回格式：只开放 json / txt（html 无法解析出 ip:port）。
# 官方文档写 txt，实测 text 同样可用，故一并接受。
FORMAT_JSON = 'json'
TEXT_FORMATS = ('txt', 'text')
ALLOWED_FORMATS = (FORMAT_JSON,) + TEXT_FORMATS
