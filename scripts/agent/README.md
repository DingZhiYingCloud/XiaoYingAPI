# 🧠 ai-brain / ai-agent 部署与使用手册

> **一句话**：你跟「大脑」说大白话，它拆解任务、**同时指挥**你所有服务器上的「子 agent」，
> 各自在本机独立干活，最后汇总成「**哪台成功、哪台失败、关键数据是多少**」汇报给你。
>
> 面向"不想懂太多 Linux 也能照着做"：**每一步都有完整命令 + "看到什么算成功"**。
> 出问题先看 **第 16 节《常见问题》**。

**当前版本**　🧠 大脑 `3.4.0`　·　🐧 Linux 子 agent `2.13.0`　·　🪟 Windows 子 agent `2.3.0`

---

**🗂️ 本手册怎么读**

| 部分 | 管什么 | 节 |
| :-- | :-- | :-- |
| 🧠 **第一部分 · 大脑** | 只装 1 台（Linux）：部署 / 升级 / 运维 / 配置 | 3 – 5 |
| 🐧 **第二部分 · 子 agent（Linux）** | 每台 Linux 装一遍：部署 / 升级 / 运维 / 卸载 | 6 – 7 |
| 🪟 **第三部分 · 子 agent（Windows）** | 每台 Windows 装一遍：部署 / 升级 / 运维 / 卸载 | 8 – 9 |
| 📚 **附录 · 与平台无关** | 怎么用 / 提示词 / 拉黑自毁 / 排查 / 版本记录… | 10 – 21 |

> 🤝 **两个平台的子 agent，对大脑来说行为完全一致**（同协议 / 同签名 / 同端点 / 同会合）；
> 区别只在"程序形态、装法、自启方式、命令长相" —— 一张表看懂 → **第 1 节**。

**📖 图例（全文通用）**

| 标记 | 含义 |
| :-- | :-- |
| 💡 | 提示 / 小技巧 |
| ⚠️ | 注意，容易踩坑 |
| ✅ ❌ | 推荐做法 / 不要这样做 |
| 🖥️【…】 | 这条命令**在哪台机器**上执行，如【你的电脑 / 本地机】【新服务器】【大脑那台】 |

**🧭 快速导航**（按"想干什么"找）：

| 想干什么 | 看第几节 |
| :-- | :-- |
| 搞懂这东西是啥 / 两个平台的区别 / 开工前须知 | 0、1、2 |
| 🧠 **【第一部分】部署「大脑」** | 3 |
| 🧠 大脑的升级 / 运维命令 / 数据文件 / 配置项 | 4、5 |
| 🐧 **【第二部分】Linux 子 agent**：部署 | 6 |
| 🐧 Linux 子 agent：升级 / 运维 / 卸载 / 数据文件 | 7 |
| 🪟 **【第三部分】Windows 子 agent**：部署 | 8 |
| 🪟 Windows 子 agent：升级 / 运维 / 卸载 / 数据文件 | 9 |
| 📚 【通用】怎么用 / 改提示词加技能 / 换个目录放 | 10、11、12 |
| 📚 【通用】拉黑自毁 / 邮件报警 / 彻底清理 | 13、14、15 |
| 📚 【通用】出错排查 / 域名+HTTPS / 安全 / 计划 / 会合 / 版本 | 16–21 |

---

## 🎯 0. 这东西是干什么的

你跟 **Agent 大脑** 说大白话，它拆解任务、**同时指挥**你所有服务器的 **子 agent**；
每个子 agent 在**自己那台机器上独立完成**（自己直连大模型），把结论回报给大脑；
最后由大脑汇总成 **「哪台成功、哪台失败、关键数据是多少」** 汇报给你。

```
   你（命令行）
      │  跟它说大白话
      ▼
   Agent 大脑（1 台，Linux）    ← 理解意图 / 下发任务 / 汇总结果
      │
      │  子 agent 主动连它（穿透 NAT，不用给每台开端口）
      ├──────────────┬──────────────┐
      ▼              ▼              ▼
   ai-agent       ai-agent       ai-agent
   server-1       server-2       win-pc-3
   （Linux）      （Linux）      （Windows）    ← 每台自己直连大模型干活
```

| 文件/目录 | 放在哪 | 作用 |
| --- | --- | --- |
| `brain` | **1 台**（大脑） | 入口脚本：解析命令、分发 |
| `brainlib/` | 同上 | 大脑的实现（十几个小模块，见第 1 节） |
| `prompts/` | 同上 | **提示词与技能**（纯文本，改这里不用碰代码） |
| `ai-agent` | **每台 Linux** 服务器 | Linux 子 agent：领任务、本机干活、回报结论 |
| `win/ai-agent.ps1` | **每台 Windows** 机器 | Windows 子 agent（纯 PowerShell，功能与 Linux 版一模一样） |

### 开发版 / 生产版（加密）

子 agent 分成两份，各管各的（**两个平台都是这个套路**）：

| 版本 | Linux 在哪 | Windows 在哪 | 长什么样 |
| --- | --- | --- | --- |
| **开发版**（明文） | `scripts/agent/ai-agent` | `scripts/agent/win/ai-agent.ps1` | 可读、可改、可 diff —— 平时改代码、查问题都用它 |
| **生产版**（加密） | 部署到服务器上那份 | 部署到 Windows 上那份 | 正文 AES-256 加密，打开是乱码 |

在 `scripts/agent/` 下打包（**两个平台各有各的打包脚本**）：

```bash
# —— Linux 生产版 ——
bash tools/pack-agent.sh ai-agent --online --brain https://{大脑域名}/ai-brain   # 推荐：在线取密钥
bash tools/pack-agent.sh ai-agent                                              # 内嵌口令（旧模式）
```

```powershell
# —— Windows 生产版 ——（在你自己的 Windows 上打；大脑在远端，本机没有 brain.conf）
# ⚠️ 所以 `-Online` 必须显式给 `-Key`：先把大脑上的 PACK_KEY 取到本机变量，再打包
$pk = (ssh -p {SSH端口} root@{大脑IP} "grep '^PACK_KEY=' /root/.ai-brain/brain.conf | cut -d= -f2-").Trim()
powershell -File .\win\pack-agent.ps1 -Online -Brain https://{大脑域名}/ai-brain -Key $pk -Out .\win\dist\ai-agent.ps1

powershell -File .\win\pack-agent.ps1     # 内嵌口令（旧模式：文件里自带钥匙，安全性差一档，不推荐）
```

> ⚠️ **Windows 打包最常踩的坑**：`-Online` 打包**必须先有 `PACK_KEY`**（正文要用它加密）；
> 而 `pack-agent.ps1` 在没给 `-Key` 时，只会去**打包这台机器**上找 `%USERPROFILE%\.ai-brain\brain.conf` ——
> 大脑在远端、本机没这个文件，于是报 **`读不到大脑的 PACK_KEY：请先 brain init，或用 -Key 指定`**。
> **解法**：按上面的写法，先 `ssh` 把 `PACK_KEY` 取下来再 `-Key`。
> （Linux 版没这个坑：它认 `BRAIN_HOME`，而且通常就在大脑那台打包，能就地读到。）

| 模式 | 文件里有密钥吗 | 拷走文件能解吗 |
| --- | --- | --- |
| `--online`（推荐） | **没有** | **解不开**（除非他同时知道注册口令、且能连上大脑） |
| 默认（内嵌） | 有（拆段 + 变换） | 花点功夫能解 |

`--online` 换了密钥后：`PACK_SECRET` 会缓存在子 agent 的 `agent.conf`（Linux 600），启动时复用，不再问你。
（轮换大脑的 `PACK_KEY` 走**双口令过渡**：`brain pack-key rotate` 会把旧口令留作过渡，新口令生效后**还没升级的老文件仍能启动**，不会整片失联；等全部子 agent 都升级完，再 `brain pack-key drop-old`。详见 §5。）

产物与用法：

- **Linux**：产物 `tools/dist/ai-agent`，**本身仍是合法 bash**（`bash -n` 能过），运行时在**内存里**解密执行（**不落明文文件**），照样支持 `--version` / 自升级 / 多副本。
- **Windows**：产物 `win/dist/ai-agent.ps1`，**本身仍是合法 PowerShell**（能通过语法解析），运行时在**内存里**解密执行（`[ScriptBlock]::Create`），照样支持 `version` / 自升级 / 多副本。
- **部署和升级都用加密版**：Linux `scp tools/dist/ai-agent …`、`brain release … --os linux`；Windows `tools\pack-agent.ps1` 产物 + `brain release … --os win`（这样升完级也还是加密的）。

**打包做了哪些加固**（两个平台一致，都是"提高门槛"，不是不可破）：

1. **瘦身**：生产版里**不留注释、不留空行**；
2. **压缩**：正文（Linux 先 gzip）后再加密；
3. **加密**：AES-256-CBC + PBKDF2（**60 万次**迭代、随机 salt）；
4. **口令不整存**：拆成几段，base64 + rot13 变换后藏进随机变量；
5. **密文打散**：base64 密文切成 4 段、各藏进随机变量名，运行时再拼回（防"抓一整条 base64"式提取）；
6. **去特征**：命令名/算法名在**运行时拼装** —— 文件里搜不到 `openssl` / `base64` / `gzip` / `aes-256-cbc` 等字样；变量名每次随机、报错信息通用化；
7. **完整性校验**：密文带 **HMAC-SHA256**，被改过即 `package error`；
8. **轮换友好**：密文先按「当前口令」校验、不匹配自动退到「过渡旧口令」—— 大脑轮换口令时，还没升级的老文件仍能启动（配合 `brain pack-key`）。

> ⚠️ 两点必须知道：
> 1. 打包口令在 `tools/pack.key`（Linux）/ `win/pack.key`（Windows）—— **别提交进仓库**（已在 `.gitignore` 里加了 `pack.key`；产物目录 `dist/` 也由 `dist` 规则覆盖）；口令丢了，以后就打不出"同一把钥匙"的包了。
> 2. 以上都只是**提高门槛**：密钥必须随文件走，有管理员权限、又会写脚本的人仍能还原（静态解不开就动态取）。

---

## 🧭 1. 总览：三个角色、两个平台

### 1.1 三个角色

| 角色 | 装在哪 | 干什么 |
| --- | --- | --- |
| **大脑**（`brain`） | 1 台 Linux 服务器（对外走 `https://域名`） | 理解你的话 → 拆解 → 下发 → 汇总；管注册 / 心跳 / 升级发布 / 审计 / 邮件报警 |
| **子 agent（Linux）** | 每台被管的 Linux 服务器 | 领任务 → 在本机用大模型+shell 干活 → 回报 |
| **子 agent（Windows）** | 每台被管的 Windows 机器 | 领任务 → 在本机用大模型+PowerShell 干活 → 回报 |

### 1.2 Linux / Windows 子 agent 对照表（**重点**）

> 一句话：**对大脑来说两者一模一样**（同协议/同端点/同签名/同会合/同注册流程/同自升级/同多副本/同自愈/同自毁）；
> 下面的差异只是"在这台机器上怎么装、怎么起、敲什么命令"。

| 维度 | 子 agent（Linux） | 子 agent（Windows） |
| --- | --- | --- |
| **程序文件** | `ai-agent`（单文件 bash；开发版在 `scripts/agent/ai-agent`，生产版在服务器上） | `ai-agent.ps1`（单文件 PowerShell；开发版在 `win/ai-agent.ps1`，生产版在 Windows 上） |
| **运行环境** | 需 `bash`/`curl`/`openssl`/`gzip`（服务器一般都有） | **纯 PowerShell 5.1**（Windows 自带，**零依赖**，不用装任何东西） |
| **"本机干活"用什么** | `bash` 命令 | `powershell` 命令 |
| **加密打包工具** | `bash tools/pack-agent.sh ai-agent` | `powershell -File win\pack-agent.ps1` |
| **部署入口** | 一行 `curl … \| ai-agent setup` | 一行 `iwr … ; ai-agent.ps1 setup` |
| **命令长相** | `./ai-agent <子命令>` | `.\ai-agent.ps1 <子命令>`（子命令同名） |
| **数据目录** | `~/.ai-agent/` | 管理员：`C:\ProgramData\.ai-agent\`<br>非管理员：`%LOCALAPPDATA%\.ai-agent\` |
| **隐藏副本目录** | `~/.local/.a-<8位哈希>/<1..N>/ai-agent` | 管理员：`C:\ProgramData\.a-<8位哈希>\<1..N>\ai-agent.ps1`<br>非管理员：`%LOCALAPPDATA%\.a-<8位哈希>\` |
| **开机自启** | root：systemd 服务 `ai-agent`（没有 systemd 就退回 cron `@reboot`）<br>**非 root：写进你自己的 crontab**（`@reboot` + 每分钟 watchdog，**不需要 sudo**） | 管理员：**计划任务** `WinHealthCheck`（开机启动，SYSTEM）+ `WinHealthCheck1`（每分钟 watchdog）<br>非管理员：**注册表 Run 键** + 常驻"监工"进程 |
| **每分钟兜底** | cron `* * * * *` 跑 `watchdog` | 计划任务 `WinHealthCheck1` 每分钟跑 `watchdog`（非管理员则是常驻 `supervise` 进程） |
| **暂停子 agent** | `systemctl stop ai-agent` / `pkill -f 'ai-agent run'` | `Stop-ScheduledTask -TaskName WinHealthCheck`（或 `Get-Process … \| Stop-Process`） |
| **看运行日志** | `~/.ai-agent/agent.log` + `journalctl -u ai-agent -f` | `C:\ProgramData\.ai-agent\agent.log` |
| **自升级** | 自动（≤10 分钟）或 `./ai-agent update` | 自动（≤10 分钟）或 `.\ai-agent.ps1 update` |
| **发布到大脑** | `brain release <包> --os linux --version x` | `brain release <包> --os win --version x` |
| **给主人传文件** | `./ai-agent upload <文件>` → 打印在线链接 | `.\ai-agent.ps1 upload <文件>` → 打印在线链接 |
| **拉黑自毁** | 同：大脑 `brain block <id>` → 它自己清干净 | 同（行为一致） |
| **卸载** | `./ai-agent uninstall` + 删目录 | `.\ai-agent.ps1 uninstall` + 删两个目录（见 §9） |

### 1.3 大脑的目录结构

```
agent/
├── brain                  ← 大脑入口（很薄，只管参数分发）
├── brainlib/              ← 大脑的实现，按职责拆分
│   ├── __init__.py        包标记 + 大脑版本号（VERSION）
│   ├── conf.py            配置与路径（所有“放哪、读什么”都在这）
│   ├── ui.py              终端输出与交互（颜色 / 动作样式 / 确认）
│   ├── store.py           SQLite：表结构、查询、审计
│   ├── secure.py          HMAC 请求签名校验、RSA 签名/验签
│   ├── llm.py             调用大模型（流式 / 整段，按配置切换）
│   ├── render.py          把流式输出渲染成「思考 / 结果」两种样式
│   ├── prompts.py         加载 prompts/ 里的提示词与技能
│   ├── registry.py        数据驱动的"文件文档"（brain files / explain 用）
│   ├── rendezvous.py      会合：用种子+期号算域名、brain_id、注册状态判定
│   ├── server.py          HTTP 服务与全部对外端点
│   ├── api.py             本机 CLI 与服务之间的小客户端
│   ├── admin.py           init / status / stop / rendezvous / release / pending / approve…
│   ├── explain.py         "让 AI 用大白话解读文件"（brain explain）
│   ├── chat.py            对话 CLI（把大白话变成动作，再汇总汇报）
│   └── util.py            零散小工具
├── prompts/               ← 提示词与技能（纯文本）
│   ├── system.md          系统提示词主体（含 {{ACTIONS}}/{{SKILLS}}/{{ENV}} 占位）
│   ├── actions.md         可用动作清单
│   └── skills/            额外技能/背景知识（丢 *.md 进去即可生效）
├── ai-agent               ← 子 agent（Linux，**故意保持单文件**）
└── win/
    ├── ai-agent.ps1       ← 子 agent（Windows，**同样是单文件**）
    ├── pack-agent.ps1     ← Windows 生产版打包工具
    └── dist/              ← 打包产物（`ai-agent.ps1`；不进仓库）
```

**为什么子 agent 不像大脑那样拆成多文件？**
因为子 agent 的「自升级」机制是**用新版本覆盖自己那一个文件**；拆成多文件后，
升级就要处理"哪个文件属于哪个版本、旧文件怎么清理"，很容易升到一半变坏。
**两个平台的子 agent 都是单文件**，升级最稳。

> **每个数据文件是干什么的**：大脑见 **4.3**，Linux 子 agent 见 **7.3**，Windows 子 agent 见 **9.3**；
> **当前版本与升级记录**见 **第 21 节**。也可以直接敲下面这几个命令。

- `python3 brain files` —— **文件文档控制台**，逐条列出：位置 / 何时产生 / 干什么用 / 能不能删 / 怎么看
- `python3 brain explain` —— 让 AI 用大白话讲一遍（还能追问，如 `brain explain "删了会怎样"`）
- `python3 brain version` —— **看版本**（大脑 / 两个平台各自的最新发布版 / 每台服务器实际版本）

---

## 📌 2. 开工前，先弄懂 3 件事

### ① "脚本文件"和"数据目录"是两回事

| | 是什么 | 能不能换位置 |
| --- | --- | --- |
| **程序文件** | 代码 + 提示词（大脑是 `agent/` 整个目录；子 agent 是那**一个文件**） | ✅ 放哪都行（第 12 节） |
| **数据目录** | 配置、数据库、密钥、令牌 | ✅ 也能换，用环境变量指定（第 12 节） |

> 子 agent 的数据目录：Linux `~/.ai-agent/`；Windows 管理员 `C:\ProgramData\.ai-agent\`、非管理员 `%LOCALAPPDATA%\.ai-agent\`。

### ② 需要几把"大模型 Key"

| 谁 | 需要吗 | 说明 |
| --- | --- | --- |
| 大脑 | **1 把** | 它自己要用一次大模型：理解你的意图 + 汇总汇报 |
| 每个子 agent | **每台 1 把** | 子 agent 在本机自己直连大模型干活（v1 固定 Key；v2 会改成向大脑要临时 Key） |

> Key 只写在机器的权限受保护配置文件里（Linux 600），**不要贴在聊天/文档里**。

### ③ 两台机器要能通（**必须域名 + HTTPS**）

- 子 agent → 大脑：`https://你的域名`（**子 agent 主动连出去**，只需"出口"能通 443）；
  Linux 和 Windows 都一样，**Windows 那台只要能访问这个 https 域名即可**。
- 大脑**只监听本机**；对外一律经 nginx + 域名 + 有效证书，**不允许** `http://` 或 IP 直连。

> 硬规则：`PUBLIC_URL` / `BRAIN_URL` **只能是 `https://域名`**。写成 `http://` 或 IP：
> 子 agent 会**拒绝连接并等待**（`run` 常驻自动重试；`enroll` 直接提示并退出）。

---

# 🧠 第一部分 · 大脑（只装 1 台，Linux）

## 🚀 3. 部署「大脑」（只做 1 次）

### 3.1 上传**整个目录**

> ⚠️ **必须把 `brain` + `brainlib/` + `prompts/` 一起传**，只传 `brain` 会起不来。

**方式 A：用 scp 传整个目录**（在你的电脑 / 本地机上，于 `x:\XiaoYingAPI\scripts\` 下执行）

```powershell
scp -r -P {SSH端口} .\agent root@{大脑IP}:/root/agent
```

> ⚠️ 首次部署（`/root/agent` 本来不存在）上面这条没问题；
> 但若该目录**已存在**，`scp -r` 会把 `agent` 塞进去变成 `/root/agent/agent/`。
> 那种情况属于「升级」，请走 **第 4 节**（先删远端旧目录，再传）。

**方式 B：宝塔面板** → 文件 → 进入 `/root/` → 上传 `agent` 文件夹（面板支持传目录；不行就先本地压缩成 zip，传上去再解压）。

### 3.2 转换行 + 加执行权限（**从本地机上传必做**）

```bash
cd /root/agent
find . -type f -exec sed -i 's/\r$//' {} +      # 一次把所有文件转成 Linux 换行
chmod +x brain
python3 -c "import py_compile,pathlib; [py_compile.compile(str(p),doraise=True) for p in pathlib.Path('brainlib').glob('*.py')]; print('代码自检 OK')"
```

**看到 `代码自检 OK` 就说明文件没问题。**

### 3.3 初始化

```bash
python3 brain init
```

**看到类似输出就算成功**（两样都要抄下来保存）：

```
大脑已初始化（数据目录 /root/.ai-brain）

下面两样请记好：
  注册口令   174b9c66……（一长串）        ← 部署子 agent 时要输入它
  子 agent 公钥  /root/.ai-brain/signing.pub   ← 要拷到每台子 agent
```

### 3.4 填大脑自己的大模型 Key

```bash
vi /root/.ai-brain/brain.conf
```

把 `AI_API_KEY=` 填上你的 Key，保存退出（其他行保持默认）：

```ini
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash        # ← 改成你后台实际能用的模型名
AI_API_KEY=sk-你的Key              # ← 填这里
STREAM=1                          # 1=流式输出（默认）；0=整段输出
SHOW_REASONING=1                  # 1=显示模型思维链（💭 那段）；0=不显示
```

> 全部可配置项见 **第 5 节**。

### 3.5 启动并验证

```bash
cd /root/agent
nohup python3 brain serve >/root/.ai-brain/serve.out 2>&1 &
sleep 2
# 仅确认“进程起来了”（走回环自检；正式访问一律走 https 域名）
curl -s http://127.0.0.1:8787/health      # 应回 {"ok": true, "version": "2.10.1", ...}
```

> ⚠️ **光起进程还不算完**：本机 CLI 与子 agent 都只认 `https://域名`。所以**必须**先按第 17 节
> 配好 域名 + nginx + 证书，并在 `brain.conf` 里设置 `PUBLIC_URL=https://你的域名[/ai-brain]`，
> 之后 `python3 brain status` 才会出结果。

**接着配好第 17 节后，用这条验证最终可用性**：

```bash
curl -s https://你的域名/ai-brain/health  # 应回 {"ok": true, ...}
```

### 3.6 （可选）让 `brain` 变成随手可用的命令

```bash
ln -sf /root/agent/brain /usr/local/bin/brain
brain status        # 能出结果就成了
```

---

## 🔧 4. 大脑：升级 / 运维命令 / 数据文件

### 4.1 升级「大脑」（全手动，换代码不丢数据）

> **一条铁律**：升级只换「程序目录」，**绝对不要删 `~/.ai-brain`**。
> 那里放着签名密钥、注册口令、数据库；删了就等于重装（要重新 `brain init` + 所有子 agent 重新注册）。
> 大脑重启后，所有子 agent 会**自动重连**，子 agent 什么都不用做。

下面的命令分在**两个地方**执行，每条都标了标签，别搞混：

| 在哪执行 | 干什么 |
| --- | --- |
| **你的电脑 / 本地机** | 删掉服务器上的旧程序目录 → 上传新版 |
| **大脑服务器（SSH 登录后）** | 备份 → 转换行/自检 → 重启 → 验证 |

按顺序做，**第 1~5 步，一步都不能跳**。

#### 第 1 步｜备份 —— 【在大脑服务器执行】

```bash
cp -r /root/agent /root/agent.bak-$(date +%Y%m%d-%H%M)
```

#### 第 2 步｜上传新版 —— 【在你的电脑 / 本地机执行】

> ⚠️ **最容易翻车的一步，务必看清**：
> 服务器上 `/root/agent` 如果**已经存在**，直接 `scp -r .\agent root@{大脑IP}:/root/agent`
> 会把整个 `agent` **塞进旧目录里**，变成 `/root/agent/agent/` —— 新版根本没生效，
> `brain version` 还是旧号。**正确做法：先删远端旧目录，再传。**

在 `x:\XiaoYingAPI\scripts\` 目录下，**一行一条**执行：

```powershell
# 2-1 让服务器删掉旧程序目录（第 1 步已备份，删程序目录不影响数据）
ssh -p {SSH端口} root@{大脑IP} "rm -rf /root/agent"

# 2-2 上传新版整个 agent 目录（此时 /root/agent 不存在，scp 会直接创建，不会套层）
scp -r -P {SSH端口} .\agent root@{大脑IP}:/root/agent
```

> 也可以用宝塔面板：进入 `/root/`，**先删掉** `agent` 文件夹，再把新 `agent` 文件夹传上去
> （或传 zip 后解压）；同样是"先删再传"，别直接覆盖。

#### 第 3 步｜转换行 + 权限 + 自检 —— 【在大脑服务器执行】

```bash
cd /root/agent
find . -type f -exec sed -i 's/\r$//' {} +
chmod +x brain
python3 -c "import py_compile,pathlib; [py_compile.compile(str(p),doraise=True) for p in pathlib.Path('brainlib').glob('*.py')]; print('代码自检 OK')"
```

**看到 `代码自检 OK` 才继续往下。** 这一步报错就**别重启**，先按 4.3 回滚。

#### 第 4 步｜重启 —— 【在大脑服务器执行】

```bash
python3 brain stop
nohup python3 brain serve >/root/.ai-brain/serve.out 2>&1 &
sleep 2
```

#### 第 5 步｜验证 —— 【在大脑服务器执行】

```bash
curl -s https://你的域名/ai-brain/health  # 应回 {"ok": true, "version": "2.10.1", ...}
python3 brain version                     # 应显示「大脑当前版本: 2.10.1」
python3 brain status                      # 能出结果、子 agent 仍在线（说明数据没丢）
```

**升级成功的标志（三个都对才算成功）：**

- `brain version` 显示的版本号是**新版号**；
- `/health` 里的 `version` 也是**新版号**；
- `brain status` 里子 agent **仍在线**（说明数据没丢）。

补两句：

- 第 3 步报错 → **别重启**，把备份换回来：`rm -rf /root/agent && mv /root/agent.bak-xxxx /root/agent`
- 新增的配置项（例如新版本多了 `STREAM`）**不会自动写进你的 conf**，用默认值即可；
  想改就手动加一行到 `~/.ai-brain/brain.conf`
- 你放在 `~/.ai-brain/prompts/` 的自定义提示词**不受升级影响**（这是设计如此）

### 4.2 大脑的日常运维命令

```bash
python3 brain serve        # 前台跑（调试看日志用）
python3 brain status       # 服务 + 各服务器概况（含系统 / 挡位）
python3 brain version      # 看版本：大脑 / 两个平台各自最新发布版 / 各机实际版本
python3 brain files        # 文件文档控制台（每个文件干什么用、能不能删）
python3 brain explain "问题"   # 让 AI 用大白话解读这些文件
python3 brain pending      # 待批准的新机器
python3 brain approve <id> # 批准接入
python3 brain deny <id>    # 拒绝接入
python3 brain stop         # 停止后台服务：先按 brain.pid 停，再兜底检查端口(8787) 是否还被旧 brain 占着并一并终止
python3 brain pubkey       # 打印公钥
python3 brain rendezvous   # 会合：看/换后台域名（换服务器 / 换域名时用，见第 20 节）
python3 brain block <id>   # 拉黑一台子 agent：三层确认后，命令它自毁（见第 13 节）
python3 brain unblock <id> # 解除拉黑（误拉黑时用）
python3 brain test-mail    # 发一封测试邮件，验证"邮件报警"通道（见第 14 节）
python3 brain uploads      # 看子 agent 传上来的文件（截图/日志…）：列表带在线链接
                           #   --rm <id> 删一个；--clean 全清
python3 brain get <id>     # 把某个上传的文件取回本机（默认存当前目录，-o 指定路径）
python3 brain tasks        # 看任务与结果（默认最近 20 条；--running 只看排队/执行中）
                           #   参数可以是 agent_id，也可以直接是任务 id（那会显示全文）
python3 brain cancel <任务id>  # **真取消**：排队的直接作废；执行中的会在**下一步之前**停手
                           #   也支持 --agent <agent_id> / --all
python3 brain rename <旧名> <新名>  # 给一台子 agent 改名（只改大脑；旧名自动变别名，机器不用动）
python3 brain rm <名字> [--force] [--purge]
                           # 删除一台：先命令它自毁 → 确认后再从大脑删掉记录
                           #   --force 不等确认；--purge 连任务与上传文件一起清
python3 brain release <包> --os linux|win --version <版本> [--notes "说明"]   # 发布子 agent 升级包

# —— 看日志 ——
tail -f ~/.ai-brain/brain.log     # 大脑运行日志
tail -f ~/.ai-brain/serve.out     # 大脑启动输出
```

> `brain release --os win` 用于发布 **Windows 子 agent** 升级包；Linux 用 `--os linux`（默认）。
> 两个平台**各自维护"最新发布版"**，互不影响。

### 4.3 大脑的数据文件

**最省事的看法**（不用记下面的表）：

```bash
python3 brain files                 # 文档控制台：逐条列出 位置/何时产生/干什么用/能不能删/怎么看
python3 brain explain               # 让 AI 用大白话讲一遍
python3 brain explain "signing.key 删了会怎样？"   # 还能追问
```

#### 大脑数据目录 `~/.ai-brain/`

| 文件 | 何时产生 | 干什么用 | 能删吗 |
| --- | --- | --- | --- |
| `brain.conf` | `brain init` 生成；改挡位/手动编辑时更新 | 全部配置：端口、模型与 Key、挡位 `MODE`、步数上限、注册口令、管理令牌。**权限 600** | ❌ 不能删（等于恢复出厂：要重新 `init`，所有子 agent 重新注册） |
| `brain.db` | `init` 建表；之后每次注册/心跳/下发/执行/升级都写入 | **主数据库**。7 张表：agents 已接入的服务器、enrollments 注册申请、tasks 任务与结果、releases 升级包记录、audit 审计流水、nonces 防重放、meta 管理令牌 | ❌ 不能删（服务器要重注册、任务与审计全没） |
| `brain.db-wal` | 数据库开着时自动出现 | SQLite 的预写日志（新数据先落这里再合并），断电不易坏 | ⚠️ 别单独删（会丢最近写入）。要处理请先停服务 |
| `brain.db-shm` | 数据库开着时自动出现 | WAL 用的共享内存索引，纯运行态 | ✅ 停服后可删，会自动重建 |
| `brain.log` | 服务启动 + 运行中出错时追加 | 运行日志：启停、接口异常、未预期错误（含堆栈）。**排查问题先看它** | ✅ 可删（会重建），排查前建议留着 |
| `brain.pid` | `brain serve` 启动写、正常退出删 | 服务进程号，`brain stop` 靠它精确停**这一个**服务 | ✅ 可删（删了 stop 找不到 pid，但会兜底按端口把旧 brain 停掉） |
| `serve.out` | 后台启动时的输出重定向（程序自动 `nohup` 时也会写） | 服务"前台输出"存档：启动横幅、端口被占用等。**起不来先看它** | ✅ 可删 |
| `signing.key` | `brain init` 生成（RSA 2048，600） | **签名私钥**，给子 agent 升级包签名。是"发布权"的根 | ❌ **绝对不能删、不能外传**（删了要重新 init + 重发公钥给所有子 agent） |
| `signing.pub` | `init` 由私钥导出 | **公钥**，拷到每台子 agent（`brain.pub`）用于验签 | ✅ 可删（`brain pubkey` 能再导出） |
| `releases/` | `init` 建目录；每次 `brain release` 写一个包 | 已签名的**升级包**（`ai-agent-<os>-<版本>`）+ 库里的版本记录。子 agent 来取的就是它 | ✅ 可删旧版本（只影响"回滚到那一版"）；别删最新的 |
| `uploads/` | 子 agent 第一次上传文件时自动建 | 子 agent 传上来的**文件**（截图 / 日志 / 报告…），按 `<agent_id>/<时间>-<随机码>-<文件名>` 存放；在线链接 `/f/<id>` 就指向这里 | ✅ 可删（用 `brain uploads --rm <id>` / `--clean` 删更干净，会连库记录一起清） |
| `prompts/` | **你自己建**（可选，程序不会自动建） | 你的自定义提示词（`system.md`/`actions.md`/`skills/*.md`），**同名即覆盖程序自带**，升级不会冲掉 | ✅ 可删（退回用程序自带的） |

#### 大脑程序目录（部署时上传的，如 `/root/agent/`）

| 文件 | 干什么用 | 能删吗 |
| --- | --- | --- |
| `brain` | 入口脚本：解析命令并分发到 `brainlib/` | 删了用不了；重传即可，数据不丢 |
| `brainlib/` | 全部实现（配置/数据库/签名/模型/渲染/提示词/接口/管理/对话…） | 删了起不来；重传即可 |
| `prompts/` | 随程序发布的**默认**提示词与技能 | 删了没法对话（服务端仍能跑） |
| `ai-agent` | Linux 子 agent 脚本（**开发版/兜底用**；正式部署用加密生产版） | 不影响已装机的子 agent；重传即可 |
| `win/ai-agent.ps1` | Windows 子 agent 脚本（**开发版/兜底用**） | 同上 |
| `win/pack-agent.ps1` | Windows 生产版打包工具 | 不影响运行 |
| `brainlib/__pycache__/` | Python 自动生成的字节码缓存 | ✅ 可删，会自动重建 |
| `*.bak-年月日-时分` | **你按升级步骤手做的备份** | ✅ 确认新版稳定后可删；想回滚就留 |

---

## ⚙️ 5. 大脑配置项（`~/.ai-brain/brain.conf`）

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `BRAIN_BIND` | `127.0.0.1` | **只监听本机**；对外一律走 nginx + 域名 + HTTPS。**不要**改 `0.0.0.0`（那是明文对外） |
| `BRAIN_PORT` | `8787` | 监听端口（只给本机 nginx 反代用） |
| `PUBLIC_URL` | 空 | **必填**：大脑对外地址，**必须** `https://域名`（如 `https://brain.example.com`，或 `https://example.com/ai-brain`）。本机 CLI 与子 agent 都只认它；`http://` 或 IP 一律拒绝 |
| `RDV_SEED` | 自动生成 | 会合主密钥；子 agent 失联后靠它算出未来的后台域名。**别外传**（见第 20 节） |
| `RDV_PATTERN` | `xybrain-{h}.icu` | 会合域名模板，`{h}` 会被替换成"每期不同"的哈希 |
| `RDV_INDEX` | `1` | 当前期号；换后台域名时 +1（用 `brain rendezvous set <n>`） |
| `BRAIN_ADMIN_TOKEN` | 自动生成 | 本机 CLI 用，**别动** |
| `ENROLL_SECRET` | 自动生成 | 注册口令，**别动**（部署子 agent 时用；也是换"生产版解密口令"的凭证） |
| `PACK_KEY` | 自动生成 | 【生产版】解密口令，**只留在大脑**；生产版启动时凭注册口令来换（`POST /agent/key`）。轮换用 `brain pack-key rotate`（新旧口令并行过渡，**不会让已装机的失联**），全部子 agent 升级完再 `brain pack-key drop-old` |
| `PACK_KEY_OLD` | 空 | 轮换过渡期的**旧**口令（`brain pack-key rotate` 写入）；打包脚本会"先按新口令、不匹配退旧口令"。全部升级完后用 `brain pack-key drop-old` 清掉 |
| `PUSH_*` | 见第 14 节《邮件报警》 | 通知（邮件报警）配置：`PUSH_APP_ID` / `PUSH_APP_SECRET` / `PUSH_TO` 等 |
| `AI_API_KEY` | — | **必填**：大脑自己用的模型 Key |
| `AI_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `AI_MODEL` | `deepseek-v4-flash` | 模型名 |
| `AI_MAX_STEPS` | `20` | 【手动审核挡】一次提问最多来回几步（超了会停下提示，输入「继续」可接着做） |
| `AI_MAX_STEPS_AUTO` | `200` | 【完全放行挡】的兜底上限，等同"一直做下去"，只为防死循环 |
| `AI_CMD_TIMEOUT` | `120` | `run_local` 单条命令最长秒数 |
| `AI_API_TIMEOUT` | `180` | 单次模型请求最长秒数 |
| `POLL_TIMEOUT` | `25` | 子 agent 领任务的长轮询秒数 |
| `TASK_TIMEOUT` | `180` | **多久没有新进展**算"卡住"（秒）：只要子 agent 每步都在回报就一直等；连续这么久**毫无动静**才先不等 |
| `TASK_MAX_WAIT` | `7200` | 单条任务最多等多久（硬上限，秒）：到点先不等，但任务**没取消**、做完仍会回报 |
| `MAX_UPLOAD_MB` | `50` | 子 agent `upload` **单个文件**的大小上限（MB）。改完要**重启 `serve`** 才生效 |
| `BRAIN_URLS` | 空 | 下发给子 agent 的"大脑地址清单"（换地址用） |
| `PUSH_BASE` | `https://www.xiaoyingapi.com` | 通知（邮件）走你的「消息推送」服务 |
| `PUSH_APP_ID` | 空 | 推送服务接入项目的 **APPID** |
| `PUSH_APP_SECRET` | 空 | 推送服务的 **APPSECRET**（签名密钥，**务必保密**） |
| `PUSH_TO` | 空 | 报警收件人邮箱，多个用逗号分隔 |
| `PUSH_MIN_INTERVAL` | `600` | 同类事件的最小发送间隔（秒），**防刷邮件** |
| `OFFLINE_ALERT_SEC` | `300` | 子 agent 心跳中断超过这个秒数 → 发邮件报警 |
| `STREAM` | `1` | **1=流式输出；0=等生成完整段再显示** |
| `SHOW_REASONING` | `1` | 1=显示思维链 💭；0=只留「思考/动作/结果」 |
| `STDIO_ENCODING` | `utf-8` | 终端编码。默认 UTF-8；若你的终端/面板是 **GBK**（输中文报"无法识别的字节"），改成 `gbk` |
| `MODE` | `manual` | **挡位**：`manual`=每个动作都问你确认；`auto`=完全放行（不问、不停，直到做完或失败）。交互里输 `/auto` 切换并自动写入 |

改完不用重启也能生效（每次对话现读）；服务端相关的项（端口等）需要重启 `serve`。

---

# 🐧 第二部分 · 子 agent（Linux）

> 每台被管的 **Linux 服务器**做一遍。命令都是 `./ai-agent <子命令>`。
> 如果你要装的是 **Windows** 机器，直接跳到 **第三部分（第 8–9 节）**。

## 📦 6. Linux 子 agent：部署

> **先确认两样东西在手**（第 3 节部署大脑时得到的）：
> - **注册口令** —— 第 3.3 步 `brain init` 打印的那串，下面要输入它
> - 一个能 SSH 登录**这台新服务器**的账号（用 root 最省事）

### 6.0 第 0 步｜先把「加密生产版」备好（跑加密版必做）—— 【你的电脑 / 本地机 + 大脑那台】

服务器上**应该跑加密版**（明文那份留在你仓库里）。在 `x:\XiaoYingAPI\scripts\agent\` 下：

```bash
# ① 打包出加密生产版（AES-256；产物 tools/dist/ai-agent）
bash tools/pack-agent.sh ai-agent
```

```powershell
# ② 把加密版放到「大脑」的程序目录（作为兜底 —— 公开端点优先发"已发布的升级包"）
scp -P {SSH端口} .\tools\dist\ai-agent root@{大脑IP}:/root/agent/ai-agent
```

这样**新服务器拿到的就是加密版**（方式一从大脑下载、方式二从你本机传），而且以后 `brain release` 也用它 → **升完级依然是加密的**。

> 安全兜底：公开端点 `/agent/install` **只发密文** —— 优先发"最新发布的升级包"；若程序目录里那份是**明文**（含 `SYS_TASK`），一律**拒发(403)**。所以就算忘了放加密版，也不会把源码/提示词公开到网上。

> 不想加密（只自己用、图省事）→ **跳过本步**，把后面的 `.\tools\dist\ai-agent` 换成 `.\ai-agent` 即可（但注意：`/agent/install` 仍会拒发明文，走"一行命令"前请先 `brain release` 一版）。

---

### 6.1 方式一｜**一条命令搞定**（推荐，最省事）—— 【在新服务器执行】

SSH 登录到新服务器后，**只敲这一行**：

```bash
curl -fsSL https://{大脑域名}/ai-brain/agent/install -o /usr/local/bin/ai-agent && chmod +x /usr/local/bin/ai-agent && ai-agent setup
```

它会自己**跑完一条龙**：

1. 从大脑下载子 agent 程序（就是上面这行的 `curl`）；
2. 依次问你要填的东西，**照着填、回车确认**：
   - **大脑地址**：`https://{大脑域名}/ai-brain`（只认 https + 域名，填错会让你重填）
   - **本机模型 Key**：每台服务器各自一把
   - **注册口令**：`brain init` 时打印的那串
3. 自动「写配置 → 注册 → **装好开机自启**」（systemd，没有则退回 cron）；
4. 注册后会停在"等待大脑侧人工批准" —— 切到**大脑那台**执行：

   ```bash
   python3 brain pending               # 看新机器在不在待批准列表
   python3 brain approve <那一串 id>    # 批准
   ```

   子 agent 那边随即打印"注册成功"，并给出本机状态（看到 `大脑连通 : https://…` 就成了）。

> **公钥不用手动拷**：`setup` 会自动从大脑取回 `brain.pub`；仅当自动取回失败时，再按"方式二"手动补。

---

### 6.2 方式二｜手动一步步来（想自己掌控每一步时用）

**下面命令要在 3 个地方执行，每步都标了标签，别搞混：**

| 在哪执行 | 干什么 |
| --- | --- |
| **你的电脑 / 本地机** | 把程序 + 公钥传到新服务器 |
| **新服务器（要装子 agent 的那台，SSH 登录后）** | 写配置、注册、启动 |
| **大脑那台（SSH 登录后）** | 批准这台机器接入 |

---

#### 第 1 步｜把文件传上去 —— 【在你的电脑 / 本地机执行】

每个子 agent 只需要 **两个文件**：`ai-agent`（程序）、`brain.pub`（大脑公钥）。
在 `x:\XiaoYingAPI\scripts\agent\` 目录下，**一行一条**：

```powershell
# 1-1 先在新服务器建好目录（scp 不会自动建目录，缺了会报错）
ssh -p {SSH端口} root@{新服务器IP} "mkdir -p /root/agent"

# 1-2 传子 agent 程序（**加密生产版**；不加密就用 .\ai-agent）
scp -P {SSH端口} .\tools\dist\ai-agent root@{新服务器IP}:/root/agent/ai-agent

# 1-3 从大脑把公钥拉到本机（临时存成本地的 brain.pub）
scp -P {SSH端口} root@{大脑IP}:/root/.ai-brain/signing.pub .\brain.pub

# 1-4 再把公钥传到新服务器（子 agent 靠它校验升级包，很关键，别漏）
scp -P {SSH端口} .\brain.pub root@{新服务器IP}:/root/agent/brain.pub
```

> 💡 `{SSH端口}` 填各自的 SSH 端口（默认 22）；大脑和新服务器端口可能不同，按实际填。
> 不想用命令，也可以用宝塔面板把这几个文件传上去，效果一样。

#### 第 2 步｜写配置 —— 【在新服务器执行】

SSH 登录到**这台新服务器**，逐段粘贴：

```bash
# 2-1 进目录、转成 Linux 换行、加执行权限
cd /root/agent
sed -i 's/\r$//' ai-agent
chmod +x ai-agent

# 2-2 建数据目录、写配置文件
mkdir -p ~/.ai-agent
cat > ~/.ai-agent/agent.conf <<'EOF'
BRAIN_URL=https://{大脑域名}/ai-brain
AI_API_KEY=sk-这台服务器自己用的Key
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
EOF
chmod 600 ~/.ai-agent/agent.conf

# 2-3 放好公钥
cp -f /root/agent/brain.pub ~/.ai-agent/brain.pub
```

**只有两行要改成你自己的：**

- `BRAIN_URL` —— 大脑地址，**必须 https + 域名**：填 `https://{大脑域名}/ai-brain`（若 nginx 没带 `/ai-brain` 路径，就去掉该后缀）。写成 `http://` 或 IP 会被**拒绝**
- `AI_API_KEY` —— 这台服务器自己直连大模型用的 Key

> ⚠️ **地址只认 https + 域名**：写成 `http://` 或 IP，子 agent 会**拒绝连接**（`run` 常驻等待重试、`enroll` 提示退出）。
> 大脑不直接对外开端口，务必先按第 17 节把 nginx + 域名 + 证书配好。
>
> `AGENT_ID` 不写也行，默认用 `hostname`；同一台机器要跑多个 agent 才需要显式指定。

#### 第 3 步｜注册，然后去大脑批准 —— 【新服务器 + 大脑那台】

**【在新服务器】** 发起注册（会提示输入注册口令）：

```bash
cd /root/agent
./ai-agent enroll
# 屏幕提示：请输入注册口令  ← 粘贴第 3.3 步抄下的那串，回车
```

看到这行 = 已提交、在等大脑点头：

```
口令校验已通过，等待大脑侧人工批准…
```

**【在大脑那台】** 批准它（两种方式任选其一）：

```bash
# 方式一：直接进对话，屏幕会问“允许它接入吗？[y/N]”，输 y
cd /root/agent && python3 brain

# 方式二：先看谁在等，再按 id 批准
python3 brain pending            # 列出待批准的 id
python3 brain approve <那个id>
```

批准后，**新服务器**那台会打印：`注册成功！agent_id=xxx，令牌已写入 …（600）`，并**自动设好开机自启**。

> 卡在这一步：先在新服务器执行 `./ai-agent status`，看能不能连上大脑（多半是 `BRAIN_URL` 写法 / 域名解析 / 证书的问题）。

#### 第 4 步｜确认上线（开机自启**已自动装好**）—— 【大脑那台】

> 第 3 步注册成功时，子 agent **已经自动**把自己设成了开机自启：**root** 走 systemd（没有就退回 cron `@reboot`）；**非 root 也照样能装** —— 它会写进**你这个账号自己的 crontab**（`@reboot` 开机起一次 + 每分钟 `watchdog` 保活），**完全不需要 sudo**。
> 非 root 时**多副本与自愈同样有效**（副本在你自己的 `~/.local/.a-…/` 下）；想改用 systemd（最稳）：`sudo ./ai-agent install`。
> 自检：`crontab -l` 应能看到两行（`@reboot … watchdog` 和 `* * * * * … watchdog`）。

**【在大脑那台】** 确认它上线：

```bash
python3 brain status
```

**看到那台机器显示「在线」（系统列是 `Linux`），并带负载 / 磁盘 / 版本，就成了。**

> **一台机器照做一遍**：走完一台；换下一台时，把 `{新服务器IP}` 换掉、重复即可。
> 建议先跑通一台、确认没问题，再批量部署。

---

## 🔧 7. Linux 子 agent：升级 / 运维 / 卸载 / 数据文件

### 7.1 升级「Linux 子 agent」

**方式 A：让它们自己升级（推荐，机器多时用）**

改了代码要**先重新打包加密版**，发布的就是"要装到服务器上的那份"：

```bash
# ① 在你电脑 / 本地机（scripts/agent/ 下）：改完代码 → 重新打包
#    bash tools/pack-agent.sh ai-agent          → 生成 tools/dist/ai-agent
# ② 把加密版传上大脑（覆盖大脑程序目录里的那份）
#    scp -P {SSH端口} .\tools\dist\ai-agent root@{大脑IP}:/root/agent/ai-agent
# ③ 在大脑上发布（自动 sha256 + RSA 签名）
python3 brain release /root/agent/ai-agent --os linux --version 2.8.11 --notes "改了 xxx"   # ← 版本号必须等于 ai-agent 里的 VERSION
```

> 没做加密的话（跳过了 6.0）→ 直接用明文 `ai-agent` 发布也行；但要清楚：那样升下去的**也是明文**。

- 子 agent **最多 10 分钟**内自动升级；也可在任意一台 `./ai-agent update` 立刻升。
- 升级由**新版本自己完成**：下载 → sha256 校验 → **RSA 签名校验** → 语法自检 → 试运行 →
  **原子替换原文件** → 删除旧版本目录；任何一步不过就放弃、保留旧版。
- 版本号只要和当前**不同**就会触发升级（想"降级"就发一个低版本号）。
- ⚠️ 前提：子 agent 上有正确的 `~/.ai-agent/brain.pub`（公钥不对会被拒绝，这是特性）。

**方式 B：手工替换（只有一两台时更直观）**

```bash
cp /root/agent/ai-agent /root/agent/ai-agent.bak-$(date +%Y%m%d)
# 上传新版（加密版：你电脑上的 tools/dist/ai-agent）覆盖 /root/agent/ai-agent，然后：
cd /root/agent && sed -i 's/\r$//' ai-agent && chmod +x ai-agent
bash -n ai-agent && echo '语法 OK'
# 重启（装了开机自启服务就用 systemctl，否则手动起）：
systemctl restart ai-agent 2>/dev/null || { pkill -9 -f 'ai-agent run'; nohup ./ai-agent run >>~/.ai-agent/run.out 2>&1 & }
./ai-agent status
```

> 令牌在 `~/.ai-agent/agent.conf` 里，**不用重新注册**。

**回滚**：`cp /root/agent/ai-agent.bak-xxxx /root/agent/ai-agent`，再重启（同方式 B）。

### 7.2 Linux 子 agent 的日常运维命令

```bash
# —— 在子 agent 那台 ——
./ai-agent setup           # 一条龙：问该填的 → 写配置 → 注册 → 装开机自启（新机器推荐）
./ai-agent install         # 手动补设开机自启（注册时已自动做，一般不用）
./ai-agent uninstall       # 取消开机自启（数据保留）
./ai-agent selfdestruct    # 清除本机关于自己的一切（程序/配置/令牌/缓存/日志/自启；慎用）
./ai-agent selfcheck       # 自查+自愈：副本 / 服务单元 / cron 兜底 齐不齐（缺了就补齐）
./ai-agent run             # 前台运行（systemd 会调它；也可手动调时用）
./ai-agent once            # 手动领一次任务（调试）
./ai-agent version         # 看版本：本机版本 + 大脑上可升级到的最新版
./ai-agent update          # 立刻检查升级
./ai-agent upload <文件>   # 把本机文件传给主人（截图/日志/报告…）→ 打印在线查看/下载链接
./ai-agent status          # 看配置/大脑连通性/版本
systemctl status ai-agent  # 看服务状态（装过 install 之后）
journalctl -u ai-agent -f  # 看服务日志
tail -f ~/.ai-agent/agent.log   # 干活的日志
```

**停止子 agent**：装了开机自启就用 `systemctl stop ai-agent`；否则 `pkill -f 'ai-agent run'`
（它可能正卡在 25 秒长轮询里，最多约 25 秒才退出；急停用 `pkill -9 -f 'ai-agent run'`）。

### 7.3 Linux 子 agent 数据目录 `~/.ai-agent/`

| 文件 | 何时产生 | 干什么用 | 能删吗 |
| --- | --- | --- | --- |
| `agent.conf` | 部署时手写基本项；`enroll` 成功后写入本机令牌与会合信息 | 大脑地址 `BRAIN_URL`、本机 `agent_id`、**本机专属令牌**、这台机器调模型用的 Key、**会合信息 `RDV_*`**（第 20 节）。**权限 600** | ❌ 不要删（要重新 enroll + 大脑侧批准） |
| `brain.pub` | 部署时从大脑拷来 | 大脑公钥副本，用于校验下载到的升级包 | ✅ 可删，但删了升级会**跳过签名校验**（不安全） |
| `brain_cache` | 第一次成功连上大脑时写入 | 上次连通的**大脑地址**（换地址能自愈） | ✅ 可删（会重新探测） |
| `agent.pid` | `ai-agent run` 启动写、正常退出删 | 子 agent 进程号 | ✅ 可删 |
| `agent.log` | 运行中持续追加 | **干活记录**：领到什么任务、每步在本机跑了什么命令、何时回报 | ✅ 可删，排查前建议留着 |
| `run.out` | 手动 / `cron` 方式启动时产生（用 systemd 时输出在 journal） | 子 agent 前台输出存档 | ✅ 可删 |
| `tmp/` | 运行时自动建（`tmp/<进程号>/`） | 临时文件（请求体、模型响应等）。**不放 `/tmp`**：`/tmp` 会被系统/面板清理，长跑进程会因此算错签名而失联 | ✅ 可删（会自动重建） |
| `versions/` | 自升级时临时创建 | 升级包下载到这，校验通过后由**新版本自己**替换原文件，然后整个目录被删 | ✅ 正常会自己消失；残留说明升级失败过，可删 |

> 另外：`./ai-agent install` 会在 `/etc/systemd/system/ai-agent.service` 写一个开机自启的服务定义
> （不在数据目录里；用 `./ai-agent uninstall` 卸载）。

> **一句话记住**：`~/.ai-brain` 和 `~/.ai-agent` 里放的是**身份和记忆**（密钥、令牌、数据库），
> 升级程序**只换程序目录**，这两个目录一个字都别动。

### 7.4 抗清理（多副本 + 互保：被删了能自己顶上）

部署时（`setup` / `enroll`）会自动做三件事，让它在"被清理"后还能活：

1. **多副本**：把自己复制成 N 份（默认 3），放在 `~/.local/.a-<8位哈希>/<1..N>/ai-agent`，**目录与文件权限都是 700**（非 root 看不到、也不显眼）；
2. **cron 兜底**：加一条 `* * * * * <副本1> run`，**每分钟试跑一次** —— 正在跑的那份没了，1 分钟内就顶上；因为 `run` 有"防重复实例"，所以永远只跑一份；
3. **自愈 + 上报**：运行中每 5 分钟自查一次，发现副本 / 服务 / 自启被删 → **补齐并重建**，同时**上报大脑** → 你会收到邮件「某台被清理过，已由副本接替」。

手动查一遍：**`./ai-agent selfcheck`**（逐条列出副本 / 服务单元 / cron 兜底在不在）。
改份数：在 `agent.conf` 里加 `AI_AGENT_COPIES=5`。

> ⚠️ 老实讲：这些只是**提高存活率**——对方若有 root 且持续清理，本机任何方案都可能被清光。
> 真正靠得住的兜底是**大脑的「失联报警」邮件**（它不在被清的那台机器上）。

### 7.5 卸载「Linux 子 agent」

```bash
# 1) 先停
./ai-agent uninstall                            # 取消开机自启
pkill -9 -f 'ai-agent run'                      # 兜底再杀一次

# 2) 再删
rm -rf ~/.ai-agent                              # 数据：配置、令牌、公钥、日志
rm -rf ~/.local/.a-*                            # 隐藏多副本
rm -f /root/agent/ai-agent                      # 程序文件（按你实际路径）
```

（若这台机器还要留着，只做第 1 步即可；想彻底清干净见 **第 15 节**。）

---

# 🪟 第三部分 · 子 agent（Windows）

> 每台被管的 **Windows 机器**做一遍。命令都是 `.\ai-agent.ps1 <子命令>`（**子命令名与 Linux 版完全一样**）。
> **无需装任何东西**：纯 PowerShell 5.1，Windows 自带。
> 如果你要装的是 **Linux** 服务器，请看 **第二部分（第 6–7 节）**。

## 📦 8. Windows 子 agent：部署

> **先确认一样东西在手**：**注册口令**（第 3.3 步 `brain init` 打印的那串）。
> 然后**用管理员身份**打开 PowerShell（右键"以管理员身份运行"）—— 管理员装法最稳（SYSTEM 级计划任务）；
> 非管理员也能装（自动降级为注册表 Run + 常驻监工），见下面注。

### 8.0 第 0 步｜先把「加密生产版」备好（跑加密版必做）—— 【你的电脑 / 本地机 + 大脑那台】

在你的电脑 / 本地机（Windows），于 `x:\XiaoYingAPI\scripts\agent\` 下：

```powershell
# ① 打包出加密生产版（产物 win\dist\ai-agent.ps1）
#    打包机是你的 Windows、大脑在远端 → 本机没有 brain.conf，必须显式给 -Key：
$pk = (ssh -p {SSH端口} root@{大脑IP} "grep '^PACK_KEY=' /root/.ai-brain/brain.conf | cut -d= -f2-").Trim()
powershell -File .\win\pack-agent.ps1 -Online -Brain https://{大脑域名}/ai-brain -Key $pk -Out .\win\dist\ai-agent.ps1

# ② 把加密版放到「大脑」的程序目录（可选；作为 404 兜底，公开端点优先发"已发布的升级包"）
scp -P {SSH端口} .\win\dist\ai-agent.ps1 root@{大脑IP}:/root/agent/win/dist/ai-agent.ps1
```

> ⚠️ **Windows 的生产版必须先 `brain release --os win` 发布过一次**，否则公开端点 `/agent/install?os=win`
> 会**明确拒绝**（找不到可分发的 Windows 生产版）—— 这是故意的：绝不让"明文开发版"被公开下载。
> 也就是说 **Windows 走"方式一（一行命令）"之前，必须先发布一版**（见 8.1 开头的第 0 步）。
>
> ⚠️ **Windows 包只能在 Windows 上打**（大脑那台是 Linux，没有 PowerShell；要硬在大脑上打就得装 `pwsh`，不划算）。
> 打包机的"本机没有 `brain.conf`" → `-Online` 必须显式 `-Key`（做法见上面第 ① 步和 **§0 的 ⚠️**）。

---

### 8.1 方式一｜**一条命令搞定**（推荐）—— 【在 Windows 目标机执行】

**用管理员 PowerShell**，先在大脑上发布一版 Windows 生产版（若还没发过）：

```bash
# 【在大脑那台】把上传的 win 生产版登记为"最新发布版"
python3 brain release /root/agent/win/dist/ai-agent.ps1 --os win --version 1.1.8 --notes "首发"   # ← 版本号必须等于 win/ai-agent.ps1 里的 $VERSION
```

然后在 **Windows 目标机**（**管理员** PowerShell）执行 —— **一行搞定**（两条命令用 `;` 串起来）：

```powershell
# 下载客户端 → 一条龙安装（配置 → 注册 → 装开机自启）
iwr -UseBasicParsing https://{大脑域名}/ai-brain/agent/install?os=win -OutFile $env:TEMP\ai-agent.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\ai-agent.ps1 setup --brain https://{大脑域名}/ai-brain
```

想**零提问**（该填的都一次给全，适合脚本化 / 远程）就用这条：

```powershell
iwr -UseBasicParsing https://{大脑域名}/ai-brain/agent/install?os=win -OutFile $env:TEMP\ai-agent.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\ai-agent.ps1 setup --brain https://{大脑域名}/ai-brain --ai-key sk-这台机器自己的Key --secret {注册口令}
```

> ⚠️ **为什么不能 `iwr … | iex`（下载完直接在内存里跑）**：子 agent 装好后要把**自己这个文件**复制到固定位置
> （`C:\ProgramData\.ai-agent\ai-agent.ps1`），它靠"自己的文件路径"（`$PSCommandPath`）来定位自己；
> 内存执行**没有文件路径** → 装不进固定位置 → **开机自启会失败**。所以必须先用 `-OutFile` 落地成文件。
> （`-UseBasicParsing` 是为老系统上 `iwr` 起不来准备的，5.1 上带上它最稳。）

`setup` 会自己**跑完一条龙**：

1. 写配置（`agent.conf`）到数据目录；
2. 注册（会要你输入**注册口令**；也可加 `--secret {口令}` 一次给全，零提问）；
3. **装好开机自启**；
4. 停在"等待大脑侧人工批准" —— 切到**大脑那台**执行：

   ```bash
   python3 brain pending               # 看新机器在不在待批准列表
   python3 brain approve <那一串 id>    # 批准
   ```

批准后，Windows 那台打印"注册成功"，并显示本机状态。

> **公钥不用手动拷**：`setup` / `enroll` 会自动从大脑取回 `brain.pub`。
> **程序会落到固定路径**：即使你是从 `%TEMP%` 直接跑的，安装后程序本体也会被复制到
> `C:\ProgramData\.ai-agent\ai-agent.ps1`（隐藏），计划任务 / 监工 / 隐藏副本全部指向它 —— 不怕系统清理 `%TEMP%`。

---

### 8.2 方式二｜手动一步步来（想自己掌控每一步时用）

**下面命令要在 3 个地方执行，别搞混：**

| 在哪执行 | 干什么 |
| --- | --- |
| **你的电脑 / 本地机** | 把程序 + 公钥送到 Windows 目标机 |
| **Windows 目标机（管理员 PowerShell）** | 写配置、注册 |
| **大脑那台（SSH 登录后）** | 批准这台机器接入 |

#### 第 1 步｜把文件传上去 —— 【在你的电脑 / 本地机执行】

Windows 目标机需要 **一个程序文件** +（可选）**公钥文件**。用 scp（目标机需装了 OpenSSH Server）或直接拷贝：

```powershell
# 1-1 把加密生产版传到目标机（非加密就用 .\win\ai-agent.ps1）
scp -P {SSH端口} .\win\dist\ai-agent.ps1 {用户名}@{WindowsIP}:C:/Users/{用户名}/ai-agent.ps1
# 1-2 从大脑把公钥拉到本机，再送到目标机（可选：enroll 会自动取，取不到才需手动）
scp -P {SSH端口} root@{大脑IP}:/root/.ai-brain/signing.pub .\brain.pub
scp -P {SSH端口} .\brain.pub {用户名}@{WindowsIP}:C:/Users/{用户名}/brain.pub
```

#### 第 2 步｜注册，然后去大脑批准 —— 【Windows 目标机 + 大脑那台】

**【在 Windows 目标机，管理员 PowerShell】**

```powershell
# 2-1 写配置（数据目录：管理员 ProgramData；非管理员用 $env:LOCALAPPDATA\.ai-agent）
$d = 'C:\ProgramData\.ai-agent'
New-Item -ItemType Directory -Force -Path $d | Out-Null
@"
BRAIN_URL=https://{大脑域名}/ai-brain
AI_API_KEY=sk-这台机器自己用的Key
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
"@ | Set-Content -Encoding UTF8 (Join-Path $d 'agent.conf')

# 2-2 放公钥（可选）
Copy-Item .\brain.pub (Join-Path $d 'brain.pub') -Force -ErrorAction SilentlyContinue

# 2-3 注册（提示输入注册口令），并自动装好开机自启
powershell -ExecutionPolicy Bypass -File .\ai-agent.ps1 enroll --secret {注册口令}
```

> 非管理员安装：把上面的 `C:\ProgramData\.ai-agent` 换成 `$env:LOCALAPPDATA\.ai-agent`；
> 自启会降级为 **注册表 Run 键 + 常驻监工**（见 9.2 / 9.4）。

**【在大脑那台】** 批准它：

```bash
python3 brain pending            # 列出待批准的 id
python3 brain approve <那个id>
```

#### 第 3 步｜确认上线 —— 【大脑那台】

```bash
python3 brain status
```

**看到那台机器显示「在线」（系统列是 `Windows`），带负载 / 磁盘 / 版本，就成了。**

---

## 🔧 9. Windows 子 agent：升级 / 运维 / 卸载 / 数据文件

### 9.1 升级「Windows 子 agent」

和 Linux 一个套路：**改了 `win/ai-agent.ps1` → 重新打包 → 传上大脑 → 给大脑发布 `--os win`**。

```powershell
# ① 在你电脑 / 本地机（scripts/agent/ 下）：改完代码 → 重新打包
#    （本机没有 brain.conf，先 ssh 取 PACK_KEY 再 -Key；详见第 8.0 节的 ⚠️）
$pk = (ssh -p {SSH端口} root@{大脑IP} "grep '^PACK_KEY=' /root/.ai-brain/brain.conf | cut -d= -f2-").Trim()
powershell -File .\win\pack-agent.ps1 -Online -Brain https://{大脑域名}/ai-brain -Key $pk -Out .\win\dist\ai-agent.ps1

# ② 把加密版传上大脑
scp -P {SSH端口} .\win\dist\ai-agent.ps1 root@{大脑IP}:/root/agent/win/dist/ai-agent.ps1
```

```bash
# ③ 在大脑上发布（自动 sha256 + RSA 签名）
python3 brain release /root/agent/win/dist/ai-agent.ps1 --os win --version 1.1.8 --notes "改了 xxx"   # ← 版本号必须等于 win/ai-agent.ps1 里的 $VERSION
```

- Windows 子 agent **最多 10 分钟**内自动升级；也可在那台执行 `.\ai-agent.ps1 update` 立刻升。
- 升级链路与 Linux 一致：下载（**带签名请求**）→ sha256 校验 → **RSA 签名校验** → **语法自检**
  （PowerShell 解析通过才换）→ **原子替换原文件** → 同步隐藏副本；任何一步不过就放弃、保留旧版。
- 版本号只要和当前**不同**就会触发升级。
- ⚠️ 前提：那台机器上有正确的 `brain.pub`（公钥不对会被拒绝，这是特性）。

**手工替换（一两台时更直观）**：

```powershell
# 备份 → 用新版覆盖固定路径的那个文件 → 重启计划任务
Copy-Item C:\ProgramData\.ai-agent\ai-agent.ps1 C:\ProgramData\.ai-agent\ai-agent.bak -Force
Copy-Item .\win\dist\ai-agent.ps1 C:\ProgramData\.ai-agent\ai-agent.ps1 -Force
Stop-ScheduledTask  -TaskName WinHealthCheck -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName WinHealthCheck -ErrorAction SilentlyContinue
```

> 令牌在数据目录的 `agent.conf` 里，**不用重新注册**。回滚把 `.bak` 覆盖回去、重启任务即可。

### 9.2 Windows 子 agent 的日常运维命令

**在 Windows 目标机（管理员 PowerShell，`-File` 指向固定路径的那个文件）**：

```powershell
$agent = 'C:\ProgramData\.ai-agent\ai-agent.ps1'      # 非管理员：$env:LOCALAPPDATA\.ai-agent\ai-agent.ps1

powershell -ExecutionPolicy Bypass -File $agent setup         # 一条龙：配置 → 注册 → 装自启
powershell -ExecutionPolicy Bypass -File $agent install       # 手动补设开机自启（一般不用）
powershell -ExecutionPolicy Bypass -File $agent uninstall     # 取消开机自启（数据保留）
powershell -ExecutionPolicy Bypass -File $agent selfcheck     # 自查+自愈：副本/自启 齐不齐
powershell -ExecutionPolicy Bypass -File $agent selfdestruct  # 清除本机关于自己的一切（慎用）
powershell -ExecutionPolicy Bypass -File $agent run           # 前台运行（计划任务会调它）
powershell -ExecutionPolicy Bypass -File $agent once          # 手动领一次任务（调试）
powershell -ExecutionPolicy Bypass -File $agent version       # 本机版本 + 大脑上可升级到的最新版
powershell -ExecutionPolicy Bypass -File $agent update        # 立刻检查升级
powershell -ExecutionPolicy Bypass -File $agent upload 'C:\路径\文件'   # 传给主人 → 打印在线链接
powershell -ExecutionPolicy Bypass -File $agent status        # 看配置/连通性/自启/运行状态
powershell -ExecutionPolicy Bypass -File $agent watchdog      # 兜底入口（计划任务每分钟调）

# 看状态 / 日志 / 自启任务
Get-ScheduledTask -TaskName WinHealthCheck,WinHealthCheck1 -ErrorAction SilentlyContinue
Get-Content C:\ProgramData\.ai-agent\agent.log -Tail 30
```

**停止 / 重启子 agent**：

```powershell
Stop-ScheduledTask  -TaskName WinHealthCheck                    # 停主进程
Start-ScheduledTask -TaskName WinHealthCheck                    # 再拉起
# 兜底：直接杀掉与本 agent 相关的 PowerShell 进程
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -like '*ai-agent*' } | Stop-Process -Force
```

> 计划任务名是**中性**的：`WinHealthCheck`（开机启动的主进程）+ `WinHealthCheck1`（每分钟 watchdog）。
> 非管理员装法没有计划任务，自启在 **注册表 `HKCU\...\Run`** 里，另有常驻"监工"进程。

### 9.3 Windows 子 agent 数据目录

**数据目录**：管理员 `C:\ProgramData\.ai-agent\`；非管理员 `%LOCALAPPDATA%\.ai-agent\`。

| 文件 | 何时产生 | 干什么用 | 能删吗 |
| --- | --- | --- | --- |
| `agent.conf` | 部署时由 `setup` 写入；`enroll` 成功后写入令牌与会合信息 | 大脑地址 `BRAIN_URL`、`agent_id`、**本机专属令牌 `AGENT_TOKEN`**、这台机器调模型用的 Key、会合信息 `RDV_*`、自启方式 `AUTOSTART`（`task`/`run`）、在线取密钥缓存 `PACK_SECRET` | ❌ 不要删（要重新 enroll + 大脑侧批准） |
| `ai-agent.ps1` | `install`/`setup` 时由 `Install-Self` 落地（隐藏） | **程序本体的固定位置**：计划任务 / 监工 / 隐藏副本都指向它 | ❌ 不要删（删了自启指向空） |
| `brain.pub` | `setup`/`enroll` 自动从大脑取回 | 大脑公钥副本，用于校验升级包 | ✅ 可删，但删了升级会**跳过签名校验**（不安全） |
| `brain_cache` | 第一次成功连上大脑时写入 | 上次连通的**大脑地址** | ✅ 可删（会重新探测） |
| `.installed` | 装好开机自启后写入 | 标记"这台已正式安装"（自愈只在装了之后才动手） | ⚠️ 别删（删了自愈不再补齐），要卸载请用 `uninstall` |
| `agent.pid` | `run` 启动写、正常退出删 | 主进程号（防重复实例 / watchdog 判活） | ✅ 可删 |
| `agent.log` | 运行中持续追加 | **干活记录**：领到什么任务、每步在本机跑了什么命令、何时回报 | ✅ 可删，排查前建议留着 |
| `tmp\` | 运行时自动建（`tmp\<进程号>\`） | 临时文件（请求体、命令脚本、模型响应等） | ✅ 可删（会自动重建） |
| `versions\` | 自升级时临时创建 | 升级包下载到这，校验通过后替换原文件 | ✅ 正常会自己消失；残留说明升级失败过，可删 |

**隐藏多副本**：管理员 `C:\ProgramData\.a-<8位哈希>\<1..3>\ai-agent.ps1`（目录与文件都标 Hidden）；
非管理员 `%LOCALAPPDATA%\.a-<8位哈希>\`。

**开机自启（看 `agent.conf` 里的 `AUTOSTART`）**：

| 装法 | 自启载体 | 每分钟兜底 |
| --- | --- | --- |
| 管理员（推荐） | 计划任务 `WinHealthCheck`（`AtStartup`，以 **SYSTEM** 运行） | 计划任务 `WinHealthCheck1` 每分钟跑 `watchdog` |
| 非管理员 | 注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 里的 `WinHealthCheck`（登录自启） | 常驻"监工"进程 `supervise`（每 60s 拉起） |

### 9.4 抗清理（多副本 + 互保：Windows 版）

与 Linux 思路一致，落到 Windows 上：

1. **多副本**：把自己复制成 3 份，放在隐藏目录 `.a-<8位哈希>\<1..3>\ai-agent.ps1`；
2. **每分钟兜底**：计划任务 `WinHealthCheck1`（或常驻监工）每分钟调 `watchdog` —— 主进程没了就 1 分钟内顶上（`run` 有"防重复实例"，永远只跑一份）；
3. **自愈 + 上报**：运行中每 **5 分钟**（300s）自查一次，发现副本 / 自启被删 → **补齐并重建**，同时**上报大脑** → 你会收到邮件「某台被清理过，已由副本接替」。

手动查一遍：**`.\ai-agent.ps1 selfcheck`**。

> ⚠️ 同样地：这些只是**提高存活率**；对方有管理员权限且持续清理，本机任何方案都可能被清光。
> 真正靠得住的兜底是**大脑的「失联报警」邮件**。

### 9.5 卸载「Windows 子 agent」

```powershell
# 1) 先停 + 取消自启（会同时删掉计划任务 / Run 键）
powershell -ExecutionPolicy Bypass -File C:\ProgramData\.ai-agent\ai-agent.ps1 uninstall

# 2) 再删（管理员）
Remove-Item -Recurse -Force C:\ProgramData\.ai-agent
Remove-Item -Recurse -Force C:\ProgramData\.a-*

# 非管理员装法：
# Remove-Item -Recurse -Force $env:LOCALAPPDATA\.ai-agent
# Remove-Item -Recurse -Force $env:LOCALAPPDATA\.a-*   （Remove-ItemProperty -Path 'HKCU:\...\Run' -Name WinHealthCheck）
```

> 懒得手删？大脑 `brain block <id>`（第 13 节）会让它**自己把自己清干净**（含用户级残留），
> 或在那台执行 `.\ai-agent.ps1 selfdestruct`。

---

# 📚 附录 · 与平台无关（Linux / Windows 都适用）

## 💬 10. 怎么用（跟大脑说话）

> 这一节跟子 agent 是 Linux 还是 Windows **无关** —— 你只管跟大脑说人话，它自己去指挥各台机器。

```bash
python3 brain                      # 进入对话
你 ❯ 让所有服务器看一下磁盘和内存，把紧张的告诉我
```

**大脑是流式回复的，并把「思考」和「结果」分开显示**（Linux 那台用 shell、Windows 那台用 PowerShell，你都不用管）：

````text
你 ❯ 让所有服务器看一下磁盘和内存，把紧张的告诉我
💭 思考中：用户要看所有服务器的磁盘和内存，需要 dispatch 到全部 agent…   ← 暗色：模型思维链
· 思考 我先让三台服务器各自查一下磁盘和内存。                          ← 暗色：动作前的说明
```json
{"action":"dispatch","agents":"all","task":"检查磁盘和内存用量，指出紧张的"}
```
▶ 将在 3 台执行：server-1, server-2, win-pc-3                          ← 黄色：程序动作
▶ 任务：检查磁盘和内存用量，指出紧张的
  （回车＝跳过；也可直接打字说你的修改）
  [y=执行 / n=跳过 / a=以后都别问] y
▶ 已下发 3 条任务，等待各服务器回报…
▶ 【server-1】已领取任务，执行中…（还有 2 台未领取）                    ← 实时进度：谁领走了、还剩几台
▶ 【win-pc-3】已领取任务，执行中…（还有 1 台未领取）
▶ 【server-2】已领取任务，执行中…（还有 0 台未领取）
▶ 【server-1】第 1 步：查看根分区剩余空间                               ← 子 agent 每跑一步就回报一次
▶ 【win-pc-3】第 1 步：Get-PSDrive 查看各盘剩余空间
▶ 【server-1】已回报（成功）
  …（迟迟没动静时会每 15 秒报一次：未领取 N / 执行中 N / 已回报 N）
💭 思考中：三台都回来了…                                               ← 暗色：模型思维链
── 结果 ──────────────────────────                                    ← 高亮：最终结论
三台机器全部成功，磁盘都很健康：
| 机器 | C盘/根分区 | 数据盘 | 是否有超 80% | 结论 |
| server-1 | 99G/70G/26% | 98G/93G/1% | 无 | 空间充裕 |
...
──────────────────────────────────
````

| 样式 | 含义 | 怎么关 |
| --- | --- | --- |
| `💭 思考中：`（暗色） | 模型**思维链**（reasoner 类模型才有） | `SHOW_REASONING=0` |
| `· 思考 `（暗色） | 模型说「我打算做什么」——**思考模式** | 关不掉（这是模型的正式内容） |
| `▶ `（黄色） | 程序在执行：下发 / 本机执行 / 等待回报 / **子 agent 逐步进度**——**动作模式** | — |
| `── 结果 ──`（高亮框） | 最终答复——**结果模式** | — |

**它是执行者，不是顾问。** 你说什么它就直接去做、做完汇报；**不会**反问你"要不要我帮你做"、
**不会**给你讲道理、**不会**替你做决定。

### 📎 让子 agent 把文件发给你（截图 / 日志 / 报告）

任何一台子 agent 都能把**本机文件**传给你，你在浏览器点开就能看 / 下载（Linux、Windows 一样）：

1. 你在任务里说清"把哪个文件给我看"，它自己就会用 `./ai-agent upload <文件>`
   （Windows：`.\ai-agent.ps1 upload <文件>`）传上来 —— **不用你教它路径、也不用你指定任务号**；
2. 命令会打印一个链接（`https://域名/f/<一串随机码>`）—— **点开即看**，想存档就另存为；
3. 汇总时大脑还会把该任务上传的文件**连链接一起附在结论里**（`【本任务上传的文件】…`）。

- 单文件默认 **≤ 50MB**（`brain.conf` 的 `MAX_UPLOAD_MB` 可调，改完重启 `serve`）；文件存在大脑的 `~/.ai-brain/uploads/`。
- 在**大脑那台**也能用命令行取回：`brain uploads`（列表，带链接）、`brain get <id>`（下到当前目录）；
  清理：`brain uploads --rm <id>`（删一个）/ `brain uploads --clean`（全清）。
- 🔒 链接里的 ID 是**不可猜的随机串**；图片 / 纯文本可在线看，**html、svg 等一律当附件下载**（不当网页渲染），并带 `noindex`。

### 确认时想改一下？——现场改任务 / 逐条拍板

在下发前那一步，**不是只能按 `y/n/a`**：

- **直接打字就是修改意见**。比如它准备"先备份再删"，你可以直接回 `不要备份，直接删`——
  它会**改写任务、重新给你确认一次**，绝不会闷头照原方案执行。
- 如果这件事里**确实有需要你拍板的点**，它会在确认前列出**最多 4 条**（每条附上它自己的倾向），你可以**逐条**给意见：

  ```
  ▶ 将在 2 台执行：server-1, server-2
  ▶ 任务：把与 IP 1.2.3.4 有关的日志清理掉（按它倾向的稳妥做法）

  它想请你拍板（2 条）：
    1) 要不要先把要改的日志备份一份？   它倾向：先备份
    2) 要不要连 journald 一起清？       它倾向：一起清

    逐条给意见（直接回车＝照它倾向办）：
    1 ❯ 不要备份，直接删
    2 ❯

  ▶ 已按你的意见改写，重新给你看：
  ▶ 任务：把与 IP 1.2.3.4 有关的日志直接删除（不做备份）……
  确认下发？ [y=执行 / n=跳过 / a=以后都别问] y
  ```

  - **全回车**＝照它的倾向办，直接进最后的 `y/n/a`；
  - **哪条写了**＝它把这些意见**回喂给模型改写任务**，再展示一次让你确认——不会"你没看清就执行"。
- 切到 `auto`（完全放行）后：待拍板项**照样打印出来**，只是不拦你、直接执行。

> 这条能力只用在「要动手前」的确认（下发 / 本机执行）；它平时仍然是**执行者**，不会到处反问你。

### 两个挡位（`MODE`）

| 挡位 | 行为 |
| --- | --- |
| **`manual` 手动审核**（默认） | 每个动作（下发任务 / 本机执行）执行前问你**一次**；也受步数上限 `AI_MAX_STEPS` 约束 |
| **`auto` 完全放行** | **不问、不停**：不点确认、不看步数上限，一直做到任务完成或彻底失败 |

切挡位三种办法（任选其一）：

- 交互里输 **`/auto`** —— 来回切换，写进 `brain.conf`，重启也生效
- 在确认提示里按 **`a`** —— 表示"以后都别问"
- 直接编辑 `brain.conf` —— 把 `MODE=` 改成 `manual` 或 `auto`

只想放行一次（不改挡位）：命令行加 `-y`，例如 `brain -y "把 /tmp 里 7 天没动的文件删掉"`。

### 关于"已达到步数上限"

一次提问里，它"想一步 → 做一步"算一步。手动挡默认给 **20 步**，超了就停下并提示
（**这不是失败**，任务可能只做了一半）。这时候：

- 直接输入 **「继续」**，它接着往下做（上下文都还在）
- 想让它一口气做完：把 `brain.conf` 里 `AI_MAX_STEPS` 调大，或直接切到 `MODE=auto`
  （完全放行挡不看这个上限，用的是 `AI_MAX_STEPS_AUTO`，默认 200，只用来防死循环）

**流畅度**：默认 `STREAM=1`（边生成边显示，首字很快）。若你的模型/中转站不支持流式，
或你就想一次看完整段，把 `brain.conf` 改成 `STREAM=0`。

交互内命令：`/help` `/agents` `/status` `/pending` `/auto` `/exit`

命令行：`brain "一句话"`（终端里问完**继续留在对话**，只有被管道/脚本调用才问完即退）、`brain -y "一句话"`（自动确认）、`brain -h`

---

## ✍️ 11. 改提示词 / 加技能（不用碰代码）

> 提示词是**大脑**的，跟子 agent 平台无关。

提示词就是普通文本文件，**改完下次对话就生效，不用重启**。

### 11.1 目录与覆盖规则

```
/root/agent/prompts/            ← 程序自带（升级时会更新）
~/.ai-brain/prompts/            ← 你自己的（优先级更高，升级不会动）
```

同名文件**后者优先**。想改哪里，就把对应文件复制到 `~/.ai-brain/prompts/` 再改：

```bash
mkdir -p ~/.ai-brain/prompts/skills
cp /root/agent/prompts/system.md ~/.ai-brain/prompts/system.md
vi ~/.ai-brain/prompts/system.md
```

### 11.2 三个文件各管什么

| 文件 | 作用 |
| --- | --- |
| `system.md` | 系统提示词主体。里面有 `{{ACTIONS}}`（动作清单）、`{{SKILLS}}`（技能）、`{{ENV}}`（当前环境）三个占位符，程序会自动替换 |
| `actions.md` | 可用动作清单（会被塞进 `{{ACTIONS}}` 处）——**加新动作时才需要改这里** |
| `skills/*.md` | 额外技能/背景知识，按文件名排序追加到系统提示词最后 |

### 11.3 加一个"技能"（最常用）

丢一个 `.md` 进 `skills/` 就行，例如：

```bash
cat > ~/.ai-brain/prompts/skills/company.md <<'EOF'
## 我们公司的服务器

- server-1：主站（nginx + uwsgi），**不能随便重启**
- server-2：数据库，改动前一定先备份
- win-pc-3：办公室这台 Windows，随便折腾
EOF
```

下次对话，大脑就"知道"这些背景了（`skills/README.md` 本身不会被加载）。

---

## 📁 12. 能不能放到其它目录？

### 结论：**都能。没有任何路径写死在程序里。**

| | 默认位置 | 怎么改 |
| --- | --- | --- |
| **程序目录**（`brain`+`brainlib`+`prompts`） | 你放哪就是哪，如 `/root/agent` | 直接 `mv` 到别处，用新路径启动即可 |
| **大脑数据目录** | `~/.ai-brain/` | 环境变量 `BRAIN_HOME=/data/aibrain` |
| **子 agent 数据目录（Linux）** | `~/.ai-agent/` | 环境变量 `AI_AGENT_HOME=/data/aiagent` |
| **子 agent 数据目录（Windows）** | `C:\ProgramData\.ai-agent\`（管理员） | 环境变量 `AI_AGENT_HOME=D:\ai-agent`（或改非管理员默认的 `%LOCALAPPDATA%`） |

举例（Linux 大脑）：

```bash
export BRAIN_HOME=/data/aibrain           # 建议写进 /etc/profile 或 ~/.bashrc
python3 /opt/agent/brain init
python3 /opt/agent/brain serve
```

### 换路径必须遵守的 5 条规矩

1. **启动时的环境变量要一致**。`BRAIN_HOME`/`AI_AGENT_HOME` 变了就等于换了套配置
   （找不到会要求重新 `init`/`enroll`）。
2. **别放临时目录**（Linux `/tmp`、Windows `%TEMP%`，重启就清空）。推荐 `/root/...`、`/data/...`、`/opt/...`；Windows 用 `C:\ProgramData\...` 或 `D:\...`。
3. **`brain` 和 `brainlib/`、`prompts/` 必须待在同一个目录里**（入口靠同级路径找它们），
   要移动就整目录一起移。
4. **子 agent 部署后别随便移动它那个文件**。自升级会**原地替换它自己**：
   移动后重启一次即可；用软链/快捷方式时替换的是**它指向的真实文件**。
5. **换用户 = 换默认目录**。Linux 默认 `~/.ai-brain`、`~/.ai-agent`（`~`＝当前用户家目录）；
   Windows 默认与"是否管理员"有关（管理员 `C:\ProgramData`，否则 `%LOCALAPPDATA%`）。
   建议统一用同一个身份跑（Linux 用 root；Windows 用管理员）。

---

## ⛔ 13. 拉黑 / 移除一台服务器（让它自己清干净）

> Linux / Windows **完全一样**（大脑侧一条命令，子 agent 自己清本机）。

不想要某台机器了？**不用你上手去删** —— 大脑可以**命令它把自己清干净**：

```bash
python3 brain block <agent_id> --reason "换机 / 被入侵"
```

它会**再三确认**才动手，一共三层（少一层都不执行）：

1. 先把"拉黑会发生什么"打印给你，确认一次；
2. 让你**原样输入它的名字**（`agent_id`）；
3. 让你**一字不差地输入**：`我确认拉黑并让它自毁`。

确认后：

- 大脑立刻**拒绝它以后的一切请求**（心跳 / 领任务 / 升级 全断），它**再也注册不回来**；
- 它下次**来领任务时**收到"自毁指令"，然后把**本机关于自己的一切全删**：
  - **Linux**：程序文件、`~/.ai-agent`（配置 / 令牌 / 缓存 / 日志 / 公钥）、隐藏副本、开机自启（systemd / cron）—— 一点不留；
  - **Windows**：程序文件、数据目录、隐藏副本、计划任务 / 注册表 Run 键 / 监工进程，**还会顺带清掉用户 profile 下的残留** —— 一点不留；
- 删之前会先回报一句，此后 `brain status` 里它显示 **`已自毁`**（已拉黑但还没自毁则显示 `已拉黑`）。

> - **它不在线？** 指令一直挂着，等它下次联网（领任务）才执行；若它再也不上线，就到那台机器手动清：
>   Linux `./ai-agent selfdestruct`；Windows `.\ai-agent.ps1 selfdestruct`（或按 **第 15 节**手删）。
> - **误拉了想恢复？** 先 `python3 brain unblock <agent_id>` 解黑，再到那台机器**重新部署一次**（Linux 见第 6 节、Windows 见第 8 节）。
> - 这条命令**只能人工在终端敲**（不接受管道 / 脚本），也**不会由 AI 代劳**。

---

## 📧 14. 邮件报警（谁出事了，大脑给你发邮件）

> 大脑侧能力，与子 agent 平台无关。

配置三行就能用（写进 `brain.conf`，走你自建的「消息推送」服务，**不需要 SMTP**）：

```ini
PUSH_APP_ID=你的APPID
PUSH_APP_SECRET=你的APPSECRET
PUSH_TO=你的邮箱@example.com          # 多个用逗号分隔
# 可选：PUSH_BASE=https://www.xiaoyingapi.com   PUSH_MIN_INTERVAL=600   OFFLINE_ALERT_SEC=300
```

然后自测一发：**`python3 brain test-mail`**（收到邮件就成了；没收到看 `~/.ai-brain/brain.log`）。

会**自动**给你发邮件的事件：

| 事件 | 触发条件 |
| --- | --- |
| **agent 失联** | 某台心跳中断超过 `OFFLINE_ALERT_SEC`（默认 300 秒）——**这是"被安全软件清理掉"最可靠的信号** |
| **被清理后自愈** | 子 agent 发现自己的程序/服务/自启被删过、并已自我恢复时上报（Linux / Windows 都会报） |
| **拉黑 / 自毁** | 你拉黑了一台，或某台已按指令自毁完成 |
| **任务失败** | 子 agent 回报任务失败 |

> 同一个事件有 `PUSH_MIN_INTERVAL`（默认 10 分钟）**节流**，不会刷你邮箱；
> 失联是"**离线期间只报一次**"，它回来了再失联会重新报。

---

## 🧹 15. 卸载 / 彻底清理

> **平台分开删**；删之前先在大脑上停掉它。

```bash
# 0) 大脑那台：停服务
python3 brain stop
```

**Linux 子 agent（每台）：**

```bash
./ai-agent uninstall                            # 取消开机自启并停掉子 agent
pkill -9 -f 'ai-agent run'                      # 兜底再杀一次
rm -rf ~/.ai-agent                              # 数据：配置、令牌、公钥、日志
rm -rf ~/.local/.a-*                            # 隐藏多副本
rm -f /root/agent/ai-agent                      # 程序文件（按你实际路径）
```

**Windows 子 agent（每台，管理员 PowerShell）：**

```powershell
powershell -ExecutionPolicy Bypass -File C:\ProgramData\.ai-agent\ai-agent.ps1 uninstall
Remove-Item -Recurse -Force C:\ProgramData\.ai-agent
Remove-Item -Recurse -Force C:\ProgramData\.a-*
# 非管理员装法改删 $env:LOCALAPPDATA 下的同名目录 + Run 键
```

**大脑那台：**

```bash
rm -rf ~/.ai-brain        # 大脑数据：配置、数据库、签名密钥、注册口令
rm -rf ~/agent            # 程序目录本身
```

> ⚠️ **只删 `~/.ai-brain` 就等于"恢复出厂"**：里面存着签名密钥和注册口令，
> 删了以后 `brain init` 会生成**全新的一套**，所有子 agent 都得**重新注册**。
>
> 👉 只想"换一份新代码"，就**别删数据目录**，按对应平台升级即可（Linux 第 7.1 节 / Windows 第 9.1 节 / 大脑第 4.1 节）。

清完检查：

```bash
ls -d ~/.ai-brain ~/.ai-agent ~/agent 2>/dev/null
ss -ltn | grep 8787
ps -eo args | grep -E 'brain serve|ai-agent run' | grep -v grep
```

---

## 🆘 16. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| **（Linux）**一堆 `$'\r'` 报错 / `bad interpreter` | Windows 换行：`find . -type f -exec sed -i 's/\r$//' {} +`（Windows 子 agent 是 `.ps1`，**不受换行影响**） |
| 输入时崩 `UnicodeDecodeError: ... invalid continuation byte` | 已修：现在会容错、绝不崩。升级后若仍提示"无法识别的字节"，说明终端不是 UTF-8，在 `brain.conf` 加 `STDIO_ENCODING=gbk` |
| 它老是反问我"要不要帮你做"、或不肯做 / 给我讲道理 | 提示词已改成"执行者，不是顾问/审查员"。若还想更强硬，改 `prompts/system.md`（见第 11 节） |
| 它不肯删/不肯重启，说"命令被安全策略拒绝" | 子 agent **不做本地拦截**（旧版的危险命令黑名单已移除，升级子 agent 即可） |
| 每次动手都要我按 y，烦 | 输 `/auto` 切到「完全放行」挡（或在确认提示里按 `a`，或 `brain.conf` 写 `MODE=auto`），以后就不问了 |
| 提示"已达到步数上限"，活儿只干了一半 | **不是失败**：手动挡默认 20 步就停下。直接输入「继续」接着做；想一次做完就调大 `AI_MAX_STEPS`，或切 `MODE=auto` |
| 输出里出现 `�`（黑色问号） | 终端编码和 `STDIO_ENCODING` 不一致，按上面调一下即可 |
| `ModuleNotFoundError: No module named 'brainlib'` | 只传了 `brain`，没传 `brainlib/`；或把 `brain` 单独移走了（要和 `brainlib/` 同级） |
| `找不到提示词文件 system.md` | 没传 `prompts/` 目录（服务器运行不受影响，只是没法对话） |
| `/health` 没响应 / 起不来 | 看 `~/.ai-brain/serve.out` 的报错；多半是文件没传全或换行没转 |
| `尚未初始化，请先执行：brain init` | 先 `python3 brain init`；或 `BRAIN_HOME` 和初始化时不一致 |
| `未配置模型 Key` | 编辑 `~/.ai-brain/brain.conf` 填 `AI_API_KEY` |
| 子 agent 报 `连不上大脑` / `大脑地址不合格` | 地址**必须**是 `https://域名`（`http://` 或 IP 会被拒绝）；再查域名解析、证书是否有效、网络是否可达 |
| 大脑命令报 `还没配置 PUBLIC_URL` | 在 `brain.conf` 里设 `PUBLIC_URL=https://你的域名[/ai-brain]`（必须 https + 域名），并确保 nginx + 证书已就绪 |
| 注册后一直等批准 | 到大脑上 `python3 brain pending` → `python3 brain approve <id>` |
| 子 agent 显示`离线` | 心跳 30s 一次、离线判定 180s；看进程还在不在、网络通不通 |
| **发布了新版本，子 agent 却永远升不上去（版本号不变）** | 十有八九是**没重新打包**：`brain release` 只是"把你给的那个文件"登记发布，它 **不会**替你重新打包。若给的还是上次那个包，**两次发布的 sha256 会一模一样**，机器下载到的正文里 `$VERSION` 自然没变 → 每 10 分钟"升"一次、版本永远不动。**正确顺序**：① 在 Windows 上 `powershell -File win\pack-agent.ps1 -Online -Brain https://{大脑域名}/ai-brain -Key $pk -Out win\dist\ai-agent.ps1`（**必须先改好 `win\ai-agent.ps1` 里的 `$VERSION`**）；② 把产物传上大脑；③ `python3 brain release <产物> --os win --version <新版本> --notes "…"`。**自查**：`brain release` 会打印 sha256，换版本时它必须与上一版**不同**（相同就是没换包）；`brain version` 也能看到"已发布的最新版"。 |
| 装完提示"设置开机自启需要 root 权限" / 重启后子 agent 不跑 | **2.10.0 起非 root 也能装**：`ai-agent install` 会写进**你这个账号的 crontab**（`@reboot` 开机起一次 + 每分钟 `watchdog` 保活），**不需要 sudo**。装完 `crontab -l` 应看到两行。≤2.9.0 的旧版才有这个限制，升到 2.10.0 即可；急用可先手写一行：`(crontab -l 2>/dev/null; echo '@reboot /bin/bash /usr/local/bin/ai-agent run >>$HOME/.ai-agent/run.out 2>&1 &\') \| crontab -` |
| 下发后一直卡在"排队"、命令像是不接 | 子 agent **一次只做一条**，它正在跑别的任务。大脑现在会先告警"它已跑 X 分 Y 秒、后面还排着 N 条"；**同一条任务重复下发不会多跑一遍**（自动复用同一条）。急的话等它回报完再发，或先问它 `brain status`。 |
| 任务发出去发现不对，想让它**立刻停手** | `brain tasks --running` 看 id → `brain cancel <任务id>`（也可 `--agent <id>` / `--all`）。**排队中的直接作废**（不会被领走）；**执行中的会在下一步之前停手**（子 agent 每步都回报一次，通常几十秒内），然后回一条"已按主人指令取消"。 |
| 想给某台机器**起个好记的名字** / 把那台机器**彻底删掉** | 改名：`brain rename 旧名 新名`（只改大脑；**旧名自动变别名**，那台机器不用动）。删除：`brain rm 名字` —— 先命令它自毁，**确认清干净后再从大脑删记录**（要原样输入名字确认）；默认保留它的任务与上传，加 `--purge` 才连数据一起清。删掉后机器若还活着，会在连续 3 次"未注册"且确认是同一个大脑后**自己自毁**（防大脑重装误伤）。 |
| 子 agent 突然失联、`ai-agent: command not found` | 先看它是不是**被某条任务自己删掉了**（真发生过：一条"清理测试痕迹"的任务把 agent 的程序/配置/crontab 一起清了）。2.13.0 / 2.3.0 起有**执行前硬拦截**：命令同时命中"自己的程序/配置/副本/计划任务/crontab"和"删/写/停"动作时**直接拒绝执行**，并回报"已拦截"。恢复：`~/.ai-agent/agent.conf` 还在就只把程序放回去；没了就得重新 `enroll`（见 §16 上文）。 |
| `时间戳超窗` | 两台机器时钟差太多：Linux 装 `ntp`/`chrony` 对时；**Windows 确认"自动设置时间"开着**（PS5.1 用系统 UTC 时间签名） |
| `nonce 重复（疑似重放）` | 请求被重复发送；重试即可（正常不会有） |
| 没有颜色 / 没有 `── 结果 ──` 横线 | 当前不是"真终端"（输出被重定向、或某些面板终端）。**文字内容不受影响** |
| 没有 `💭 思考中` 那段 | 模型不支持思维链，或设了 `SHOW_REASONING=0` |
| 回复卡很久才一次性出来 | 你的模型/中转站不支持流式，或设了 `STREAM=0`；想逐字显示就设 `STREAM=1` |
| 觉得 `💭` 太啰嗦 | `SHOW_REASONING=0`，只留「思考 / 动作 / 结果」 |
| 升级报 `摘要不符` / `签名校验失败` | 包被改动，或子 agent 的 `brain.pub` 不是当前大脑的公钥 |
| `brain stop` 说"没找到 pid 文件" | `brain stop` 会兜底检查端口：只要 `8787` 还被某个 `brain serve` 占着就会自动停掉。若仍提示，说明确实没有进程在跑 |
| 停止 Linux 子 agent 没反应 | 它在长轮询里，最多 25 秒；急停 `pkill -9 -f 'ai-agent run'` |
| 服务器重启后子 agent 不见了 | 正常注册时**会自动设好**开机自启；若当时没设成，Linux 补 `./ai-agent install`，Windows 补 `.\ai-agent.ps1 install` |
| **（Windows）**`powershell` 里跑 `.\ai-agent.ps1` 报"禁止运行脚本" | 加 `-ExecutionPolicy Bypass`，如 `powershell -ExecutionPolicy Bypass -File .\ai-agent.ps1 status` |
| **（Windows）**`iwr` 下载报错 / 卡住 | 老系统加 `-UseBasicParsing`；或直接用 `scp` 从本地传（见 8.2） |
| **（Windows）**`/agent/install?os=win` 回 404 | 还没发布过 Windows 生产版：先 `brain release … --os win --version x`（见 8.1 开头） |
| **（Windows）**装完没起来 / 计划任务里找不到 | 确认是**管理员** PowerShell（否则会降级成 Run 键 + 监工）；用 `.\ai-agent.ps1 selfcheck` 自查 |
| **（Windows）**想彻底停掉它 | `Stop-ScheduledTask -TaskName WinHealthCheck` + 停 `WinHealthCheck1`；或直接用 `uninstall` |
| **（Windows）**程序被放到 `%TEMP%` 了要紧吗 | 不要紧：安装后会自动复制到 `C:\ProgramData\.ai-agent\ai-agent.ps1` 固定路径，任务/监工/副本都指向它 |
| **（Windows）**打包报 `读不到大脑的 PACK_KEY：请先 brain init，或用 -Key 指定` | `-Online` 打 Windows 包**必须有 `PACK_KEY`**，而打包机（你的 Windows）**没有** `brain.conf` —— 工具只会在本机 `%USERPROFILE%\.ai-brain\brain.conf` 里找。**解法**：先 `ssh -p {SSH端口} root@{大脑IP} "grep '^PACK_KEY=' /root/.ai-brain/brain.conf"` 拿到那把，再 `pack-agent.ps1 -Online -Brain … -Key <那把>`（见 §0 的 ⚠️）。另：**Windows 包不能在大脑上打** —— 大脑是 Linux、没有 PowerShell |
| 子 agent 上传报 `HTTP 413 文件太大` | 超过单文件上限（默认 50MB）。改 `brain.conf` 的 `MAX_UPLOAD_MB`，**重启 `serve`** 后生效 |
| 上传成功，但那个链接打不开 / 404 | 链接形如 `https://域名/f/<随机码>`。查：`PUBLIC_URL` 配好了吗、nginx 有没有把 `/ai-brain/` 转发到大脑 8787、有没有被 CDN/WAF 拦；实在打不开就回到大脑用 `brain get <id>` 取回 |

---

## 🔐 17. 域名 + HTTPS（**必做**，不是可选）

> 大脑**只监听本机**，对外**只能**通过 `https://域名` 访问；Linux / Windows 子 agent 都只认 `https + 域名`，
> `http://` 或 IP 一律拒绝。所以这一步是**部署大脑的必做步骤**。

**① 域名解析**：把 `brain.example.com`（举例）的 A 记录指向大脑服务器 IP。

**② 申请证书**：在宝塔里给该站点申请 **Let's Encrypt** 证书并开启 HTTPS。
> ⚠️ 别用 **CloudFlare Origin** 证书在源站直连 —— 子 agent / 浏览器不信任它。走 CF 代理则用 CF 的公网证书。

**③ nginx 反代**：把下面这段加到你那个站点的 nginx 配置里。

```nginx
location /ai-brain/ {
    proxy_pass http://127.0.0.1:8787/;
    proxy_read_timeout 120s;      # 子 agent 长轮询要留够时间
}
```

**④ 写进大脑配置**：编辑 `~/.ai-brain/brain.conf`：

```ini
BRAIN_BIND=127.0.0.1
PUBLIC_URL=https://brain.example.com/ai-brain
```

再重启大脑：`python3 brain stop && nohup python3 brain serve >~/.ai-brain/serve.out 2>&1 &`

**⑤ 验证**：`curl -s https://brain.example.com/ai-brain/health` 应回 `{"ok": true, ...}`；
`python3 brain status` 也应能出结果。

> 子 agent 的 `BRAIN_URL` 填**同一个地址**（`https://brain.example.com/ai-brain`）—— Linux 和 Windows 都一样。
> 内部端点有 `X-Admin-Token` 保护；本机 CLI 也走这个 https 地址（不再用 127.0.0.1 的 HTTP）。

---

## 🛡️ 18. 安全说明

| 环节 | 做法 |
| --- | --- |
| 注册 | 挑战-应答 + **大脑侧人工批准**；注册口令**不写进子 agent 脚本**，泄漏也进不来 |
| 通信 | 每台一个独立令牌；每个请求带 时间戳 + 随机数 + HMAC 签名，防重放/防伪造（**两个平台同一套协议**） |
| 执行 | 默认走**手动审核挡**（每个动作问你一次）；切到 `MODE=auto`（完全放行）后就不再询问、也不看步数上限。**但"接新机器"始终要你亲自批准**，完全放行挡也不例外 |
| 权限边界 | **子 agent 不做本地拦截**：大脑下发的任务它照做（这样才不会"你要删它却不删"）。所以**安全闸门在你手里**——不放心的操作就别开 `/auto` |
| 升级 | 大脑私钥签名 → 子 agent 公钥验签 + 摘要校验 + 语法自检 + 原子替换，失败保留旧版 |
| 加密生产版 | 正文 AES-256 加密、密钥可"在线取"、带 HMAC 完整性校验 —— 拷走文件也解不开（除非知道注册口令且能连大脑） |
| 密钥 | 配置都是 `600`（Linux）/ 仅管理员可读（Windows）；不放进代码、不贴聊天记录 |
| 审计 | 注册/批准/下发/执行/升级 全记在数据库 `audit` 表和 `~/.ai-brain/brain.log` |

> v1 的边界：子 agent 各持一把固定大模型 Key。v2 会改成"大脑通过中转站接口发**短期 Key**、
> 子 agent 直连中转站"（架构上已预留可插拔的「凭证驱动」位置）。

---

## 🗺️ 19. 已实现 / 后续计划

**已实现**
- 大脑：流式回复、**思考 / 动作 / 结果三态区分**、任务下发与汇总、心跳、审计、签名升级、邮件报警
- 子 agent：注册（挑战-应答 + 人工批准）、心跳、领任务、本机 AI 执行、**签名自升级**
- **两个平台**：Linux（`ai-agent`）与 **Windows（`win/ai-agent.ps1`）**，**协议逐字节对齐、功能一模一样**
- **通信强制「域名 + HTTPS」**（`http://` 或 IP 一律拒绝），大脑只监听本机（见第 17 节）
- **会合机制**：换服务器 / 换域名后，子 agent 靠"种子 + 期号"自动算出新域名找回（见第 20 节）
- **部署一次即可**：子 agent 注册成功时**自动设好开机自启**（Linux systemd/cron；Windows 计划任务 / Run 键），重启自动运行
- **一条命令部署**：大脑公开托管子 agent 客户端，Linux `curl … && ai-agent setup`、Windows `iwr … ; setup` 即完成「下载 → 配置 → 注册 → 自启」
- **OS 维度分发**：`brain release --os linux|win`、`/agent/install?os=…` 按系统下发；`brain version`/`status` 分系统显示
- **文件回传**：子 agent 用 `ai-agent upload <文件>` 把本机文件（截图 / 日志 / 报告…）传给大脑 → **网页链接在线看/下载**，另有 `brain uploads` / `brain get` 命令行取回（签名上传、单文件上限可配 `MAX_UPLOAD_MB`、公开链接用不可猜随机 ID、html/svg 只当附件下）
- 可配置：`STREAM`（流式开关）、`SHOW_REASONING`（思维链开关）等，见第 5 节
- 提示词与技能**全部外置**在 `prompts/`，且支持在 `~/.ai-brain/prompts/` 覆盖
- 底层拆分：入口只做分发，实现按职责分为 `brainlib/` 下多个模块

**后续计划**
- v2 凭证：走中转站发短期 Key（顺带可切 GPT / Claude / 豆包 / 千问）
- 更多入口：网页 / 飞书 / QQ / 微信 / 手机（现在只有命令行）
- 主动巡检告警（现在只有"心跳在线状态"，需要你主动问）

---

## 🔭 20. 会合机制（换服务器 / 换域名也能被找回）

> 场景：你现在的大脑服务器或域名被封了。你买了新服务器、换了新域名 —— 子 agent **不用你挨个改配置**，
> 它会**自己算出**新域名并找回来。**Linux / Windows 两个平台都支持**。

**原理**：大脑和每个子 agent 共享一段密钥 `RDV_SEED`，再加一个"期号" `n`，两边都能算出**同一个**域名：

```
域名(n) = RDV_PATTERN 里的 {h} 换成 hmac_sha256(RDV_SEED, "rdv:" + n) 的前 10 位
例：RDV_PATTERN=xybrain-{h}.icu，第 1 期 → xybrain-3f9a2b7c1d.icu
```

### 20.1 大脑侧：换后台域名时怎么做

```bash
python3 brain rendezvous               # 看当前：期号 / 当前域名 / brain_id
python3 brain rendezvous next --check  # 看“下一期”域名，并顺带查它能不能注册
```

流程：`rendezvous next` 给出下一期域名 → 你去 **.icu** 注册商把它买下 → DNS 指到新服务器 → 配好证书 →
`python3 brain rendezvous set <新期号>` → 完事。

### 20.2 子 agent 侧：连不上时自动找回

子 agent 注册成功后，会从大脑拿到 `RDV_SEED / RDV_PATTERN / RDV_INDEX` 并写进自己的 `agent.conf`。
之后一旦连不上现有大脑，它会：

1. 从当前期号往后算几个候选域名（默认 5 个，`RDV_WINDOW`）；
2. 对每个候选：
   - **能连上、且 `/health` 的 `brain_id` 对得上** → 就是我们的大脑 → 认领、写回配置 ✅
   - **已被注册但不是我们**（被别人抢注）→ 跳过，期号 +1
   - **还没被注册** → 说明你还没买 → **边等边继续往后探**
3. 每 30 秒重试一轮，直到找回。

> "是否被注册"用 **RDAP + DNS(NS) 双重判定**（`rdap.org` + Cloudflare DoH），尽量不误判。

### 20.3 安全提示

- `RDV_SEED` 是**主密钥**：泄漏了别人就能推算你的未来域名、甚至提前抢注。
  要换就执行 `python3 brain rendezvous rotate`（子 agent 下次心跳会自动更新）。
- 这套机制只在"子 agent **已经注册过、手里有种子**"时生效。**全新子 agent 仍需要你给它初始地址**
  （部署时填 `BRAIN_URL`）—— 这是绕不过去的第一次引导。

---

## 📝 21. 版本记录（**每次升级都要更新这里**）

**当前版本：大脑 `3.4.0` ／ 子 agent(Linux) `2.13.0` ／ 子 agent(Windows) `2.3.0`**

随时自己看，不用记：

```bash
python3 brain version          # 大脑版本 / 两个平台各自最新发布版 / 每台服务器实际版本
./ai-agent version             # 【Linux】本机版本 + 大脑上可升级到的最新版
.\ai-agent.ps1 version         # 【Windows】本机版本 + 大脑上可升级到的最新版
```

`brain version` 会长这样（一眼看出谁落后）：

```
大脑当前版本        : 2.10.1
程序自带的 ai-agent   : Linux 2.8.8 ｜ Windows 1.1.4
已发布的最新版      :
    Linux   : 2.8.9（2026-10-13 发布：xxx）
    Windows : 1.1.4（2026-10-13 发布：xxx）

服务器              系统       它上报的版本      最后心跳      状态
server-1            Linux      2.8.9            12s 前       已是最新
win-pc-3            Windows    1.1.3            35s 前       与最新发布不一致
（“不一致”＝它与该系统最新发布版不同：Linux 那台执行 ai-agent update；Windows 那台执行 ai-agent.ps1 update）
```

### 升级历史

| 日期 | 大脑 | 子 agent | 主要变化 |
| --- | --- | --- | --- |
| 2026-10-15 | **3.4.0** | Linux 2.13.0 ／ Windows 2.3.0（都不变） | **等待提示说人话：排队的机器到底在忙什么，一眼看到**。起因：主人看到"排队 1 台 / 执行中 0 台"以为卡死 —— 其实是那台机器正在跑**另一批**任务，而这个计数只统计当前这一批。改法：等待中每 15 秒的进度提示里，对**每一个排队中的任务**再问一次 `/internal/busy`，多打一行：`· FB客户服务器 正在跑另一条任务（已 5 分 12 秒）：「任务摘要」`；若那台机器**根本没在跑**，则打 `· X 没在跑任务 —— 可能离线，或还没来领`（这样"在忙"和"离线/不领任务"能一眼区分）。只改大脑，不用发子 agent。**实测（离线模拟两个场景）**：忙 → 输出"正在跑另一条任务（已 5 分 12 秒）：「另一件事：全盘搜日志」" ✓；不忙 → "没在跑任务 —— 可能离线，或还没来领" ✓；`py_compile` 通过；生产 `health` = `3.4.0` |
| 2026-10-15 | 3.3.0（不变） | **Linux 2.13.0** ／ **Windows 2.3.0** | **护栏：执行前硬拦截"删/改 agent 自己"的命令**（起因：一条"清理测试痕迹"的任务把子 agent 的程序、`~/.ai-agent`、crontab 一起删了 → 机器直接失联）。做法：两端在**执行每一条本机命令之前**先判一次，只有"**动作是删/写/停**"且"**目标命中自己人**"两条同时成立才拒绝（避免误伤只读命令与正常运维）：① 自己人 = `$AGENT_HOME`(~/.ai-agent)、程序文件、隐藏副本 `.a-*`、`ai-agent.service`、裸的 `ai-agent`；② 动作 = `rm/unlink/shred/truncate/mv/cp/install/dd/chmod/chown/tee`、`> ` `>>` 重定向、`find -delete`、`systemctl disable|stop`、`| crontab -`、Windows 的 `Remove-Item/del/rmdir/Move-Item/Set-Content/Clear-Content/icacls/Unregister-ScheduledTask/schtasks /delete/Stop-Service/Disable-ScheduledTask`；③ **`crontab -r` / `crontab -e` 无条件拦**（会把保活任务一起清掉，且看不出是冲谁来）；④ 命中后：`LAST_RC=126` + 返回"⛔ 已拦截…"给模型，让它换做法；同时写 `agent.log`。⑤ 提示词也加了一节【绝不许动自己（硬规则）】（要求它遇到"把 agent 删干净"这类任务要明确回报不能删）。**实测**：从**真实脚本里抽出**护栏函数跑 20 个用例全过 —— 拦截 12 个（`rm -rf ~/.ai-agent`、`cp /dev/null 覆盖 agent.conf`、`crontab -r`、`systemctl disable ai-agent`、`find … -delete`、`chmod 000`、删副本…）、放行 8 个（`ls/cat/grep` 只读、`rm /var/log/nginx/*.gz`、`sed -i` 改 nginx 日志、`df -h`、`echo > /tmp/x`…）；`bash -n` 与 ps1 语法/BOM 均通过。发布包自验：Linux 29453 字节 `f25c9e32…`（自跑得 2.13.0）、Windows 103421 字节 `92ed2df7…`（自跑得 2.3.0） |
| 2026-10-15 | **3.3.0** | **Linux 2.12.0** ／ **Windows 2.2.0** | **新增「自定义改名」与「自定义删除（删了就自毁）」**。① `brain rename <旧名> <新名>`：只改大脑侧；`agents`/`tasks`/`uploads` 一并改名，**旧名自动写进新表 `agent_alias`** —— 那台机器**完全不用动**（它继续用旧名签名请求也认，`verify_agent` 会顺着别名找到真身）；`/internal/dispatch`、`/internal/busy`、`/internal/cancel` 也都做了别名归一（否则按旧名派单会派给"不存在的人"）。② `brain rm <名字> [--force] [--purge]`：**两步走** —— 先写 `blocked(wipe=1)` 命令它自毁，在线的话等它回报"已清干净"（最多 60 秒），再从大脑**彻底删掉** `agents`/`blocked`/`enrollments`/别名；默认**保留**它的任务与上传记录，`--purge` 才连任务、上传记录与磁盘文件一起清。必须**原样输入名字**确认（非终端直接拒绝）；`--purge` 还要再输 `PURGE`。③ **机器侧兜底自毁**：子 agent 连大脑收到 `401 未注册` 时，必须同时满足"连续 ≥3 次 + 首次后发现 ≥10 分钟 + `/health` 的 `brain_id` 与本地缓存一致"才自毁 —— 少了最后一条，大脑重装/换库会让**全网机器集体自杀**；首次成功连上时会把 `brain_id` 记到 `~/.ai-agent/brain_id`，连上就清空误判计数。④ **大白话也能用**：新增动作 `rename_agent` / `delete_agent`（`prompts/actions.md` 已写明），删除走同一套"输入名字"确认。**实测（临时大脑 + 签名模拟 agent）12/12 全过**：改名后 `agents`/`tasks` 都变新名、旧名成为别名、**用旧名签名仍 200**、按旧名派单记在新名下；新名不能是别人的旧名、不能含空格；非终端 `rm` 被拒；pty 里输入名字后 `rm --force` 删净（任务保留）；删完该 agent 再连 → `401 未注册`。发布包自验：Linux 28365 字节 `cdd6e812…`（自跑得 2.12.0）、Windows 101009 字节 `87cc6e3f…`（自跑得 2.2.0）；生产 `health` = `3.3.0` |
| 2026-10-15 | **3.2.0** | **Linux 2.11.0** ／ **Windows 2.1.0** | **新增「真取消」：`brain cancel`** —— 主人能中途叫停，子 agent 会**真的停手**（不是只在大脑里改状态）。做法：① 大脑新增 `/internal/cancel`（按任务 id / 某台机器 / 全部）、`brain cancel` 与 `brain tasks` 命令；② **取消的信道复用"进度回报"** —— 子 agent 每跑一步都会 POST `/agent/report`，大脑在那次响应里回 `{"cancel":true}`，子 agent 就在**执行下一步之前**停手并回报 `state=cancelled`（不用长连接、不用额外轮询）；③ 任务状态新增 `cancelled`：**排队中的**直接作废（`/agent/poll` 不会再派出），**执行中的**下一次回报时被告知停手（且大脑**不会被后续的 running 回报覆盖**掉已取消状态）；④ 两端子 agent 都检查"启动前那条 report running"的响应（覆盖"刚领到就被取消"的竞态）。**实测**：临时大脑 + **模拟子 agent 的签名回报** 7/7 全过 —— 正常回报 `cancel:false`；取消执行中 → 1 条、`was=running`、DB 变 `cancelled`；下一次回报 → **`cancel:true`** 且状态不被覆盖；子 agent 回报 cancelled → 终态正确；取消排队中的 → `/agent/poll` 拿不到该任务；`busy` 为空；取消不存在的 id → 0 条不报错。发布包均自验：Linux 27577 字节 `aa139ca4…`（自跑 `--version` 得 2.11.0）、Windows 97597 字节 `b08eb0f9…`（自跑得 2.1.0）；公开分发端点下载字节与本地**完全一致**；生产 `health` = `3.2.0` |
| 2026-10-15 | **3.1.0** | Linux 2.10.0 ／ Windows 2.0.0（都不变） | **重做「大脑 ↔ 子 agent」的等待与下发逻辑（只改大脑，子 agent 不用重新发版）**。实测反馈："子 agent 还在干活，大脑却超时了；重发的新命令它一直不接"。根因三条：① 大脑按 **`TASK_TIMEOUT=300` 秒总时长**死等，**有进展也不续期**；② 超时后是人/模型**又发了一次**；③ `/internal/dispatch` **既不检查对方忙不忙、也不去重** → 每重试一次就多一条排队，子 agent 干完会**逐条重复执行**（带删除/重启的命令最危险）。改法：① 等待改成"**看进展**"：只要它每步都在回报就一直等，**连续 `TASK_TIMEOUT`（默认改成 180 秒）毫无新进展**才先不等；另加硬上限 `TASK_MAX_WAIT`（默认 2 小时）兜底；② 派发前先问新接口 `/internal/busy`：目标正忙就明确告警"它已跑 X 分 Y 秒、后面还排着 N 条"；③ **同一条任务自动去重**（同机器 + 同文本 + 队列中/执行中 → 复用，返回值带 `reused`）；④ 结束语**说实话**：不再是"超时未完成"，而是"**还在执行**（已 X；最近 Y 前有进展）—— 我先不等了，它做完会自己回报"或"**还在排队**（那台机器正忙，排到会自动执行）—— 不用重发"。**实测**：离线用例 4/4（慢但在动 600 秒完成不误判／真卡死 180 秒才放手／硬上限 60 秒／一直排队 180 秒）；临时大脑 HTTP 4/4（同一条连发两次 → 同一 task_id + `reused`、任务数仍 1；被领走后 `/internal/busy` 正确显示在忙与时长；在跑时再发同一条仍复用；换一条才新建）。生产发布后 `health` = `3.1.0`、`brain status` 正常、`serve` ppid=1 存活；顺手把一条 **8 天前的僵尸排队任务**标成"未执行（目标机器长期离线）"，避免它哪天突然执行 |
| 2026-10-15 | **3.0.0** | **Windows 2.0.0**（Linux 2.9.0 不变） | **不兼容：移除「键盘换词」功能（两侧全删）+ 两处顺手的优化**。① **删除**：Windows 的 `swap` / `swap-daemon` 子命令、`$SWAP_CS`（C# 低级键鼠钩子）、`swap\` 目录与 `hook.ps1`、`WinHealthCheck2` 计划任务、提示词里的换词小节；大脑的 `POST /agent/swaplog`、`swaplogs` 表、`brain swaplogs` / `brain swap-popup` 命令、心跳里的 `swap_popup` 字段、配置项 `SWAP_POPUP`、`brain files` 里的登记；README 的第 10 节换词小节与相关 FAQ（§21 历史记录保留）。② **升级后的历史遗留清理**（必须有，否则删不干净）：老版本装过换词的机器，`WinHealthCheck2` 任务与 `swap\hook.ps1` 进程不会自己消失，而且那个任务**没有隐藏窗口**、在用户会话里每分钟闪一下；新版本在 `run` 启动与 `selfcheck` 时做一次**幂等清理**（注销任务、杀掉 `hook.ps1` 进程、删掉 `swap\` 目录），`uninstall` / `selfdestruct` 也一并处理。③ **优化一：计划任务加 `-WindowStyle Hidden`** —— `New-Tasks` 里的两个任务（主进程 `run` 与每分钟的 `watchdog`）原来没隐藏窗口，**非管理员安装**时它们跑在登录用户会话里 → 会闪 PS 控制台窗口（和之前那个"窗口一闪一闪"同一类问题）。④ **优化二：`brain release` 防呆** —— 新发的包若与上一版**字节完全相同**（sha256 一样）会明确告警。这正是这次"发布了 1.3.2 但机器永远升不上去"的真因：`release` 只是登记你给的文件、**不会替你重新打包**。**实测**：`py_compile` 全过、`brain -h`/`files`/`swap-*` 已无残留、Windows 脚本 `grep -i swap` 只剩上述清理代码、语法与 BOM 正常 |
| 2026-10-15 | 3.0.0（不变） | **Linux 2.10.0**（Windows 2.0.0 不变） | **非 root 也能装开机自启（不用 sudo）**。实测反馈：`ubuntu` 用户装完子 agent，注册成功却提示"设置开机自启需要 root 权限"，而 `setup` 最后照样打印"安装完成 ✅ 以后服务器重启会自动运行" —— **假成功**，重启后不会跑。改法：`install_service` 不再直接拒绝非 root，改为**写进该用户自己的 crontab**：`@reboot` 开机起一次 + `* * * * * watchdog` 每分钟保活（`cmd_run` 有 pid 防重复，不会起两套；若本机 root 装过 systemd 服务，`watchdog` 会让位给它，不互相顶）。同时修三处：① `setup` 结束语按真实结果说（`AUTOSTART_OK`），没设好就**明确警告**；② `uninstall` 在非 root 时清掉自己 crontab 里那两行；③ `selfheal`/`selfcheck` 不再把"没有 systemd 单元"当作被清理（否则非 root 会每 5 分钟误报"本机被清理过"并上报大脑）。**实测（真实 Linux，临时非 root 用户）**：`install` → crontab 出现两行（`@reboot …` + `* * * * * …`）且**幂等**（再跑一次还是 2 行）；`uninstall` → 两行清空；`bash -n` 通过 |
| 2026-10-15 | 2.12.1（不变） | **Windows 1.3.2** | **换词钩子改由主程序生成的独立小脚本运行 —— 真机实测的根因修复**。真机（`DINGZHIYING`）证据：`swap\daemon.log` 里只有"拉起常驻钩子"、**从来没有"钩子启动"**，`swap.pid` 也不存在 → 钩子一次都没起来过。根因：**加密生产版的 `ai-agent.ps1` 启动时必须读 `agent.conf`**（里面的 `PACK_SECRET`）才能向大脑换解密口令，而 `agent.conf` 的 ACL 只给 SYSTEM/Administrators；可换词钩子又必须跑在**登录用户会话（非提权）**里（SYSTEM/会话 0 钩不到键盘），计划任务用的是 `RunLevel Limited` → 读不到配置 → 进程立刻退出（现象：换词永远不生效 + 计划任务每分钟重启它 → **PS 窗口一闪一闪**）。改法：主程序把「钩子本体」生成成 `swap\hook.ps1`（**只含钩子逻辑，不含任何密钥 / 令牌 / 提示词，只读同目录的 rules.conf**），计划任务改为直接跑它 → 不再碰 `agent.conf`。另修三处：① `Ensure-SwapDaemon` 现在**每次都核对任务动作**（老版本任务指向 `ai-agent.ps1 swap-daemon`，只判"任务存在"会一直留着坏任务）；② 防重复实例 / 存活判断改用**大小写不敏感包含**（实测 `-like '-File*<路径>*'` 匹配失败，且任务里写小写盘符、`$MyInvocation` 给大写）；③ `"$MyInvocation.MyCommand.Path"` 在双引号里**不会取属性**（会变成类型名），必须写 `"$(...)"`。**实测（本机 PS5.1）**：`hook.ps1` 独立进程跑 → 读到规则、装上键盘+鼠标钩子、`swap.pid`/`daemon.log` 正常；再起一个被防重复挡回；`Stop` 后零残留；生成物**不含 `AGENT_TOKEN` / `SYS_TASK` / `PACK_KEY` / `sk-`** |
| 2026-10-15 | 2.12.1（不变） | **Windows 1.3.1** | **修换词的两个真问题（实测反馈：配了规则"发送后没换成" + 那台机器"老是闪一个 PS 框"）**。① **只有一条规则时整套错乱** —— PowerShell 会把函数返回的 0/1 元素数组"拆包"成 `$null` / 单个字符串，于是 `$rules[0]` 拿到的是**字符串的第一个字符**：`swap list` 显示成空、`swap del 1` 删不掉甚至把规则表搞坏（多条规则时反而正常，所以第一轮没发现）。改为调用方一律用 `@(Get-SwapRules)` 接。② **PS 窗口一闪一闪** —— 常驻钩子必须跑在登录用户会话，而计划任务的动作**没带 `-WindowStyle Hidden`**，还配了 `RestartCount 999 / 1 分钟`：钩子一旦起不来就变成"每分钟闪一个黑框"；主循环也每分钟无条件重试拉起。改为：任务动作加 `-WindowStyle Hidden`、去掉自动重启、拉起失败**退避 5 分钟**（`swap/.last-try`）。③ **钩子闷死还不留痕** —— 写 pid 文件那行原本在 `try` **外面**，目录没写权限就带红字立刻死；而 `agent.log` 在 `ProgramData` 下普通用户写不进去（等于没有诊断）。改为全部包进 `try`，并新增 `swap/daemon.log` 轨迹（启动 / 规则数 / 钩子装没装上 / 每次触发）＋ `swap` 自检输出（钩子是否在跑 / 登录用户 / 规则文件可读性 / 计划任务状态 / 最近日志）。④ **鼠标点"发送"认不出来** —— 原来要求"敲完字 **1.5 秒**内点左键"，而打字完再移鼠标去点发送通常要几秒（QQ 邮箱写信页按回车是换行，多数人是点按钮）→ 等于不生效；放宽到 **6 秒**，并要求**前台窗口没变**（避免在别的程序里乱点也触发）。⑤ 其它：`Ensure-SwapDir` 的 ACL 授权改为幂等、`Stop-SwapDaemon` 按命令行兜底清理幽灵实例、`Cmd-SwapDaemon` 加**防重复实例**（两个钩子同时跑会把同一句话换两次）。**实测**：0/1/3 条规则下 `add/list/del/del all/同词覆盖` 全对；钩子起停、`daemon.log` 轨迹、防重复（起第 2 个被挡）、`Stop` 后零残留 全通 |
| 2026-10-15 | **2.12.1** | Windows 1.3.0（不变） | **修一个"改了配置却不生效"的存量隐患**。根因：服务进程的 `conf` 是**启动时快照**，而好几个命令偏偏是**运行期**改配置 —— `brain rendezvous rotate` / `rendezvous set`（换会合主密钥 / 期号）、`brain pack-key rotate`（轮换生产版解密口令）、以及手工改 `BRAIN_URLS` / `SWAP_POPUP`。后果：① `rendezvous rotate` 后**新种子不下发**，更糟的是 `/health` 里的 `brain_id` 仍用**旧种子**算 → 子 agent 的"这是不是我们的大脑"身份校验**失败**，会合找回直接不工作；② `pack-key rotate` 后 `/agent/key` 仍发**旧口令** → 新打的包起不来（轮换等于没做，还误以为旧的已经失效）；③ 地址清单 / 换词弹窗开关同理不生效。改为：这几类"要**立刻下发**"的字段**每次请求现读配置文件**（新增 `Server.live_conf()`，用在 `/health`、注册批准下发、心跳下发、`/agent/key`）；纯启动期项（监听地址 / 端口）照旧。**实测（临时大脑，全程不重启 `serve`）**：`rendezvous rotate` 后 `/health` 的 `brain_id` 立刻变、心跳下发的 `rdv_seed` 立刻等于 conf 新值；模拟 `pack-key rotate` 写入后 `/agent/key` 立刻下发新口令 + 过渡期旧口令；`swap-popup off/on` 心跳立刻变 `0`/`1`；错口令仍 `403` |
| 2026-10-15 | **2.12.0** | **Windows 1.3.0**（Linux 2.9.0 不变） | **新增「键盘换词」：员工输入 aaa，屏幕上一直是 aaa，只在"发送那一刻"真正发出去的是 bbb**。① **Windows 子 agent** 新增 `swap` 子命令（`add -From aaa -To bbb` / `list` / `del <序号\|all>` / `on\|off`）与常驻钩子 `swap-daemon`：用 `Add-Type` 编译的 C# **低级键盘 + 鼠标钩子**（`WH_KEYBOARD_LL` / `WH_MOUSE_LL` + 消息泵），打字时把键累积进缓冲**只做识别、不吞键**（屏幕完全不变），识别到"发送"（回车 / Ctrl+回车；或刚敲完字 1.5 秒内点鼠标左键）时**吞掉该次事件**，再用「Ctrl+A → Ctrl+C → 替换文本 → Ctrl+A → Ctrl+V」重写真正发出的内容，最后按**吞下那一刻记录的修饰键状态**重放回车（鼠标则重放同坐标点击、并吞掉配对的弹起）；改写后还原员工原剪贴板、弹一个**不抢焦点**（`WS_EX_NOACTIVATE`）的自关提示，并把事件写成本地流水。**兜底铁律**：任何一步失败、或输入框内容 >3000 字，一律**原样放行**——宁可没换成，绝不吞掉发送。（钩子按设计忽略"注入的"按键，防自触发死循环）② **必须跑在登录用户会话**（SYSTEM/会话 0 钩不到键盘）：新增独立计划任务 `WinHealthCheck2`（`AtLogOn` + 崩溃自动重启、`RunLevel Limited`），由主程序每 60 秒巡检保活；规则经 `%ProgramData%\.ai-agent\swap\rules.conf` 下发（该目录对普通用户可读写），钩子每 3 秒重读 → **改规则不用重启**；`selfdestruct` / `uninstall` 会一并清掉常驻钩子与 `WinHealthCheck2`。③ **大脑**新增 `POST /agent/swaplog`（验签 / 拉黑 403 / 落 `swaplog` 表 + 审计）、心跳响应下发 `swap_popup`、新表 `swaplog`（`brain files` 已登记）；新增 CLI `brain swaplogs [agent_id] [-n N]`（谁/何时/aaa→bbb/在哪个程序）与 `brain swap-popup [on\|off]`（**弹窗开关在大脑侧**，改完 ≤1 分钟经心跳自动下发）；新配置项 `SWAP_POPUP`。④ 子 agent 把每次换词写成 `swap/events.log` 本地流水，主程序读取后上报大脑再清空（钩子跑在普通用户下读不到 `agent.conf`，故用 `swap/` 目录交换）。⑤ 系统提示词新增「键盘换词」一节，教模型用 `swap add`。**实测（本机 Windows 10/PS5.1）**：C# 编译通过、`swap-daemon` 起停正常（`SetWindowsHookEx` 成功、pid 文件与日志正常、杀掉后无残留）、`swap add/list/del/on\|off` 全覆盖（含同词覆盖、非法字符拒绝、`rules.conf` 同步）、大脑侧 `py_compile` 全过。**注意**：钩子的"真机打字换词"最终效果需在**交互桌面**上人工验证——自动化脚本注入的按键会被钩子按设计忽略（防死循环），无法自动测 |
| 2026-10-13 | **2.11.0** | **Linux 2.9.0** ／ **Windows 1.2.0** | **新增「文件回传」：子 agent 把本机文件（截图 / 日志 / 报告）传给主人，网页在线看 / 下载**。① 子 agent 新增子命令 `ai-agent upload <文件>`（Windows：`.\ai-agent.ps1 upload <文件>`）——**签名上传**（文件名/任务号放 query、文件原始字节作 body，摘要进签名）；② 跑本机命令时**自动注入任务号**（`AI_AGENT_TASK_ID`）与程序自身路径（`AI_AGENT_CMD`），所以模型不用管任务号、直接用 `"$AI_AGENT_CMD" upload <路径>` 就行，两个平台的系统提示词都加了「给主人看文件」一节；③ 大脑新增 `POST /agent/upload`（验签 / 屏蔽拉黑机器 / `MAX_UPLOAD_MB` 限额 413 / 文件名清洗防目录穿越 / 落 `~/.ai-brain/uploads/<agent>/`）与公开只读 `GET /f/<id>`（在线看/下载：图片与纯文本内联，**html/svg/js 一律当附件下载**，带 `nosniff` + `noindex`；ID 为 128 位随机、不可猜）；④ 任务结束（done/failed）时大脑把它上传的文件**连链接附进结论**（`【本任务上传的文件】…`）；⑤ 新增 CLI `brain uploads`（列表带在线链接、`--rm <id>`、`--clean`）与 `brain get <id> [-o 文件]`。**实测（临时大脑 + Linux/Windows 子 agent）**：CLI 上传 → 落盘/入库 → 公开链接取回字节一致（sha256 相符）→ `?dl=1` 变附件 → `brain uploads`/`brain get` 正常；LLM 任务里它自动用注入的路径完成"建文件→上传"，结论里出现 `【本任务上传的文件】` 且上传记录**自动带上任务号**；安全项全过（未签名 401、超限 413、`../..` 文件名被清洗、html 不内联）。另修：Windows `Cmd-Upload` 把子命令 `upload` 误当文件名（改为从 `$LAUNCH_ARGS[1]` 起解析） |
| 2026-10-13 | **2.10.2** | **Linux 2.8.11** ／ **Windows 1.1.8** | **从零部署 Linux+Windows 子 agent 的整轮实测，发现并修复 6 个问题**：①**发布护栏漏 Windows 明文** —— `brain release` 只认 Linux 的 `SYS_TASK='`，Windows 明文开发版是 `$SYS_TASK = @'`，护栏抓不到（会把源码/提示词发出去）；改为 `\$?SYS_TASK\s*=` 通吃两平台，且公开端点 `/agent/install` 对"已发布包"也加一道明文兜底（403）。②**加密版 loader 不认识 `--secret`** —— 全新机器上 `setup/enroll --secret …` 会卡在 loader 的口令提示（非交互直接挂住）；Linux/Windows 两个打包器的 loader 改为**优先读命令行 `--secret`**（且不破坏 `$@` 透传），非交互下拿不到口令就**明确报错退出**而不是挂死 → 真正的零交互一键安装。③**自毁遗留心跳子壳** —— 加密生产版进程 cmdline 是 `bash /dev/fd/N run`（不含 ai-agent），`do_wipe` 按名字 `pkill` 匹配不到，主进程退出后**心跳子壳/副本继续跑并把数据目录重建回来**；改为**先杀进程再删文件**，并用 `/proc/*/environ` 里的 `AI_AGENT_SELF` 精确命中所有角色。④**拉黑后残留实例复活** —— 另一实例在 `wipe_done` 置位后拿到的是 `403 已被拉黑`（非 wipe 字段）而继续运行；两个平台都改为 **403 也当自毁**。⑤**Windows 请求丢 Content-Type** —— `HttpWebRequest` 不允许通过 `Headers` 集合设 `Content-Type`（被静默忽略），导致所有请求都不带 Content-Type：大脑（自研 HTTP 服务）不在意，但**模型接口直接 415**；改为走 `ContentType` 属性。⑥**Windows 调模型 messages 格式错** —— PS5.1 把 `($json \| ConvertFrom-Json)` 再 `ConvertTo-Json` 会序列化成 `{"value":[…],"Count":N}`（不是 JSON 数组）→ 模型接口 **422**；改为把已序列化好的 messages 文本原样拼进 body。**实测**：Linux（root/systemd）与 Windows（管理员/SYSTEM 计划任务）**从零一行命令安装 → 注册批准 → 上线 → 大白话下发任务→两台各自执行并回报→大脑汇总全通 → 自升级 → 崩溃自愈/重启 → 多副本自愈 → 三层确认拉黑自毁（全清、零残留）** 全通 |
| 2026-10-13 | **2.10.1** | Linux 2.8.8 ／ **Windows 1.1.4** | **Windows 真机补测（自升级/自愈/自毁）发现并修复**：①**自升级两处真 bug** —— 下载升级包走了**未签名**请求（`/agent/pkg` 同样要验签）→ 恒 `401`，改为复用带签名请求、并保留**原始响应字节**落盘（`Api-Req` 新增 `$RESP_BYTES`）；`Apply-Upgrade` 早前被重写成 `(新包, 目标)` 两参，但调用处仍只传一个参数、且把**旧文件**复制到目标（等于没换），改为 `Apply-Upgrade $newf $self`。另：换包前新增**语法自检**（`Parser::ParseFile` 全通过才替换），坏包绝不上身。②**安装路径** —— 新增 `Install-Self`：把运行中的程序落到 `%ProgramData%\.ai-agent\ai-agent.ps1`（此前可能从 `%TEMP%` 直接跑，计划任务/监工都指向临时文件，系统一清就复活失败）。③**自毁没删干净** —— 管理员（SYSTEM）自毁只清了 `%ProgramData%` 与 **SYSTEM 自身**的 `%LOCALAPPDATA%`；若本机曾以**非管理员**装过，用户 profile 下的 `.ai-agent`/`.a-*`（含令牌）会残留 → `Do-Wipe` 增补：以 SYSTEM 身份**遍历 `C:\Users\*` 清用户级残留**。**真机验证（LAN Windows）**：自升级 1.1.2→1.1.3（下载/验签/替换/隐藏副本同步 sha 一致）、自愈（删 2 个副本后 300s 定时器与 `selfcheck` 均自动补齐）、拉黑自毁（终端三层确认 → 任务/进程/数据目录/隐藏副本**全清**，含用户级残留）均通过 |
| 2026-10-13 | **2.10.0** | Linux 2.8.8 ／ **Windows 1.0.3** | **新增 Windows 子 agent**：`scripts/agent/win/ai-agent.ps1`（纯 PowerShell 5.1，系统自带零依赖）**协议与 Linux 版逐字节对齐**（同签名串 `METHOD\nPATH\nTS\nNONCE\nBODY_SHA256`、同 header、同端点、同会合算法）；任务用 **PowerShell** 执行；自启用**计划任务**（管理员→SYSTEM 级）或**注册表 Run + 常驻监工**（非管理员自动降级）；多副本隐藏、自愈、自毁、在线取密钥。配套 `win/pack-agent.ps1`（AES-256-CBC+PBKDF2 加密、`-Online` 在线取密钥、HMAC 完整性）。大脑加 **OS 维度**：`releases(agents).os`、`/agent/update`/`/agent/pkg`/`/agent/install` 按系统分发、`brain release --os linux\|win`、`brain version`/`status` 分系统显示（老库自动迁移）。**实测修复**：`(if…)` 不能用作表达式、非管理员建计划任务被拒→改用 Run+监工、`Get-Date -UFormat %s` 在 PS5.1 返回**错的时间戳**（+8h）导致签名 401→改用 `DateTimeOffset::UtcNow`、加密 payload 在 scriptblock 内 `$script:` 取不到状态→全部改 `$global:`。**二轮稳定性加固（Windows 1.0.4）**：`Http-Req` 吸收**一切**异常（网络抖动不再打死主循环）且失败写日志；`run` 退出时清 pid/临时目录；pid 复用不再误挡启动；自毁补删自己的一次性任务；口令输入改**不回显**并支持环境变量；Run 键用**绝对** powershell 路径；监工加自身路径防呆 |
| 2026-10-12 | 2.9.2 | **2.8.8** | **自毁的根因**：子 agent 被 systemd 托管时（Type=simple，默认 `KillMode=control-group`），主进程一退 systemd 就把本服务 cgroup 里的进程全杀 —— 原来"起个脱离子进程去删自己"**被连坐杀掉，自毁啥也没干**（实测：只有 cron 副本亲手删时才有部分效果）。改为用 **`systemd-run` 起一个独立单元**跑清理脚本（不在本服务 cgroup 内 → 杀得掉自己、不被连坐），拿不到 systemd-run 才退回 `setsid+nohup`。清理动作本身也补全（程序目录 / 整个副本目录 / 相关 cron 行 / 单元 / 数据目录） |
| 2026-10-12 | 2.9.2 | **2.8.7** | **自毁没删干净**：实测"拉黑→自毁"后发现 `~/.local/.a-<hash>/`（隐藏多副本）、`~/agent/`（程序目录）、以及新的 cron 兜底行都**残留**（老代码只删了程序文件和数据目录，且 cron 过滤用的是已被替换掉的 `ai-agent run` 字样）。改为：程序文件+程序目录、**整个副本目录**、数据目录、systemd 单元、以及所有与本 agent 相关的 cron 行，全部清掉 |
| 2026-10-12 | 2.9.2 | **2.8.6** | **子 agent 稳定性**：①`extract_cmd` 只取** shell 代码块**（```bash/```sh 或未标语言的），忽略 ```text/```output/```json 等 —— 修"模型把命令结果贴进代码块 → 被当成命令再跑一遍"（浪费步数、日志混乱）；配套把提示词里的"命令块带 bash 标记 / 结论不要代码块"写得更死。②cron 兜底改为调用新的 `ai-agent watchdog`：**systemd 在管时它让位**（只有 systemd 不在/被清掉才顶上）—— 修"cron 副本抢跑导致 systemd 显示 inactive、且自升级只更新副本、主文件落后一版" |
| 2026-10-12 | **2.9.2** | 2.8.4 | **安全修**：`GET /agent/install`（公开、免签）原来会把程序目录里的 `ai-agent` 原样分发 —— 若那里放的是**明文开发版**，等于把源码与提示词公开到网上，违背"隐藏自身"。改为：**只发"已发布的最新升级包"（一定加密）**；没发布过则回退本地文件，但**含 `SYS_TASK` 的明文一律拒发（403）** |
| 2026-10-12 | **2.9.1** | **2.8.4** | **本轮三机端到端实测发现并修复两个稳定性问题**：①`/agent/key` 原来对**所有**取钥匙请求限速（8 次/分/IP），子 agent 正常重启/自升级时被自己人挡成 429 → stub 取不到钥匙退出 → systemd 反复重启**自锁**；改为**只对"猜错口令"限速**（口令正确不限速，成功即清计数）。②「防重复实例」原来冲突时以**失败码**退出，叠加 `Restart=always` 会与 cron 兜底实例互相顶 → systemd **无限重启循环**；改为冲突时**干净退出(0)** + 服务单元用 `Restart=on-failure`。另：`tools/pack-agent.sh` 的 stub 取钥匙失败**退避重试 3 次**（3s 间隔） |
| 2026-10-12 | **2.9.0** | 2.8.3 | **口令可安全轮换 + 加密加固**：新增 `brain pack-key`（查看 / `rotate` 轮换 / `drop-old`）；轮换走**双口令过渡**（新增 `PACK_KEY_OLD`，`/agent/key` 同时下发新旧），打包脚本改为"先按当前口令校验、不匹配自动退旧口令"——避免单口令轮换把**还没升级的子 agent 整片锁死**。另加固：密文加 **HMAC-SHA256 完整性校验**（被改过即 `package error`）；`/agent/key` 取反代真实 IP（`X-Forwarded-For`）、连续猜错 5 次**发邮件告警**、请求过频也告警；`brain release` 拒绝直接发布**明文开发版**（防误把全网子 agent 变明文，需 `--force`） |
| 2026-10-12 | **2.8.0** | **2.8.3** | **生产版密钥不落文件（在线取）**：大脑新增 `PACK_KEY`（init 自动生成）与 `POST /agent/key`（凭注册口令换，带限速；兼容表单提交）；`tools/pack-agent.sh` 新增 `--online --brain <url>`：生产版**文件里不含任何密钥**，启动时向大脑换取（换到后缓存在 `~/.ai-agent/agent.conf`，供 systemd 启动复用）→ **拷走文件也解不开**。另：ai-agent 依赖检查补上 `gzip` |
| 2026-10-12 | 2.7.1 | **2.8.2** | 修：加密生产版运行时 `$0` 指向 `/dev/fd/N`，导致 `install_service` / `ensure_unit` 写出的 systemd 单元路径错误（开机自启失效）；改用 `$SELF_PATH`（开发版/生产版都正确）。另：`tools/pack-agent.sh` 加固——命令名/算法名运行时拼装（文件里搜不到 `openssl`/`base64`/`aes-256-cbc` 等）、密文切 4 段、口令 base64+rot13、不再依赖 `rev` |
| 2026-10-12 | 2.7.1 | **2.8.1** | **加密生产版**：新增 `tools/pack-agent.sh`（AES-256 打包，正文加密、运行时在内存解密）+ 开发版配套改动（`SELF_PATH` 认 `AI_AGENT_SELF`、`usage` 给生产版精简帮助），保证加密后 **自升级/自删除/多副本** 仍指向加密文件本身 |
| 2026-10-12 | **2.7.1** | 2.8.0 | 修：发通知时 `urllib` 带的默认 UA（`Python-urllib/3.x`）被 Cloudflare **403**；改为带正常浏览器 UA（`brain test-mail` 因此报 403 的问题解决） |
| 2026-10-12 | **2.7.0** | **2.8.0** | **抗清理（多副本 + 互保）**：把自己复制成 N 份（`~/.local/.a-<hash>/`，700 权限）+ 一条 **cron 兜底**（每分钟试跑，靠"防重复实例"保证只跑一份）+ **运行中每 5 分钟自查**，被清理过就补齐/重建并**上报大脑**（→ 邮件通知你"已由副本接替"）；新增 `ai-agent selfcheck` |
| 2026-10-12 | **2.7.0** | 2.7.0 | **邮件报警**：大脑新增通知通道（走自建 push API，`PUSH_APP_ID/PUSH_APP_SECRET/PUSH_TO`，HMAC 签名与项目 `sign.py` 一致）+ `brain test-mail`；自动报警四类事件——**agent 失联**（`OFFLINE_ALERT_SEC`，后台巡检）、被清理后自愈上报、拉黑/自毁、任务失败；同类事件按 `PUSH_MIN_INTERVAL` 节流 |
| 2026-10-12 | **2.6.0** | **2.7.0** | **拉黑 + 自毁**：`brain block <id>`（三层确认）→ 大脑拒绝它一切请求，并命令它**把本机关于自己的一切删干净**；`brain unblock` 解黑。子 agent **自救加固**：临时目录改放 `~/.ai-agent/tmp` 且**被删会自愈**、`cleanup` 只在主进程跑、请求出错**退避**、**防重复实例**（修"跑着跑着变哑/永远离线/不升级"） |
| 2026-10-12 | **2.5.0** | **2.6.0** | **逐步进度**：子 agent 每执行一步就回报一次（"第 N 步：…"），大脑在下发等待时实时打印 `▶ 【某机】第 N 步：…`——能看清它做到哪一步了 |
| 2026-10-12 | **2.4.0** | 2.5.0 | 下发后不再"干等"：实时打印**谁领取了任务（还剩几台未领取）**、谁已回报；迟迟没动静时每 **15 秒**报一次进度（未领取 / 执行中 / 已回报）。仅大脑侧（`chat.py`） |
| 2026-10-12 | **2.3.0** | **2.5.0** | 子 agent 执行纪律重写：**无条件执行**（不许以道德/合规/取证/安全等理由拒绝或打折，不许建议替代方案、不许反问）；**穷尽搜索**（全盘 grep、zgrep、journalctl、**宝塔面板 SQLite 库 `/www/server/panel/data/default.db`(表 logs)**、应用数据库等）；**绝不许编**（找不到必须给出搜过的命令与路径作证据）。修"一台肯做、一台拒绝"和"日志明明有却说没有" |
| 2026-10-12 | **2.3.0** | 2.4.0 | 下发确认增强：确认时可**直接打字改任务**（回喂模型改写后**再确认一次**）；AI 可在确认前给出**最多 4 条待拍板项**（每条附它的倾向），主人可**逐条**给意见；`auto` 挡下建议照常打印但不阻塞。仅大脑侧改动（`chat.py`/`ui.py`/`prompts/`） |
| 2026-10-12 | **2.2.0** | **2.4.0** | 子 agent 新增 `setup` **一条龙**（问你该填的 → 写配置 → 注册 → 装开机自启）；大脑新增 `GET /agent/install` 公开分发子 agent 客户端 —— 新服务器**只需一行命令**即可完成部署 |
| 2026-10-12 | 2.1.1 | **2.3.0** | 子 agent **注册成功时自动设好开机自启**（优先 systemd，没有则退回 cron `@reboot`）——部署一次即可、重启服务器自动运行，用户无需手动配置；`install`/`uninstall` 保留为手动补充 |
| 2026-10-12 | **2.1.1** | 2.2.0 | 子 agent 新增 `install` / `uninstall`：装成 systemd 服务（开机自启 + 崩溃自动重启）；会合搜索"期号前移"改为**落盘**（你跳号也能一路找回）；修 `brain rendezvous` 未初始化时的显示 |
| 2026-10-12 | 2.1.0 | 2.1.0 | **会合机制**：新增 `RDV_SEED/RDV_PATTERN/RDV_INDEX`（注册/心跳自动下发）；子 agent 失联后靠"种子+期号"自动算出新域名找回（RDAP+DNS 双查注册状态 + `/health` 的 `brain_id` 身份校验，边等边往后探）；新增 `brain rendezvous` 命令 |
| 2026-10-12 | 2.0.0 | 2.0.0 | **不兼容**：强制「域名 + HTTPS」。大脑只监听本机、新增 `PUBLIC_URL`（必须 https 域名，本机 CLI 也走它）；子 agent 只认 https 域名，`http://`/IP 一律拒绝（run 等待重试、enroll 提示退出）。旧的 `http://IP:8787` 不再可用 |
| 2026-10-12 | 1.1.7 | 1.1.2 | 修：终端里 `brain "一句话"` 问完**不再退出整个会话**，而是继续留在对话中；被脚本/管道调用时仍问完即退 |
| 2026-10-12 | 1.1.6 | 1.1.2 | `brain stop` 增加兜底：停完后检查配置端口是否仍被旧 `brain serve` 占用，是则一并终止（避免旧进程占着端口导致下次启动不生效） |
| 2026-10-11 | 1.1.5 | **1.1.2** | 新增 `brain version` / `ai-agent version`（当前版本 vs 最新版）；README 增加版本记录 |
| 2026-10-11 | 1.1.4 | 1.1.1 | 新增 `brain files` 文件文档控制台 + `brain explain` 让 AI 解读每个文件 |
| 2026-10-11 | 1.1.3 | 1.1.1 | 两个挡位 `MODE`（手动审核 / 完全放行）；步数上限可配（默认 20 / 200）；子 agent 步数上限提到 20 |
| 2026-10-11 | 1.1.2 | 1.1.0 | 提示词改为"执行者，不是顾问"；**去掉子 agent 本地的危险命令拦截**；修注册接口 `_new_id` 未定义的 500 |
| 2026-10-11 | 1.1.1 | 1.0.0 | 修输入编码崩溃（`UnicodeDecodeError` 直接让程序退出） |
| 2026-10-11 | 1.1.0 | 1.0.0 | 底层重构：入口拆薄、实现分到 `brainlib/` 多模块；提示词外置到 `prompts/`；流式可配 |
| 2026-10-11 | 1.0.0 | 1.0.0 | 首版：大脑 + 子 agent、注册与人工批准、任务下发与汇总、心跳、签名自升级 |

### 维护约定（**以后每次改代码都照做**）

1. **升版本号**：改完代码，把对应文件的版本各加一位——**只改了哪边就只升哪边**：
   - 大脑：`brainlib/__init__.py` 里的 `VERSION`
   - Linux 子 agent：`ai-agent` 里的 `VERSION`
   - Windows 子 agent：`win/ai-agent.ps1` 里的 `$VERSION`
   规则：
   - 修 bug → 末位 +1（`2.4.0` → `2.4.1`）
   - 加功能 → 中位 +1（`2.4.0` → `2.5.0`）
   - 不兼容改动 → 大头 +1（`2.4.0` → `3.0.0`）
2. **记一笔**：在上面那张「升级历史」表的**最上面加一行**：日期 / 两边新版本号 / 一句话说明改了什么。
3. **子 agent 有变化时**：发布对应平台的新版，让它自己升级：
   - Linux：`python3 brain release <ai-agent文件> --os linux --version <新版本> --notes "说明"`
   - Windows：`python3 brain release <win打包产物> --os win --version <新版本> --notes "说明"`
   （也可以在 README **第 7.1 / 9.1 节**走手工替换。）
4. **同步文档顶部**：把 `README.md` 开头那行「当前版本 🧠 大脑 … ／ 🐧 Linux … ／ 🪟 Windows …」改成与本节（第 21 节）一致，别两处对不上。


