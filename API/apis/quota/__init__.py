"""服务余量监控（`API/apis/quota/`）

对平台自用的第三方服务账号做余量巡检与低量告警：

    services.py   被监控服务的注册表与取数实现（新增服务只改这里）
    utils.py      巡检、告警判定与邮件通知、后台定时线程

控制台页面见 `API/website/console_quota.py`，模型见 `API/models/Quota/`。
"""
