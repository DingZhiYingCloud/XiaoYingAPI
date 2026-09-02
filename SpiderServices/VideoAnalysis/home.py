"""
视频解析服务 - VideoAnalysisService

统一的视频解析服务入口，聚合多个平台解析源并返回无水印下载链接。

架构:
  VideoAnalysisService (home.py)     # 主入口，按平台路由解析
    ├── Douyin/                      # 抖音解析源（自研：a_bogus 签名 + 官方接口）
    └── ...（后续可添加微博、小红书等解析源）

核心逻辑:
  1. 根据 source 参数选择对应平台的解析器
  2. 调用解析器将分享文本解析为无水印下载信息
  3. 返回统一结构 {title, cover, duration, medias, images}

使用示例:
    service = VideoAnalysisService()
    # 抖音解析
    result = service.parse("5.89 dAT:/ ... https://v.douyin.com/xxxxx/ ...", source="douyin")
    # 成功: code=0, data={title, cover, duration, medias, images}
    # 失败: code=1, message=错误描述
"""

import sys
import os
import importlib.util


# ── Python 3.14 兼容：手动加载子包 ──
# Python 3.14 的 PathFinder 无法通过 sys.path 定位带 __init__.py 的子包，
# 因此使用 spec_from_file_location 预先注册所有子包。
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
for _sub in ["Douyin"]:
    _ensure_subpackage(
        f"VideoAnalysis.{_sub}",
        os.path.join(_PKG_DIR, _sub, "__init__.py"),
    )


from .utils import response_dict
from .Douyin.home import DouyinVideoAnalysis


class VideoAnalysisService:
    """视频解析服务 - 主入口"""

    SOURCE_MAP = {
        "douyin": DouyinVideoAnalysis,
    }
    """解析源映射表：source_name -> ParserClass
    后续新增平台（微博、小红书等）时只需在此注册即可。"""

    def __init__(self):
        self._parsers = {}

    def _get_parser(self, source: str):
        """延迟加载指定平台的解析器实例"""
        if source not in self._parsers:
            cls = self.SOURCE_MAP.get(source)
            if not cls:
                raise ValueError(f"不支持的解析源: {source}，可选: {list(self.SOURCE_MAP.keys())}")
            self._parsers[source] = cls()
        return self._parsers[source]

    def parse(self, share_text: str, source: str = "douyin") -> dict:
        """
        解析分享文本，返回无水印下载信息。

        :param share_text: 平台分享文本（完整复制内容）或链接
        :param source: 解析源名称（默认 "douyin"）
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: 成功时 {title, cover, duration, medias, images}
        """
        try:
            parser = self._get_parser(source)
            result = parser.parse(share_text)
            return response_dict(code=0, message="解析成功", data=result)
        except ValueError as e:
            return response_dict(code=1, message=str(e), data=None)
        except Exception as e:
            return response_dict(code=1, message=f"解析失败: {e}", data=None)


if __name__ == "__main__":
    service = VideoAnalysisService()

    print("===== 抖音解析 =====")
    result = service.parse(
        "和7.43 zTy:/ G@v.FH 02/17 :9pm 2026惊悚新片《鲨笼绝境》 # 惊悚电影 # 动作片 # 好看电影分享 "
        "https://v.douyin.com/m0ObKweP8EU/ 复制此链接，打开Dou音搜索，直接观看视频！",
        source="douyin",
    )
    print(f"状态: {'成功' if result['code'] == 0 else '失败: ' + result['message']}")
    if result["code"] == 0:
        data = result["data"]
        print(f"标题: {data['title']}")
        print(f"时长: {data['duration']}s")
        for m in data["medias"]:
            print(f"  {m['format']} | {m['file_size']} 字节 | {m['url'][:80]}...")
