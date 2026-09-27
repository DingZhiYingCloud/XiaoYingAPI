"""小影API 官网前台模块

职责边界：仅负责「官网前台页面 + 会话化用户认证代理」，不承载业务 API。
- 页面模板位于 API/templates/（继承全站母版 template.html）
- 官网作为用户中心的一个接入项目（UserApp），注册/登录/退出由本模块
  服务端代理调用用户中心业务逻辑（API.apis.user_center.users.utils），
  登录态存 Django 会话（Session），不向前端暴露 APPID/APPSECRET。

注意：本目录不放在 API/apis/ 下，其路由也不在 /api/ 前缀下，因此不会被「服务策略」
的服务树枚举（API/website/service_tree.py 只扫 /api/ 下的真实路由）当成一条 API 服务。
"""
