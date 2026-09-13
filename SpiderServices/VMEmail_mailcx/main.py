import random
import string
import uuid

import requests


class VMEmailMailcxSpider:
    """
    VMEmail 虚拟邮件服务爬虫（mail.cx），只能收邮件不能发邮件。

    工作原理（逆向自 https://mail.cx/zh/）:
        - 邮箱地址由「随机 local part + 域名」组成，前端本地生成，无需服务端注册；
          地址本身即邮箱唯一标识，直接查询即可收信（有邮件保留 1 小时）。
        - 官网提供 3 个后缀域名: ddker.com / 9k3r.com / uqu.me（默认 uqu.me）。
        - 请求需携带 X-Client-ID 头（客户端标识），未指定时自动生成 UUID。
        - 邮件通过长轮询拉取: 有新邮件立即返回，无新邮件时挂起约 25 秒后返回 204。
        - 邮件列表仅含摘要（preview_text），完整正文需按邮件 id 查询详情。

    接口:
        GET /v1/config                     获取配置（域名列表、local part 规则等）
        GET /v1/inbox/{address}[?since=]   拉取邮件列表（长轮询）
        GET /v1/email/{id}                 邮件详情（含完整正文）
    """

    # ---------- 基础配置 ----------
    BASE_URL = "https://mail.cx"
    # 通用请求头（X-Client-ID 在 __init__ 中动态添加）
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),
        "Referer": "https://mail.cx/zh/",
        "Accept": "*/*",
    }
    # 请求超时时间（秒）：需大于服务端长轮询挂起时长（约 25 秒）
    TIMEOUT = 35
    # 官网 3 个后缀域名（接口不可用时的回退值）
    DEFAULT_DOMAINS = ["ddker.com", "9k3r.com", "uqu.me"]
    # 默认域名
    DEFAULT_DOMAIN = "uqu.me"
    # 邮箱 local part 长度（与官网前端生成规则一致）
    LOCAL_PART_LENGTH = 6
    # local part 可选字符集
    LOCAL_PART_CHARS = string.ascii_lowercase + string.digits

    def __init__(self, client_id=None):
        """
        初始化爬虫会话。

        :param client_id: 客户端标识（X-Client-ID）。
            - 不传则随机生成 UUID
            - 传入已知值可保持同一客户端身份
        """
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.client_id = client_id or str(uuid.uuid4())
        self.session.headers["X-Client-ID"] = self.client_id
        # 当前邮箱地址（调用 generate_email 后赋值）
        self.address = None

    def list_domains(self):
        """
        获取官网当前可用的全部后缀域名。

        :return: list[str] 域名列表，如 ["ddker.com", "9k3r.com", "uqu.me"]
            接口异常时返回内置的默认域名列表
        """
        try:
            resp = self.session.get(f"{self.BASE_URL}/v1/config", timeout=self.TIMEOUT)
            config = resp.json()
            domains = [
                item["domain"]
                for item in config.get("system_domains", [])
                if item.get("domain")
            ]
            return domains or list(self.DEFAULT_DOMAINS)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return list(self.DEFAULT_DOMAINS)

    def generate_email(self, domain=None):
        """
        生成一个临时邮箱地址。

        地址由本地随机生成（无需服务端注册），生成后即可收信。

        :param domain: 指定后缀域名。不传则使用默认域名（uqu.me）。
            官网支持 ddker.com / 9k3r.com / uqu.me 三种。
        :return: dict 含:
            - address: 邮箱地址，如 "abc123@uqu.me"
            - domain: 后缀域名
            - client_id: 当前客户端标识
        :raises ValueError: 域名不在官网可用列表中时抛出
        """
        domain = domain or self.DEFAULT_DOMAIN
        if domain not in self.DEFAULT_DOMAINS:
            raise ValueError(
                f"不支持的域名: {domain}，可选: {self.DEFAULT_DOMAINS}"
            )

        local_part = "".join(
            random.choice(self.LOCAL_PART_CHARS) for _ in range(self.LOCAL_PART_LENGTH)
        )
        self.address = f"{local_part}@{domain}"
        return {
            "address": self.address,
            "domain": domain,
            "client_id": self.client_id,
        }

    def get_emails(self, address=None, since=None):
        """
        获取邮箱的邮件列表（长轮询）。

        无新邮件时接口会挂起约 25 秒后返回 204（即空列表）。

        :param address: 邮箱地址。不传则使用当前已生成的地址。
        :param since: 增量时间戳（秒）。不传返回当前全部邮件；
            传入后仅返回该时间戳之后的新邮件（可取上次结果的 next_since）。
        :return: list[dict] 邮件摘要列表，每项含:
            - id: 邮件唯一标识（用于查询详情）
            - from_name: 发件人名称
            - from_email: 发件人邮箱地址
            - subject: 邮件主题
            - preview_text: 正文预览（截断）
            - preview_status: 预览状态
            - size: 邮件大小（字节）
            - created_at: 收件时间（ISO 8601 格式，如 "2026-09-13T04:44:17Z"）
            无邮件时返回空列表 []
        :raises RuntimeError: 尚未生成邮箱或请求失败时抛出
        """
        target = address or self.address
        if not target:
            raise RuntimeError("尚未生成邮箱，请先调用 generate_email() 或传入 address")

        params = {}
        if since is not None:
            params["since"] = since

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/v1/inbox/{target}",
                params=params,
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"获取邮件失败: {e}")

        # 204：长轮询超时无新邮件
        if resp.status_code == 204:
            return []
        if resp.status_code != 200:
            raise RuntimeError(f"获取邮件失败，接口返回状态码 {resp.status_code}")

        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError("获取邮件失败，接口返回非 JSON 数据")

        return data.get("emails", [])

    def get_email_detail(self, email_id):
        """
        获取单封邮件的完整详情（含完整正文）。

        :param email_id: 邮件 id（来自 get_emails 返回的 id 字段）
        :return: dict 含:
            - id: 邮件唯一标识
            - from / from_email / from_name: 发件人信息
            - to: 收件人地址
            - subject: 邮件主题
            - text_body: 纯文本正文
            - html_body: HTML 正文
            - attachments: 附件列表
            - date: 邮件日期（RFC 2822 格式）
            - created_at: 收件时间（ISO 8601 格式）
        :raises RuntimeError: 邮件不存在或请求失败时抛出
        """
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/v1/email/{email_id}",
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"获取邮件详情失败: {e}")

        if resp.status_code == 404:
            raise RuntimeError(f"邮件不存在: {email_id}")
        if resp.status_code != 200:
            raise RuntimeError(f"获取邮件详情失败，接口返回状态码 {resp.status_code}")

        try:
            return resp.json()
        except ValueError:
            raise RuntimeError("获取邮件详情失败，接口返回非 JSON 数据")


# ---------- 使用示例 ----------
if __name__ == "__main__":
    spider = VMEmailMailcxSpider()

    # 1. 查看可用后缀域名（3 种）
    print(f"可用后缀域名: {spider.list_domains()}")

    # 2. 生成临时邮箱（逐个后缀演示）
    for domain in spider.DEFAULT_DOMAINS:
        info = spider.generate_email(domain=domain)
        print(f"生成邮箱: {info['address']}")

    # 重新生成一个用于测试的地址
    email_info = spider.generate_email()
    print(f"\n测试邮箱: {email_info['address']}")
    print("发送邮件到该地址即可收到（本服务仅收信）。")
    print("注意: 小影 API 发信接口需要签名参数(见 API 文档)，示例:")
    print(
        f"  POST http://127.0.0.1:8000/api/email/v1/send\n"
        f"  app_id/timestamp/nonce/sign + subject/body/recipients={email_info['address']}"
    )

    # 3. 轮询查询邮件（有邮件立即返回，无邮件约 25 秒后返回空）
    print("\n等待 25 秒后查询邮件...")
    import time
    time.sleep(25)
    emails = spider.get_emails()
    print(f"\n收到 {len(emails)} 封邮件:")
    for i, mail in enumerate(emails, 1):
        print(f"\n--- 邮件 {i} ---")
        print(f"发件人: {mail.get('from_email')}")
        print(f"主题: {mail.get('subject')}")
        print(f"预览: {mail.get('preview_text')}")
        print(f"时间: {mail.get('created_at')}")

        # 查询完整正文
        detail = spider.get_email_detail(mail["id"])
        print(f"完整正文: {detail.get('text_body')}")
