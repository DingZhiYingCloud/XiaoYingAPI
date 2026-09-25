"""临时调试：轮播结构"""
import sys
sys.path.insert(0, "SpiderServices/movies")

from curl_cffi import requests as creq
from lxml import etree

from movie_555 import utils as U

S = creq.Session(impersonate="chrome")
S.headers.update({"User-Agent": U.UA_STRING, "Accept-Language": "zh-CN,zh;q=0.9"})
h = S.get(U.BASE_URL + "/index/home.html", timeout=U.REQUEST_TIMEOUT).text

idx = h.find("banner")
print("=== banner 附近 2200 字 ===")
print(h[max(0, idx-800):idx+1400])

t = etree.HTML(h)
print("\n=== 找 carousel/focus/slide 相关 class ===")
import re
for c in sorted(set(re.findall(r'class="([^"]*(?:carousel|focus|slide|banner|swiper)[^"]*)"', h)))[:20]:
    print(f"  {c}")
