# Chrome DevTools MCP 多实例使用规范

> **目的**：让多个 agent / 多个 Trae 窗口各用各的 Chrome，**互不抢占**。
> **适用**：本机已安装 `chrome-devtools-mcp`（安装与自检见第八节）。
> **示例环境**：Windows + PowerShell；Linux / macOS 的差异见 2.1。

---

## 一、先搞清「会不会只有一个」

**不会只有一个。** `chrome-devtools-mcp` 是 **stdio MCP 服务器**：每个 MCP 客户端（每个 Trae 窗口 / 每个 agent 会话）都会**各自拉起一份独立进程**，天然就是多实例。

真正会「互相抢」的只有一种情况：**多个实例去连同一个 Chrome 用户目录（profile）**。
官方原文：user data dir「Only one browser can use it at a time.」

所以规则只有一句话：**一个实例 = 一个独立的 profile 目录（或各连各的端口）。**

---

## 二、参数约定（先填这张表，后文全部引用它）

本文所有命令都用占位符，**不要照抄字面值**。先按下表替换成你机器上的实际值；只改这一处，后文无需再改。

| 占位符 | 含义 | 获取方式 / 建议 |
| --- | --- | --- |
| `{MCP_HOME}` | npm 全局前缀（MCP 包与可执行文件所在目录） | `npm config get prefix` |
| `{MCP_CMD}` | MCP 服务器可执行文件 | `{MCP_HOME}/chrome-devtools-mcp.cmd`（Linux/macOS 无 `.cmd`） |
| `{CLI_CMD}` | 命令行 CLI 可执行文件 | `{MCP_HOME}/chrome-devtools.cmd` |
| `{NPM_CACHE}` | npm 缓存目录 | `npm config get cache`；要换盘见第六节 |
| `{PROFILE_ROOT}` | 各实例 profile 的根目录 | 任选**非系统盘**目录（示例形态：`<盘符>:\DevTools\chrome-profiles`） |
| `{INSTANCE}` | 实例名（一个窗口 / agent 一个） | 自取且**全局唯一**，如 `win1`、`agent-seo` |
| `{PROFILE_DIR}` | 本实例的 profile 目录 | `{PROFILE_ROOT}/{INSTANCE}` |
| `{SHOT_DIR}` | 截图与产物目录 | 建议与 profile 同盘 |
| `{LOG_DIR}` | 日志目录 | 建议与 profile 同盘 |
| `{CDP_PORT}` | 外部 Chrome 的调试端口（仅模式 C 用） | 默认 `9222`；被占用就换一个空闲端口 |
| `{CHROME_EXE}` | Chrome 可执行文件 | `Get-Command chrome.exe`；或打开 `chrome://version` 查看 |
| `{TARGET_URL}` | 你要调试的页面地址 | 任意 http(s) 地址 |

PowerShell 里一次设好（仅当前终端有效）：

```powershell
$MCP_HOME     = '<npm 全局前缀>'
$PROFILE_ROOT = '<非系统盘的 profile 根目录>'
$INSTANCE     = '<实例名，必须唯一>'
$SHOT_DIR     = '<截图与产物目录>'
$LOG_DIR      = '<日志目录>'
$CDP_PORT     = 9222
$CHROME_EXE   = '<Chrome 可执行文件>'
$TARGET_URL   = '<要调试的页面地址>'

$MCP_CMD      = Join-Path $MCP_HOME 'chrome-devtools-mcp.cmd'
$CLI_CMD      = Join-Path $MCP_HOME 'chrome-devtools.cmd'
$PROFILE_DIR  = Join-Path $PROFILE_ROOT $INSTANCE
```

> **想长期生效**：写进系统环境变量、PowerShell `$PROFILE`，或维护一个 `devtools.env.ps1` 统一加载。
> **JSON 配置不支持变量展开**（见 4.2），需要手动替换成实际路径。

### 2.1 非 Windows 对照

| Windows | Linux / macOS |
| --- | --- |
| `chrome-devtools-mcp.cmd` | `chrome-devtools-mcp` |
| `chrome-devtools.cmd` | `chrome-devtools` |
| `D:\...`、`\` | `/...`、`/` |
| `Get-Command chrome.exe` | `command -v google-chrome` / `command -v chromium` |
| `Join-Path A B` | `A/B` |

只需替换可执行文件名与路径写法，第一、二、三、五、七节的原则完全一致。

---

## 三、三种部署模式（按场景选）

| 模式 | 做法 | 适用 | 是否互相干扰 |
| --- | --- | --- | --- |
| A. 各自独立（推荐） | 每个实例传**不同的** `--user-data-dir`，或统一用 `--isolated` | 多窗口 / 多 agent 各干各的 | 互不干扰 |
| B. 共享一个服务器 | 同一客户端内多会话共用一个 server；默认开 `pageIdRouting`，每个会话按 `pageId` 路由到自己的标签页 | 一个窗口内并发多任务 | 靠 pageId 区分 |
| C. 连外部已开的 Chrome | 先用调试端口启动 Chrome，各实例用 `--browser-url` 连同一浏览器 | 想「人工登录一次、agent 复用登录态」 | 共享浏览器，同一时刻**只让一个实例操作** |

> 想复用「已登录状态」用 C；想完全隔离用 A。

---

## 四、开一个新实例的标准做法（避免抢占）

### 4.1 隔离启动（最常用）

给**每个窗口 / agent 一个专属 profile 目录**，目录名**绝不能重复**：

```text
{PROFILE_ROOT}/{INSTANCE_A}
{PROFILE_ROOT}/{INSTANCE_B}
{PROFILE_ROOT}/{INSTANCE_C}
```

一次性用完即弃的，可用 `--isolated`（临时目录，浏览器关掉自动清）。但临时目录通常落在系统临时目录（可能在系统盘），需要严格不占系统盘时**优先用 `--user-data-dir`**。

### 4.2 Trae 中新增一个 MCP 服务器（粘贴 JSON）

在 Trae「MCP」面板 → 添加（手动配置），粘贴下面的配置，并把 `{...}` 换成实际值：

```json
{
  "mcpServers": {
    "chrome-devtools-{INSTANCE}": {
      "command": "{MCP_CMD}",
      "args": [
        "--user-data-dir={PROFILE_DIR}",
        "--no-usage-statistics"
      ]
    }
  }
}
```

- 服务名 `chrome-devtools-{INSTANCE}`：**每个窗口取不同名字**，便于辨认。
- Windows 路径在 JSON 里写成 `D:\\DevTools\\...`（双反斜杠）或 `D:/DevTools/...`（正斜杠）均可。
- 未全局安装时，可改用 npx 临时启动：`"command": "<npx 可执行文件>", "args": ["-y", "chrome-devtools-mcp@latest", "--user-data-dir={PROFILE_DIR}", "--no-usage-statistics"]`。npx 每次会检查/拉取最新版，启动更慢；长期使用仍建议全局安装并写绝对路径。

### 4.3 连接外部 Chrome（模式 C，复用登录态）

```powershell
# 1) 用一个专用 profile 启动 Chrome 并开调试端口
& $CHROME_EXE "--remote-debugging-port=$CDP_PORT" "--user-data-dir=$PROFILE_ROOT\shared"

# 2) 确认端口已被监听（没有输出通常表示没起来或端口不对）
Get-NetTCPConnection -LocalPort $CDP_PORT -ErrorAction SilentlyContinue
```

```json
{
  "mcpServers": {
    "chrome-devtools-shared": {
      "command": "{MCP_CMD}",
      "args": ["-u", "http://127.0.0.1:{CDP_PORT}"],
      "env": { "CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS": "1" }
    }
  }
}
```

> ⚠️ 开调试端口 = 本机任何程序都能控制这个浏览器，别用它浏览敏感网站。
> ⚠️ 多个实例连同一个 `--browser-url` 时，**别同时操作同一个标签页**；需要并发就让各自开新标签（`new_page`）。
> ⚠️ 同一个 `shared` profile 只能被一个 Chrome 进程使用；要并行多个「共享登录态」浏览器，就给每个实例换 profile 目录并换 `{CDP_PORT}`。

---

## 五、硬性规则（红线）

1. **同一个 `--user-data-dir` 不能被两个实例同时使用**（会报 profile 占用 / 行为错乱）。
2. 一个 agent 会话**不要**去抢另一个会话正在操作的标签页；并发时各开各的页（`new_page`）。
3. 需要独立登录态的验证（如需先登录后台再截图），用**专属 profile**；用完 `--isolated` 或删除目录。
4. **不要落到系统盘**：profile、截图、日志、npm 缓存一律指到 `{PROFILE_ROOT}` / `{SHOT_DIR}` / `{LOG_DIR}` / `{NPM_CACHE}`。Chrome 程序本体可以留在系统默认安装位置。
5. 用完把后台常驻进程停掉，避免长期占端口 / 资源：`& $CLI_CMD stop`。

---

## 六、目录与 npm 配置（不落系统盘）

| 用途 | 占位符 | 说明 |
| --- | --- | --- |
| MCP 程序（全局 npm 包） | `{MCP_HOME}\node_modules\chrome-devtools-mcp` | 随 npm prefix 变化 |
| MCP 服务器可执行 | `{MCP_CMD}` | 建议在 MCP 配置里写绝对路径 |
| CLI 可执行 | `{CLI_CMD}` | 不在 PATH 时用 `& $CLI_CMD` 调用 |
| npm 全局前缀 | `{MCP_HOME}` | `npm config get prefix` |
| npm 缓存 | `{NPM_CACHE}` | `npm config get cache` |
| 各实例 Chrome profile | `{PROFILE_ROOT}\<实例名>` | 每个实例唯一 |
| 截图 / 产物 | `{SHOT_DIR}` | — |
| 日志 | `{LOG_DIR}` | — |

> 默认 profile 目录在用户目录（通常位于系统盘）：Windows 为 `%USERPROFILE%\.cache\chrome-devtools-mcp\...`，Linux/macOS 为 `~/.cache/chrome-devtools-mcp/...`——**必须用 `--user-data-dir` 覆盖**。
> npm 的 prefix / cache 默认也可能在系统盘，需要时显式改（改完确认目录存在、当前用户可写）：

```powershell
npm config set prefix "{MCP_HOME}"
npm config set cache  "{NPM_CACHE}"
```

> 改 prefix 后要把 `{MCP_HOME}` 加进 `PATH`，否则命令需写绝对路径（`$CLI_CMD`）。升级 Node / npm 后复查这两个配置是否仍生效。

Chrome 本体位置因安装方式而异（系统安装、便携版、多版本共存都可能不同），一律以 `{CHROME_EXE}` 为准；需要显式指定时可用 MCP 的 `-e / --executable-path` 参数。

---

## 七、不用 MCP 也能用：命令行 CLI

包内自带 CLI（直接驱动 Chrome，适合脚本化 / 排查）：

```powershell
& $CLI_CMD status
& $CLI_CMD start --headless --userDataDir="$PROFILE_DIR"
& $CLI_CMD new_page "$TARGET_URL"
& $CLI_CMD take_snapshot 1
& $CLI_CMD fill 1 "<uid>" "<值>"
& $CLI_CMD click 1 "<uid>"
& $CLI_CMD evaluate_script "() => document.title" --pageId 1
& $CLI_CMD take_screenshot 1 --filePath "$SHOT_DIR\screenshot.png"
& $CLI_CMD list_console_messages 1
& $CLI_CMD stop
```

- CLI 默认 **headless + isolated**；要持久 profile 就显式传 `--userDataDir`。
- CLI 也走同一个后台 daemon（Windows 用命名管道；Linux/macOS 为对应的本地通信方式）。**同一时刻一套 daemon**，`stop` 后再换参数启动。
- `{CLI_CMD}` 已在 `PATH` 时，可直接写 `chrome-devtools ...`；否则统一用 `& $CLI_CMD`。

---

## 八、安装与自检（任何人可复现）

```powershell
npm i -g chrome-devtools-mcp              # 安装 / 升级到 npm 上的当前版本
npm ls -g chrome-devtools-mcp --depth=0   # 查看实际安装版本
& $MCP_CMD --help                         # 查看当前版本支持的参数
& $CLI_CMD status                         # CLI 是否可用 / 后台 daemon 状态
```

- 本文按 `chrome-devtools-mcp` 的通用行为编写，**不绑定具体版本号**；不同版本的参数可能增减，一律以 `--help` 为准。
- 不要遥测：加 `--no-usage-statistics`，或设环境变量 `CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1`。
- 保存 MCP 配置后，需要让 Trae **重新加载 MCP**（重启窗口 / 重连）；**当前正在运行的会话不会热更新**。
- 自检通过标准：`npm ls` 能显示版本号、`--help` 正常输出、`status` 能返回状态、用独立 profile 打开 `{TARGET_URL}` 并截图成功。

---

## 九、排障

| 症状 | 处理 |
| --- | --- |
| 连不上 / 卡住 | `& $CLI_CMD stop` 后重试；或换一个 `{PROFILE_DIR}` |
| 提示 profile 被占用 | 该目录已被别的实例使用 → 换目录，或先停掉那个实例 |
| Trae 里看不到工具 | 保存 MCP 配置后**重新加载 MCP**（重启窗口/重连），本次会话不会热更新 |
| 想看后台细节 | 启动参数加 `--log-file="{LOG_DIR}\mcp.log"` |
| 不要遥测 | 加 `--no-usage-statistics`（或设 `CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1`） |
| 模式 C 端口被占用 | 换一个 `{CDP_PORT}`；用 `Get-NetTCPConnection -LocalPort <端口>` 确认是否已被监听 |
| Chrome 起不来 | 核对 `{CHROME_EXE}` 路径；检查 profile / 截图 / 日志目录是否存在且有写权限 |
| 命令找不到 | `{MCP_HOME}` 未加入 `PATH` → 用绝对路径 `$MCP_CMD` / `$CLI_CMD`，或把 `{MCP_HOME}` 加进 `PATH` |
