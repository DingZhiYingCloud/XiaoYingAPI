"""
抖音视频解析 - 配置常量

集中管理抖音解析所需的请求参数、UA、超时等配置。
"""

# 请求 UA（必须与 abogus.py 中 ua_code 特征码对应，不可随意修改）
UA_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# detail API 基础参数（与抖音 web 端请求保持一致）
BASE_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "190500",
    "version_name": "19.5.0",
    "cookie_enabled": "true",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Edge",
    "browser_online": "true",
    "engine_name": "Blink",
    "os_name": "Windows",
    "os_version": "10",
    "platform": "PC",
    "screen_width": "1920",
    "screen_height": "1080",
}

# 接口地址
API_DETAIL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
HOME_URL = "https://www.douyin.com/"

# 请求超时（秒）
REQUEST_TIMEOUT = 15
