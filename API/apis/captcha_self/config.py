"""自研图形验证码 - 公共配置读取

有效期等参数允许通过环境变量覆盖；留空或写得不是数字时回退默认值，
保证 `.env` 写错也不会在导入阶段崩掉。
"""
import os


def env_int(name, default):
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default
