"""开发服务器（runserver）补丁：让 WSGI 服务器能读 chunked 请求体

**为什么需要**：NapCat 的 HTTP 客户端上报事件时用 `Transfer-Encoding: chunked` 发送请求体。
Django 自带的开发服务器只按 `Content-Length` 包装请求体（见
`django.core.servers.basehttp.ServerHandler`：拿不到 Content-Length 就按 0 字节算），
于是 chunked 请求进到视图里 `request.body` **永远是空** —— 现象是：

    · NapCat 日志显示「HTTP上报服务已启动」并把消息推了过来；
    · 我们这边也回了 200（视图跑了，只是 JSON 解析出空对象 → 判定为「不是消息事件」→ 静默忽略）；
    · Django 日志里会出现 `"c2" 400`、`"b0" 400` 这类记录 —— 那些 token 就是 chunk 的十六进制长度，
      被服务器当成了「下一个请求的请求行」。

**影响范围**：只有 Django 自带的开发服务器（runserver / testserver）如此。
生产上 gunicorn / uvicorn 会自行解开 chunked，前面挂 nginx 更是在反代层就还原成
Content-Length 了 —— 所以这里只在开发服务器上打补丁，不引入任何新依赖。

**实现**：把 `basehttp.WSGIRequestHandler`（`basehttp.run()` 里按模块全局名取的）换成子类，
其在 `parse_request()` 之后、交给 WSGI 之前，先把 chunked 请求体解出来，再把
`CONTENT_LENGTH` 与 `wsgi.input` 换成解好码的内容 —— 这样 Django 那套「按长度包 LimitedStream」
的逻辑就能正常读到 body。原始实现见 `django/core/servers/basehttp.py`。
"""
import io
import logging

logger = logging.getLogger('api.server')


def _read_chunked(rfile) -> bytes:
    """从原始 socket 文件对象里读出一段 chunked 编码的请求体（含结尾 trailer）

    只做「够用」的解析：按 RFC 9112 读「十六进制长度行 → 数据 → CRLF」直到长度为 0，
    再吃掉 trailer。任何非法/EOF 都按「读到为止」处理 —— 宁可少读，也绝不在这里卡死。
    """
    body = bytearray()
    while True:
        line = rfile.readline(65537)
        if not line:
            break
        size_token = line.split(b';', 1)[0].strip()      # 允许 "1a7;ext=1" 这种分块扩展
        try:
            size = int(size_token, 16)
        except ValueError:
            break
        if size == 0:
            while True:                                  # 吃掉 trailer（正常只有一个空行）
                trailer = rfile.readline(65537)
                if trailer in (b'\r\n', b'\n', b''):
                    break
            break
        remaining = size
        while remaining > 0:
            chunk = rfile.read(remaining)
            if not chunk:
                return bytes(body)
            body += chunk
            remaining -= len(chunk)
        rfile.read(2)                                    # 每个分块数据后的 CRLF
    return bytes(body)


def install():
    """把开发服务器的请求处理器换成「认 chunked」的版本（幂等，可重复调用）"""
    from django.core.servers import basehttp

    if getattr(basehttp.WSGIRequestHandler, '_xy_chunked', False):
        return
    base_handler = basehttp.WSGIRequestHandler
    wsgi_server_handler = basehttp.ServerHandler

    class ChunkedWSGIRequestHandler(base_handler):
        _xy_chunked = True

        def handle_one_request(self):
            # 与 Django 自带实现一致，差异只有：chunked 时先把请求体解出来再交给 WSGI
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ''
                self.request_version = ''
                self.command = ''
                self.send_error(414)
                return
            if not self.parse_request():                 # 解析失败时已回错误码，直接结束
                return

            environ = self.get_environ()
            stdin = self.rfile
            if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                body = _read_chunked(self.rfile)
                environ['CONTENT_LENGTH'] = str(len(body))
                environ.pop('HTTP_TRANSFER_ENCODING', None)
                stdin = io.BytesIO(body)

            handler = wsgi_server_handler(stdin, self.wfile, self.get_stderr(), environ)
            handler.request_handler = self                # 返回指针：日志与连接关闭要用
            handler.run(self.server.get_app())

    basehttp.WSGIRequestHandler = ChunkedWSGIRequestHandler
    logger.info('开发服务器已启用 chunked 请求体支持（NapCat 事件上报需要）')
