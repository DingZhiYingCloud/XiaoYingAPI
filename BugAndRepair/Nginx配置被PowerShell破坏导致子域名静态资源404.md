# 事故报告：Nginx 配置被 PowerShell 破坏导致子域名静态资源 404

> **⚠️ 使用说明**: 本文档中包含 `{占位符}` 的部分，需要根据实际服务器环境替换为真实值。AI 在参考本文档时，应先向用户确认这些参数再执行操作。

---

## 一、事故概述

- **事故编号**: INC-2026-001
- **严重等级**: 高（影响线上权重项目的子域名静态资源加载）
- **关键词**: Nginx、sed、PowerShell、$变量展开、@static_fallback、多域名静态资源

## 二、故障现象

权重项目绑定了多域名（如主域名 `{主域名}`、子域名 `{子域名1}`、`{子域名2}`）后：

- 主域名 → CSS/JS/媒体资源加载 **正常**
- 子域名 → CSS/JS/媒体资源 **加载失败（404）**
- 子域名访问时页面 HTML 正常加载，但静态资源全部 404

## 三、影响范围

- 所有使用 `sed` 命令从 **PowerShell 终端**修改 Nginx 配置的服务器
- 所有配置了 `@static_fallback` 回退代理块来服务子项目静态资源的权重项目

## 四、根因分析

### 4.1 直接原因

在 PowerShell 中执行 `sed` 命令修改 Nginx 配置文件时，PowerShell **自动展开**了 Nginx 的 `$变量`，导致 Nginx 配置中的变量被替换为错误的值：

| 原 Nginx 变量 | PowerShell 展开结果 | 后果 |
|--------------|-------------------|------|
| `$http_host` | 空字符串 | `Host` 请求头为空 |
| `$remote_addr` | 空字符串 | 客户端 IP 为空 |
| `$host` | `System.Management.Automation.Internal.Host.InternalHost` | 主机名变为 PowerShell 内部对象 |
| `$server_port` | 空字符串 | 端口为空 |
| `$scheme` | 空字符串 | 协议为空 |
| `$proxy_add_x_forwarded_for` | 空字符串 | 转发 IP 链为空 |

### 4.2 根本原因

1. **工具链兼容性问题**: `sed` 是 Unix 工具，在 PowerShell 下执行时 `$` 符号的行为与预期不同
2. **未在应用前验证**: 修改后的 Nginx 配置未使用 `nginx -t` 做语法检查
3. **缺少 Nginx 配置备份**: 修改前未备份原始配置，导致难以回滚对比

### 4.3 为什么主域名看似正常？

Nginx 的 `location /static/` 配置了 `alias` 直接映射到主项目的静态目录：

```nginx
location /static/ {
    alias {STATIC_ROOT};
    try_files $uri $uri/ @static_fallback;  # 找不到时才 fallback
}
```

- **主域名**: 部分静态文件恰好存在于主项目的 `static/` 目录中，被 `alias` 直接命中 → 正常
- **子域名**: 子项目可能有独立的静态文件，不在主项目目录中，需要 fallback 到子项目 → 但 `@static_fallback` 的 Host 头已被破坏，后端服务收到请求时无法匹配域名 → 返回 404

## 五、解决方法

### 5.1 标准修复流程

> **关键原则**: 不要使用 `sed` 从 PowerShell 修改 Nginx 配置。

**推荐方案：使用 Python 脚本修改**

将以下脚本中的 `{NGINX_CONF_PATH}` 替换为实际路径后执行：

```python
import re

filepath = '{NGINX_CONF_PATH}'  # 例: /etc/nginx/sites-enabled/default
with open(filepath, 'r') as f:
    content = f.read()

# 用正则匹配需要替换的区域（根据实际注释标识调整）
old_pattern = re.compile(
    r'# =====+ 静态资源配置开始 =====+\n'
    r'.*?location /static/ \{[^}]*?\}\n'
    r'.*?location @static_fallback \{[^}]*?\}\n'
    r'.*?location /media/ \{[^}]*?\}\n'
    r'.*?# =====+ 静态资源配置结束 =====+',
    re.DOTALL
)

# 注意: {STATIC_ROOT}、{MEDIA_ROOT}、{PROXY_PASS_URL} 替换为实际值
new_block = '''# ===================== 静态资源配置开始 =====================
    location /static/ {
        alias {STATIC_ROOT};
        expires 30d;
        add_header Cache-Control "public, no-transform";
        access_log off;
        try_files $uri $uri/ @static_fallback;
    }
    location @static_fallback {
        proxy_pass {PROXY_PASS_URL};
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Real-Port $remote_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header Remote-Host $remote_addr;
    }
    location /media/ {
        alias {MEDIA_ROOT};
        expires 30d;
        add_header Cache-Control "public, no-transform";
        access_log off;
        try_files $uri $uri/ @static_fallback;
    }
    # ===================== 静态资源配置结束 ====================='''

if old_pattern.search(content):
    content = old_pattern.sub(new_block, content)
    with open(filepath, 'w') as f:
        f.write(content)
    print('修复成功')
else:
    print('未找到匹配的配置块')
```

### 5.2 验证步骤

```bash
# 1. 检查 Nginx 语法
nginx -t

# 2. 重载 Nginx
nginx -s reload

# 3. 验证访问（替换为实际域名）
curl -I https://{子域名}/static/css/style.css
# 预期返回 200，而非 404
```

## 六、Nginx 静态资源配置（通用模板）

> 将以下 `{占位符}` 替换为实际值。

```nginx
# ===================== 静态资源配置开始 =====================
location /static/ {
    alias {STATIC_ROOT};          # 例: /www/wwwroot/myproject/static/
    expires 30d;
    add_header Cache-Control "public, no-transform";
    access_log off;
    try_files $uri $uri/ @static_fallback;
}
location @static_fallback {
    proxy_pass {PROXY_PASS_URL};  # 例: http://127.0.0.1:8000
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Real-Port $remote_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header Remote-Host $remote_addr;
}
location /media/ {
    alias {MEDIA_ROOT};           # 例: /www/wwwroot/myproject/media/
    expires 30d;
    add_header Cache-Control "public, no-transform";
    access_log off;
    try_files $uri $uri/ @static_fallback;
}
# ===================== 静态资源配置结束 =====================
```

## 七、预防措施

### 7.1 修改 Nginx 配置的规范流程

```
1. [备份]     cp {NGINX_CONF} {NGINX_CONF}.bak.$(date +%Y%m%d)
2. [修改]     不要在 PowerShell 中执行 sed，改用 vi/vim 或 Python 脚本
3. [验证]     nginx -t
4. [重载]     nginx -s reload
5. [验收]     访问多个子域名的静态资源，确认均返回 200
```

### 7.2 安全检查清单

- [ ] 修改前备份：`cp {NGINX_CONF} {NGINX_CONF}.bak.$(date +%Y%m%d)`
- [ ] 修改后语法检查：`nginx -t`
- [ ] 重载后访问验证：`curl -I https://{子域名}/static/css/style.css`
- [ ] 检查所有域名的静态资源均可正常加载
- [ ] 检查 Nginx 错误日志：`tail -f /var/log/nginx/error.log`

### 7.3 保险命令（一键回滚）

```bash
# 如果 nginx -t 失败，立即回滚（将文件名替换为实际备份文件）
cp {NGINX_CONF}.bak.$(date +%Y%m%d) {NGINX_CONF}
nginx -t && nginx -s reload
```

## 八、AI 排查 SOP（通用版）

当出现"主域名正常、子域名静态资源 404"时，按以下顺序排查：

> AI 在执行每一步前，先向用户确认 `{NGINX_CONF_PATH}` 等参数的实际值。

1. **检查 Nginx 配置语法**
   ```bash
   nginx -t
   ```
   如果报错，检查配置中是否有 `^` 残留、引号未闭合、PowerShell 变量展开等问题。

2. **检查 `@static_fallback` 块的 proxy_set_header**
   ```bash
   grep -A 10 'location @static_fallback' {NGINX_CONF_PATH}
   ```
   确认所有 `$变量` 没有被展开成空值或错误值。

3. **检查后端应用的中间件域名匹配逻辑**
   - 确认域名匹配中间件中是否遍历了项目的多个域名
   - 确认通配符匹配（`*.xxx.com`）逻辑是否正确
   - 确认数据库中的域名字段是否支持存储多个域名

4. **跳过 Nginx 直连后端测试**
   ```bash
   # 将 {PROXY_PASS_URL} 和 {子域名} 替换为实际值
   curl -H "Host: {子域名}" {PROXY_PASS_URL}/static/css/style.css
   ```
   跳过 Nginx，直接测试后端能否正常提供静态文件。

---

## 附录：参数确认表（AI 需先向用户确认）

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `{NGINX_CONF_PATH}` | `/etc/nginx/nginx.conf` | Nginx 配置文件路径 |
| `{STATIC_ROOT}` | `/www/wwwroot/myproject/static/` | 主项目静态文件目录 |
| `{MEDIA_ROOT}` | `/www/wwwroot/myproject/media/` | 主项目媒体文件目录 |
| `{PROXY_PASS_URL}` | `http://127.0.0.1:8000` | Django 后端代理地址 |
| `{主域名}` | `example.com` | 权重项目绑定的主域名 |
| `{子域名}` | `www.example.com` | 出现 404 的子域名 |
