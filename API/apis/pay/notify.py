"""第三方支付 · 异步通知入口（免签名）

路径：`/pay/notify/<渠道标识>/`（注册在站点路由，见 `API/website/urls.py`）

为什么不在 `/api/` 下：`ApiAuthMiddleware` 只放行 `/api/` 的**项目签名**请求，而支付平台
的回调天然带不了我们的签名，只能靠「平台公钥验签」自证身份 —— 所以它必须挂在 `/api/` 之外，
并单独做 CSRF 豁免。

处理结果必须回显平台约定的成功标志（易支付为纯文本 `success`），否则平台会持续重推。
"""
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from API.apis.pay import service


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def notify_view(request, code):
    """接收异步通知并推进订单（验签 + 金额核对 + 幂等发货都在 service 里）"""
    params = request.POST.dict() if request.method == 'POST' else request.GET.dict()
    ok, _message = service.handle_notify(code, params, request)
    return HttpResponse('success' if ok else 'fail',
                        content_type='text/plain; charset=utf-8')
