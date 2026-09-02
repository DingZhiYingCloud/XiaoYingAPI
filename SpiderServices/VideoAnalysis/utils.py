"""
视频解析服务 - 公共工具模块

提供统一的响应格式等公共功能。
"""


def response_dict(code: int = 0, message: str = "", data: dict | list = None) -> dict:
    """统一的响应字典返回"""
    return {"code": code, "message": message, "data": data}
