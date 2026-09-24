"""
青雨住宅长效代理 - 辅助工具模块

提供青雨（qydailiip.com）「住宅长效」代理节点的默认连接配置。
连接主机 / 端口 / 账号 / 密码默认从 .env 读取
（PROXY_QY_RES_HOST / PROXY_QY_RES_PORT / PROXY_QY_RES_USERNAME / PROXY_QY_RES_PASSWORD），
禁止硬编码；调用方传参时以调用方为准。

说明：住宅长效节点由青雨侧「提取」得到（一组固定的连接地址 + 账号密码），
本身带到期时间（到期需重新提取），因此本线路只做连接信息拼装与可选的可用性验证，
不提供「拉取节点列表」的接口。
"""
import os

from dotenv import load_dotenv

load_dotenv()

# 默认节点连接信息（从 .env 读取；调用方传参时以调用方为准）
DEFAULT_HOST = (os.getenv("PROXY_QY_RES_HOST", "") or "").strip()
DEFAULT_PORT = (os.getenv("PROXY_QY_RES_PORT", "") or "").strip()
DEFAULT_USERNAME = (os.getenv("PROXY_QY_RES_USERNAME", "") or "").strip()
DEFAULT_PASSWORD = (os.getenv("PROXY_QY_RES_PASSWORD", "") or "").strip()

# 代理协议（国内 HTTP 代理）
PROTOCOL = "HTTP"

# 归属（返回给调用方展示用）
REGION = "国内住宅长效"
