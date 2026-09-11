"""抖音评论发布 - 配置常量

集中管理接口地址、请求参数、UA、超时，以及补环境签名用的 node 脚本位置。
"""

from pathlib import Path

# 发布评论接口
PUBLISH_API = "https://www.douyin.com/aweme/v1/web/comment/publish/"

# 请求 UA（须与补环境里 bdms 的签名环境一致，勿随意更换）
UA_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# 公共参数（与抖音 web 端一致，[实测] 参与 a_bogus 签名）
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

# 业务参数默认值（[实测] 抖音前端固定值，属风控画像的一部分）：
# 第一版只做一级纯文本评论，故 reply_id 固定 "0"、无 @/话题时 text_extra 固定 "[]"
PUBLISH_DEFAULTS = {
    "text_extra": "[]",
    "reply_id": "0",
    "comment_send_celltime": "0",
    "comment_video_celltime": "0",
    "one_level_comment_rank": "5",
    "paste_edit_method": "non_paste",
}

# 运行时安全头（[实测] comment/publish 只校验这两个）：
# x-tt-session-dtrait 由 node 补环境现场产出，csrf 头是固定常量
SECSDK_CSRF_TOKEN = "DOWNGRADE"

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# ---------- 补环境签名脚本（node） ----------

SIGN_DIR = Path(__file__).resolve().parent / "sign"
SIGN_CLI = SIGN_DIR / "sign_cli.js"        # 生成 a_bogus
SECSDK_CLI = SIGN_DIR / "secsdk_cli.js"    # 生成 x-tt-session-dtrait

NODE_BIN = "node"
# 单次 node 调用超时（秒）：secsdk_cli 需加载 chunk 并访问抖音后端，实测约 1.3s，留足余量
SIGN_TIMEOUT = 30
