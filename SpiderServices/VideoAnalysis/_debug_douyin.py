"""临时调试脚本：测试抖音各种解析 API 链路"""
import re
import requests

UA_PC = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
)

AWEME_ID = "7679639856579107746"


def try_get(name, url, headers, params=None):
    print(f"\n===== {name} =====")
    print(f"URL: {url}")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"状态码: {resp.status_code} | 长度: {len(resp.text)}")
        text = resp.text
        for kw in ["play_addr", "playwm", "download_addr", "uri", "url_list", "video_id"]:
            idx = text.find(kw)
            if idx >= 0:
                print(f"  找到 '{kw}' @{idx}: {text[idx:idx+200]}")
        return text
    except Exception as e:
        print(f"失败: {e}")
        return ""


# 1. 老版 iteminfo API
try_get("老版 iteminfo API", "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/",
        {"User-Agent": UA_MOBILE, "Referer": "https://www.iesdouyin.com/"},
        {"item_ids": AWEME_ID})

# 2. web aweme detail API (无签名)
try_get("web aweme detail (无签名)", "https://www.iesdouyin.com/aweme/v1/web/aweme/detail/",
        {"User-Agent": UA_PC, "Referer": "https://www.douyin.com/"},
        {"aweme_id": AWEME_ID, "device_platform": "webapp", "aid": "6383",
         "channel": "channel_pc_web", "pc_client_type": "1", "version_code": "170400",
         "version_name": "17.4.0", "cookie_enabled": "true", "browser_name": "Chrome",
         "browser_language": "zh-CN", "browser_platform": "Win32"})

# 3. 主站 www.douyin.com/video/{id} (PC)
text = try_get("主站 PC", f"https://www.douyin.com/video/{AWEME_ID}",
               {"User-Agent": UA_PC, "Referer": "https://www.douyin.com/"})
if text:
    m = re.search(r'playAddr[":=]+\s*"([^"]+)"', text)
    print(f"  playAddr 正则: {m.group(1)[:200] if m else '未匹配'}")

# 4. 移动端主站 www.douyin.com/video/{id}
text = try_get("主站 Mobile", f"https://www.douyin.com/video/{AWEME_ID}",
               {"User-Agent": UA_MOBILE, "Referer": "https://www.douyin.com/"})
if text:
    m = re.search(r'"playAddr"\s*:\s*"([^"]+)"', text)
    print(f"  playAddr 正则: {m.group(1)[:200] if m else '未匹配'}")
    m2 = re.search(r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>', text, re.S)
    if m2:
        print(f"  _ROUTER_DATA 长度: {len(m2.group(1))}")
