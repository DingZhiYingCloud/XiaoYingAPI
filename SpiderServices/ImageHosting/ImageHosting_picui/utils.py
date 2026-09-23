"""
PicUI 图床线路 - 辅助工具模块

提供 PicUI 上传接口相关的常量配置。
接口文档: https://picui.apifox.cn/471310694e0
"""

# 基础地址与上传接口
BASE_URL = "https://v2.picui.cn"
API_PATH = "/api/v1/upload"
UPLOAD_URL = BASE_URL + API_PATH

# 请求超时（秒）
REQUEST_TIMEOUT = 60

# 图片权限（permission）：1=公开，0=私有
PERMISSIONS = ("0", "1")

# 图片过期时间格式（expired_at）
EXPIRED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

# 响应中 data.size 的单位换算：PicUI 返回千字节(KB)，1KB = 1024 字节
SIZE_UNIT_BYTES = 1024
