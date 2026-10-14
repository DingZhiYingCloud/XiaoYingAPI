# -*- coding: utf-8 -*-
"""ai-brain 大脑内部包。

入口脚本是同目录上一层的 `brain`，它只负责解析参数并分发；
真正的实现按职责拆在这里的几个模块里：

    util      时间/随机数等零散小工具
    conf      配置与路径（所有“放哪、读什么”都在这里）
    ui        终端输出与交互（颜色、动作样式、确认）
    store     SQLite：表结构、查询、审计
    secure    HMAC 请求签名校验、RSA 签名/验签、哈希
    llm       调用大模型（流式 / 整段，按配置切换）
    render    把流式增量渲染成「思考 / 结果」两种样式
    prompts   加载 prompts/ 目录里的提示词与技能
    server    HTTP 服务与全部对外端点
    api       本机 CLI 与服务之间的小客户端
    admin     init / status / stop / release / pending / approve …
    chat      对话 CLI（把用户的话变成动作，再汇总汇报）
"""

VERSION = '2.11.0'
