"""
Thordata 动态住宅代理 - 辅助工具模块

提供 Thordata（thordata.com）动态住宅代理的默认网关配置。
主机 / 端口 / 账号 / 密码默认从 .env 读取
（PROXY_THORDATA_HOST / PROXY_THORDATA_PORT / PROXY_THORDATA_USERNAME / PROXY_THORDATA_PASSWORD），
禁止硬编码；调用方传参时以调用方为准。

说明：Thordata 住宅代理是「网关型」代理——入口主机 / 端口固定，出口 IP 由
Thordata 侧按请求轮换，因此没有可拉取的 IP 列表接口，本线路只做入口地址拼装
与可选的可用性验证。
"""
import os

from dotenv import load_dotenv

load_dotenv()

# 默认网关入口（从 .env 读取；调用方传参时以调用方为准）
DEFAULT_HOST = (os.getenv("PROXY_THORDATA_HOST", "") or "").strip()
DEFAULT_PORT = (os.getenv("PROXY_THORDATA_PORT", "") or "").strip()
DEFAULT_USERNAME = (os.getenv("PROXY_THORDATA_USERNAME", "") or "").strip()
DEFAULT_PASSWORD = (os.getenv("PROXY_THORDATA_PASSWORD", "") or "").strip()

# 代理协议（Thordata 住宅网关的 HTTP / HTTPS 共用同一入口）
PROTOCOL = "HTTP"

# 出口归属（返回给调用方展示用）
REGION = "海外动态住宅"
