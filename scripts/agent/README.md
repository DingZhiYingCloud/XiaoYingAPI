# ai-brain / ai-agent 部署与使用手册

> 面向"不想懂太多 Linux 也能照着做"的版本：**每一步都有完整命令 + "看到什么算成功"**。
> 出问题先看第 12 节《常见问题》。

**快速导航**（按"想干什么"找）：

| 想干什么 | 看第几节 |
| --- | --- |
| 搞懂这东西是啥、开工前须知 | 0、2 |
| 第一次部署「大脑」 | 3 |
| 部署「子 agent」（每台服务器） | 4 |
| 日常怎么用 / 手动·自动挡位 | 5 |
| 改配置 / 改提示词加技能 | 6、7 |
| 换个目录放 | 8 |
| **升级（最常看）** | 9 |
| 日常运维命令 | 10 |
| 卸载 / 彻底清理 | 11 |
| 出错排查 | 12 |
| 域名 + HTTPS（必做） | 13 |
| 安全说明 / 计划 / 文件说明 | 14–16 |
| 会合（换域名后自动找回） | 17 |
| 版本记录 + 维护约定 | 18 |

---

## 0. 这东西是干什么的

你跟 **Agent 大脑** 说大白话，它拆解任务、**同时指挥**你所有服务器的 **子 agent**；
每个子 agent 在**自己那台机器上独立完成**（自己直连大模型），把结论回报给大脑；
最后由大脑汇总成 **「哪台成功、哪台失败、关键数据是多少」** 汇报给你。

```
   你（命令行）
      │  跟它说大白话
      ▼
   Agent 大脑（1 台）   ← 理解意图 / 下发任务 / 汇总结果
      │
      │  子 agent 主动连它（穿透 NAT，不用给每台开端口）
      ├──────────────┬──────────────┐
      ▼              ▼              ▼
   ai-agent       ai-agent       ai-agent
   server-1       server-2       server-3      （未知权限也能跑）
```

| 文件/目录 | 放在哪 | 作用 |
| --- | --- | --- |
| `brain` | **1 台**（大脑） | 入口脚本：解析命令、分发 |
| `brainlib/` | 同上 | 大脑的实现（十几个小模块，见第 1 节） |
| `prompts/` | 同上 | **提示词与技能**（纯文本，改这里不用碰代码） |
| `ai-agent` | **每台**服务器 | 子 agent：领任务、本机干活、回报结论 |

---

## 1. 文件与目录

```
agent/
├── brain                  ← 入口（很薄，只管参数分发）
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
├── ai-agent               子 agent（**故意保持单文件**）
└── README.md              本文档
```

**为什么 `ai-agent` 不像大脑那样拆成多文件？**
因为子 agent 的「自升级」机制是**用新版本覆盖自己那一个文件**；拆成多文件后，
升级就要处理"哪个文件属于哪个版本、旧文件怎么清理"，很容易升到一半变坏。
子 agent 就一个文件，升级最稳。

> **每个数据文件是干什么的**（`brain.conf`、`brain.db`、`signing.key`…）见 **第 16 节**；
> **当前版本与升级记录**见 **第 18 节**。也可以直接敲下面这几个命令。

- `python3 brain files` —— **文件文档控制台**，逐条列出：位置 / 何时产生 / 干什么用 / 能不能删 / 怎么看
- `python3 brain explain` —— 让 AI 用大白话讲一遍（还能追问，如 `brain explain "删了会怎样"`）
- `python3 brain version` —— **看版本**（大脑 / 程序自带的子 agent / 已发布最新版 / 每台服务器实际版本）

---

## 2. 开工前，先弄懂 3 件事

### ① "脚本文件"和"数据目录"是两回事

| | 是什么 | 能不能换位置 |
| --- | --- | --- |
| **程序文件**（整个 `agent/` 目录） | 代码 + 提示词 | ✅ 放哪都行（第 8 节） |
| **数据目录** | 配置、数据库、密钥、令牌 | ✅ 也能换，用环境变量指定（第 8 节） |

### ② 需要几把"大模型 Key"

| 谁 | 需要吗 | 说明 |
| --- | --- | --- |
| 大脑 | **1 把** | 它自己要用一次大模型：理解你的意图 + 汇总汇报 |
| 每个子 agent | **每台 1 把** | 子 agent 在本机自己直连大模型干活（v1 固定 Key；v2 会改成向大脑要临时 Key） |

> Key 只写在服务器的 600 权限配置文件里，**不要贴在聊天/文档里**。

### ③ 两台机器要能通（**必须域名 + HTTPS**）

- 子 agent → 大脑：`https://你的域名`（**子 agent 主动连出去**，只需"出口"能通 443）
- 大脑**只监听本机**；对外一律经 nginx + 域名 + 有效证书，**不允许** `http://` 或 IP 直连

> 硬规则：`PUBLIC_URL` / `BRAIN_URL` **只能是 `https://域名`**。写成 `http://` 或 IP：
> 子 agent 会**拒绝连接并等待**（`run` 常驻自动重试；`enroll` 直接提示并退出）。

---

## 3. 部署「大脑」（只做 1 次）

### 3.1 上传**整个目录**

> ⚠️ **必须把 `brain` + `brainlib/` + `prompts/` 一起传**，只传 `brain` 会起不来。

**方式 A：Windows 用 scp 传整个目录**（在 `x:\XiaoYingAPI\scripts\` 下执行）

```powershell
scp -r -P {SSH端口} .\agent root@{大脑IP}:/root/agent
```

> ⚠️ 首次部署（`/root/agent` 本来不存在）上面这条没问题；
> 但若该目录**已存在**，`scp -r` 会把 `agent` 塞进去变成 `/root/agent/agent/`。
> 那种情况属于「升级」，请走 **第 9.1 节**（先删远端旧目录，再传）。

**方式 B：宝塔面板** → 文件 → 进入 `/root/` → 上传 `agent` 文件夹（面板支持传目录；不行就先本地压缩成 zip，传上去再解压）。

### 3.2 转换行 + 加执行权限（**从 Windows 上传必做**）

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

> 全部可配置项见 **第 6 节**。

### 3.5 启动并验证

```bash
cd /root/agent
nohup python3 brain serve >/root/.ai-brain/serve.out 2>&1 &
sleep 2
# 仅确认“进程起来了”（走回环自检；正式访问一律走 https 域名）
curl -s http://127.0.0.1:8787/health      # 应回 {"ok": true, "version": "2.1.1", ...}
```

> ⚠️ **光起进程还不算完**：本机 CLI 与子 agent 都只认 `https://域名`。所以**必须**先按第 13 节
> 配好 域名 + nginx + 证书，并在 `brain.conf` 里设置 `PUBLIC_URL=https://你的域名[/ai-brain]`，
> 之后 `python3 brain status` 才会出结果。

**接着配好第 13 节后，用这条验证最终可用性**：

```bash
curl -s https://你的域名/ai-brain/health  # 应回 {"ok": true, ...}
```

### 3.6 （可选）让 `brain` 变成随手可用的命令

```bash
ln -sf /root/agent/brain /usr/local/bin/brain
brain status        # 能出结果就成了
```

---

## 4. 部署「子 agent」（每台被管的服务器做一遍）

> **先确认两样东西在手**（第 3 节部署大脑时得到的）：
> - **注册口令** —— 第 3.3 步 `brain init` 打印的那串，下面第 3 步要输入它
> - 一个能 SSH 登录**这台新服务器**的账号（用 root 最省事）

**下面命令要在 3 个地方执行，每步都标了标签，别搞混：**

| 在哪执行 | 干什么 |
| --- | --- |
| **你的电脑（Windows）** | 把程序 + 公钥传到新服务器 |
| **新服务器（要装子 agent 的那台，SSH 登录后）** | 写配置、注册、启动 |
| **大脑那台（SSH 登录后）** | 批准这台机器接入 |

---

### 第 1 步｜把文件传上去 —— 【在你的电脑（Windows）执行】

每个子 agent 只需要 **两个文件**：`ai-agent`（程序）、`brain.pub`（大脑公钥）。
在 `x:\XiaoYingAPI\scripts\agent\` 目录下，**一行一条**：

```powershell
# 1-1 先在新服务器建好目录（scp 不会自动建目录，缺了会报错）
ssh -p {SSH端口} root@{新服务器IP} "mkdir -p /root/agent"

# 1-2 传子 agent 程序
scp -P {SSH端口} .\ai-agent root@{新服务器IP}:/root/agent/ai-agent

# 1-3 从大脑把公钥拉到本机（临时存成本地的 brain.pub）
scp -P {SSH端口} root@{大脑IP}:/root/.ai-brain/signing.pub .\brain.pub

# 1-4 再把公钥传到新服务器（子 agent 靠它校验升级包，很关键，别漏）
scp -P {SSH端口} .\brain.pub root@{新服务器IP}:/root/agent/brain.pub
```

> 💡 `{SSH端口}` 填各自的 SSH 端口（默认 22）；大脑和新服务器端口可能不同，按实际填。
> 不想用命令，也可以用宝塔面板把这几个文件传上去，效果一样。

### 第 2 步｜写配置 —— 【在新服务器执行】

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
> 大脑不直接对外开端口，务必先按第 13 节把 nginx + 域名 + 证书配好。
>
> `AGENT_ID` 不写也行，默认用 `hostname`；同一台机器要跑多个 agent 才需要显式指定。

### 第 3 步｜注册，然后去大脑批准 —— 【新服务器 + 大脑那台】

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

### 第 4 步｜确认上线（开机自启**已自动装好**）—— 【大脑那台】

> 第 3 步注册成功时，子 agent **已经自动**把自己设成了开机自启（优先 systemd；
> 没有 systemd 就退回 cron `@reboot`）—— **这一步你不用做任何事**，以后服务器重启它会自己起来。
> 万一当时没设上（比如不是 root），补跑一条即可：`cd /root/agent && ./ai-agent install`

**【在大脑那台】** 确认它上线：

```bash
python3 brain status
```

**看到那台机器显示「在线」，并带负载 / 磁盘 / 版本，就成了。**

---

> **一台机器照做一遍**：第 1~4 步走完一台；换下一台时，把 `{新服务器IP}` 换掉、重复即可。
> 建议先跑通一台、确认没问题，再批量部署。

---

## 5. 怎么用（跟大脑说话）

```bash
python3 brain                      # 进入对话
你 ❯ 让所有服务器看一下磁盘和内存，把紧张的告诉我
```

**大脑是流式回复的，并把「思考」和「结果」分开显示**：

````text
你 ❯ 让所有服务器看一下磁盘和内存，把紧张的告诉我
💭 思考中：用户要看所有服务器的磁盘和内存，需要 dispatch 到全部 agent…   ← 暗色：模型思维链
· 思考 我先让三台服务器各自查一下磁盘和内存。                          ← 暗色：动作前的说明
```json
{"action":"dispatch","agents":"all","task":"检查磁盘和内存用量，指出紧张的"}
```
▶ 将在 3 台执行：server-1, server-2, server-3                          ← 黄色：程序动作
▶ 任务：检查磁盘和内存用量，指出紧张的
  [y=执行 / n=跳过 / a=本次全部自动 / e=改一下] y
▶ 已下发 3 条任务，等待各服务器回报…
💭 思考中：三台都回来了…                                               ← 暗色：模型思维链
── 结果 ──────────────────────────                                    ← 高亮：最终结论
三台服务器全部成功，磁盘都很健康：
| 服务器 | 根分区 / | 数据盘 /home | 是否有超 80% | 结论 |
| server-1 | 99G/70G/26% | 98G/93G/1% | 无 | 空间充裕 |
...
──────────────────────────────────
````

| 样式 | 含义 | 怎么关 |
| --- | --- | --- |
| `💭 思考中：`（暗色） | 模型**思维链**（reasoner 类模型才有） | `SHOW_REASONING=0` |
| `· 思考 `（暗色） | 模型说「我打算做什么」——**思考模式** | 关不掉（这是模型的正式内容） |
| `▶ `（黄色） | 程序在执行：下发 / 本机执行 / 等待回报——**动作模式** | — |
| `── 结果 ──`（高亮框） | 最终答复——**结果模式** | — |

**它是执行者，不是顾问。** 你说什么它就直接去做、做完汇报；**不会**反问你"要不要我帮你做"、
**不会**给你讲道理、**不会**替你做决定。

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

## 6. 配置项（`~/.ai-brain/brain.conf`）

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `BRAIN_BIND` | `127.0.0.1` | **只监听本机**；对外一律走 nginx + 域名 + HTTPS。**不要**改 `0.0.0.0`（那是明文对外） |
| `BRAIN_PORT` | `8787` | 监听端口（只给本机 nginx 反代用） |
| `PUBLIC_URL` | 空 | **必填**：大脑对外地址，**必须** `https://域名`（如 `https://brain.example.com`，或 `https://example.com/ai-brain`）。本机 CLI 与子 agent 都只认它；`http://` 或 IP 一律拒绝 |
| `RDV_SEED` | 自动生成 | 会合主密钥；子 agent 失联后靠它算出未来的后台域名。**别外传**（见第 17 节） |
| `RDV_PATTERN` | `xybrain-{h}.icu` | 会合域名模板，`{h}` 会被替换成"每期不同"的哈希 |
| `RDV_INDEX` | `1` | 当前期号；换后台域名时 +1（用 `brain rendezvous set <n>`） |
| `BRAIN_ADMIN_TOKEN` | 自动生成 | 本机 CLI 用，**别动** |
| `ENROLL_SECRET` | 自动生成 | 注册口令，**别动**（部署子 agent 时用） |
| `AI_API_KEY` | — | **必填**：大脑自己用的模型 Key |
| `AI_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `AI_MODEL` | `deepseek-v4-flash` | 模型名 |
| `AI_MAX_STEPS` | `20` | 【手动审核挡】一次提问最多来回几步（超了会停下提示，输入「继续」可接着做） |
| `AI_MAX_STEPS_AUTO` | `200` | 【完全放行挡】的兜底上限，等同"一直做下去"，只为防死循环 |
| `AI_CMD_TIMEOUT` | `120` | `run_local` 单条命令最长秒数 |
| `AI_API_TIMEOUT` | `180` | 单次模型请求最长秒数 |
| `POLL_TIMEOUT` | `25` | 子 agent 领任务的长轮询秒数 |
| `TASK_TIMEOUT` | `300` | 等所有服务器回报的最长秒数 |
| `BRAIN_URLS` | 空 | 下发给子 agent 的"大脑地址清单"（换地址用） |
| `STREAM` | `1` | **1=流式输出；0=等生成完整段再显示** |
| `SHOW_REASONING` | `1` | 1=显示思维链 💭；0=只留「思考/动作/结果」 |
| `STDIO_ENCODING` | `utf-8` | 终端编码。默认 UTF-8；若你的终端/面板是 **GBK**（输中文报"无法识别的字节"），改成 `gbk` |
| `MODE` | `manual` | **挡位**：`manual`=每个动作都问你确认；`auto`=完全放行（不问、不停，直到做完或失败）。交互里输 `/auto` 切换并自动写入 |

改完不用重启也能生效（每次对话现读）；服务端相关的项（端口等）需要重启 `serve`。

---

## 7. 改提示词 / 加技能（不用碰代码）

提示词就是普通文本文件，**改完下次对话就生效，不用重启**。

### 7.1 目录与覆盖规则

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

### 7.2 三个文件各管什么

| 文件 | 作用 |
| --- | --- |
| `system.md` | 系统提示词主体。里面有 `{{ACTIONS}}`（动作清单）、`{{SKILLS}}`（技能）、`{{ENV}}`（当前环境）三个占位符，程序会自动替换 |
| `actions.md` | 可用动作清单（会被塞进 `{{ACTIONS}}` 处）——**加新动作时才需要改这里** |
| `skills/*.md` | 额外技能/背景知识，按文件名排序追加到系统提示词最后 |

### 7.3 加一个"技能"（最常用）

丢一个 `.md` 进 `skills/` 就行，例如：

```bash
cat > ~/.ai-brain/prompts/skills/company.md <<'EOF'
## 我们公司的服务器

- server-1：主站（nginx + uwsgi），**不能随便重启**
- server-2：数据库，改动前一定先备份
- server-3：测试机，随便折腾
EOF
```

下次对话，大脑就"知道"这些背景了（`skills/README.md` 本身不会被加载）。

---

## 8. 能不能放到其它目录？

### 结论：**都能。没有任何路径写死在程序里。**

| | 默认位置 | 怎么改 |
| --- | --- | --- |
| **程序目录**（`brain`+`brainlib`+`prompts`） | 你放哪就是哪，如 `/root/agent` | 直接 `mv` 到别处，用新路径启动即可 |
| **大脑数据目录** | `~/.ai-brain/` | 环境变量 `BRAIN_HOME=/data/aibrain` |
| **子 agent 数据目录** | `~/.ai-agent/` | 环境变量 `AI_AGENT_HOME=/data/aiagent` |

举例：

```bash
export BRAIN_HOME=/data/aibrain           # 建议写进 /etc/profile 或 ~/.bashrc
python3 /opt/agent/brain init
python3 /opt/agent/brain serve
```

### 换路径必须遵守的 5 条规矩

1. **启动时的环境变量要一致**。`BRAIN_HOME`/`AI_AGENT_HOME` 变了就等于换了套配置
   （找不到会要求重新 `init`/`enroll`）。
2. **别放 `/tmp`**（重启清空）。推荐 `/root/...`、`/data/...`、`/opt/...`。
3. **`brain` 和 `brainlib/`、`prompts/` 必须待在同一个目录里**（入口靠同级路径找它们），
   要移动就整目录一起移。
4. **子 agent 部署后别随便移动 `ai-agent` 文件**。自升级会**原地替换它自己**：
   移动后重启一次即可；用软链时替换的是**软链指向的真实文件**。
5. **换用户 = 换默认目录**。默认数据目录是 `~/.ai-brain`、`~/.ai-agent`，`~` 指当前用户家目录；
   建议统一用同一个用户（比如 root）跑。

---

## 9. 升级（全手动，换代码不丢数据）

> **一条铁律**：升级只换「程序目录」，**绝对不要删 `~/.ai-brain` / `~/.ai-agent`**。
> 那两个目录里放着签名密钥、注册口令、各机令牌；删了就等于重装
> （要重新 `brain init` + 所有子 agent 重新注册）。

### 9.1 升级「大脑」

> 大脑重启后，所有子 agent 会**自动重连**，子 agent 什么都不用做。

**先记两件事：**

1. 升级**只换「程序目录」**（默认 `/root/agent`）；`~/.ai-brain`（配置 / 密钥 / 数据库）
   **一项都不要碰**，碰了就等于重装。
2. 下面的命令分在**两个地方**执行，每条都标了标签，别搞混：

| 在哪执行 | 干什么 |
| --- | --- |
| **你的电脑（Windows）** | 删掉服务器上的旧程序目录 → 上传新版 |
| **大脑服务器（SSH 登录后）** | 备份 → 转换行/自检 → 重启 → 验证 |

下面按顺序做，**第 1~5 步，一步都不能跳**。

---

#### 第 1 步｜备份 —— 【在大脑服务器执行】

出问题能一键回滚，先备份旧版：

```bash
cp -r /root/agent /root/agent.bak-$(date +%Y%m%d-%H%M)
```

#### 第 2 步｜上传新版 —— 【在你的电脑（Windows）执行】

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

**看到 `代码自检 OK` 才继续往下。** 这一步报错就**别重启**，先按 9.3 回滚。

#### 第 4 步｜重启 —— 【在大脑服务器执行】

```bash
python3 brain stop
nohup python3 brain serve >/root/.ai-brain/serve.out 2>&1 &
sleep 2
```

#### 第 5 步｜验证 —— 【在大脑服务器执行】

```bash
curl -s https://你的域名/ai-brain/health  # 应回 {"ok": true, "version": "2.1.1", ...}
python3 brain version                     # 应显示「大脑当前版本: 2.1.1」
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

### 9.2 升级「子 agent」

**方式 A：让它们自己升级（推荐，机器多时用）**

```bash
# 在大脑上：把改好的 ai-agent 传成新文件，然后发一版（自动签名）
python3 brain release /root/agent/ai-agent.new --version 1.0.1 --notes "修了 xxx"
```

- 子 agent **最多 10 分钟**内自动升级；也可在任意一台 `./ai-agent update` 立刻升。
- 升级由**新版本自己完成**：下载 → sha256 校验 → **RSA 签名校验** → 语法自检 → 试运行 →
  **原子替换原文件** → 删除旧版本目录；任何一步不过就放弃、保留旧版。
- 版本号只要和当前**不同**就会触发升级（想"降级"就发一个低版本号）。
- ⚠️ 前提：子 agent 上有正确的 `~/.ai-agent/brain.pub`（公钥不对会被拒绝，这是特性）。

**方式 B：手工替换（只有一两台时更直观）**

```bash
cp /root/agent/ai-agent /root/agent/ai-agent.bak-$(date +%Y%m%d)
# 上传新版覆盖 /root/agent/ai-agent，然后：
cd /root/agent && sed -i 's/\r$//' ai-agent && chmod +x ai-agent
bash -n ai-agent && echo '语法 OK'
# 重启（装了开机自启服务就用 systemctl，否则手动起）：
systemctl restart ai-agent 2>/dev/null || { pkill -9 -f 'ai-agent run'; nohup ./ai-agent run >>~/.ai-agent/run.out 2>&1 & }
./ai-agent status
```

> 令牌在 `~/.ai-agent/agent.conf` 里，**不用重新注册**。

### 9.3 回滚

| 对象 | 操作 |
| --- | --- |
| 大脑 | `rm -rf /root/agent && mv /root/agent.bak-xxxx /root/agent`，再按 9.1 的**第 4 步**重启 |
| 子 agent | `cp /root/agent/ai-agent.bak-xxxx /root/agent/ai-agent`，再重启（`systemctl restart ai-agent`，或 9.2 B 里的重启命令） |

---

## 10. 日常运维命令

```bash
# —— 大脑 ——
python3 brain serve        # 前台跑（调试看日志用）
python3 brain status       # 服务 + 各服务器概况（含当前挡位）
python3 brain version      # 看版本：大脑 / 程序自带agent / 已发布最新版 / 各机实际版本
python3 brain files        # 文件文档控制台（每个文件干什么用、能不能删）
python3 brain explain "问题"   # 让 AI 用大白话解读这些文件
python3 brain pending      # 待批准的新机器
python3 brain approve <id> # 批准接入
python3 brain deny <id>    # 拒绝接入
python3 brain stop         # 停止后台服务：先按 brain.pid 停，再兜底检查端口(8787) 是否还被旧 brain 占着并一并终止
python3 brain pubkey       # 打印公钥
python3 brain rendezvous   # 会合：看/换后台域名（换服务器 / 换域名时用，见第 17 节）

# —— 子 agent（在子 agent 那台）——
./ai-agent install         # 手动补设开机自启（注册时已自动做，一般不用）
./ai-agent uninstall       # 卸载该服务（数据保留）
./ai-agent run             # 前台运行（systemd 会调它；也可手动调时用）
./ai-agent once            # 手动领一次任务（调试）
./ai-agent version         # 看版本：本机版本 + 大脑上可升级到的最新版
./ai-agent update          # 立刻检查升级
./ai-agent status          # 看配置/大脑连通性/版本
systemctl status ai-agent  # 看服务状态（装过 install 之后）
journalctl -u ai-agent -f  # 看服务日志

# —— 看日志 ——
tail -f ~/.ai-brain/brain.log     # 大脑
tail -f ~/.ai-brain/serve.out     # 大脑启动输出
tail -f ~/.ai-agent/agent.log     # 子 agent
```

**停止子 agent**：装了开机自启就用 `systemctl stop ai-agent`；否则 `pkill -f 'ai-agent run'`
（它可能正卡在 25 秒长轮询里，最多约 25 秒才退出；急停用 `pkill -9 -f 'ai-agent run'`）。

---

## 11. 卸载 / 彻底清理

```bash
# 1) 先停
python3 brain stop                              # 停大脑
./ai-agent uninstall                            # 取消开机自启并停掉子 agent（每台都要；没装则忽略）
pkill -9 -f 'ai-agent run'                      # 兜底再杀一次

# 2) 再删（按你实际路径删）
rm -rf ~/.ai-brain        # 大脑数据：配置、数据库、签名密钥、注册口令
rm -rf ~/.ai-agent        # 子 agent 数据：配置、令牌、公钥、日志
rm -rf ~/agent            # 程序目录本身
```

> ⚠️ **只删 `~/.ai-brain` 就等于"恢复出厂"**：里面存着签名密钥和注册口令，
> 删了以后 `brain init` 会生成**全新的一套**，所有子 agent 都得**重新注册**。
>
> 👉 只想"换一份新代码"，就**别删数据目录**，按第 9 节升级即可。

清完检查：

```bash
ls -d ~/.ai-brain ~/.ai-agent ~/agent 2>/dev/null
ss -ltn | grep 8787
ps -eo args | grep -E 'brain serve|ai-agent run' | grep -v grep
```

---

## 12. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 一堆 `$'\r'` 报错 / `bad interpreter` | Windows 换行：`find . -type f -exec sed -i 's/\r$//' {} +` |
| 输入时崩 `UnicodeDecodeError: ... invalid continuation byte` | **1.1.1 已修**：现在会容错、绝不崩。升级后若仍提示"无法识别的字节"，说明终端不是 UTF-8，在 `brain.conf` 加 `STDIO_ENCODING=gbk` |
| 它老是反问我"要不要帮你做"、或不肯做 / 给我讲道理 | **1.1.2 已修**：提示词已改成"执行者，不是顾问/审查员"，你的服务器上的事直接照做。若还想更强硬，改 `prompts/system.md`（见第 7 节） |
| 它不肯删/不肯重启，说"命令被安全策略拒绝" | **1.1.2 起子 agent 不再做本地拦截**（旧版的危险命令黑名单已移除，升级 `ai-agent` 即可，见 9.2） |
| 每次动手都要我按 y，烦 | 输 `/auto` 切到「完全放行」挡（或在确认提示里按 `a`，或 `brain.conf` 写 `MODE=auto`），以后就不问了 |
| 提示"已达到步数上限"，活儿只干了一半 | **不是失败**：手动挡默认 20 步就停下。直接输入「继续」接着做；想一次做完就调大 `AI_MAX_STEPS`，或切 `MODE=auto`（那一挡不看这个上限） |
| 输出里出现 `�`（黑色问号） | 同上：终端编码和 `STDIO_ENCODING` 不一致，按上面调一下即可 |
| `ModuleNotFoundError: No module named 'brainlib'` | 只传了 `brain`，没传 `brainlib/`；或把 `brain` 单独移走了（要和 `brainlib/` 同级） |
| `找不到提示词文件 system.md` | 没传 `prompts/` 目录（服务器运行不受影响，只是没法对话） |
| `/health` 没响应 / 起不来 | 看 `~/.ai-brain/serve.out` 的报错；多半是文件没传全或换行没转 |
| `尚未初始化，请先执行：brain init` | 先 `python3 brain init`；或 `BRAIN_HOME` 和初始化时不一致 |
| `未配置模型 Key` | 编辑 `~/.ai-brain/brain.conf` 填 `AI_API_KEY` |
| 子 agent 报 `连不上大脑` / `大脑地址不合格` | 地址**必须**是 `https://域名`（`http://` 或 IP 会被拒绝）；再查域名解析、证书是否有效、网络是否可达 |
| 大脑命令报 `还没配置 PUBLIC_URL` | 在 `brain.conf` 里设 `PUBLIC_URL=https://你的域名[/ai-brain]`（必须 https + 域名），并确保 nginx + 证书已就绪 |
| 注册后一直等批准 | 到大脑上 `python3 brain pending` → `python3 brain approve <id>` |
| 子 agent 显示`离线` | 心跳 30s 一次、离线判定 180s；看进程还在不在、网络通不通 |
| `时间戳超窗` | 两台机器时钟差太多：装 `ntp`/`chrony` 对时 |
| `nonce 重复（疑似重放）` | 请求被重复发送；重试即可（正常不会有） |
| 没有颜色 / 没有 `── 结果 ──` 横线 | 当前不是"真终端"（输出被重定向、或某些面板终端）。**文字内容不受影响** |
| 没有 `💭 思考中` 那段 | 模型不支持思维链，或设了 `SHOW_REASONING=0` |
| 回复卡很久才一次性出来 | 你的模型/中转站不支持流式，或设了 `STREAM=0`；想逐字显示就设 `STREAM=1` |
| 觉得 `💭` 太啰嗦 | `SHOW_REASONING=0`，只留「思考 / 动作 / 结果」 |
| 升级报 `摘要不符` / `签名校验失败` | 包被改动，或子 agent 的 `brain.pub` 不是当前大脑的公钥 |
| `brain stop` 说"没找到 pid 文件" | 1.1.6 起 `brain stop` 会兜底检查端口：只要 `8787` 还被某个 `brain serve` 占着就会自动停掉。若仍提示，说明确实没有进程在跑；用 `ps -eo pid,args \| grep 'brain serve'` 核对 |
| 停止子 agent 没反应 | 它在长轮询里，最多 25 秒；急停 `pkill -9 -f 'ai-agent run'` |
| 服务器重启后子 agent 不见了 | 正常注册时**会自动设好**开机自启；若当时没设成，手动补 `./ai-agent install`（别只用 `nohup`） |

---

## 13. 域名 + HTTPS（**必做**，不是可选）

> v2 起：大脑**只监听本机**，对外**只能**通过 `https://域名` 访问；子 agent 只认 `https + 域名`，
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

> 子 agent 的 `BRAIN_URL` 填**同一个地址**（`https://brain.example.com/ai-brain`）。
> 内部端点有 `X-Admin-Token` 保护；本机 CLI 也走这个 https 地址（不再用 127.0.0.1 的 HTTP）。

---

## 14. 安全说明

| 环节 | 做法 |
| --- | --- |
| 注册 | 挑战-应答 + **大脑侧人工批准**；注册口令**不写进子 agent 脚本**，泄漏也进不来 |
| 通信 | 每台一个独立令牌；每个请求带 时间戳 + 随机数 + HMAC 签名，防重放/防伪造 |
| 执行 | 默认走**手动审核挡**（每个动作问你一次）；切到 `MODE=auto`（完全放行）后就不再询问、也不看步数上限。**但"接新机器"始终要你亲自批准**，完全放行挡也不例外 |
| 权限边界 | **子 agent 不做本地拦截**：大脑下发的任务它照做（这样才不会"你要删它却不删"）。所以**安全闸门在你手里**——不放心的操作就别开 `/auto` |
| 升级 | 大脑私钥签名 → 子 agent 公钥验签 + 摘要校验 + 自检 + 原子替换，失败保留旧版 |
| 密钥 | 配置都是 `600`；不放进代码、不贴聊天记录 |
| 审计 | 注册/批准/下发/执行/升级 全记在数据库 `audit` 表和 `~/.ai-brain/brain.log` |

> v1 的边界：子 agent 各持一把固定大模型 Key。v2 会改成"大脑通过中转站接口发**短期 Key**、
> 子 agent 直连中转站"（架构上已预留可插拔的「凭证驱动」位置）。

---

## 15. 已实现 / 后续计划

**已实现**
- 大脑：流式回复、**思考 / 动作 / 结果三态区分**、任务下发与汇总、心跳、审计、签名升级
- 子 agent：注册（挑战-应答 + 人工批准）、心跳、领任务、本机 AI 执行、**签名自升级**
- **通信强制「域名 + HTTPS」**（`http://` 或 IP 一律拒绝），大脑只监听本机（见第 13 节）
- **会合机制**：换服务器 / 换域名后，子 agent 靠"种子 + 期号"自动算出新域名找回（见第 17 节）
- **部署一次即可**：子 agent 注册成功时**自动设好开机自启**（systemd，或退回 cron），重启服务器自动运行
- 可配置：`STREAM`（流式开关）、`SHOW_REASONING`（思维链开关）等，见第 6 节
- 提示词与技能**全部外置**在 `prompts/`，且支持在 `~/.ai-brain/prompts/` 覆盖
- 底层拆分：入口只做分发，实现按职责分为 `brainlib/` 下多个模块

**后续计划**
- v2 凭证：走中转站发短期 Key（顺带可切 GPT / Claude / 豆包 / 千问）
- 更多入口：网页 / 飞书 / QQ / 微信 / 手机（现在只有命令行）
- 主动巡检告警（现在只有"心跳在线状态"，需要你主动问）

---

## 16. 数据文件总览（哪个文件是干什么的）

**最省事的看法**（不用记下面的表）：

```bash
python3 brain files                 # 文档控制台：逐条列出 位置/何时产生/干什么用/能不能删/怎么看
python3 brain explain               # 让 AI 用大白话讲一遍
python3 brain explain "signing.key 删了会怎样？"   # 还能追问
```

### 16.1 大脑数据目录 `~/.ai-brain/`

| 文件 | 何时产生 | 干什么用 | 能删吗 |
| --- | --- | --- | --- |
| `brain.conf` | `brain init` 生成；改挡位/手动编辑时更新 | 全部配置：端口、模型与 Key、挡位 `MODE`、步数上限、注册口令、管理令牌。**权限 600** | ❌ 不能删（等于恢复出厂：要重新 `init`，所有子 agent 重新注册） |
| `brain.db` | `init` 建表；之后每次注册/心跳/下发/执行/升级都写入 | **主数据库**。7 张表：agents 已接入的服务器、enrollments 注册申请、tasks 任务与结果、releases 升级包记录、audit 审计流水、nonces 防重放、meta 管理令牌 | ❌ 不能删（服务器要重注册、任务与审计全没） |
| `brain.db-wal` | 数据库开着时自动出现 | SQLite 的预写日志（新数据先落这里再合并），断电不易坏 | ⚠️ 别单独删（会丢最近写入）。要处理请先停服务 |
| `brain.db-shm` | 数据库开着时自动出现 | WAL 用的共享内存索引，纯运行态 | ✅ 停服后可删，会自动重建 |
| `brain.log` | 服务启动 + 运行中出错时追加 | 运行日志：启停、接口异常、未预期错误（含堆栈）。**排查问题先看它** | ✅ 可删（会重建），排查前建议留着 |
| `brain.pid` | `brain serve` 启动写、正常退出删 | 服务进程号，`brain stop` 靠它精确停**这一个**服务 | ✅ 可删（删了 stop 找不到 pid，但 1.1.6 起会兜底按端口把旧 brain 停掉） |
| `serve.out` | 后台启动时的输出重定向（程序自动 `nohup` 时也会写） | 服务"前台输出"存档：启动横幅、端口被占用等。**起不来先看它** | ✅ 可删 |
| `signing.key` | `brain init` 生成（RSA 2048，600） | **签名私钥**，给子 agent 升级包签名。是"发布权"的根 | ❌ **绝对不能删、不能外传**（删了要重新 init + 重发公钥给所有子 agent） |
| `signing.pub` | `init` 由私钥导出 | **公钥**，拷到每台子 agent（`~/.ai-agent/brain.pub`）用于验签 | ✅ 可删（`brain pubkey` 能再导出） |
| `releases/` | `init` 建目录；每次 `brain release` 写一个包 | 已签名的**升级包**（`ai-agent-版本`）+ 库里的版本记录。子 agent 来取的就是它 | ✅ 可删旧版本（只影响"回滚到那一版"）；别删最新的 |
| `prompts/` | **你自己建**（可选，程序不会自动建） | 你的自定义提示词（`system.md`/`actions.md`/`skills/*.md`），**同名即覆盖程序自带**，升级不会冲掉 | ✅ 可删（退回用程序自带的） |

### 16.2 程序目录（部署时上传的，如 `/root/agent/`）

| 文件 | 干什么用 | 能删吗 |
| --- | --- | --- |
| `brain` | 入口脚本：解析命令并分发到 `brainlib/` | 删了用不了；重传即可，数据不丢 |
| `brainlib/` | 全部实现（配置/数据库/签名/模型/渲染/提示词/接口/管理/对话…） | 删了起不来；重传即可 |
| `prompts/` | 随程序发布的**默认**提示词与技能 | 删了没法对话（服务端仍能跑） |
| `ai-agent` | 子 agent 脚本（拷到每台被管服务器） | 那台会掉线；重传即可，**不用重新注册** |
| `brainlib/__pycache__/` | Python 自动生成的字节码缓存 | ✅ 可删，会自动重建 |
| `*.bak-年月日-时分` | **你按升级步骤手做的备份** | ✅ 确认新版稳定后可删；想回滚就留 |

### 16.3 子 agent 数据目录 `~/.ai-agent/`（每台被管服务器上）

| 文件 | 何时产生 | 干什么用 | 能删吗 |
| --- | --- | --- | --- |
| `agent.conf` | 部署时手写基本项；`enroll` 成功后写入本机令牌与会合信息 | 大脑地址 `BRAIN_URL`、本机 `agent_id`、**本机专属令牌**、这台机器调模型用的 Key、**会合信息 `RDV_*`**（第 17 节）。**权限 600** | ❌ 不要删（要重新 enroll + 大脑侧批准） |
| `brain.pub` | 部署时从大脑拷来 | 大脑公钥副本，用于校验下载到的升级包 | ✅ 可删，但删了升级会**跳过签名校验**（不安全） |
| `brain_cache` | 第一次成功连上大脑时写入 | 上次连通的**大脑地址**（换地址能自愈） | ✅ 可删（会重新探测） |
| `agent.pid` | `ai-agent run` 启动写、正常退出删 | 子 agent 进程号 | ✅ 可删 |
| `agent.log` | 运行中持续追加 | **干活记录**：领到什么任务、每步在本机跑了什么命令、何时回报 | ✅ 可删，排查前建议留着 |
| `run.out` | 手动 / `cron` 方式启动时产生（用 systemd 时输出在 journal） | 子 agent 前台输出存档 | ✅ 可删 |
| `versions/` | 自升级时临时创建 | 升级包下载到这，校验通过后由**新版本自己**替换原文件，然后整个目录被删 | ✅ 正常会自己消失；残留说明升级失败过，可删 |

> 另外：`./ai-agent install` 会在 `/etc/systemd/system/ai-agent.service` 写一个开机自启的服务定义
> （不在数据目录里；用 `./ai-agent uninstall` 卸载）。

> **一句话记住**：`~/.ai-brain` 和 `~/.ai-agent` 里放的是**身份和记忆**（密钥、令牌、数据库），
> 升级程序**只换程序目录**，这两个目录一个字都别动。

---

## 17. 会合机制（换服务器 / 换域名也能被找回）

> 场景：你现在的大脑服务器或域名被封了。你买了新服务器、换了新域名 —— 子 agent **不用你挨个改配置**，
> 它会**自己算出**新域名并找回来。

**原理**：大脑和每个子 agent 共享一段密钥 `RDV_SEED`，再加一个"期号" `n`，两边都能算出**同一个**域名：

```
域名(n) = RDV_PATTERN 里的 {h} 换成 hmac_sha256(RDV_SEED, "rdv:" + n) 的前 10 位
例：RDV_PATTERN=xybrain-{h}.icu，第 1 期 → xybrain-3f9a2b7c1d.icu
```

### 17.1 大脑侧：换后台域名时怎么做

```bash
python3 brain rendezvous               # 看当前：期号 / 当前域名 / brain_id
python3 brain rendezvous next --check  # 看“下一期”域名，并顺带查它能不能注册
```

流程：`rendezvous next` 给出下一期域名 → 你去 **.icu** 注册商把它买下 → DNS 指到新服务器 → 配好证书 →
`python3 brain rendezvous set <新期号>` → 完事。

### 17.2 子 agent 侧：连不上时自动找回

子 agent 注册成功后，会从大脑拿到 `RDV_SEED / RDV_PATTERN / RDV_INDEX` 并写进 `~/.ai-agent/agent.conf`。
之后一旦连不上现有大脑，它会：

1. 从当前期号往后算几个候选域名（默认 5 个，`RDV_WINDOW`）；
2. 对每个候选：
   - **能连上、且 `/health` 的 `brain_id` 对得上** → 就是我们的大脑 → 认领、写回配置 ✅
   - **已被注册但不是我们**（被别人抢注）→ 跳过，期号 +1
   - **还没被注册** → 说明你还没买 → **边等边继续往后探**
3. 每 30 秒重试一轮，直到找回。

> "是否被注册"用 **RDAP + DNS(NS) 双重判定**（`rdap.org` + Cloudflare DoH），尽量不误判。

### 17.3 安全提示

- `RDV_SEED` 是**主密钥**：泄漏了别人就能推算你的未来域名、甚至提前抢注。
  要换就执行 `python3 brain rendezvous rotate`（子 agent 下次心跳会自动更新）。
- 这套机制只在"子 agent **已经注册过、手里有种子**"时生效。**全新子 agent 仍需要你给它初始地址**
  （部署时填 `BRAIN_URL`）—— 这是绕不过去的第一次引导。

---

## 18. 版本记录（**每次升级都要更新这里**）

**当前版本：大脑 `2.1.1` ／ 子 agent `2.3.0`**

随时自己看，不用记：

```bash
python3 brain version     # 大脑版本 / 程序自带 agent 版本 / 大脑上已发布的最新版 / 每台服务器实际版本
./ai-agent version        # 在子 agent 那台：本机版本 + 大脑上可升级到的最新版
```

`brain version` 会长这样（一眼看出谁落后）：

```
大脑当前版本        : 2.1.1
程序里自带的 ai-agent   : 2.3.0（程序目录里那个 ai-agent 文件自带的版本）
大脑上已发布的最新版   : 2.3.0（2026-10-12 发布：注册时自动设开机自启）

服务器              它上报的版本      最后心跳        状态
server-1            2.3.0            12s 前         已是最新
server-2            1.2.0            35s 前         与最新发布不一致
（“不一致”＝它与大脑上最新发布版 2.3.0 不同；在那一台执行 ai-agent update 即可升级）
```

### 升级历史

| 日期 | 大脑 | 子 agent | 主要变化 |
| --- | --- | --- | --- |
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

1. **升版本号**：改完代码，把 `brainlib/__init__.py` 里的 `VERSION`（大脑）和 `ai-agent` 文件里的
   `VERSION`（子 agent）各自加一位——**只改了哪边就只升哪边**。规则：
   - 修 bug → 末位 +1（`2.3.0` → `2.3.1`）
   - 加功能 → 中位 +1（`2.3.0` → `2.4.0`）
   - 不兼容改动 → 大头 +1（`2.3.0` → `3.0.0`）
2. **记一笔**：在上面那张「升级历史」表的**最上面加一行**：日期 / 两边新版本号 / 一句话说明改了什么。
3. **子 agent 有变化时**：`python3 brain release <ai-agent文件> --version <新版本> --notes "说明"`，
   让它自己升级（也可以在 README 第 9.2 节走手工替换）。
4. **升级完大脑**：按第 9.1 节的步骤重启，然后 `python3 brain version` 确认两边版本一致。
5. 改完顺手自检（避免又出现"未定义名字"这类低级错误）：
   ```bash
   python3 -c "import py_compile,pathlib; [py_compile.compile(str(p),doraise=True) for p in pathlib.Path('brainlib').glob('*.py')]; print('编译 OK')"
   bash -n ai-agent && echo 'ai-agent 语法 OK'
   ```
