"""消息推送 push · QQBot 一键部署（NapCat）

把「拿到 NapCat → 配好 HTTP 服务端与事件上报 → 启动 → 回填配置」做成一条**可实时观看**的流水线，
供超管在控制台「QQBot」页一键执行（不需要懂 NapCat）：

  · **能自动的都自动**：探测环境、下载（国内镜像优先、失败回退官方）、解压、生成 token、
    写 NapCat 配置、拉起进程、等待端口就绪、把地址与 token 回填到 `PushSetting`
  · **不能自动的才引导**：QQ 扫码登录必须人工；本机没装 QQ 时改用 OneKey 包
    （其官方安装器 `NapCatInstaller.exe` 会自行下载 QQ 与 NapCat）；Linux 上没有 docker
    时给出官方一键脚本命令

日志：内存缓冲（供 SSE 实时推送）+ 节流落库（`PushSetting.deploy_logs`，切页再回来还能看）。

进程与「是否在跑」的判定沿用红果签名服务（`SpiderServices/dramas/hongguo/sign_service.py`）
同一套做法：探测端口、锁 + 子进程句柄、日志写文件。

平台差异（实测口径，2026-10）：
  · Windows：`NapCat.Shell.zip`（28MB，需本机已装 QQ）/ `NapCat.Shell.Windows.OneKey.zip`
    （0.9MB，含 `NapCatInstaller.exe` + `bootmain/NapCatWinBootMain.exe`）
  · Linux：优先 docker（官方镜像），否则引导官方一键脚本（安装需要 root，无法由 Web 进程代替执行）
"""
import json
import logging
import os
import platform
import queue
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger('api.push')

# ==================== 状态与常量 ====================
STATE_IDLE = 'idle'
STATE_RUNNING = 'running'
STATE_SUCCESS = 'success'
STATE_FAILED = 'failed'

# 与实测一致的发布版本；升级时改这里（下载地址随之变化）
RELEASE_TAG = 'v4.18.30'
ASSET_SHELL = 'NapCat.Shell.zip'                      # 需要本机已装 QQ
ASSET_ONEKEY = 'NapCat.Shell.Windows.OneKey.zip'      # 内置安装器，自动下载 QQ + NapCat
GITHUB_DL = f'https://github.com/NapNeko/NapCatQQ/releases/download/{RELEASE_TAG}/'
# 下载源：镜像优先，最后一个是直连官方（空前缀）
DOWNLOAD_SOURCES = ('https://ghfast.top/', 'https://ghproxy.net/', 'https://gh-proxy.com/', '')

# 缺省端口（与 NapCat 默认一致；实际以「QQBot」页里已填的地址为准）
DEFAULT_HTTP_PORT = 3000
DEFAULT_WEBUI_PORT = 6099
# 等 HTTP 服务端就绪的最长时间（秒）
READY_TIMEOUT = 120
# 官方安装器（OneKey）下载 QQ 并解压的容忍时长（秒）——实测要下 300MB，给足时间
INSTALL_TIMEOUT = 1800
# 长耗时环节的「心跳」间隔（秒）：这段时间没输出也会推一行，避免页面看起来卡死
HEARTBEAT = 10

# Linux：优先使用官方 docker 镜像（如官方更名，改这里）
DOCKER_IMAGE = 'mlikiowa/napcat-docker:latest'
# Linux 下的容器名（复用判定、docker start/stop 都认这一个名字）
DOCKER_CONTAINER = 'napcat'
# Linux 无 docker 时的官方一键安装脚本
LINUX_INSTALL_CMD = ('curl -o napcat.sh https://nclatest.znin.net/NapNeko/'
                     'NapCat-Installer/main/script/install.sh && sudo bash napcat.sh')

# 内存日志保留条数（页面只需要最近这些）
LOG_LIMIT = 800

# ==================== 内存状态（单进程内共享） ====================
_lock = threading.Lock()
_thread = None
_seq = 0
_lines = []
_state = STATE_IDLE
_flush_at = 0.0
_process = None
_log_handle = None


# ==================== 基础工具 ====================

def napcat_dir() -> Path:
    """NapCat 安装目录：设置里配了就用它，否则用项目下的 napcat/"""
    from API.models import PushSetting

    configured = (PushSetting.get_solo().napcat_dir or '').strip()
    return Path(configured) if configured else Path(settings.BASE_DIR) / 'napcat'


def _default_log_dir() -> Path:
    return Path(getattr(settings, 'LOG_DIR', str(Path(settings.BASE_DIR) / 'logs')))


def _port_from_base(base: str, default: int = DEFAULT_HTTP_PORT) -> int:
    """从已填的 HTTP 地址里取端口（回填时保持一致，避免又多一套配置）"""
    try:
        return urllib.parse.urlparse(base).port or default
    except ValueError:
        return default


def is_running(timeout=0.5) -> bool:
    """QQBot HTTP 服务端口是否已在监听"""
    from API.models import PushSetting

    port = _port_from_base((PushSetting.get_solo().qqbot_api_base or '').strip())
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout):
            return True
    except OSError:
        return False


def current_state() -> str:
    return _state


def _qq_installed() -> bool:
    """本机是否装了 QQ（Windows: 查注册表与常见安装路径；Linux 交给 docker 分支，不查）"""
    if os.name != 'nt':
        return True
    candidates = [
        Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tencent' / 'QQNT',
        Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Tencent' / 'QQNT',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Tencent' / 'QQNT',
    ]
    if any(p.is_dir() for p in candidates):
        return True
    try:
        import winreg

        for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Tencent\QQNT'),
                          (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Tencent\QQNT')):
            try:
                with winreg.OpenKey(hive, key):
                    return True
            except OSError:
                continue
    except ImportError:                       # 非 Windows 环境
        pass
    return False


def _docker_available() -> bool:
    """Linux：docker 是否可用（装了且守护进程在跑）"""
    if not shutil.which('docker'):
        return False
    try:
        result = subprocess.run(['docker', 'info'], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _docker_container_state(name=DOCKER_CONTAINER) -> str:
    """已存在同名容器时的状态（`running` / `exited` / `created` …）；不存在返回空串

    注意 `--filter name=` 是**包含**匹配，必须用 `^…$` 锚定，否则 `napcat-old`
    这类名字也会被误判成我们的容器。
    """
    try:
        result = subprocess.run(
            ['docker', 'ps', '-a', '--filter', f'name=^{name}$', '--format', '{{.State}}'],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ''
    if result.returncode != 0:
        return ''
    lines = [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]
    return lines[0] if lines else ''


def _docker_container_token(name=DOCKER_CONTAINER) -> str:
    """读现有容器创建时注入的 `NAPCAT_TOKEN`（没有则返回空串）

    为什么要读：复用已有容器时**不能**把本次新生成的随机 token 回填到「QQBot」页 ——
    那个 token 属于一个根本没建起来的容器，回填会把原本能用的配置改坏。
    """
    try:
        result = subprocess.run(
            ['docker', 'inspect', name, '--format', '{{range .Config.Env}}{{println .}}{{end}}'],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ''
    if result.returncode != 0:
        return ''
    for line in (result.stdout or '').splitlines():
        if line.strip().startswith('NAPCAT_TOKEN='):
            return line.strip().split('=', 1)[1].strip()
    return ''


def find_napcat_exe() -> Path | None:
    """在安装目录里找**正式**的 NapCat 启动器

    注意排除 OneKey 包自带的 `bootmain/NapCatWinBootMain.exe` —— 那是配合已装 QQ 的引导器，
    本机没装 QQ 时跑它会失败；OneKey 必须先跑官方安装器生成 `NapCat.*.Shell/` 目录，
    那里面才是可用的启动器（实测：OneKey 与 Shell 包的目录结构不同）。
    """
    root = napcat_dir()
    if not root.is_dir():
        return None
    for hit in root.rglob('NapCatWinBootMain.exe'):
        if hit.parent.name.lower() != 'bootmain':
            return hit
    return None


def find_installer() -> Path | None:
    """OneKey 包里的官方安装器 NapCatInstaller.exe"""
    root = napcat_dir()
    return next(root.rglob('NapCatInstaller.exe'), None) if root.is_dir() else None


def napcat_config_dir() -> Path:
    """NapCat **真正读写**的配置目录

    实测（OneKey v4.18.30 装出来的目录）：
        NapCat.<版本>.Shell/versions/<ver>/resources/app/napcat/{napcat.mjs, config/}
    NapCat 只认这里，**不是**安装目录下的 config/ —— 所以配置必须写这个位置。
    找不到 napcat.mjs 时回退到 `<安装目录>/config`（Shell 包那种扁平布局）。
    """
    root = napcat_dir()
    if root.is_dir():
        hit = next(root.rglob('napcat.mjs'), None)
        if hit:
            return hit.parent / 'config'
    return root / 'config'


def webui_url() -> str:
    """NapCat WebUI 地址（带 token）：扫码登录 QQ 就在这里"""
    from API.models import PushSetting

    setting = PushSetting.get_solo()
    token = (setting.qqbot_token or '').strip()
    url = f'http://127.0.0.1:{DEFAULT_WEBUI_PORT}/webui/'
    return f'{url}?token={token}' if token else url


def probe() -> dict:
    """当前环境 / 安装 / 连通状态（页面「启动前配置」与状态徽标用）"""
    from API.models import PushSetting

    setting = PushSetting.get_solo()
    base = (setting.qqbot_api_base or '').strip()
    docker = None
    if os.name != 'nt':
        docker = _docker_available()
    return {
        'platform': 'windows' if os.name == 'nt' else 'linux',
        'os_name': f'{platform.system()} {platform.release()}',
        'dir': str(napcat_dir()),
        'installed': find_napcat_exe() is not None,
        'installer_pending': find_installer() is not None and find_napcat_exe() is None,
        'qq_installed': _qq_installed() if os.name == 'nt' else None,
        'docker': docker,
        'http_port': _port_from_base(base),
        'base_configured': bool(base),
        'token_configured': bool((setting.qqbot_token or '').strip()),
        'port_listening': is_running(),
        'webui_url': webui_url(),
        'state': _state,
        'napcat_qq': (setting.napcat_qq or '').strip(),
    }


# ==================== 日志（内存 + 节流落库） ====================

def _emit(level, text):
    """写一行日志：进内存缓冲（SSE 实时推），并按节流落库"""
    global _seq, _flush_at
    with _lock:
        _seq += 1
        _lines.append({'seq': _seq, 'level': level, 'text': str(text),
                       'ts': time.strftime('%H:%M:%S')})
        del _lines[:-LOG_LIMIT]
        should_flush = (time.time() - _flush_at) > 1.0
        if should_flush:
            _flush_at = time.time()
    if should_flush:
        _persist()


def clear_logs():
    """清空部署日志（内存 + 落库）

    正在部署时拒绝 —— 否则会把进行中的日志抹掉、看起来像卡住。
    :return: (ok, 说明)
    """
    global _lines, _seq
    with _lock:
        if _state == STATE_RUNNING:
            return False, '部署进行中，暂不能清屏'
        _lines = []
        _seq = 0
    _persist()
    return True, '已清屏'


def _set_state(state):
    global _state
    _state = state
    _persist()


def _persist():
    """把内存日志与状态写进 PushSetting（供切页回看）"""
    from API.models import PushSetting

    try:
        setting = PushSetting.get_solo()
        setting.deploy_state = _state
        setting.deploy_time = timezone_now()
        setting.deploy_logs = json.dumps(_lines, ensure_ascii=False)
        setting.save(update_fields=['deploy_state', 'deploy_time', 'deploy_logs', 'updated_time'])
    except Exception:                          # noqa: BLE001 日志落库失败不影响流程
        logger.exception('QQBot 部署日志写入失败')


def timezone_now():
    from django.utils import timezone

    return timezone.now()


def stored_lines():
    """上次的日志（页面首次渲染时用它填充，之后由 SSE 续推）"""
    from API.models import PushSetting

    try:
        data = json.loads(PushSetting.get_solo().deploy_logs or '[]')
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def next_frames(since=0):
    """取序号 > since 的日志行与当前状态（SSE 用）"""
    with _lock:
        frames = [line for line in _lines if line['seq'] > since]
        return frames, _state


# ==================== 流水线 ====================

def start_pipeline():
    """启动一键部署流水线；返回 (ok, 说明)"""
    global _thread, _state, _lines, _seq
    with _lock:
        if _state == STATE_RUNNING:
            return False, '已有一次部署正在进行中'
        _lines = []
        _seq = 0
        _state = STATE_RUNNING
    _persist()
    _thread = threading.Thread(target=_run_pipeline, name='qqbot-deploy', daemon=True)
    _thread.start()
    return True, '已开始'


def _run_pipeline():
    from django.db import close_old_connections

    close_old_connections()
    try:
        _emit('info', f'开始 QQBot（NapCat）一键部署 · 平台 {platform.system()} {platform.release()}')
        if os.name == 'nt':
            _pipeline_windows()
        else:
            _pipeline_linux()
        _set_state(STATE_SUCCESS)
    except Exception as exc:                   # noqa: BLE001 线程入口兜底，失败要如实显示
        logger.exception('QQBot 一键部署失败')
        _emit('error', f'部署失败：{exc}')
        _set_state(STATE_FAILED)
    finally:
        _persist()
        close_old_connections()                # 先落库再关连接，避免线程残留连接锁住 SQLite


def _pipeline_windows():
    """Windows：装/找 NapCat → 写配置 → 启动 → 等就绪 → 回填设置"""
    root = napcat_dir()
    _emit('info', f'安装目录：{root}')
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f'安装目录不可写：{exc}') from exc

    has_qq = _qq_installed()
    _emit('info', '本机 QQ：' + ('已检测到' if has_qq else '未检测到 → 将使用 OneKey 包（官方安装器会自动下载 QQ 与 NapCat）'))

    if find_napcat_exe() is None and _installer_dir_present():
        # 官方安装器已在跑（它会先建 NapCat.*.Shell 目录）：等它装完再继续
        _emit('info', '检测到官方安装器正在运行（NapCat.*.Shell 目录已出现），等它装完…')
        if not _wait_for_exe():
            raise RuntimeError('安装器迟迟未产出启动器，请查看安装器窗口/日志后重试')
    elif find_napcat_exe() is None:
        installer = find_installer()
        if installer is None:
            _download_and_extract(ASSET_SHELL if has_qq else ASSET_ONEKEY, root)
            installer = find_installer()
        if installer is not None and find_napcat_exe() is None:
            # OneKey 只带官方安装器：直接跑它（输出实时转发到本页日志，跑完自动继续）
            _emit('warn', 'OneKey 包只带官方安装器：现在自动运行它，'
                          '它会下载 QQ 与 NapCat（约 300MB）并解压，进度就在下面这些日志里')
            _step('运行 NapCat 官方安装器（下载 QQ + NapCat）')
            _run_streaming([str(installer)], str(installer.parent), INSTALL_TIMEOUT, 'NapCat 官方安装器')
            _emit('ok', '官方安装器已跑完')
        if find_napcat_exe() is None:
            raise RuntimeError('未找到 NapCat 启动器（安装器可能失败），请把上方日志发我排查')

    token = _write_configs()
    hook_url = _hook_url()
    _emit('info', f'NapCat 配置已写入（HTTP 服务端 + 事件上报 + WebUI）：{napcat_config_dir()}')
    if hook_url:
        _emit('info', f'事件上报已启用：好友私聊消息会推送到 {hook_url}')
    else:
        _emit('warn', '事件上报未启用：本页「事件回调基址」为空，后台收不到好友消息'
                      '（填好后再点一次「一键启动」）')

    # 已在运行时先停下：HTTP 服务端配置要重启 NapCat 才生效
    if is_running():
        _emit('info', '检测到 NapCat 正在运行 —— 正在重启以让新配置生效…')
        stopped, stop_msg = stop()
        if stopped:
            for _ in range(20):
                if not is_running():
                    break
                time.sleep(0.5)
        if is_running():
            _emit('warn', f'未能真正停掉 NapCat（{stop_msg}）：请手动关闭 NapCat 的 QQ 窗口后，再点一次「一键启动」')

    if not is_running():
        exe = find_napcat_exe()
        qq = _napcat_qq()
        cmd = [str(exe)] + ([qq] if qq else [])
        _emit('info', f'启动 NapCat：{exe.name} {"（QQ " + qq + "）" if qq else ''}')
        _spawn_detached(cmd, cwd=str(exe.parent), log_name='napcat.log')
        _emit('info', '提示：NapCat/QQ 会额外弹出一个它自己的窗口，里面可能出现乱码 '
                      '（它用 GBK 控制台打印 UTF-8 文本）——那是上游程序的行为，不影响使用，'
                      '看本页日志即可；需要你操作的是下面的 WebUI（会自动打开）。')

    _emit('info', f'等待 HTTP 服务端就绪（最多 {READY_TIMEOUT} 秒；首次需扫码登录，登录成功后会立即就绪）…')
    ready = _wait_ready()
    _apply_setting(token)                      # 地址与 token 已确定，无论是否就绪都先回填
    if ready:
        _emit('ok', f'HTTP 服务端已就绪：{_configured_base()}')
        _emit('info', f'WebUI 控制台：{webui_url()}')
        return
    # 未就绪不算失败：多数情况是还没扫码登录（首次必经），把话说明白、给出下一步
    _emit('warn', 'HTTP 服务端尚未就绪 —— 通常是还没扫码登录 QQ（首次必经步骤）')
    _emit('info', f'👉 WebUI 扫码入口（复制到浏览器打开，用手机 QQ 扫码）：{webui_url()}')
    if not _napcat_qq():
        _emit('info', '提示：扫码登录成功后若端口仍不通，请到本页填上「机器人 QQ 号」再点一次「一键启动」'
                      '—— NapCat 按账号保存配置，填了 QQ 号我们才能把 HTTP 服务端写进该账号的配置')
    _emit('info', '登录成功后回到本页点「测试连接」即可确认打通（NapCat 会常驻后台，无需重复启动）')


def _reuse_linux_container(state):
    """复用已存在的 napcat 容器（**只启动，不重建**）

    为什么要单独一条路（两个真实踩过的坑）：
    · 服务器重启后容器会按 `--restart unless-stopped` 自动拉起，此时再
      `docker run --name napcat` 会因**名字冲突**返回 125，整个「一键部署」直接失败；
    · 反过来「删掉重建」更糟 —— QQ 登录态存在容器里，重建会被 NapCat 判定为新设备、
      必须重新扫码。所以已存在就只做「确保在运行」，其余交给下一步的就绪等待。
    """
    _emit('warn', f'已存在同名容器 {DOCKER_CONTAINER}（{state}），跳过创建、直接复用'
                  '（重建会丢掉已扫码的登录态）')
    if state != 'running':
        _emit('info', '容器未在运行，正在启动 …')
        _run_cmd(['docker', 'start', DOCKER_CONTAINER], timeout=180)

    _emit('info', f'等待 HTTP 服务端就绪（最多 {READY_TIMEOUT} 秒）…')
    if not _wait_ready():
        raise RuntimeError('容器已启动但端口未就绪：请进容器 WebUI 扫码登录 QQ 后重试')

    token = _docker_container_token()
    if token:
        _apply_setting(token)
    else:
        _emit('info', '未能从容器读出 token，保留「QQBot」页现有配置；若调用不通，'
                      '请核对 token 与 NapCat 的 HTTP 服务端是否一致')
    _emit('ok', f'HTTP 服务端已就绪：{_configured_base()}')
    _emit('info', f'WebUI 控制台（扫码登录 QQ）：{webui_url()}')


def _pipeline_linux():
    """Linux：优先 docker（官方镜像），没有 docker 时给出官方一键脚本命令"""
    if _docker_available():
        _emit('info', f'docker 可用，使用官方镜像 {DOCKER_IMAGE}')
        state = _docker_container_state()
        if state:
            _reuse_linux_container(state)
            return
        token = _random_token()
        # 用 --network host 而不用 `-p 端口:端口`：docker 发布端口是往 iptables 的 DOCKER 链插
        # DNAT 规则，早于 ufw / firewalld 生效 —— 一旦云安全组漏配，NapCat 的 OneBot API
        # （只有一个 token 保护）就被挂到公网。host 网络下端口由普通进程持有，主机防火墙重新
        # 生效，与生产实例、与主站「只监听回环」（S-11）的口径也一致。
        cmd = ['docker', 'run', '-d', '--name', DOCKER_CONTAINER, '--restart', 'unless-stopped',
               '--network', 'host',
               '-e', f'NAPCAT_TOKEN={token}', DOCKER_IMAGE]
        _emit('info', 'docker run：' + ' '.join(cmd))
        _run_cmd(cmd, timeout=600)
        _emit('info', f'等待 HTTP 服务端就绪（最多 {READY_TIMEOUT} 秒）…')
        if not _wait_ready():
            raise RuntimeError('容器已启动但端口未就绪：请进容器 WebUI 扫码登录 QQ 后重试')
        _apply_setting(token)
        _emit('ok', f'HTTP 服务端已就绪：{_configured_base()}')
        _emit('info', f'WebUI 控制台（扫码登录 QQ）：{webui_url()}')
        return

    _emit('warn', '未检测到可用的 docker（未安装或守护进程未运行）')
    _emit('info', '在 Linux 上安装 NapCat 需要 root 权限，无法由本站代你执行；请复制下面这条命令到服务器终端运行：')
    _emit('cmd', LINUX_INSTALL_CMD)
    _emit('info', '装完后 NapCat 会自建 systemd 服务并可在其 WebUI 配置 HTTP 服务端；'
                  '把地址与 token 填回本页，点「测试连接」即可')
    _emit('info', '（若你希望全程用 docker：装好 docker 后回到本页再点一次「一键启动」即可自动完成）')


def _step(title):
    _emit('step', f'▸ {title}')


# ==================== 下载 / 解压 ====================

def _download_and_extract(asset, root):
    root = Path(root)
    archive = root / asset
    _emit('info', f'下载 {asset} …')
    url = _download(asset, archive)
    _emit('ok', f'下载完成：{archive.name}（{archive.stat().st_size / 1024 / 1024:.1f} MB）· 源 {url}')
    _emit('info', f'解压到 {root} …')
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(root)
    _emit('ok', '解压完成')


def _download(asset, target):
    """流式下载（镜像优先、失败自动回退下一个源），带进度日志；返回实际使用的 URL"""
    import requests

    last_error = ''
    for prefix in DOWNLOAD_SOURCES:
        url = prefix + GITHUB_DL + asset
        label = '官方' if not prefix else prefix
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get('Content-Length') or 0)
                if total:
                    _emit('info', f'  文件大小 {total / 1024 / 1024:.1f} MB')
                done = 0
                marked = 0
                reported_at = time.time()
                with open(target, 'wb') as fh:
                    for chunk in resp.iter_content(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        # 每 ~10% 或每 3 秒报一次（小文件也能看到动静）
                        if total and (done - marked >= total // 10 or now - reported_at >= 3):
                            marked = done
                            reported_at = now
                            _emit('info', f'  已下载 {done / 1024 / 1024:.1f}'
                                          f'/{total / 1024 / 1024:.1f} MB')
            return label
        except Exception as exc:               # noqa: BLE001 换下一个源继续试
            last_error = f'{label}: {exc}'
            _emit('warn', f'  源 {label} 失败，尝试下一个（{exc}）')
    raise RuntimeError(f'所有下载源都失败：{last_error}')


# ==================== 配置写入 ====================

def _random_token(length=24):
    import secrets

    return secrets.token_urlsafe(length)[:32]


def _read_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            return {}
    return {}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _write_configs(root=None) -> str:
    """写 NapCat 配置：HTTP 服务端（端口 + token + 启用）与 WebUI，返回本次的 token

    默认写到 NapCat 真正读的那个配置目录（见 `napcat_config_dir`）；传 root 时写 `<root>/config`
    （单测用）。已有同名文件时**合并**写入（只改/加我们需要的字段，尽量不动其它配置）。
    onebot11.json 是默认配置；已知机器人 QQ 时再写一份 `onebot11_<QQ>.json`（部分版本按账号存配置）。
    """
    from API.models import PushSetting

    setting = PushSetting.get_solo()
    token = (setting.qqbot_token or '').strip() or _random_token()
    port = _port_from_base((setting.qqbot_api_base or '').strip())
    if setting.qqbot_token != token:
        # 立刻落库：保证「写进 NapCat 配置的 token」与「设置里的 token」永不失配（重跑也稳定）
        setting.qqbot_token = token
        setting.save(update_fields=['qqbot_token', 'updated_time'])

    config_dir = (Path(root) / 'config') if root else napcat_config_dir()
    payload = {
        'name': 'xiaoYingHttp', 'enable': True, 'host': '0.0.0.0', 'port': port,
        'enableCors': True, 'enableWebsocket': True,
        'messagePostFormat': 'array', 'token': token, 'debug': False,
    }
    # 事件上报（HTTP 客户端）：把 message 事件 POST 回本站回调，用于实时接收好友私聊消息
    hook_url = setting.hook_callback_url()
    hook_payload = {
        'name': 'xiaoYingHook', 'enable': True, 'url': hook_url,
        'messagePostFormat': 'json', 'reportSelfMessage': False, 'token': '', 'debug': False,
    }
    names = ['onebot11.json']
    qq = (setting.napcat_qq or '').strip()
    if qq:
        names.append(f'onebot11_{qq}.json')
    for name in names:
        path = config_dir / name
        data = _read_json(path)
        network = data.setdefault('network', {})
        servers = network.setdefault('httpServers', [])
        entry = next((s for s in servers if s.get('name') == 'xiaoYingHttp'), None)
        if entry is None:
            servers.append(dict(payload))
        else:
            entry.update(payload)

        clients = network.setdefault('httpClients', [])
        client = next((c for c in clients if c.get('name') == 'xiaoYingHook'), None)
        if hook_url:
            if client is None:
                clients.append(dict(hook_payload))
            else:
                client.update(hook_payload)
        elif client is not None:
            # 回调基址还没确定：先停用，避免 NapCat 往空地址反复上报
            client['enable'] = False
        _write_json(path, data)

    webui_path = config_dir / 'webui.json'
    webui = _read_json(webui_path)
    webui.update({'host': '0.0.0.0', 'port': DEFAULT_WEBUI_PORT, 'token': token})
    _write_json(webui_path, webui)
    return token


def _configured_base() -> str:
    from API.models import PushSetting

    return (PushSetting.get_solo().qqbot_api_base or '').strip()


def _napcat_qq() -> str:
    from API.models import PushSetting

    return (PushSetting.get_solo().napcat_qq or '').strip()


def _hook_url() -> str:
    """好友消息事件回调地址（基址未配置时为空串）"""
    from API.models import PushSetting

    return PushSetting.get_solo().hook_callback_url()


def _apply_setting(token):
    """把地址与 token 回填到「QQBot」页（地址已填就用原值）"""
    from API.models import PushSetting

    setting = PushSetting.get_solo()
    base = (setting.qqbot_api_base or '').strip()
    if not base:
        base = f'http://127.0.0.1:{DEFAULT_HTTP_PORT}'
        setting.qqbot_api_base = base
    setting.qqbot_token = token
    setting.save(update_fields=['qqbot_api_base', 'qqbot_token', 'updated_time'])
    _emit('info', '已回填「QQBot」页配置：HTTP 地址与 token')


# ==================== 进程与就绪 ====================

def _spawn_detached(cmd, cwd=None, log_name='napcat.log'):
    """以「脱离父进程」的方式拉起（Django 重启不会带走它），输出重定向到日志文件"""
    global _process, _log_handle

    log_dir = _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    if _log_handle:
        try:
            _log_handle.close()
        except OSError:
            pass
    _log_handle = open(log_dir / log_name, 'ab', buffering=0)

    flags = 0
    if os.name == 'nt':
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP
                 | getattr(subprocess, 'DETACHED_PROCESS', 0)
                 | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    _process = subprocess.Popen(cmd, cwd=cwd, stdout=_log_handle, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return _process


def _run_cmd(cmd, timeout=300):
    """同步执行命令并把输出写进日志（Linux docker 用）"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f'执行失败：{" ".join(cmd)} · {exc}') from exc
    out = (result.stdout or '').strip() or (result.stderr or '').strip()
    if out:
        _emit('info', out[:2000])
    if result.returncode != 0:
        raise RuntimeError(f'命令返回码 {result.returncode}：{" ".join(cmd)}')
    return out


def _decode(raw: bytes) -> str:
    """解码子进程输出：先按 UTF-8，失败再按 GBK（Windows 中文控制台多为 GBK）"""
    for encoding in ('utf-8', 'gbk'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def _run_streaming(cmd, cwd, timeout, label):
    """同步执行并把子进程输出**逐行实时转发**到流水线日志（页面「实时日志」可见）

    用于 NapCat 官方安装器：它是个控制台程序，原来用 CREATE_NO_WINDOW 静默跑，
    用户完全看不到进度。这里改为捕获它的输出并实时回显（含 GBK 解码），
    流水线等它跑完再继续 —— 所以「下载 300MB QQ → 解压」全自动，无需再点一次。

    安装器可能长时间不输出（在下载/解压），故用「读取线程 + 队列超时」实现心跳：
    超过 HEARTBEAT 秒没有输出就推一行「仍在运行（已 N 秒）」，页面不会看起来卡死。
    """
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=flags)
    except OSError as exc:
        raise RuntimeError(f'无法启动 {label}：{exc}') from exc

    lines = queue.Queue()

    def _reader():
        try:
            for raw in proc.stdout:
                lines.put(raw)
        except Exception:                      # noqa: BLE001 读取中断按结束处理
            pass
        finally:
            lines.put(None)                    # 结束标记

    threading.Thread(target=_reader, name='qqbot-installer-reader', daemon=True).start()

    started = time.time()
    deadline = started + timeout
    while True:
        try:
            raw = lines.get(timeout=HEARTBEAT)
        except queue.Empty:
            if time.time() > deadline:
                proc.kill()
                raise RuntimeError(f'{label} 超时（{timeout} 秒），已终止')
            _emit('info', f'  …{label} 仍在运行（已 {int(time.time() - started)} 秒，请勿关闭）')
            continue
        if raw is None:
            break
        text = _decode(raw).rstrip()
        if text:
            _emit('info', text)
        if time.time() > deadline:
            proc.kill()
            raise RuntimeError(f'{label} 超时（{timeout} 秒），已终止')

    code = proc.wait()
    if code != 0:
        raise RuntimeError(f'{label} 退出码 {code}（详细输出见上方日志）')


def _installer_dir_present() -> bool:
    """官方安装器是否已经开跑（它会先建 NapCat.*.Shell 目录再解压）"""
    root = napcat_dir()
    return root.is_dir() and next(root.glob('NapCat.*.Shell'), None) is not None


def _wait_for_exe(timeout=INSTALL_TIMEOUT):
    """等安装器把启动器解出来（已开跑的安装器不在本进程里，只能轮询）

    每 HEARTBEAT 秒推一行进度，页面不会看起来卡死。
    """
    started = time.time()
    deadline = started + timeout
    last = started
    while time.time() < deadline:
        if find_napcat_exe() is not None:
            return True
        time.sleep(2)
        if time.time() - last >= HEARTBEAT:
            last = time.time()
            _emit('info', f'  …仍在等待官方安装器产出启动器（已 {int(time.time() - started)} 秒）')
    return False


def _open_webui():
    """自动用默认浏览器打开 NapCat WebUI（扫码登录用）；失败只提示不报错"""
    url = webui_url()
    try:
        if os.name == 'nt':
            os.startfile(url)                  # noqa: S606 Windows：交给默认浏览器
        else:
            subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        _emit('ok', f'已用默认浏览器打开 WebUI（在里面扫码登录 QQ）：{url}')
        return True
    except Exception as exc:                   # noqa: BLE001 打不开浏览器不影响流程
        _emit('warn', f'未能自动打开浏览器，请手动复制到浏览器打开：{url}（{exc}）')
        return False


def _wait_ready(timeout=READY_TIMEOUT):
    """等 HTTP 服务端端口就绪；每 HEARTBEAT 秒推一行进度（首次需先扫码登录）

    启动后自动打开一次 WebUI（扫码登录的唯一入口），并把完整地址写进日志 ——
    否则用户根本不知道该去哪儿扫码（这是实际踩过的坑）。
    """
    started = time.time()
    deadline = started + timeout
    last = started
    opened = False
    while time.time() < deadline:
        if is_running():
            return True
        time.sleep(1)
        if not opened and time.time() - started >= 3:
            opened = _open_webui()
        if time.time() - last >= HEARTBEAT:
            last = time.time()
            _emit('info', f'  …仍在等待 HTTP 服务端就绪（已 {int(time.time() - started)} 秒）；'
                          f'扫码入口 WebUI：{webui_url()}')
    return False


def stop():
    """停止 NapCat

    注意：NapCat 是**注入进它自带的那份 QQ** 运行的，HTTP 端口实际由那个 QQ 的 node 子进程持有，
    只去结束启动器（NapCatWinBootMain.exe）会「杀了个空」——端口仍在监听、旧配置照样在跑
    （实测踩过的坑）。故 Windows 下按「可执行文件位于 NapCat 安装目录内」筛出进程逐个结束，
    只关 NapCat 自带的那份 QQ，不动用户自己的 QQ。
    """
    ok, message = False, ''
    if os.name != 'nt' and _docker_available():
        try:
            _run_cmd(['docker', 'stop', DOCKER_CONTAINER], timeout=60)
            return True, '已停止 NapCat 容器'
        except RuntimeError as exc:
            message = str(exc)
    if os.name == 'nt':
        ok, message = _stop_windows()
    elif _process and _process.poll() is None:
        _process.terminate()
        ok, message = True, '已请求停止 NapCat 进程'
    if not ok and not message:
        message = '没有正在运行的 NapCat 进程（可能由系统服务托管，请手动停止）'
    _emit('info', '停止 NapCat：' + message)
    return ok, message


def _stop_windows():
    """结束 NapCat 自带进程（按可执行文件路径限定在安装目录内）"""
    pids = _windows_napcat_pids()
    if not pids:
        return False, '未找到 NapCat 自带进程（可能未在运行）'
    killed = 0
    for pid in pids:
        try:
            subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                           capture_output=True, timeout=30)
            killed += 1
        except (OSError, subprocess.SubprocessError):
            continue
    return True, f'已结束 NapCat 自带进程 {killed} 个'


def _windows_napcat_pids():
    """本机运行中的 NapCat 进程 PID：可执行文件位于 NapCat 安装目录下的进程

    与 `find_napcat_exe`（找启动器）不同，这里要的是**真正在跑的宿主**（QQ.exe 及其子进程）。
    用 PowerShell 取全部进程的可执行路径再按前缀过滤，避免 `taskkill /IM QQ.exe` 误杀用户自己的 QQ。
    """
    root = str(napcat_dir()).lower().rstrip('\\/') + '\\'
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath } | "
              "Select-Object ProcessId, ExecutablePath | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                                capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout or '[]')
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if isinstance(data, dict):
        data = [data]
    return [int(item['ProcessId']) for item in data
            if str(item.get('ExecutablePath') or '').lower().startswith(root)]
