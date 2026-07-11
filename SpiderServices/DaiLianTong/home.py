# 代练通 - https://m.dailiantong.com/#/pages
# 注意：本文件仅包含业务功能方法，所有辅助函数/常量已迁移至 utils.py

import requests
import time
import json
import hashlib
from urllib.parse import quote, unquote

from utils import (
    get_mobile_headers,
    md5_encrypt,
    response_dict,
    get_public_data,
    parse_response,
    encrypt_actors,
    API_URL,
    SIGN_KEY,
    SENSITIVE_WORDS_PATH,
)

# 全局请求超时（秒）
_REQUEST_TIMEOUT = 30


class DaiLianTongService:
    # 类级别敏感词缓存，避免每个实例都重新读文件
    _sensitive_words_cache = None

    def __init__(self):
        self.api_url = API_URL
        self.SignKey = SIGN_KEY
        # 复用 Session 以启用 HTTP Keep-Alive，减少连接开销
        self.session = requests.Session()
        self.session.headers.update(get_mobile_headers())
        # 惰性加载敏感词列表
        if DaiLianTongService._sensitive_words_cache is None:
            with open(SENSITIVE_WORDS_PATH, "r", encoding="utf-8") as f:
                DaiLianTongService._sensitive_words_cache = json.loads(f.read())
        self.sensitive_words = DaiLianTongService._sensitive_words_cache

    @staticmethod
    def _ensure_str(value) -> str:
        """确保返回字符串类型"""
        return value if isinstance(value, str) else str(value)

    # 发送(注册、登录)验证码
    def send_code(self, phone, UseType: str = "17"):
        """
        发送(注册、登录)验证码
        参数:
            phone: 手机号
            UseType: 验证码类型，17为注册，12为登录
        """
        data, params = get_public_data({
            'ImageCode': 'donglangapp5890',
            'Mobile': phone,
            'SmsStyle': '10',
            'Rand': '',
            'UseType': str(UseType),
            'UserID2': '0',
            'UserID': '0',
        }, 'SendSMS', sign_key=self.SignKey)

        response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
        return parse_response(response)

    # 注册
    def register(self, phone, code):
        data, params = get_public_data({
            'AFFID': '',
            'Mobile': phone,
            'Pass': '',
            'ImageCode': '1234',
            'OS': 'WebApp',
            'Rand': '',
            'VerifyStr': code,
            'PayPassword': '',
            'Question': '',
            'Answer': '',
            'QQ': '',
            'IsReCode': '0',
            'Channels': 'web',
            'InviteVer': '5.1.9',
            'UserID': '0',
        }, 'UserRegister', sign_key=self.SignKey)

        response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
        return parse_response(response)

    # 登录
    def login(self, phone, code, code_type="VerificationCode"):
        """
        登录
        参数:
            phone: 手机号
            code: 验证码或密码
            code_type: 验证码类型，VerificationCode为验证码，Password为密码
        """
        if code_type == "VerificationCode":
            data, params = get_public_data({
                'LoginID': phone,
                'HD': '',
                'PhoneType': '',
                'OS': 'WebApp',
                'VerifyStr': str(code),
                'UserID': '0',
            }, 'UserLoginByMobile', sign_key=self.SignKey)
        elif code_type == "Password":
            data, params = get_public_data({
                'LoginID': phone,
                'UserID': '0',
            }, 'UserTipForChangePass', sign_key=self.SignKey)

            response = parse_response(self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT))
            if response["code"] != 0:
                return response
            data, params = get_public_data({
                'LoginID': response["data"]["LoginID"],
                'Pass': md5_encrypt(md5_encrypt(code) + response['data']['LoginID']),
                'OS': 'WebApp',
                'verifystr': '',
                'HD': '',
                'Channels': 'web',
                'UserID': '0',
            }, 'GoHome', sign_key=self.SignKey)

        response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
        return parse_response(response)

    # 获取我的信息
    def get_user_info(self, user_id, token):
        data, params = get_public_data({
            'UserID': self._ensure_str(user_id),
        }, 'UserInfoList', sign_key=self.SignKey, token=token)

        response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
        return parse_response(response)

    # 设置联系方式
    def set_contact(self, contact, user_id, token, set_contact_type="qq"):
        """
        设置联系方式
        参数:
            contact: 联系方式
            user_id: 用户ID
            token: 登录令牌
            set_contact_type: 联系方式类型，qq为QQ号，mobile为手机号
        """
        data, params = get_public_data({
            '': '',
            'NickName': '',
            'Email': '',
            'QQ': contact if set_contact_type == "qq" else '',
            'Mobile': contact if set_contact_type == "mobile" else '',
            'LoginMode': '-1',
            'IconIndex': '-1',
            'MySign': '',
            'MySet': '',
            'IconUrl': '',
            'UserID': self._ensure_str(user_id),
        }, 'UserInfoUpdate', sign_key=self.SignKey, token=token)

        response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
        return parse_response(response)

    # 设置个性签名
    def set_mysign(self, mysign, user_id):
        """
        设置个性签名(DZY提醒您,该接口只需要获取user_id即可,简而言之是一个小漏洞,可以留着打广告,)
        参数:
            mysign: 个性签名
            user_id: 用户ID
        """
        user_id = self._ensure_str(user_id)
        time_stamp = str(int(time.time()))
        params = {
            'UserId': user_id,
            'NickName': '',
            'IconUrl': '',
            'uSign': mysign,
            'Sex': '',
            'timeStamp': time_stamp,
        }
        sign_raw = user_id + mysign + time_stamp + self.SignKey
        params['Sign'] = unquote(quote(hashlib.md5(sign_raw.encode('utf-8')).hexdigest(), encoding='utf-8'), encoding='utf-8')

        try:
            resp_json = self.session.post(
                'https://api2.dailiantong.com.cn/User/SetUserInfoRZ',
                params=params, timeout=_REQUEST_TIMEOUT,
            ).json()
            ok = resp_json.get("Tag") == 1
            return response_dict(
                code=0 if ok else 1,
                message="设置成功" if ok else resp_json.get("Message", "未知错误"),
            )
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            return response_dict(code=1, message=f"设置个性签名异常: {e}")

    # 修改密码
    def change_password(self, old_password, new_password, user_id, login_id, uid, token):
        """
        修改密码
        参数:
            old_password: 旧密码, 为空时表示未设置过密码
            new_password: 新密码
            user_id: 用户ID
            login_id: 登录ID
            uid: UID
            token: 登录令牌
        """
        data, params = get_public_data({
            'UserID2': self._ensure_str(user_id),
            'ChangeType': '0',
            'VerifyStr': md5_encrypt(md5_encrypt(old_password) + login_id),
            'NewPassword': md5_encrypt(md5_encrypt(new_password) + login_id),
            'VPassword': md5_encrypt(md5_encrypt(new_password) + uid),
            'UserID': self._ensure_str(user_id),
        }, 'UserChangePassword', sign_key=self.SignKey, token=token)
        response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
        return parse_response(response)

    # 签到得20代币
    def sign_in(self, user_id):
        """
        签到得20代币
        参数:
            user_id: 用户ID

        流程:
            1. 调用 SelectUserSignin 获取当前签到周期任务列表
            2. 找到 SingnDay==0（今日未签到）的任务
            3. 用该任务的 SigninId 和 SigninDetailsId 调用 UserSignin 执行签到
        """
        user_id = self._ensure_str(user_id)
        try:
            # ---- 1. 获取签到任务列表 ----
            ts1 = str(int(time.time()))
            select_params = {
                'UserID': user_id,
                'timeStamp': ts1,
                'Sign': md5_encrypt(user_id + ts1 + self.SignKey),
            }
            select_resp = self.session.get(
                'https://quickorder.dailiantong.com.cn/api/share/SelectUserSignin',
                params=select_params, timeout=_REQUEST_TIMEOUT,
            ).json()

            if select_resp.get("ReturnCode") != 1:
                return response_dict(code=1, message=select_resp.get("Message", "获取签到任务列表失败"))

            task_list = select_resp.get("Result", [])
            if not task_list:
                return response_dict(code=1, message="没有可用的签到任务")

            # 找到 SingnDay==0（今日待签到）的任务
            today_task = None
            for task in task_list:
                if task.get("SingnDay") == 0:
                    today_task = task
                    break

            if not today_task:
                return response_dict(code=1, message="今日已签到，无需重复签到")

            signin_id = str(today_task["SigninId"])
            signin_detail_id = str(today_task["SigninDetailsId"])

            # ---- 2. 执行签到 ----
            ts2 = str(int(time.time()))
            sign_params = {
                'UserID': user_id,
                'SigninId': signin_id,
                'SigninDetailsId': signin_detail_id,
                'timeStamp': ts2,
                'Sign': md5_encrypt(user_id + signin_id + signin_detail_id + ts2 + self.SignKey),
            }

            sign_resp = self.session.get(
                'https://quickorder.dailiantong.com.cn/api/share/UserSignin',
                params=sign_params, timeout=_REQUEST_TIMEOUT,
            ).json()

            return_code = sign_resp.get("ReturnCode")
            ok = return_code is not None and str(return_code) == "1"
            return response_dict(
                code=0 if ok else 1,
                message=sign_resp.get("Message", "未知结果"),
                data=sign_resp.get("Result1") if ok else None,
            )

        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            return response_dict(code=1, message=f"签到请求异常: {e}")

    # 获取我的实名认证信息
    def get_my_real_name_info(self, user_id):
        """
        获取我的实名认证信息 (DZY提醒您,该接口只需要获取user_id即可,属于漏洞,可以通过user_id获取其他用户的实名认证信息)
        参数:
            user_id: 用户ID
        """
        user_id = self._ensure_str(user_id)
        time_stamp = str(int(time.time()))
        params = {
            'UserID': user_id,
            'timeStamp': time_stamp,
            'Sign': md5_encrypt(user_id + time_stamp + self.SignKey),
        }

        try:
            resp_json = self.session.get(
                'https://quickorder.dailiantong.com.cn/api/share/IdCardInfo1',
                params=params, timeout=_REQUEST_TIMEOUT,
            ).json()
            result = resp_json.get("Result")
            if result and len(result) > 0:
                return response_dict(code=0, message=resp_json.get("Message", "成功"), data=result)
            else:
                return response_dict(code=1, message="没有找到该身份信息")
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            return response_dict(code=1, message=f"实名信息请求异常: {e}")

    # 获取公共订单列表
    def get_public_order_list(self,
        user_id,
        token,
        page_index=1,
        page_size=20,
        game_id=107,
        price_str='10_20',
        is_pub=1,
        search_str='',
        pg_type=0,
        filter_sensitive=False,
        ):
        """
        获取公共订单列表

        参数:
            user_id: 用户ID
            token: 登录令牌
            page_index: 页码, 默认为1
            page_size: 每页数量, 默认为20
            game_id: 游戏ID, 默认为107
            price_str: 价格范围, 默认为10_20
            is_pub: 是否公共订单, 默认为1
            search_str: 搜索字符串
            pg_type: 区服, 0全部 1安卓 2IOS
            filter_sensitive: 是否过滤敏感词订单

        返回:
            成功时返回订单列表，启用敏感词过滤时额外返回过滤统计信息
        """
        try:
            pub_flag = int(is_pub) if not isinstance(is_pub, int) else is_pub
            if pub_flag == 0 and not search_str:
                return response_dict(code=1, message="is_pub为0时必须输入search_str")

            data, params = get_public_data({
                'IsPub': str(is_pub),
                'GameID': str(game_id),
                'ZoneID': '0',
                'ServerID': '0',
                'SearchStr': search_str,
                'STier': '',
                'ETier': '',
                'Sort_Str': '',
                'PageIndex': str(page_index),
                'PageSize': str(page_size),
                'Price_Str': price_str,
                'PubCancel': '0',
                'SettleHour': '0',
                'FilterType': '0',
                'PGType': str(pg_type),
                'Focused': '-1',
                'OrderType': '0',
                'PubRecommend': '0',
                'Score1': '0',
                'Score2': '0',
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderList", sign_key=self.SignKey, token=token)

            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT).json()
            order_list = response.get('LevelOrderList')
            if not order_list:
                return response_dict(code=1, message="没有找到该订单")

            if not filter_sensitive:
                return response_dict(code=0, message="获取单子成功", data=order_list)

            # ---------- 敏感词过滤 ----------
            filtered_orders = []
            filtered_count = 0
            filtered_reasons = []
            lower_title_cache = {}  # 缓存已 lower() 的标题，重复订单标题可复用

            for order in order_list:
                order_title = order.get('Title') or order.get('OrderName') or ''
                if order_title not in lower_title_cache:
                    lower_title_cache[order_title] = order_title.lower()

                title_lower = lower_title_cache[order_title]
                is_sensitive = False
                matched_words = []
                for word in self.sensitive_words:
                    if len(word) <= 1:
                        continue
                    if word.lower() in title_lower:
                        is_sensitive = True
                        matched_words.append(word)

                if is_sensitive:
                    filtered_count += 1
                    filtered_reasons.append({
                        'order_id': order.get('ODSerialNo', ''),
                        'title': order_title,
                        'matched_words': matched_words,
                    })
                else:
                    filtered_orders.append(order)

            return response_dict(
                code=0,
                message=f"获取单子成功，已过滤{filtered_count}条敏感订单" if filtered_count > 0 else "获取单子成功",
                data={
                    'orders': filtered_orders,
                    'total_count': len(order_list),
                    'filtered_count': filtered_count,
                    'remaining_count': len(filtered_orders),
                    'filtered_reasons': filtered_reasons if filtered_count > 0 else [],
                },
            )
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"请求异常: {e}")

    # 获取订单详情
    def get_order_detail(self, user_id, token, order_id):
        """
        获取订单详情
        参数:
            user_id: 用户ID
            token: 登录令牌
            order_id: 订单ID
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': self._ensure_str(order_id),
                'IsPublish': '2',
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderDetail", sign_key=self.SignKey, token=token)

            resp_json = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT).json()
            if "CreateUserID" in resp_json:
                return response_dict(code=0, message="获取订单详情成功", data=resp_json)
            else:
                return response_dict(code=1, message="没有找到该订单")
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"请求异常: {e}")

    # 接收订单
    def receive_order(self, order_id, pay_pass, uid, token, user_id):
        """
        接收订单
        参数:
            order_id: 订单ID
            pay_pass: 支付密码
            uid: 登录令牌
            token: 登录令牌
            user_id: 用户ID
        """
        try:
            order_detail = self.get_order_detail(order_id=order_id, user_id=user_id, token=token)
            if order_detail["code"] != 0:
                return order_detail

            data, params = get_public_data({
                'ODSerialNo': order_id,
                'Stamp': str(order_detail["data"]["Stamp"]),
                'PayPass': md5_encrypt(md5_encrypt(pay_pass) + uid),
                'Insurance': '0',
                'MaxClaimAmount': '0',
                'VisitType': '0',
                'NonceStr': '',
                'NoEnsure': '0',
                'IsWx': '0',
                'SourceType': '0',
                'UserID': self._ensure_str(user_id),
            }, "NewLevelOrderAccept", sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"接收订单异常: {e}")

    # 发布订单
    def publish_order(self,
        title,
        uid,
        price,
        time_limit,
        token,
        user_id,
        ensure1,
        ensure2,
        game_mobile,
        pay_pass,
        game_account,
        game_password,
        game_author_name,
        hero_count=10,
        requirements="1、未经同意请勿动用账号点券、物品，不要联系或回复好友信息\n\n2、切勿使用外挂，不允许打广告、挂机、恶意骂人等恶意行为",
        zone_serverID='107103017095500',
        ):
        """
        发布订单
        参数:
            title: 订单标题
            uid: 登录令牌
            price: 订单价格
            time_limit: 订单时间限制
            token: 登录令牌
            user_id: 用户ID
            ensure1: 安全保证金
            ensure2: 效率保证金
            game_mobile: 号主联系方式
            pay_pass: 支付密码
            game_account: 游戏账号
            game_password: 游戏密码
            game_author_name: 游戏角色名
            hero_count: 英雄数量,默认10
            requirements: 代练要求
            zone_serverID: 游戏ID,默认王者荣耀
        """
        try:
            actors_str = f"{game_account}|*|{game_password}|*|{game_author_name}|*|英雄数量{hero_count}个|*|{requirements}"
            ext_str = f'{{"ID":4,"IsEnable":1,"Content":"{requirements}","Mode":0,"Data":[],"YSData":[]}}'

            data, params = get_public_data({
                'ZoneServerID': zone_serverID,
                'Title': title,
                'Price': price,
                'TimeLimit': time_limit,
                'Ensure1': ensure1,
                'Ensure2': ensure2,
                'GameMobile': game_mobile,
                'PayPass': md5_encrypt(md5_encrypt(pay_pass) + uid),
                'Mobile': '',
                'QQ': '',
                'LimitAccept': '0',
                'BasePrice': '0',
                'Label1': '',
                'Label2': '',
                'Memo': '',
                'Groups': 'OTHER',
                'Actors': encrypt_actors(actors_str),
                'Members': '',
                'ReCode': '',
                'OverPrice': '',
                'LevelType2': '14',
                'Insurance': '0',
                'MaxClaimAmount': '20',
                'OrderType': '0',
                'NonceStr': '',
                'ExtStr': ext_str,
                'ReceiveOrderSetInfoId': '0',
                'IsMerchant': '0',
                'IsNeedExtraDeposit': '0',
                'TransTime': '0',
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderAdd", sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"发布订单异常: {e}")

    # 删除订单
    def delete_order(self, order_id, token, user_id, reason="不用了"):
        """
        删除订单
        参数:
            order_id: 订单ID
            token: 登录令牌
            user_id: 用户ID
            reason: 删除原因,默认"不用了"
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': order_id,
                'Reason': reason,
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderDelSelf", sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"删除订单异常: {e}")

    # 获取我的订单
    def get_my_order(self,
        token,
        user_id,
        page_index='1',
        page_size='20',
        over_days='-99',
        search_str="",
        ):
        """
        获取我的订单
        参数:
            token: 登录令牌
            user_id: 用户ID
            page_index: 页码,默认1
            page_size: 每页数量,默认20
            over_days: -99代表正在代练的订单,99已完成的订单
            search_str: 搜索字符串,默认空
        """
        try:
            data, params = get_public_data({
                'Publish': '1',
                'Status': '0',
                'CancelStatus': '0',
                'GameID': '0',
                'OverDays': str(over_days),
                'SearchStr': search_str,
                'PageIndex': str(page_index),
                'PageSize': str(page_size),
                'GameMobile': '',
                'WithTG': '1',
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderMyList", sign_key=self.SignKey, token=token)
            resp_json = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT).json()

            if "LevelOrderList" in resp_json:
                return response_dict(code=0, message="获取我的订单成功", data=resp_json["LevelOrderList"])
            else:
                return response_dict(code=1, message=resp_json.get("Err", "未知错误"), data=None)
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"获取我的订单异常: {e}")

    # 在订单留言中上传图片
    def upload_image_in_order_comment(self, token, user_id, image_path, order_id):
        """
        在订单留言中上传图片
        参数:
            token: 登录令牌
            user_id: 用户ID
            image_path: 图片路径
            order_id: 订单ID
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': order_id,
                'Tier': '',
                'Msg': '留言',
                'Img': image_path,
                'OrderWinTxt': '',
                'UserID': self._ensure_str(user_id),
            }, 'LevelOrderProgressAdd', sign_key=self.SignKey, token=token)

            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"上传图片异常: {e}")

    # 上传自己的头像
    def upload_own_avatar(self, user_id, image_path):
        """
        上传自己的头像(DZY提醒:属于漏洞范围,只需要获取user_id即可修改头像,没有经过token验证)
        参数:
            user_id: 用户ID
            image_path: 图片路径
        """
        try:
            user_id = self._ensure_str(user_id)
            timestamp = str(int(time.time()))
            sign_raw = user_id + image_path + timestamp + self.SignKey
            sign_md5 = hashlib.md5(sign_raw.encode('utf-8')).hexdigest()

            params = {
                "UserID": user_id,
                "NickName": "",
                "IconUrl": image_path,
                "uSign": "",
                "Sex": "",
                "TimeStamp": timestamp,
                "Sign": sign_md5,
                "ODM": "xinxiliu04",
            }

            resp_json = self.session.post(
                'https://api2.dailiantong.com.cn/User/SetUserInfoRZ',
                params=params, timeout=_REQUEST_TIMEOUT,
            ).json()

            ok = resp_json.get("Tag") == 1
            return response_dict(
                code=0 if ok else 1,
                message="上传头像成功" if ok else resp_json.get("Message", "未知错误"),
            )
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            return response_dict(code=1, message=f"上传头像异常: {e}")


if __name__ == "__main__":
    dailiantong_service = DaiLianTongService()
    print(dailiantong_service.get_public_order_list(
        user_id="24479174",
        token="E74C430D9CC24338B654B9339069F36F",
        page_index=1,
        page_size=20,
        game_id=107,
    ))
