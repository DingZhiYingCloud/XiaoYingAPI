# 事故报告：Nginx HTTPS 无限重定向循环

## 一、基本信息

| 项目 | 内容 |
|------|------|
| **报告编号** | INC-20260720-001 |
| **事故等级** | P1（核心服务不可用） |
| **发现时间** | 2026-07-20 11:20 CST |
| **修复时间** | 2026-07-20 11:30 CST |
| **影响范围** | 小影CMS 所有域名 HTTPS 访问（约 60+ 域名） |
| **影响表现** | 浏览器访问网站时持续 301 重定向，页面无法加载，显示"重定向过多"错误 |
| **服务器** | 192.253.235.28 (Ubuntu 22.04 Nginx) |
| **项目路径** | `/www/wwwroot/xiaoying/小影CMS通用版本` |

---

## 二、事故现象

用户通过浏览器访问 `https://xiaoyingclub.com/xiaoying_admin/login/` 时，浏览器提示"ERR_TOO_MANY_REDIRECTS"或"重定向过多"，页面始终无法加载。

---

## 三、根因分析

### 3.1 问题定位

宝塔面板自动生成的 Nginx 配置文件中，`#SSL-START` 区域存在一条**不区分端口**的 rewrite 规则：

```nginx
server {
    listen 80;
    listen 443 ssl;    # ← 同一 server 块同时监听 HTTP 和 HTTPS
    ...

    #SSL-START SSL相关配置
    if ( $uri ~ /\.well-known/ ) {
        set $isRedcert 1;
    }
    if ( $isRedcert != 1 ) {
        rewrite ^(.*)$ https://$host$1 permanent;  # ← 问题行
    }
```

### 3.2 触发链路

```
用户访问 https://xiaoyingclub.com/xxx
    → DNS 解析到 192.253.235.28
    → Nginx 在端口 443 上接收请求
    → 进入 SSL-START 区域
    → 检查 $isRedcert != 1 → TRUE（非 .well-known 请求）
    → 执行 rewrite ^(.*)$ https://$host$1 permanent
    → 返回 301，Location: https://xiaoyingclub.com/xxx（与原 URL 完全一致！）
    → 浏览器跟随 301 重定向
    → Nginx 再次在端口 443 上接收相同请求
    → 再次命中 rewrite
    → ...无限循环...
```

### 3.3 根本原因

- `rewrite` 规则没有检查请求端口（`$server_port != 443`）
- `server` 块同时监听 80 和 443，该 rewrite 在 HTTPS 请求上也会命中
- 导致 HTTPS 请求被 301 重定向到**完全相同的 URL**，形成死循环

### 3.4 为什么本地环境没问题

本地开发环境使用 `python manage.py runserver` 直接运行，不经过 Nginx，因此不受影响。线上使用 Nginx 反向代理到 uWSGI（端口 10005），Nginx 配置中的 rewrite 规则才被触发。

---

## 四、解决方案

### 4.1 修复操作

删除 `#SSL-START SSL相关配置` 区域中的 rewrite 规则，仅保留注释。

**修改前：**

```nginx
#SSL-START SSL相关配置
    if ( $uri ~ /\.well-known/ ) {
        set $isRedcert 1;
    }
    if ( $isRedcert != 1 ) {
        rewrite ^(.*)$ https://$host$1 permanent;
    }
```

**修改后：**

```nginx
#SSL-START SSL相关配置
    # 注：HTTPS强制跳转在下方 HTTP_TO_HTTPS_START 中处理（含端口判断），SSL-START 中不重复跳转
```

### 4.2 修复步骤

```bash
# 1. 备份原配置
cp /www/server/panel/vhost/nginx/python_小影CMS通用版本.conf \
   /www/server/panel/vhost/nginx/python_小影CMS通用版本.conf.bak

# 2. 编辑配置，删除 SSL-START 中的 rewrite 规则
vim /www/server/panel/vhost/nginx/python_小影CMS通用版本.conf

# 3. 测试配置语法
nginx -t

# 4. 热重载 Nginx
nginx -s reload
```

### 4.3 修复验证

| 测试项目 | 结果 |
|---------|------|
| HTTP 访问 `http://xiaoyingclub.com` | `301 → https://...` 正常跳转 ✅ |
| HTTPS 访问 `https://xiaoyingclub.com` | `200 OK` 无重定向 ✅ |
| 内部 uWSGI 直接访问 `127.0.0.1:10005` | `200 OK` 服务正常 ✅ |

---

## 五、涉及文件

| 文件 | 说明 |
|------|------|
| `/www/server/panel/vhost/nginx/python_小影CMS通用版本.conf` | Nginx 站点配置（已修复） |
| `/www/server/panel/vhost/nginx/python_小影CMS通用版本.conf.bak` | 修复前的原始配置备份 |
| `/www/wwwroot/xiaoying/小影CMS通用版本/uwsgi.ini` | uWSGI 配置（未改动） |
| `/www/wwwroot/xiaoying/小影CMS通用版本/gunicorn_conf.py` | Gunicorn 配置（未改动） |

---

## 六、排查指南（给运维人员）

如果再次遇到类似问题，按以下步骤排查：

### 6.1 确认是否为重定向循环

```bash
# 测试 HTTP 响应
curl -sI http://192.253.235.28/xiaoying_admin/login/ -H "Host: xiaoyingclub.com" -w "\nHTTP Code: %{http_code}\n"

# 测试 HTTPS 响应
curl -sk https://192.253.235.28/xiaoying_admin/login/ -H "Host: xiaoyingclub.com" -o /dev/null -w "HTTP Code: %{http_code}\n"
```

- 如果 HTTPS 返回 `301` 而非 `200` → rewrite 规则有误
- 如果 HTTPS 返回 `302` → 可能是 Django 中间件或应用层重定向

### 6.2 绕开 Nginx，直测后端服务

```bash
curl -v http://127.0.0.1:10005/xiaoying_admin/login/
```

- 如果后端返回 `200` → 问题在 Nginx 层
- 如果后端也返回非 `200` → 问题在 Django 或 uWSGI 层

### 6.3 常见 Nginx 重定向配置检查

```bash
# 查看站点完整配置
cat /www/server/panel/vhost/nginx/python_*通用版本*.conf

# 关注以下三个区域：
# 1. SSL-START → rewrite 是否缺少端口判断
# 2. HTTP_TO_HTTPS_START → $server_port != 443 判断是否完整
# 3. error_page 497 → HTTPS 证书错误时的处理
```

### 6.4 如果宝塔面板覆盖了修改

宝塔面板的"SSL"或"强制HTTPS"设置可能会重新生成配置，覆盖手动修改。如果修改后问题复现：

1. 检查配置是否被宝塔还原：`grep -n "rewrite.*permanent" /www/server/panel/vhost/nginx/python_*通用版本*.conf`
2. 可在宝塔面板中关闭"强制HTTPS"，然后在 HTTP_TO_HTTPS_START 中手动配置（含端口判断的版本）
3. 或在宝塔面板中只监听 443（不勾选 80），避免混用

---

## 七、预防措施

1. **Nginx 配置 Review**：部署新站点或修改 SSL 配置后，执行 `nginx -t` 并验证 HTTPS 无循环重定向
2. **配置规范**：`server` 块若同时监听 80 和 443，HTTPS 强制跳转一定要检查 `$server_port != 443`
3. **监控告警**：建议对关键域名配置 HTTPS 可达性监控（如 `curl -skI https://domain.com | head -1`）
4. **宝塔面板注意**：部分版本的宝塔面板在开启"强制HTTPS"时可能生成不完整的 rewrite 规则，建议修改后手动审查

---

## 八、参考命令速查

```bash
# 测试 Nginx 配置语法
nginx -t

# 热重载 Nginx
nginx -s reload

# 查看 Nginx 访问日志（定位重定向行为）
tail -f /www/wwwlogs/小影CMS通用版本.log

# 查看 Nginx 错误日志
tail -f /www/wwwlogs/小影CMS通用版本.error.log

# 查看 uWSGI 日志（确认后端是否正常）
tail -f /www/wwwlogs/python/小影CMS通用版本/uwsgi.log
```
