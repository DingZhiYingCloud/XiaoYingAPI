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
    base64_encrypt,
    response_dict,
    get_public_data,
    parse_response,
    guess_image_ext,
    image_content_type,
    oss_object_key,
    oss_policy_and_signature,
    API_URL,
    IMG_SERVER_URL,
    OSS_ACCESS_KEY_ID,
    OSS_UPLOAD_URL,
    SIGN_KEY,
)

# 全局请求超时（秒）
_REQUEST_TIMEOUT = 30


class DaiLianTongService:

    def __init__(self):
        self.api_url = API_URL
        if not SIGN_KEY:
            raise RuntimeError("DAILIAN_SIGN_KEY 未配置，请在 .env 中设置")
        self.SignKey = SIGN_KEY
        # 复用 Session 以启用 HTTP Keep-Alive，减少连接开销
        self.session = requests.Session()
        self.session.headers.update(get_mobile_headers())

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

    # 获取订单详情
    def get_order_detail(self, user_id, token, order_id, is_publish='2'):
        """
        获取订单详情
        参数:
            user_id: 用户ID
            token: 登录令牌
            order_id: 订单ID
            is_publish: 视角标记；接单方取号主账号须用 '0'（默认 '2' 供接单校验取 Stamp）
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': self._ensure_str(order_id),
                'IsPublish': str(is_publish),
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

    # 申请撤销订单
    def apply_cancel_order(self, order_id, pay_pass, uid, token, user_id,
                           flag=0, pay_level_bal=0, rep_ensure_bal=0,
                           comment='', revoke_price=0):
        """
        申请撤销订单（上游 LevelOrderCancel）

        参数:
            order_id: 订单ID
            pay_pass: 支付密码（原密码，内部按 md5(md5(pwd)+uid) 处理）
            uid: 账号 UID（USR 开头，支付密码哈希用）
            token / user_id: 登录态
            flag: 0=申请撤销 1=取消撤销 2=同意撤销 3=申请平台介入
            pay_level_bal: 支付代练费金额（撤销意愿=「我愿意支付代练费」时填）
            rep_ensure_bal: 赔偿保证金金额（撤销意愿=「我要求赔偿保证金」时填）
            comment: 撤销说明（页面把撤销原因/进度/意愿等拼成一段文本，这里原样下发）
            revoke_price: 撤销金额
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': self._ensure_str(order_id),
                'Flag': str(flag),
                'PayLevelBal': str(pay_level_bal),
                'RepEnsureBal': str(rep_ensure_bal),
                'Comment': comment,
                'PayPass': md5_encrypt(md5_encrypt(pay_pass) + uid),
                'RevokePrice': str(revoke_price or 0),
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderCancel", sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"申请撤销异常: {e}")

    # 申请平台介入（撤销/协商无法达成一致时）
    def request_arbitration(self, order_id, token, user_id):
        """
        申请平台介入（上游 LevelOrderRequestArbitration）

        参数:
            order_id: 订单ID
            token / user_id: 登录态
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': self._ensure_str(order_id),
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderRequestArbitration", sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"申请平台介入异常: {e}")

    # 获取我的订单（可多条件筛选，上游服务端分页）
    def get_my_order(self, token, user_id, publish=1, over_days=-99, status=0,
                     cancel_status=0, game_id=0, search_str="", game_mobile="",
                     with_tg=1, page_index=1, page_size=20):
        """
        获取我的订单（我发布的 / 我接的）

        参数:
            token / user_id: 登录态
            publish: 1=我发布的 0=我接的, 默认1
            over_days: -99=进行中 99=已完成, 默认-99
            status: 订单状态位, 0=不限, 默认0
            cancel_status: 撤单状态位, 0=不限, 默认0
            game_id: 游戏ID筛选, 0=全部, 默认0
            search_str: 关键词, 默认空
            game_mobile: 号主联系方式筛选, 默认空
            with_tg: 是否含托管, 默认1
            page_index / page_size: 分页（上游为服务端分页，按其返回结果原样透传）

        返回:
            成功时 data 为 {"items": [...], "total": int, "page": int,
                          "page_size": int, "total_pages": int}
        """
        try:
            data, params = get_public_data({
                'Publish': str(publish),
                'Status': str(status),
                'CancelStatus': str(cancel_status),
                'GameID': str(game_id),
                'OverDays': str(over_days),
                'SearchStr': search_str,
                'PageIndex': str(page_index),
                'PageSize': str(page_size),
                'GameMobile': game_mobile,
                'WithTG': str(with_tg),
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderMyList", sign_key=self.SignKey, token=token)
            resp_json = self.session.post(self.api_url, params=params, data=data,
                                          timeout=_REQUEST_TIMEOUT).json()
            if not isinstance(resp_json, dict) or "LevelOrderList" not in resp_json:
                message = resp_json.get("Err") if isinstance(resp_json, dict) else None
                return response_dict(code=1, message=message or "获取我的订单失败", data=None)

            orders = resp_json.get('LevelOrderList') or []
            total = resp_json.get('RecordCount') or len(orders)
            return response_dict(code=0, message="获取我的订单成功", data={
                'items': orders,
                'total': total,
                'page': int(page_index),
                'page_size': int(page_size),
                'total_pages': (total + int(page_size) - 1) // int(page_size) if total else 0,
            })
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"获取我的订单异常: {e}")

    # 在订单留言中上传图片
    def upload_image_in_order_comment(self, token, user_id, image_path, order_id, msg='留言'):
        """
        在订单留言中上传图片
        参数:
            token: 登录令牌
            user_id: 用户ID
            image_path: 图片路径
            order_id: 订单ID
            msg: 留言内容（申请撤销时上传凭证用「撤销」）
        """
        try:
            data, params = get_public_data({
                'ODSerialNo': order_id,
                'Tier': '',
                'Msg': msg,
                'Img': image_path,
                'OrderWinTxt': '',
                'UserID': self._ensure_str(user_id),
            }, 'LevelOrderProgressAdd', sign_key=self.SignKey, token=token)

            response = self.session.post(self.api_url, params=params, data=data, timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"上传图片异常: {e}")

    # 上传单张图片到代练通图片存储（阿里云 OSS 直传）
    def upload_image_to_oss(self, image_bytes, ext='png'):
        """把图片二进制直传到代练通用的阿里云 OSS，返回可访问的图片地址

        参数:
            image_bytes: 图片二进制内容
            ext: 扩展名（png / jpg ...，不带点）
        返回: response_dict，data = {'key': OSS 对象名, 'url': 可访问的完整地址}
        """
        try:
            key = oss_object_key(ext)
            policy, signature = oss_policy_and_signature()
            response = requests.post(
                OSS_UPLOAD_URL,
                data={'key': key, 'policy': policy, 'OSSAccessKeyId': OSS_ACCESS_KEY_ID,
                      'signature': signature, 'success_action_status': '200'},
                files={'file': (key.rsplit('/', 1)[-1], image_bytes, image_content_type(ext))},
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                return response_dict(code=1, message=f"上传图片失败（HTTP {response.status_code}）")
            return response_dict(code=0, message="上传成功",
                                 data={'key': key, 'url': f"{IMG_SERVER_URL}/{key}"})
        except Exception as e:
            return response_dict(code=1, message=f"上传图片异常: {e}")

    # 订单图片挂单的公共流程：外链下载 → 转存 OSS → 逐张以 msg 挂到订单
    def _attach_order_images(self, serial, image_urls, token, user_id, msg,
                             tier='', order_win_txt=''):
        """「首图 / 完单图」共用的挂图流程

        参数集合与顺序必须与官方 H5 完全一致（Sign 依赖参数值拼接顺序）：
            LevelOrderProgressAdd: ODSerialNo / Tier / Msg / Img / OrderWinTxt / UserID

        返回: (images, results, error)
            images  —— 已成功挂到订单上的图片地址
            results —— 每张挂单的上游返回
            error   —— None 表示全部成功；否则为已组装好的 response_dict，
                       msg 会指明是第几张出错，已挂上的图片通过 data.images 透出
        """
        images, results = [], []
        for index, url in enumerate(image_urls, start=1):
            try:
                resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
                resp.raise_for_status()
            except Exception as e:
                return images, results, response_dict(
                    code=1, message=f"第 {index} 张图片下载失败: {e}",
                    data={'images': images, 'results': results})

            uploaded = self.upload_image_to_oss(
                resp.content, ext=guess_image_ext(url, resp.headers.get('Content-Type', '')))
            if uploaded.get('code') != 0:
                return images, results, response_dict(
                    code=1, message=f"第 {index} 张图片转存失败: {uploaded.get('message')}",
                    data={'images': images, 'results': results})
            image_url = uploaded['data']['url']

            try:
                data, params = get_public_data({
                    'ODSerialNo': self._ensure_str(serial),
                    'Tier': tier or '',
                    'Msg': msg,
                    'Img': image_url,
                    'OrderWinTxt': order_win_txt or '',
                    'UserID': self._ensure_str(user_id),
                }, 'LevelOrderProgressAdd', sign_key=self.SignKey, token=token)
                response = self.session.post(self.api_url, params=params, data=data,
                                             timeout=_REQUEST_TIMEOUT)
                one = parse_response(response)
            except Exception as e:
                return images, results, response_dict(
                    code=1, message=f"第 {index} 张图片挂单异常: {e}",
                    data={'images': images, 'results': results})
            if one.get('code') != 0:
                return images, results, response_dict(
                    code=1, message=f"第 {index} 张图片挂单失败: {one.get('message')}",
                    data={'images': images, 'results': results})
            images.append(image_url)
            results.append(one.get('data'))
        return images, results, None

    # 上传首图（接单后须在规定时间内上传；王者荣耀一般 2 张：好友天梯图 + 物品图）
    def upload_first_image(self, serial, image_urls, token, user_id='', msg='首图'):
        """把外链图片转存到代练通图片存储后，逐张以「首图」挂到订单上

        参数:
            serial: 订单号（ODSerialNo）
            image_urls: 图片地址列表（可访问的 http/https 链接）
            token: 登录令牌
            user_id: 用户ID（官方 H5 的 web_query 会自动补 UserID，缺了会「参数错误」）
            msg: 留言文案，默认「首图」
        返回: response_dict，data = {'images': [已挂到订单上的图片地址...],
                                    'results': [每张挂单的上游返回...]}
        """
        images, results, error = self._attach_order_images(
            serial, image_urls, token, user_id, msg)
        if error:
            return error
        return response_dict(code=0, message=f"首图上传成功（{len(images)} 张）",
                             data={'images': images, 'results': results})

    # 上传完单图并申请完单（接单方上传完成凭证，成功后订单进入「等待验收」）
    def upload_end_image(self, serial, image_urls, token, user_id='', uid='',
                         msg='完单图', tier='', order_win_txt='', is_share_trends=1):
        """把外链图片转存到代练通图片存储后，逐张以「完单图」挂到订单上，最后申请完单

        参数:
            serial: 订单号（ODSerialNo）
            image_urls: 图片地址列表（可访问的 http/https 链接）
            token: 登录令牌
            user_id: 用户ID（官方 web_query 会自动补 UserID）
            uid: 账号 UID（USR 开头，支付密码哈希用）
            msg: 留言文案，默认「完单图」
            tier: 段位（官方 H5 的 nowlevel，默认空）
            order_win_txt: 胜场文本（仅 107 且 LevelType2∈{10,13} 的优质单才有值，默认空）
            is_share_trends: 是否同步到动态（1 是 / 0 否，默认 1）
        返回: response_dict，data = {'images': [...], 'results': [...], 'over': 申请完单返回}
        说明：LevelOrderOver 参数顺序 ODSerialNo / Flag / PayPass / IsShareTrends / UserID；
              PayPass 传空密码哈希（完单不涉及支付），与官方 H5 一致。
        """
        images, results, error = self._attach_order_images(
            serial, image_urls, token, user_id, msg, tier=tier, order_win_txt=order_win_txt)
        if error:
            return error

        try:
            data, params = get_public_data({
                'ODSerialNo': self._ensure_str(serial),
                'Flag': '0',
                'PayPass': md5_encrypt(md5_encrypt('') + uid),
                'IsShareTrends': str(is_share_trends),
                'UserID': self._ensure_str(user_id),
            }, 'LevelOrderOver', sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data,
                                         timeout=_REQUEST_TIMEOUT)
            over = parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"图片已上传，但申请完单异常: {e}",
                                 data={'images': images, 'results': results})

        if over.get('code') != 0:
            return response_dict(code=1, message=f"图片已上传，但申请完单失败: {over.get('message')}",
                                 data={'images': images, 'results': results, 'over': over.get('data')})
        return response_dict(code=0, message=f"完单图上传成功（{len(images)} 张），已申请完单",
                             data={'images': images, 'results': results, 'over': over.get('data')})

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

    # 获取各游戏当前的公开订单数量
    def get_games(self):
        """
        获取全部游戏及其当前可接的公开订单数量

        流程:
            1. 调 GameZoneServerList 取游戏清单（GameID -> GameName）
            2. 调 LevelOrderCountGame 取各游戏公开订单数（GameID -> iCount）
            3. 按 GameID 合并，仅保留有订单的游戏，按订单数降序

        返回:
            成功时 data 为 [{"game_id": int, "game_name": str, "order_count": int}, ...]
        """
        try:
            # ---- 1. 游戏清单（GameID -> 名称）----
            data, params = get_public_data({'UserID': '0'}, "GameZoneServerList",
                                           sign_key=self.SignKey)
            games_resp = self.session.post(self.api_url, params=params, data=data,
                                           timeout=_REQUEST_TIMEOUT).json()
            if not isinstance(games_resp, list):
                return response_dict(code=1, message="获取游戏列表失败")
            game_names = {
                item.get('GameID'): item.get('GameName') or ''
                for item in games_resp if isinstance(item, dict)
            }

            # ---- 2. 各游戏公开订单数（GameID -> iCount）----
            data, params = get_public_data({'IsPub': '1', 'UserID': '0'}, "LevelOrderCountGame",
                                           sign_key=self.SignKey)
            count_resp = self.session.post(self.api_url, params=params, data=data,
                                           timeout=_REQUEST_TIMEOUT).json()
            count_list = count_resp.get('LevelOrderCountGame') if isinstance(count_resp, dict) else None
            if not count_list:
                return response_dict(code=1, message="获取游戏订单数量失败")

            # ---- 3. 合并（仅保留有订单的游戏），按订单数降序 ----
            result = [
                {
                    'game_id': item.get('GameID'),
                    'game_name': game_names.get(item.get('GameID'), ''),
                    'order_count': item.get('iCount', 0),
                }
                for item in count_list
            ]
            result.sort(key=lambda x: x['order_count'], reverse=True)
            return response_dict(code=0, message="获取成功", data=result)
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"获取游戏订单数量异常: {e}")

    # 按游戏ID获取该游戏的公开订单列表（分页）
    def get_game_orders(self, game_id, page=1, page_size=20, pg_type=0,
                        order_type='', start_tier='', end_tier='', price_str='',
                        pub_cancel=0, settle_hour=0, filter_type=1,
                        sort_str='', search_str='', user_id=0, token=''):
        """
        按游戏ID获取该游戏的公开订单列表（分页 + 多条件筛选）

        参数:
            game_id: 游戏ID
            page: 页码, 默认1
            page_size: 每页数量, 默认20
            pg_type: 区服, 0全部 1安卓 2IOS
            order_type: 订单类型(上游 LevelType2), 空=不限 / 10=5V5排位赛 / 13=巅峰赛 /
                        15=荣耀战力 / 1920=国标
            start_tier: 初始段位, 空=不限 / 青铜/白银/黄金/铂金/钻石/星耀/王者
            end_tier: 目标段位, 取值同 start_tier
            price_str: 价格区间(最低_最高), 空=不限
            pub_cancel: 仲裁介入率上限(%), 0=不限
            settle_hour: 结算时间上限(小时), 0=不限
            filter_type: 只看本账号可接手的订单, 1=是(默认) / 0=否
            sort_str: 排序, 空=平台默认排序
            search_str: 关键词; 对王者荣耀等游戏即「指定英雄」(多个英雄名用空格分隔)
            user_id: 代练通账号ID, 默认0(匿名); 与 token 一起传才按登录态筛选
            token: 代练通登录令牌, 默认空(匿名); 参与签名

        返回:
            成功时 data 为 {"items": [...], "total": int, "page": int,
                          "page_size": int, "total_pages": int}

        说明:
            上游 LevelOrderList 会一次性返回全部匹配订单（忽略 PageIndex/PageSize），
            故这里由本层按 page/page_size 对结果切片，保证分页语义正确。
            段位/订单类型/filter_type 等账号相关筛选需登录态（user_id + token）才生效。
        """
        try:
            data_params = {
                'IsPub': '1',
                'GameID': self._ensure_str(game_id),
                'ZoneID': '0',
                'ServerID': '0',
                'SearchStr': search_str,
                'STier': start_tier,
                'ETier': end_tier,
                'Sort_Str': sort_str,
                'PageIndex': str(page),
                'PageSize': str(page_size),
                'Price_Str': price_str,
                'PubCancel': str(pub_cancel),
                'SettleHour': str(settle_hour),
                'FilterType': str(filter_type),
                'PGType': str(pg_type),
                'Focused': '-1',
                'OrderType': '0',
                'PubRecommend': '0',
                'Score1': '0',
                'Score2': '0',
                'UserID': self._ensure_str(user_id),
            }
            # 订单类型（LevelType2）为空时不下发该字段：上游对空值会返回异常
            if order_type:
                data_params['LevelType2'] = order_type
            data, params = get_public_data(data_params, "LevelOrderList",
                                           sign_key=self.SignKey, token=token)
            resp = self.session.post(self.api_url, params=params, data=data,
                                     timeout=_REQUEST_TIMEOUT).json()
            if not isinstance(resp, dict) or 'LevelOrderList' not in resp:
                return response_dict(code=1, message="获取订单列表失败")

            all_orders = resp.get('LevelOrderList') or []
            # 上游忽略分页、一次性返回全部匹配订单，故以列表长度作为真实总数
            # （RecordCount 不随筛选变化，不能用）
            total = len(all_orders)
            start = (page - 1) * page_size
            return response_dict(code=0, message="获取订单列表成功", data={
                'items': all_orders[start:start + page_size],
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size if total else 0,
            })
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"获取订单列表异常: {e}")

    # 按关键词搜索订单（参数对齐官网搜索页，可高度自定义）
    def search_orders(self, game_id, search_str='', is_pub=9, pg_type=2, zone_id=0,
                      server_id=0, level_type2='', stier='', etier='', price_str='',
                      pub_cancel=0, settle_hour=0, filter_type=0, sort_str='', focused=-1,
                      order_type=0, pub_recommend=0, score1=0, score2=0,
                      page=1, page_size=20, user_id=0, token=''):
        """
        按关键词搜索订单（默认对齐官网「搜索」页，参数可高度自定义）

        默认值对齐官网搜索页：IsPub=9（优选订单池）、PGType=2（苹果）、FilterType=0。

        参数:
            game_id: 游戏ID（必填）
            search_str: 搜索关键词（如「马可波罗」「安琪拉」）
            is_pub: 订单池, 默认9（对齐官网搜索）
            pg_type: 区服, 0全部 1安卓 2IOS, 默认2
            zone_id: 大区ID, 默认0
            server_id: 服务器ID, 默认0
            level_type2: 订单类型(上游 LevelType2), 空=不限
            stier: 初始段位, 空=不限
            etier: 目标段位, 空=不限
            price_str: 价格区间(最低_最高), 空=不限
            pub_cancel: 仲裁介入率上限(%), 默认0
            settle_hour: 结算时间上限(小时), 默认0
            filter_type: 只看本账号可接手的订单, 1=是 0=否, 默认0
            sort_str: 排序, 空=默认
            focused: 关注筛选, 默认-1
            order_type: 上游 OrderType, 默认0
            pub_recommend: 上游 PubRecommend, 默认0
            score1 / score2: 上游评分筛选位, 默认0
            page: 页码, 默认1
            page_size: 每页数量, 默认20
            user_id / token: 登录态（默认走后台上管的默认账号）

        返回:
            成功时 data 为 {"items": [...], "total": int, "page": int,
                          "page_size": int, "total_pages": int}
        """
        try:
            data_params = {
                'IsPub': str(is_pub),
                'GameID': self._ensure_str(game_id),
                'ZoneID': str(zone_id),
                'ServerID': str(server_id),
                'SearchStr': search_str,
                'STier': stier,
                'ETier': etier,
                'Sort_Str': sort_str,
                'PageIndex': str(page),
                'PageSize': str(page_size),
                'Price_Str': price_str,
                'PubCancel': str(pub_cancel),
                'SettleHour': str(settle_hour),
                'FilterType': str(filter_type),
                'PGType': str(pg_type),
                'Focused': str(focused),
                'OrderType': str(order_type),
                'PubRecommend': str(pub_recommend),
                'Score1': str(score1),
                'Score2': str(score2),
                'UserID': self._ensure_str(user_id),
            }
            # 订单类型（LevelType2）为空时不下发该字段：上游对空值会返回异常
            if level_type2:
                data_params['LevelType2'] = level_type2
            data, params = get_public_data(data_params, "LevelOrderList",
                                           sign_key=self.SignKey, token=token)
            resp = self.session.post(self.api_url, params=params, data=data,
                                     timeout=_REQUEST_TIMEOUT).json()
            if not isinstance(resp, dict) or 'LevelOrderList' not in resp:
                return response_dict(code=1, message="搜索订单失败")

            all_orders = resp.get('LevelOrderList') or []
            # 上游忽略分页、一次性返回全部匹配订单，故以列表长度作为真实总数
            total = len(all_orders)
            start = (page - 1) * page_size
            return response_dict(code=0, message="搜索成功", data={
                'items': all_orders[start:start + page_size],
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size if total else 0,
            })
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"搜索订单异常: {e}")

    # 获取某游戏的热门搜索词
    def get_hot_search_words(self, game_id):
        """
        获取某游戏的热门搜索词（上游 HotSearchWord1）

        参数:
            game_id: 游戏ID

        返回:
            成功时 data 为 {"words": [词...], "tip": 说明文字}
        """
        try:
            game_id = self._ensure_str(game_id)
            timestamp = str(int(time.time()))
            params = {
                'GameID': game_id,
                'timeStamp': timestamp,
                'Sign': md5_encrypt(game_id + timestamp + self.SignKey),
            }
            resp_json = self.session.get(
                'https://quickorder.dailiantong.com.cn/api/share/HotSearchWord1',
                params=params, timeout=_REQUEST_TIMEOUT,
            ).json()
            if not isinstance(resp_json, dict) or str(resp_json.get('ReturnCode')) != '1':
                message = resp_json.get('Message') if isinstance(resp_json, dict) else None
                return response_dict(code=1, message=message or "获取热门搜索词失败")
            return response_dict(code=0, message="获取成功", data={
                'words': resp_json.get('Result') or [],
                'tip': resp_json.get('Result1') or '',
            })
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"获取热门搜索词异常: {e}")

    # 获取全部游戏 + 区服/服务器清单（发布订单选游戏/区服用）
    def get_game_zone_server_list(self):
        """
        获取全部游戏及其区服/服务器清单（上游 GameZoneServerList）

        返回:
            成功时 data 为游戏数组，每项含 GameID / GameName / ZoneList[].ServerList[].Code
        """
        try:
            data, params = get_public_data({'UserID': '0'}, "GameZoneServerList",
                                           sign_key=self.SignKey)
            resp = self.session.post(self.api_url, params=params, data=data,
                                     timeout=_REQUEST_TIMEOUT).json()
            if not isinstance(resp, list):
                return response_dict(code=1, message="获取游戏区服清单失败")
            return response_dict(code=0, message="获取成功", data=resp)
        except requests.exceptions.JSONDecodeError:
            return response_dict(code=1, message="返回数据不是JSON格式")
        except requests.exceptions.Timeout:
            return response_dict(code=1, message="请求超时")
        except Exception as e:
            return response_dict(code=1, message=f"获取游戏区服清单异常: {e}")

    # 发布订单（自定义发布）
    def publish_order(self, title, price, time_limit, ensure1, ensure2, game_mobile,
                      pay_pass, uid, game_account, game_password, game_author_name,
                      requirements, zone_server_id='107103017095500', level_type2='14',
                      game_extra='', mobile='', qq='', insurance=0,
                      max_claim_amount=20, order_type=0, user_id=0, token=''):
        """
        发布订单（自定义发布；标题/要求需自行写明规则，如「指定单」）

        参数:
            title: 订单标题
            price: 订单价格(元)
            time_limit: 代练时限(小时)
            ensure1 / ensure2: 安全保证金 / 效率保证金(元)
            game_mobile: 号主联系方式
            pay_pass: 支付密码（原密码，内部按 md5(md5(pwd)+uid) 处理；可空）
            uid: 账号 UID（USR 开头，支付密码哈希用）
            game_account / game_password / game_author_name: 游戏账号 / 密码 / 角色名
            requirements: 代练要求（写入 Actors 与 ExtStr）
            zone_server_id: 区服ID, 默认王者荣耀-安卓QQ
            level_type2: 订单类型(上游 LevelType2), 默认14
            game_extra: Actors 第 4 段（如 王者荣耀铭文等级 150）
            mobile / qq: 发单者联系方式
            insurance / max_claim_amount / order_type: 上游字段
            user_id / token: 登录态

        返回:
            成功时 data 为上游发布结果（含订单信息，字段由上游定义）
        """
        try:
            # Actors 为 Base64(游戏账号|*|游戏密码|*|角色名|*|附加信息|*|代练要求)
            actors_str = (f"{game_account}|*|{game_password}|*|{game_author_name}"
                          f"|*|{game_extra}|*|{requirements}")
            ext_str = json.dumps({'ID': 4, 'IsEnable': 1, 'Content': requirements,
                                  'Mode': 0, 'Data': [], 'YSData': []}, ensure_ascii=False)
            data, params = get_public_data({
                'ZoneServerID': zone_server_id,
                'Title': title,
                'Price': str(price),
                'TimeLimit': str(time_limit),
                'Ensure1': str(ensure1),
                'Ensure2': str(ensure2),
                'GameMobile': game_mobile,
                'PayPass': md5_encrypt(md5_encrypt(pay_pass) + uid) if pay_pass else '',
                'Mobile': mobile,
                'QQ': qq,
                'LimitAccept': '0',
                'BasePrice': '0',
                'Label1': '',
                'Label2': '',
                'Memo': '',
                'Groups': 'OTHER',
                'Actors': base64_encrypt(actors_str),
                'Members': '',
                'ReCode': '',
                'OverPrice': '',
                'LevelType2': str(level_type2),
                'Insurance': str(insurance),
                'MaxClaimAmount': str(max_claim_amount),
                'OrderType': str(order_type),
                'NonceStr': '',
                'ExtStr': ext_str,
                'ReceiveOrderSetInfoId': '0',
                'IsMerchant': '0',
                'IsNeedExtraDeposit': '0',
                'TransTime': '0',
                'UserID': self._ensure_str(user_id),
            }, "LevelOrderAdd", sign_key=self.SignKey, token=token)
            response = self.session.post(self.api_url, params=params, data=data,
                                         timeout=_REQUEST_TIMEOUT)
            return parse_response(response)
        except Exception as e:
            return response_dict(code=1, message=f"发布订单异常: {e}")
