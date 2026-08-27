# 蜘蛛（spider）类型代码示例 —— 搜索引擎爬虫（Googlebot/bingbot 等）
#
# 此目录下的全部 .py 文件会被 detect 接口返回，由客户端中间件 exec 执行。
# exec 时注入的全局变量：
#   request        - 客户端当前请求对象（Django HttpRequest）
#   detect_result  - detect 接口返回的 data 字典（含 type/confidence/referer/reasons 等）
#   logger         - logging.Logger，可打印日志
#
# 请将本示例替换为你自己的业务代码（如放行蜘蛛、SEO 抓取统计等）。

print("'请求检测中间件' 这是蜘蛛类型的代码处")
