"""
scdn.io 图床线路 - 辅助工具模块

提供 scdn.io 上传接口相关的常量配置。
接口文档: https://img.scdn.io/api_docs.php
"""

# 基础地址与上传接口
BASE_URL = "https://img.scdn.io"
API_PATH = "/api/v1.php"
UPLOAD_URL = BASE_URL + API_PATH

# 请求超时（秒）：上传含服务端压缩/转码，超时给足
REQUEST_TIMEOUT = 60

# 输出格式（outputFormat）
# auto：静态图转 webp；动图/视频转 webp_animated
OUTPUT_FORMATS = ("auto", "jpg", "jpeg", "png", "webp", "gif", "webp_animated")

# 存储位置（storage_destination）
STORAGE_DESTINATIONS = ("local", "telegram", "r2")

# 密码模式（password_type）
PASSWORD_TYPES = ("plain", "qa")

# 可用 CDN 域名（cdn_domain）；不传或传 "default" 使用系统默认域名
CDN_DOMAINS = (
    "img.scdn.io",
    "cloudflareimg.cdn.sn",
    "edgeoneimg.cdn.sn",
    "esaimg.cdn1.vip",
    "cloudflarecnimg.scdn.io",
    "anycastimg.scdn.io",
    "edgeoneimg.cdn1.vip",
)
