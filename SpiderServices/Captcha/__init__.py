"""自研图形验证码生成引擎

纯逻辑模块（不依赖 Django / Web 框架），由 API 层（API/apis/captcha_self/）调用：
- generator.new_char_captcha()       字符图片验证码
- generator.new_arithmetic_captcha() 算术图片验证码
"""
