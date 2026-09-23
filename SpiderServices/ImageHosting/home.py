"""
图床服务 - ImageHostingService

统一的图床服务入口，聚合多个图床线路，按线路分发上传请求。

架构:
  ImageHostingService (home.py)        # 主入口，按线路分发
    ├── ImageHosting_scdn/             # 线路1：scdn.io 图床（上传图片）
    ├── ImageHosting_picui/            # 线路2：PicUI 图床（上传图片，需账号 Token）
    └── ...（后续可在此目录继续添加更多图床线路）

核心逻辑:
  1. 按 source 选择线路（默认 scdn）
  2. 将上传参数透传给该线路，返回统一响应结构

使用示例:
    service = ImageHostingService()
    # 本地文件
    with open("a.jpg", "rb") as f:
        result = service.upload_image(source="scdn", image=f)
    # 远程图片（服务端代理拉图）
    result = service.upload_image(source="scdn", image_url="https://example.com/a.jpg")
"""

import importlib.util
import os
import sys


# ── Python 3.14 兼容：手动加载子包 ──
# Python 3.14 的 PathFinder 无法通过 sys.path 定位带 __init__.py 的子包，
# 因此使用 spec_from_file_location 预先注册所有子包（与 ProxyIp 保持一致）。
def _ensure_subpackage(parent_name, child_path):
    """如果子包尚未注册，使用 spec_from_file_location 加载并注册到 sys.modules"""
    if parent_name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(parent_name, child_path)
    if spec:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[parent_name] = mod


_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ["ImageHosting_scdn", "ImageHosting_picui"]:
    _ensure_subpackage(
        f"ImageHosting.{_sub}",
        os.path.join(_PKG_DIR, _sub, "__init__.py"),
    )


from .utils import response_dict
from .ImageHosting_scdn.home import ImageHostingScdn
from .ImageHosting_picui.home import ImageHostingPicui


class ImageHostingService:
    """图床服务 - 主入口"""

    SOURCE_MAP = {
        "scdn": ImageHostingScdn,
        "picui": ImageHostingPicui,
    }
    """图床线路映射表：source_name -> LineClass
    后续新增线路时只需在此注册即可。"""

    def __init__(self):
        self._lines = {}

    def _get_line(self, source: str):
        """延迟加载指定线路的实例"""
        if source not in self._lines:
            cls = self.SOURCE_MAP.get(source)
            if not cls:
                raise ValueError(f"不支持的图床线路: {source}，可选: {list(self.SOURCE_MAP.keys())}")
            self._lines[source] = cls()
        return self._lines[source]

    def upload_image(self, source: str = "scdn", **kwargs) -> dict:
        """
        按线路上传图片。

        :param source: 图床线路名（默认 "scdn"），可选值见 SOURCE_MAP
        :param kwargs: 透传给线路的 upload_image 参数，详见各线路 docstring
        :return: dict 含 {code, message, data}（code: 0 成功，1 失败）
        """
        if not source:
            return response_dict(1, "参数缺失: source(图床线路)", None)
        try:
            line = self._get_line(source)
        except ValueError as e:
            return response_dict(1, str(e), None)
        return line.upload_image(**kwargs)


if __name__ == "__main__":
    # 可选演示：传入本地图片路径做一次真实上传
    #   python home.py /path/to/image.jpg
    service = ImageHostingService()
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if not os.path.isfile(path):
            print(f"文件不存在: {path}")
        else:
            with open(path, "rb") as f:
                result = service.upload_image(source="scdn", image=f)
            print(f"状态: {'成功' if result['code'] == 0 else '失败'}")
            print(f"信息: {result['message']}")
            print(f"数据: {result['data']}")
    else:
        print("用法: python home.py <本地图片路径>   # 走 scdn 线路做一次真实上传演示")
        print('或调用: ImageHostingService().upload_image(source="scdn", image_url="https://...")')
