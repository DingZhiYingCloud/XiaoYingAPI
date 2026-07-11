"""
DdddocrRecognizer - 基于 ddddocr 的通用验证码识别服务

依赖:
    - ddddocr: https://github.com/sml2h3/ddddocr

功能:
    1. OCR 文字识别（基础识别、概率输出、自定义字符范围、颜色过滤）
    2. 目标检测（检测图片中的目标位置）
    3. 滑块验证码处理（边缘匹配法、图像差异比较法）
    4. 批量图片处理
    5. 自定义模型导入

使用示例:
    recognizer = DdddocrRecognizer()
    # 基础识别
    result = recognizer.ocr("captcha.jpg")
    # 目标检测
    boxes = recognizer.detect("image.jpg")
    # 滑块匹配
    result = recognizer.slide_match("slide.png", "bg.jpg")
"""

import os
import glob
import importlib.util
from typing import Optional

import ddddocr

# 用 importlib 加载本地 utils.py（避免模块名冲突，绕过 sys.modules 缓存）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_UTILS_PATH = os.path.join(_THIS_DIR, "utils.py")
_UTILS_SPEC = importlib.util.spec_from_file_location(
    "ddddocr_recognizer_utils", _UTILS_PATH,
)
_utils_module = importlib.util.module_from_spec(_UTILS_SPEC)
_UTILS_SPEC.loader.exec_module(_utils_module)

load_image = _utils_module.load_image
save_image = _utils_module.save_image
response_dict = _utils_module.response_dict


class DdddocrRecognizer:
    """
    ddddocr 验证码识别服务封装。

    支持 OCR 识别、目标检测、滑块验证码匹配三大功能，
    可通过参数切换不同的模型和算法。
    """

    def __init__(
        self,
        ocr: bool = True,
        det: bool = False,
        beta: bool = False,
        old: bool = False,
        use_gpu: bool = False,
        device_id: int = 0,
        show_ad: bool = False,
        import_onnx_path: str = "",
        charsets_path: str = "",
        max_image_bytes: int | str = None,
        max_image_side: int | str = None,
    ):
        """
        初始化 ddddocr 识别器。

        Args:
            ocr: 是否启用 OCR 功能。当 det=True 时会强制关闭 OCR
            det: 是否启用目标检测功能。det=True 会覆盖 ocr=True
            beta: 是否使用 Beta 版 OCR 模型（对某些验证码效果更好）。与 old 互斥
            old: 是否使用旧版 OCR 模型（兼容参数，当前不改变模型选择）
            use_gpu: 是否使用 GPU 加速（需安装 CUDA 和 onnxruntime-gpu）
            device_id: GPU 设备 ID，仅在 use_gpu=True 时生效
            show_ad: 是否显示初始化广告信息
            import_onnx_path: 自定义模型的 onnx 文件路径。需同时设置 charsets_path
            charsets_path: 自定义字符集的 json 文件路径。需与 import_onnx_path 一起使用
            max_image_bytes: 单图最大字节数上限（默认 8MB）
            max_image_side: 单图最长边像素上限（默认 4096px）

        功能组合说明:
            - ocr=True, det=False: 标准 OCR 识别模式（默认）
            - ocr=False, det=True: 目标检测模式
            - ocr=False, det=False: 滑块识别模式（需调用 slide_match/slide_comparison）
            - import_onnx_path + charsets_path: 自定义模型模式

        Raises:
            ImportError: ddddocr 未安装时抛出
            Exception: 初始化失败时抛出（如 GPU 环境问题）
        """
        # 构建参数字典，只传非默认值
        kwargs = {
            "ocr": ocr,
            "det": det,
            "old": old,
            "beta": beta,
            "use_gpu": use_gpu,
            "device_id": device_id,
            "show_ad": show_ad,
        }

        if import_onnx_path:
            kwargs["import_onnx_path"] = import_onnx_path
        if charsets_path:
            kwargs["charsets_path"] = charsets_path
        if max_image_bytes is not None:
            kwargs["max_image_bytes"] = max_image_bytes
        if max_image_side is not None:
            kwargs["max_image_side"] = max_image_side

        try:
            self.ocr_engine = ddddocr.DdddOcr(**kwargs)
        except Exception as e:
            raise RuntimeError(f"ddddocr 初始化失败: {e}. 请确认已安装: pip install ddddocr")

        # 记录当前模式，便于用户查询
        self._ocr_enabled = ocr and not det  # det 优先
        self._det_enabled = det
        self._custom_model = bool(import_onnx_path)

    # ==================== OCR 识别 ====================

    def ocr(
        self,
        image_source: str | bytes,
        probability: bool = False,
        png_fix: bool = False,
        colors: list = None,
        custom_color_ranges: dict = None,
    ) -> dict:
        """
        OCR 文字识别：识别图片中的文字内容。

        Args:
            image_source: 图片来源，支持：
                - 本地文件路径（如 "captcha.jpg"）
                - URL（如 "https://example.com/captcha.jpg"）
                - bytes 对象
            probability: 是否返回概率分布（仅对内置模型生效）
            png_fix: 是否修复透明 PNG 图片（仅对带透明通道的图片生效）
            colors: 颜色过滤列表，如 ["red", "blue"]。支持：
                red, green, blue, yellow, orange, purple, pink, brown
            custom_color_ranges: 自定义颜色范围（HSV 字典），需与 colors 配合使用
                格式: {"color_name": [(h_min,s_min,v_min), (h_max,s_max,v_max)]}

        Returns:
            dict: {"code": 0, "message": "识别成功", "data": ...}
                - probability=False: data 为识别的文本字符串
                - probability=True: data 为 {"text": "xxx", "probability": {...}}

        Raises:
            ValueError: OCR 模式未启用（初始化时 ocr=False 或 det=True）
        """
        if not self._ocr_enabled and not self._custom_model:
            raise ValueError("OCR 模式未启用。请初始化时设置 ocr=True（默认）")

        try:
            image_bytes = load_image(image_source)
        except Exception as e:
            return response_dict(code=1, message=f"图片加载失败: {e}")

        try:
            # 构建 kwargs，只传有值的参数
            kwargs = {"png_fix": png_fix, "probability": probability}
            if colors is not None:
                kwargs["color_filter_colors"] = colors
            if custom_color_ranges is not None:
                kwargs["color_filter_custom_ranges"] = custom_color_ranges

            result = self.ocr_engine.classification(image_bytes, **kwargs)

            if probability and isinstance(result, dict) and "probability" in result:
                # 概率模式：从概率分布中提取最可能的文本
                s = ""
                for i in result["probability"]:
                    s += result["charsets"][i.index(max(i))]
                return response_dict(
                    code=0,
                    message="识别成功",
                    data={"text": s, "probability": result},
                )
            else:
                return response_dict(code=0, message="识别成功", data=str(result))

        except Exception as e:
            return response_dict(code=1, message=f"OCR 识别异常: {e}")

    def set_ranges(self, ranges: int | str):
        """
        限定 OCR 识别的字符范围。

        Args:
            ranges: 字符范围，支持：
                - 预定义数字: 0(数字), 1(小写), 2(大写), 3(大小写),
                  4(小写+数字), 5(大写+数字), 6(大小写+数字), 7(默认)
                - 自定义字符串: 如 "0123456789+-x/="

        Returns:
            dict: {"code": 0, "message": "设置成功"}
        """
        try:
            self.ocr_engine.set_ranges(ranges)
            return response_dict(code=0, message="设置成功")
        except Exception as e:
            return response_dict(code=1, message=f"设置字符范围失败: {e}")

    # ==================== 目标检测 ====================

    def detect(self, image_source: str | bytes) -> dict:
        """
        目标检测：检测图片中的目标位置，返回边界框坐标。

        Args:
            image_source: 图片来源（文件路径/URL/bytes）

        Returns:
            dict: {"code": 0, "message": "检测成功", "data": [{"box": [[x1,y1],...], "score": 0.99}, ...]}
                - box: 四个顶点的坐标列表 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                - score: 置信度分数

        Raises:
            ValueError: 检测模式未启用（初始化时 det=False）
        """
        if not self._det_enabled and not self._custom_model:
            raise ValueError(
                "目标检测模式未启用。请初始化时设置 det=True, ocr=False"
            )

        try:
            image_bytes = load_image(image_source)
        except Exception as e:
            return response_dict(code=1, message=f"图片加载失败: {e}")

        try:
            results = self.ocr_engine.detection(image_bytes)
            return response_dict(code=0, message=f"检测到 {len(results)} 个目标", data=results)
        except Exception as e:
            return response_dict(code=1, message=f"目标检测异常: {e}")

    # ==================== 滑块验证码 ====================

    def slide_match(
        self,
        slide_image: str | bytes,
        background_image: str | bytes,
        simple_target: bool = False,
    ) -> dict:
        """
        滑块验证码匹配（算法1：边缘匹配法）。

        通过边缘检测匹配滑块在背景图中的缺口位置。

        Args:
            slide_image: 滑块图片（小图，通常是带阴影的滑块形状）
            background_image: 背景图片（大图，含缺口）
            simple_target: 是否使用简单目标模式

        Returns:
            dict: {"code": 0, "message": "匹配成功", "data": {"target_x": int, "target_y": int}}
                - target_x: 缺口左上角 x 坐标
                - target_y: 缺口左上角 y 坐标

        Note:
            使用此方法前，初始化时需设置 ocr=False, det=False
        """
        try:
            slide_bytes = load_image(slide_image)
            bg_bytes = load_image(background_image)
        except Exception as e:
            return response_dict(code=1, message=f"图片加载失败: {e}")

        try:
            result = self.ocr_engine.slide_match(
                slide_bytes, bg_bytes, simple_target=simple_target
            )
            if isinstance(result, dict):
                return response_dict(
                    code=0,
                    message="匹配成功",
                    data={
                        "target_x": result.get("target_x", 0),
                        "target_y": result.get("target_y", 0),
                    },
                )
            else:
                # 兼容不同版本返回值
                return response_dict(code=0, message="匹配成功", data=result)
        except Exception as e:
            return response_dict(code=1, message=f"滑块匹配异常: {e}")

    def slide_comparison(
        self,
        slide_image: str | bytes,
        background_image: str | bytes,
    ) -> dict:
        """
        滑块验证码匹配（算法2：图像差异比较法）。

        通过直接比较背景图与滑块图的位置差异来确定缺口位置。

        Args:
            slide_image: 滑块图片（小图）
            background_image: 背景图片（大图，含缺口）

        Returns:
            dict: {"code": 0, "message": "匹配成功", "data": {"target_x": int, "target_y": int}}

        Note:
            使用此方法前，初始化时需设置 ocr=False, det=False
        """
        try:
            slide_bytes = load_image(slide_image)
            bg_bytes = load_image(background_image)
        except Exception as e:
            return response_dict(code=1, message=f"图片加载失败: {e}")

        try:
            # ddddocr 接口: slide_comparison(target_img, background_img)
            result = self.ocr_engine.slide_comparison(slide_bytes, bg_bytes)
            if isinstance(result, dict):
                return response_dict(
                    code=0,
                    message="匹配成功",
                    data={
                        "target_x": result.get("target_x", 0),
                        "target_y": result.get("target_y", 0),
                    },
                )
            else:
                return response_dict(code=0, message="匹配成功", data=result)
        except Exception as e:
            return response_dict(code=1, message=f"滑块比较异常: {e}")

    # ==================== 批量处理 ====================

    def batch_ocr(
        self,
        image_dir: str,
        pattern: str = "*.jpg",
        probability: bool = False,
        png_fix: bool = False,
        colors: list = None,
    ) -> dict:
        """
        批量 OCR 识别目录下的所有图片。

        Args:
            image_dir: 图片目录路径
            pattern: 文件匹配模式，如 "*.jpg", "*.png", "*.jpg;*.png"
            probability: 是否返回概率分布
            png_fix: 是否修复透明 PNG 图片
            colors: 颜色过滤列表

        Returns:
            dict: {"code": 0, "message": f"处理完成，成功N张", "data": {"total": N, "success": N, "failed": N, "results": [...]}}
                每项结果: {"filename": "xxx", "result": "识别文本" 或 error信息}
        """
        if not os.path.isdir(image_dir):
            return response_dict(code=1, message=f"目录不存在: {image_dir}")

        # 收集所有匹配的图片文件
        if ";" in pattern:
            patterns = pattern.split(";")
            files = []
            for p in patterns:
                files.extend(glob.glob(os.path.join(image_dir, p.strip())))
        else:
            files = glob.glob(os.path.join(image_dir, pattern))

        if not files:
            return response_dict(code=1, message=f"目录 {image_dir} 中未找到匹配 {pattern} 的图片")

        results = []
        success_count = 0
        fail_count = 0

        for filepath in sorted(files):
            filename = os.path.basename(filepath)
            ret = self.ocr(
                filepath, probability=probability, png_fix=png_fix, colors=colors
            )
            if ret["code"] == 0:
                success_count += 1
                results.append({"filename": filename, "result": ret["data"]})
            else:
                fail_count += 1
                results.append({"filename": filename, "error": ret["message"]})

        return response_dict(
            code=0,
            message=f"处理完成，成功{success_count}张，失败{fail_count}张",
            data={
                "total": len(files),
                "success": success_count,
                "failed": fail_count,
                "results": results,
            },
        )

    def save_debug_image(
        self, image_source: str | bytes, filename: str = None, save_dir: str = None
    ) -> dict:
        """
        保存调试图片到本地，便于人工验证识别结果。

        Args:
            image_source: 图片来源（文件路径/URL/bytes）
            filename: 保存的文件名，不传则自动生成
            save_dir: 保存目录，不传则使用默认目录

        Returns:
            dict: {"code": 0, "message": "保存成功", "data": {"filepath": "..."}}
        """
        try:
            image_bytes = load_image(image_source)
            filepath = save_image(image_bytes, save_dir=save_dir, filename=filename)
            return response_dict(code=0, message="保存成功", data={"filepath": filepath})
        except Exception as e:
            return response_dict(code=1, message=f"保存失败: {e}")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("DdddocrRecognizer 使用示例")
    print("=" * 60)

    # 初始化识别器（关闭广告，生产环境推荐）
    recognizer = DdddocrRecognizer(show_ad=False)

    # ====== 1. 基础 OCR 识别 ======
    print("\n----- 1. 基础 OCR 识别 -----")
    # 识别本地图片
    result = recognizer.ocr("captcha_samples/test.jpg")
    print(f"识别结果: {result}")

    # 限制只识别数字
    recognizer.set_ranges(0)
    result = recognizer.ocr("captcha_samples/test.jpg")
    print(f"数字模式: {result}")

    # 恢复默认字符集
    recognizer.set_ranges(7)

    # ====== 2. OCR 概率输出 ======
    print("\n----- 2. OCR 概率输出 -----")
    result = recognizer.ocr("captcha_samples/test.jpg", probability=True)
    print(f"概率结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # ====== 3. 颜色过滤识别 ======
    print("\n----- 3. 颜色过滤识别 -----")
    result = recognizer.ocr("captcha_samples/test.jpg", colors=["red", "blue"])
    print(f"颜色过滤结果: {result}")

    # ====== 4. 目标检测 ======
    print("\n----- 4. 目标检测 -----")
    det_recognizer = DdddocrRecognizer(ocr=False, det=True, show_ad=False)
    result = det_recognizer.detect("captcha_samples/test.jpg")
    print(f"检测结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # ====== 5. 滑块验证码 ======
    print("\n----- 5. 滑块验证码匹配 -----")
    slide_recognizer = DdddocrRecognizer(ocr=False, det=False, show_ad=False)
    result = slide_recognizer.slide_match(
        "captcha_samples/slide.png",
        "captcha_samples/bg.jpg",
    )
    print(f"滑块匹配结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # ====== 6. 批量处理 ======
    print("\n----- 6. 批量识别 -----")
    result = recognizer.batch_ocr("captcha_samples", pattern="*.jpg;*.png")
    print(f"批量结果: {json.dumps(result, ensure_ascii=False, indent=2, default=str)}")

    # ====== 7. 使用 Beta 模型 ======
    print("\n----- 7. Beta 模型 -----")
    beta_recognizer = DdddocrRecognizer(beta=True, show_ad=False)
    result = beta_recognizer.ocr("captcha_samples/test.jpg")
    print(f"Beta 模型结果: {result}")

    print("\n" + "=" * 60)
    print("提示：以上示例默认使用了 captcha_samples/ 目录下的示例图片。")
    print("请将你的验证码图片放入该目录后修改对应路径测试。")
    print("=" * 60)
