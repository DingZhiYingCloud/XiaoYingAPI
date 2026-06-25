import requests
import uuid


class VMEmailMinmailSpider:
    """
    VMEmail 虚拟邮件服务爬虫（minmail.app），只能收邮件不能发邮件。

    工作原理:
        - 通过随机生成的 visitor-id（UUID）标识用户身份
        - 同一 visitor-id 对应一个临时邮箱，邮箱过期前可反复查询邮件
        - 首次调用生成接口会分配一个新邮箱地址
    """

    # ---------- 基础配置 ----------
    BASE_URL = "https://minmail.app"
    # 通用请求头（visitor-id 在 __init__ 中动态添加）
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://minmail.app/cn/email-generator",
        "Accept": "*/*",
    }
    # 请求超时时间（秒）
    TIMEOUT = 15
    # 邮箱默认过期时间（分钟），1440 分钟 = 24 小时
    DEFAULT_EXPIRE = 1440

    def __init__(self, visitor_id=None):
        """
        初始化爬虫会话。

        :param visitor_id: 访客标识（UUID 格式）。
            - 不传则随机生成，对应一个全新的临时邮箱
            - 传入已知的 visitor_id 可复用之前生成的邮箱（需在过期时间内）
        """
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        # visitor-id 决定邮箱归属，同一 visitor-id 对应同一邮箱
        self.visitor_id = visitor_id or str(uuid.uuid4())
        self.session.headers["visitor-id"] = self.visitor_id
        # 当前邮箱地址（调用 generate_email 后赋值）
        self.address = None

    def generate_email(self, expire=DEFAULT_EXPIRE, refresh=False):
        """
        生成或获取临时邮箱。

        :param expire: 邮箱过期时间（分钟），默认 1440（24小时）
        :param refresh: 是否强制生成新邮箱。
            - False（默认）: 获取当前邮箱，首次调用会生成新邮箱
            - True: 强制生成新邮箱，原邮箱及其邮件将被丢弃
        :return: dict 含:
            - address: 邮箱地址，如 "abc123@atminmail.com"
            - expire: 过期时间（分钟）
            - remaining_time: 剩余有效时间（秒）
            - visitor_id: 当前访客标识（可用于后续复用）
        :raises RuntimeError: 请求失败或接口返回异常时抛出
        """
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/mail/address",
                params={
                    "refresh": str(refresh).lower(),
                    "expire": expire,
                    "part": "emailGenerator",
                },
                timeout=self.TIMEOUT,
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise RuntimeError(f"生成邮箱失败: {e}")

        if "address" not in data:
            # 接口返回异常（如被限流、参数错误）
            raise RuntimeError(f"生成邮箱失败，接口返回: {data}")

        self.address = data["address"]
        return {
            "address": data["address"],
            "expire": data.get("expire"),
            "remaining_time": data.get("remainingTime"),
            "visitor_id": self.visitor_id,
        }

    def get_emails(self):
        """
        获取当前邮箱的全部邮件。

        :return: list[dict] 邮件列表，每项含:
            - id: 邮件唯一标识
            - from: 发件人完整信息（含地址）
            - fromAddress: 发件人邮箱地址
            - fromName: 发件人名称（可能为空）
            - to: 收件人邮箱地址
            - subject: 邮件主题
            - preview: 邮件预览内容（截断的正文）
            - content: 邮件完整正文
            - date: 收件时间（ISO 8601 格式，如 "2026-06-25T19:37:34.201Z"）
            - isRead: 是否已读
            无邮件时返回空列表 []
        :raises RuntimeError: 尚未生成邮箱或请求失败时抛出
        """
        if not self.address:
            raise RuntimeError("尚未生成邮箱，请先调用 generate_email()")

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/mail/list",
                params={"part": "emailGenerator"},
                timeout=self.TIMEOUT,
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise RuntimeError(f"获取邮件失败: {e}")

        return data.get("message", [])


# ---------- 使用示例 ----------
if __name__ == "__main__":
    spider = VMEmailMinmailSpider()

    # 1. 生成临时邮箱
    email_info = spider.generate_email()
    print(f"邮箱地址: {email_info['address']}")
    print(f"剩余有效期: {email_info['remaining_time']} 秒")
    print(f"visitor_id: {email_info['visitor_id']}")
    print(f"发送邮件到该地址即可收到，可用以下命令测试:")
    print(
        f"  curl -X POST http://127.0.0.1:8000/api/email/v1/send "
        f"--data-urlencode 'subject=测试' "
        f"--data-urlencode 'body=内容' "
        f"--data-urlencode 'recipients={email_info['address']}'"
    )

    # 2. 获取邮件列表（可多次调用轮询新邮件）
    import time
    print("\n等待 10 秒后查询邮件...")
    time.sleep(10)
    emails = spider.get_emails()
    print(f"\n收到 {len(emails)} 封邮件:")
    for i, mail in enumerate(emails, 1):
        print(f"\n--- 邮件 {i} ---")
        print(f"发件人: {mail.get('fromAddress')}")
        print(f"主题: {mail.get('subject')}")
        print(f"正文: {mail.get('content')}")
        print(f"时间: {mail.get('date')}")

    # 复用已有邮箱（保存 visitor_id 后下次直接传入）
    # saved_visitor_id = email_info['visitor_id']
    # spider2 = VMEmailMinmailSpider(visitor_id=saved_visitor_id)
    # spider2.generate_email()  # 获取同一邮箱
    # emails = spider2.get_emails()  # 查询同一邮箱的邮件
