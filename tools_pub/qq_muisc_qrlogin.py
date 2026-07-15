#!/usr/bin/env python3
"""
QQ音乐扫码登录客户端
====================
支持 qqmusic:// deep link 一键登录，qrcode_id 换取 OAuth 凭证实现长久化刷新

关键类:
  - ScanLoginHelper (o0)    — 扫码登录完成请求
  - LoginHelper             — 登录错误码定义
  - ModuleRequestArgs       — CGI 路由逻辑 (musicu/musics/musicw)
  - cyclone.builder.b       — CGI 端点配置

CGI 三端点: musicu.fcg (模块/无签名), musics.fcg (签名), musicw.fcg (JCE)
登录类型: 1=微信, 2=QQ OpenSDK, 6=扫码登录
微信 AppID: wx5aa333606550dfd5
musicKey 有效期: 300 秒, 需 OAuth 凭证刷新
"""

import json
import random
import time
import urllib.parse
import uuid
from typing import Optional

import requests

# ============================================================
# 常量定义
# ============================================================

# 微信 AppID
# ref: WXApiManager static
WX_APP_ID = "wx5aa333606550dfd5"

# QQ 互联 AppID 
# ref: Tencent.createInstance
QQ_APP_ID = "100497308"

# QQ音乐 AppID
# ref: tmeAppID 参数
TME_APP_ID = "qqmusic"

# 登录 CGI 模块/方法
LOGIN_MODULE = "music.login.LoginServer"
LOGIN_METHOD = "Login"

# OpenID 模块
OPENID_MODULE = "OpenId.OpenIdServer"

# 扫码登录 H5 页面
QR_CODE_LOGIN_URL = "https://y.qq.com/m/client/qr_code_login/index.html"
QR_CODE_LOGIN_PARAMS = {
    "tmeAppID": TME_APP_ID,
    "frame": "1",
}

# QQ音乐 CGI 基础 URL
BASE_CGI_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"

# 客户端 User-Agent
CLIENT_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S9080 Build/TP1A.220624.014; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 "
    "Mobile Safari/537.36 QQMusic/13.0.0.0"
)

# 登录类型
# ref: LoginHelper.LoginType
LOGIN_TYPE_WX = 1
LOGIN_TYPE_QQ_OPENSDK = 2
LOGIN_TYPE_PHONE = 3
LOGIN_TYPE_ONE_CLICK_PHONE = 4
LOGIN_TYPE_SCAN_QRCODE = 6


# ============================================================
# 设备标识生成
# ============================================================

def generate_device_id() -> str:
    """生成设备 ID"""
    return str(uuid.uuid4()).replace("-", "")[:32]


def generate_qimei36() -> str:
    """生成 qimei36"""
    chars = "0123456789abcdef"
    return ''.join(random.choice(chars) for _ in range(36))


# ============================================================
# QQ音乐 CGI 客户端
# ============================================================

class QQMusicCGIClient:
    """
    QQ音乐 CGI 客户端
    ref: com.tencent.qqmusiccommon.cgi.request.ModuleRequestArgs
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": CLIENT_UA,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json; charset=utf-8",
            "Referer": "https://y.qq.com/",
            "Origin": "https://y.qq.com",
        })

        # 登录态
        self.uin: str = ""
        self.encrypt_uin: str = ""
        self.music_key: str = ""
        self.refresh_key: str = ""
        self.open_id: str = ""
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.union_id: str = ""
        self.login_type: int = 0

        # musicKey 过期信息
        self._key_issued_at: int = 0
        self._key_expires_at: int = 0

    def _cgi_request(self, module: str, method: str, params: dict) -> dict:
        """发送 CGI 请求"""
        body = {
            "comm": {
                "ct": 11,
                "cv": 13000000,
                "tmeAppID": TME_APP_ID,
                "uin": self.uin,
                "uid": "",
                "format": "json",
                "platform": "android",
            },
            "req": {
                "module": module,
                "method": method,
                "param": params,
            },
        }

        resp = self.session.post(BASE_CGI_URL, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ---- 登录请求 ----

    def login_with_wx_code(
        self,
        code: str,
        openid: str = "",
        refresh_token: str = "",
        uin: str = "",
        music_key: str = "",
        union_id: str = "",
        refresh_key: str = "",
        login_mode: int = 1,
    ) -> dict:
        """
        微信授权码登录

        ref: WXLoginHelper.z() -> requestMusicKey()
        login_mode: 1=首次登录, 2=刷新
        """
        params = {"code": code}

        if openid:
            params["openid"] = openid
        if refresh_token:
            params["refresh_token"] = refresh_token
        if uin:
            params["str_musicid"] = uin
        if music_key:
            params["musickey"] = music_key
        if union_id:
            params["union_id"] = union_id
        if refresh_key:
            params["refresh_key"] = refresh_key

        params["loginMode"] = login_mode

        return self._cgi_request(LOGIN_MODULE, LOGIN_METHOD, params)

    def get_auth_access_token(
        self,
        openid: str,
        refresh_token: str,
        uin: str = "",
        music_key: str = "",
        union_id: str = "",
    ) -> dict:
        """
        获取/刷新 AccessToken (轻量刷新)

        ref: WXLoginHelper.o() -> getAuthAccessToken()
        loginMode=2, onlyNeedAccessToken=1
        """
        params = {
            "openid": openid,
            "refresh_token": refresh_token,
            "onlyNeedAccessToken": 1,
            "loginMode": 2,
        }
        if uin:
            params["str_musicid"] = uin
        if music_key:
            params["musickey"] = music_key
        if union_id:
            params["union_id"] = union_id

        return self._cgi_request(LOGIN_MODULE, LOGIN_METHOD, params)

    def login_with_qq_oauth(
        self,
        openid: str,
        access_token: str = "",
        refresh_token: str = "",
        music_id: str = "",
        music_key: str = "",
        refresh_key: str = "",
        code: str = "",
        login_mode: int = 1,
    ) -> dict:
        """
        QQ OpenSDK OAuth 登录/刷新

        ref: qqopensdklogin.o.o() -> QQRefreshKey
        """
        params = {}

        if openid:
            params["openid"] = openid
        if access_token:
            params["access_token"] = access_token
        if refresh_token:
            params["refresh_token"] = refresh_token
        if music_id:
            try:
                params["musicid"] = int(music_id)
            except (ValueError, TypeError):
                params["musicid"] = music_id
        if music_key:
            params["musickey"] = music_key
        if refresh_key:
            params["refresh_key"] = refresh_key
        if code:
            params["code"] = code

        params["loginMode"] = login_mode
        params["loginType"] = 2  # QQ OpenSDK

        return self._cgi_request(LOGIN_MODULE, LOGIN_METHOD, params)

    def login_with_wx_oauth_full(
        self,
        openid: str = "",
        refresh_token: str = "",
        uin: str = "",
        music_key: str = "",
        union_id: str = "",
        refresh_key: str = "",
        code: str = "",
        login_mode: int = 2,
    ) -> dict:
        """
        微信 OAuth 完整登录/刷新 (requestMusicKey)

        ref: WXLoginHelper.z()
        """
        params = {}

        if code:
            params["code"] = code
        if openid:
            params["openid"] = openid
        if refresh_token:
            params["refresh_token"] = refresh_token
        if uin:
            params["str_musicid"] = uin
        if music_key:
            params["musickey"] = music_key
        if union_id:
            params["union_id"] = union_id
        if refresh_key:
            params["refresh_key"] = refresh_key

        params["loginMode"] = login_mode
        params["loginType"] = 1  # 微信

        return self._cgi_request(LOGIN_MODULE, LOGIN_METHOD, params)

    def complete_qr_login(self, uin: str, qrcode_id: str, token: str) -> dict:
        """
        QR 码登录完成 — 用 qrcode_id 换取完整 OAuth 凭证

        ref: ScanLoginHelper.j() (com.tencent.qqmusic.business.user.o0)

        qrcode_id 充当一次性授权令牌, 服务端验证后返回:
          - openid, access_token, refresh_token
          - refresh_key, union_id, musickey, loginType
        """
        params = {
            "tmeAppID": TME_APP_ID,
            "str_musicid": uin,
            "qrCodeID": qrcode_id,
            "token": token,
            "loginType": 6,
        }
        return self._cgi_request(LOGIN_MODULE, LOGIN_METHOD, params)

    # ---- OpenID/扫码相关 ----

    def qrcode_auth(self, app_id: str, auth_code: str) -> dict:
        """
        扫码授权

        ref: OpenIDAuthManager.v() -> startQRCodeAuth()
        Module: OpenId.OpenIdServer / QrcodeAuth
        """
        params = {
            "appId": app_id,
            "authCode": auth_code,
        }
        return self._cgi_request(OPENID_MODULE, "QrcodeAuth", params)

    def check_auth_code(self, app_id: str, auth_code: str) -> dict:
        """
        检查授权码有效性

        ref: OpenIDAuthManager.i() -> checkAuthCode()
        """
        params = {
            "appId": app_id,
            "authCode": auth_code,
        }
        return self._cgi_request(OPENID_MODULE, "CheckAuthCode", params)

    def check_token(self, app_id: str, open_id: str, open_token: str) -> dict:
        """
        检查 OpenID Token 有效性

        ref: OpenIDAuthManager.l() -> checkToken()
        """
        params = {
            "appId": app_id,
            "openId": open_id,
            "openToken": open_token,
        }
        return self._cgi_request(OPENID_MODULE, "CheckToken", params)

    def auth_third_party(
        self, app_id: str, package_name: str, encrypt_string: str, auth_type: int = 4
    ) -> dict:
        """
        第三方授权请求

        ref: OpenIDAuthManager.h() -> authRequestImpl()
        Module: OpenId.OpenIdServer / Auth
        """
        params = {
            "appId": app_id,
            "packageName": package_name,
            "encryptString": encrypt_string,
        }
        return self._cgi_request(OPENID_MODULE, "Auth", params)

    # ---- 登录后请求 ----

    def on_login_requests(self) -> dict:
        """
        登录后批量请求 (VIP信息/用户数据等)

        ref: OnLoginRequest.b()
        """
        modules = [
            ("music.vip.VipLoginServer", "VIP_LOGIN"),
            ("music.vip.VipReminderTipsServer", "VIP_REMINDER_TIPS"),
            ("music.vip.MusicBossEngineServer", "MUSIC_BOSS_ENGINE"),
            ("music.user.UserBuyListServer", "USER_BUY_LIST"),
            ("music.user.PrivacyLockServer", "PRIVACY_LOCK"),
            ("music.user.NameCertifiedServer", "NAME_CERTIFIED"),
        ]
        results = {}
        for module, method in modules:
            try:
                results[f"{module}/{method}"] = self._cgi_request(module, method, {})
            except Exception as e:
                results[f"{module}/{method}"] = {"error": str(e)}
        return results

    # ---- 状态管理 ----

    def apply_login_result(self, result: dict, login_type: int = LOGIN_TYPE_WX):
        """
        将登录结果应用到客户端状态

        解析 LoginKeyResult (class y) 并更新内部字段
        响应格式: {req: {code, data}, req_1: ...} 或 {code, data}
        """
        data_section = None
        if "req" in result and isinstance(result["req"], dict):
            req = result["req"]
            code = req.get("code", -1)
            if code != 0:
                raise LoginError(
                    code=code,
                    sub_code=req.get("subCode", 0),
                    error_tips="",
                    feedback_url="",
                )
            data_section = req.get("data", {})
        else:
            code = result.get("code", -1)
            if code != 0:
                raise LoginError(
                    code=code,
                    sub_code=result.get("subCode", 0),
                    error_tips=result.get("errorTips", ""),
                    feedback_url=result.get("feedbackUrl", ""),
                )
            data_section = result.get("data", {})

        if data_section and isinstance(data_section, dict):
            self.music_key = data_section.get("musickey", self.music_key)
            self.refresh_key = data_section.get("refresh_key", self.refresh_key)
            self.open_id = data_section.get("openid", self.open_id)
            self.access_token = data_section.get("access_token", self.access_token)
            self.refresh_token = data_section.get("refresh_token", self.refresh_token)
            self.union_id = data_section.get("union_id", self.union_id)

            uin = data_section.get("str_musicid", "") or str(data_section.get("musicid", ""))
            if uin:
                self.uin = str(uin)

            encrypt_uin = data_section.get("encryptUin", "")
            if encrypt_uin:
                self.encrypt_uin = encrypt_uin
                if not self.uin:
                    self.uin = encrypt_uin

            resp_login_type = data_section.get("loginType", 0)
            if isinstance(resp_login_type, str):
                resp_login_type = int(resp_login_type) if resp_login_type.isdigit() else 0
            if resp_login_type:
                self.login_type = resp_login_type
            elif login_type:
                self.login_type = login_type

            expired_at = data_section.get("expired_at", 0)
            if expired_at:
                self._key_expires_at = int(expired_at)

        return self

    @property
    def is_login(self) -> bool:
        """检查是否已登录"""
        return bool(self.uin and self.music_key)


# ============================================================
# 扫码登录流程
# ============================================================

class QQMusicScanLogin:
    """
    QQ音乐扫码登录完整实现

    还原自客户端调用链:
      LoginActivity.loginByScanQrCode()
        -> UrlMapper.k("mobile_qrcode_login", fallback)
        -> WebViewJump.g(activity, url, bundle)
        -> WebView 加载 H5 页面 -> 用户扫码确认
        -> qqmusic://qq.com/other/scanLoginResult?p=... deep link 回调

    也支持直接微信 OAuth 登录:
      LoginActivity.loginToWX()
        -> WXLoginHelper -> WXApiManager -> 微信 SDK 授权
        -> WXEntryActivity.onResp() -> code -> music.login.LoginServer/Login
    """

    def __init__(self):
        self.client = QQMusicCGIClient()
        self._device_id = generate_device_id()
        self._qimei = generate_qimei36()
        self._qrcode_id: str = ""

    # ---- 扫码登录 URL ----

    def get_qr_login_url(self) -> str:
        """
        生成扫码登录页面 URL

        对应客户端: UrlMapper.k("mobile_qrcode_login") + ct/cv 参数

        返回可在浏览器中打开的 H5 扫码页面 URL。
        """
        params = {
            **QR_CODE_LOGIN_PARAMS,
            "ct": "11",
            "cv": "13000000",
        }
        return QR_CODE_LOGIN_URL + "?" + urllib.parse.urlencode(params)

    def get_qr_code_image_url(self) -> str:
        """获取二维码图片直链 (推测性, 实际客户端通过 H5 页面内嵌)"""
        return (
            "https://y.qq.com/m/client/qr_code_login/qrcode.png"
            f"?tmeAppID={TME_APP_ID}"
            f"&t={int(time.time() * 1000)}"
        )

    # ---- 轮询扫码结果 ----

    def poll_scan_result(self, session_id: str) -> Optional[dict]:
        """
        轮询扫码结果

        对应 H5 页面中的 setInterval 轮询逻辑。
        返回 None 表示尚未扫码, dict 表示已扫码。
        """
        resp = self.client.session.get(
            "https://y.qq.com/m/client/qr_code_login/check",
            params={
                "tmeAppID": TME_APP_ID,
                "sid": session_id,
                "_": int(time.time() * 1000),
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0 and data.get("data"):
            return data["data"]
        return None

    # ---- QQ 扫码登录 ----

    def login_with_qq_scan(self, auth_code: str, app_id: str = QQ_APP_ID) -> dict:
        """
        QQ 扫码登录

        对应客户端: OpenIDAuthManager.v() -> QrcodeAuth
        """
        result = self.client.qrcode_auth(app_id, auth_code)
        if result.get("code") == 0:
            callback_url = result.get("data", {}).get("callbackUrl", "")
            encrypt_string = result.get("data", {}).get("encryptString", "")
            if callback_url:
                resp = self.client.session.post(
                    callback_url,
                    json={"encryptString": encrypt_string},
                    timeout=10,
                )
                return resp.json()
        return result

    # ---- 微信扫码登录 ----

    def login_with_wx_code(
        self,
        code: str,
        openid: str = "",
        refresh_token: str = "",
        uin: str = "",
        music_key: str = "",
        union_id: str = "",
    ) -> QQMusicCGIClient:
        """
        微信授权码登录 (微信扫码后的 code 交换)

        对应客户端完整流程:
          1. WXLoginHelper.sendReq -> 微信 SDK 授权
          2. WXEntryActivity.onResp -> 收到授权码
          3. WXLoginHelper.requestMusicKey(code) -> Login CGI
          4. 解析 CommonLoginInfo 保存 musicKey/refreshKey
        """
        result = self.client.login_with_wx_code(
            code=code,
            openid=openid,
            refresh_token=refresh_token,
            uin=uin,
            music_key=music_key,
            union_id=union_id,
            login_mode=1 if not uin else 2,
        )

        self.client.apply_login_result(result, LOGIN_TYPE_WX)
        return self.client

    def refresh_wx_login(self) -> QQMusicCGIClient:
        """
        刷新微信登录态

        对应客户端: WXLoginHelper.o() -> getAuthAccessToken()
        """
        result = self.client.get_auth_access_token(
            openid=self.client.open_id,
            refresh_token=self.client.refresh_token,
            uin=self.client.uin,
            music_key=self.client.music_key,
            union_id=self.client.union_id,
        )
        if result.get("code") == 0:
            data = result.get("data", {})
            self.client.access_token = data.get("accessToken", "")

        return self.client

    # ---- Deep Link 解析 (qqmusic:// 协议) ----

    @staticmethod
    def parse_scan_login_url(url: str) -> dict:
        """
        解析 qqmusic://qq.com/other/scanLoginResult?p=... deep link

        对应客户端: WebViewJump.G() -> WebViewPluginEngine.handleRequest()

        p 参数解码后包含 cookies 字典, 关键字段:
          - qqmusic_uin, qqmusic_key: 临时登录态
          - qrcode_id: 一次性授权令牌
          - tmeLoginType: 1=微信, 2=QQ

        返回: {"cookies": {...}, "app_type": "...", "source_url": "..."}
        """
        parsed = urllib.parse.urlparse(url)

        query_params = urllib.parse.parse_qs(parsed.query)
        p_encoded = query_params.get("p", [None])[0]
        if not p_encoded:
            raise ValueError("URL 中缺少 p 参数")

        p_json = urllib.parse.unquote(p_encoded)
        data = json.loads(p_json)

        source_url = query_params.get("source", [""])[0]

        cookies_raw = data.get("cookies", {})
        cookies_flat = {}
        for key, val in cookies_raw.items():
            if isinstance(val, dict) and "value" in val:
                cookies_flat[key] = val["value"]
            else:
                cookies_flat[key] = val

        return {
            "cookies": cookies_flat,
            "app_type": data.get("appType", ""),
            "source_url": source_url,
        }

    @staticmethod
    def parse_cookies_raw(cookies_json: str) -> dict:
        """
        解析原始 cookies JSON

        输入: {"qqmusic_uin": {"value": "123", ...}, ...}
        输出: {"qqmusic_uin": "123", ...}
        """
        raw = json.loads(cookies_json) if isinstance(cookies_json, str) else cookies_json
        flat = {}
        for key, val in raw.items():
            if isinstance(val, dict) and "value" in val:
                flat[key] = val["value"]
            else:
                flat[key] = val
        return flat

    def import_from_cookies(self, cookies: dict, complete: bool = False):
        """
        从扁平化 Cookie 字典导入登录态

        :param cookies: 扁平化的 Cookie 字典
        :param complete: 是否自动调用 complete_qr_login() 换取完整 OAuth 凭证
        """
        login_type_str = cookies.get("tmeLoginType", "0")
        login_type_map = {"1": LOGIN_TYPE_WX, "2": LOGIN_TYPE_QQ_OPENSDK}
        login_type = login_type_map.get(login_type_str, 0)

        self.client.uin = cookies.get("qqmusic_uin", "")
        self.client.music_key = cookies.get("qqmusic_key", "")
        self.client.login_type = login_type

        key_at = int(cookies.get("qqmusic_key_at", "0"))
        expires_in = int(cookies.get("qqmusic_key_expiresIn", "0"))
        if key_at and expires_in:
            self.client._key_expires_at = key_at + expires_in
            self.client._key_issued_at = key_at

        self._qrcode_id = cookies.get("qrcode_id", "")

        # 注入 Cookie 到 requests Session
        for cookie_name in ("qqmusic_key", "qqmusic_uin", "qrcode_id", "euin", "tmeAppID", "tmeLoginType"):
            cookie_value = cookies.get(cookie_name, "")
            if cookie_value:
                self.client.session.cookies.set(cookie_name, cookie_value, domain=".y.qq.com")

        # 自动完成 QR 登录换取完整 OAuth 凭证
        if complete and self._qrcode_id and self.client.uin and self.client.music_key:
            try:
                result = self.client.complete_qr_login(
                    uin=self.client.uin,
                    qrcode_id=self._qrcode_id,
                    token=self.client.music_key,
                )
                self.client.apply_login_result(result, login_type)
                print(f"[QR完成] 已换取完整 OAuth 凭证, 支持后续刷新")
            except LoginError as e:
                print(f"[QR完成] 换取 OAuth 失败: {e}")
            except Exception as e:
                print(f"[QR完成] 网络异常: {e}")

        return self

    def import_from_deep_link(self, url: str, complete: bool = True):
        """
        从 qqmusic:// deep link 导入登录态

        扫码确认后将重定向 URL 粘贴到命令行即可登录。
        默认自动调用 complete_qr_login() 换取完整 OAuth 凭证。

        :param url: qqmusic:// 协议的 deep link URL
        :param complete: 是否自动完成 QR 登录换取 OAuth 凭证 (默认 True)
        """
        data = self.parse_scan_login_url(url)
        return self.import_from_cookies(data["cookies"], complete=complete)

    def try_refresh_from_cookies(self) -> dict:
        """
        尝试用 qrcode_id 换取完整 OAuth 凭证

        返回服务端响应, 调用者需检查 code 是否为 0。
        """
        if not self._qrcode_id:
            raise ValueError("缺少 qrcode_id, 无法完成 QR 登录。需要完整的 deep link 导入。")

        return self.client.complete_qr_login(
            uin=self.client.uin,
            qrcode_id=self._qrcode_id,
            token=self.client.music_key,
        )

    def complete_qr_and_refresh(self) -> QQMusicCGIClient:
        """
        完成 QR 码登录并获取可刷新的 OAuth 凭证

        组合: complete_qr_login() -> apply_login_result()
        """
        result = self.try_refresh_from_cookies()
        self.client.apply_login_result(result, self.client.login_type)
        return self.client

    # ---- OAuth 刷新 ----

    def refresh_wx_music_key(
        self,
        openid: str,
        refresh_token: str,
        union_id: str = "",
    ) -> QQMusicCGIClient:
        """
        刷新微信登录的 musicKey (完整 OAuth 刷新)

        对应客户端: WXLoginHelper.z() + loginMode=2

        必需参数 (来自 OAuth 流程):
          - openid: 微信 OpenID
          - refresh_token: 微信 refresh_token
        """
        result = self.client.login_with_wx_oauth_full(
            openid=openid,
            refresh_token=refresh_token,
            uin=self.client.uin,
            music_key=self.client.music_key,
            union_id=union_id,
            refresh_key=self.client.refresh_key,
            login_mode=2,
        )
        self.client.apply_login_result(result, LOGIN_TYPE_WX)
        return self.client

    def refresh_qq_music_key(
        self,
        openid: str,
        access_token: str,
        refresh_token: str,
    ) -> QQMusicCGIClient:
        """
        刷新 QQ 登录的 musicKey (完整 OAuth 刷新)

        对应客户端: qqopensdklogin.o.o() + loginMode=2

        必需参数 (来自 QQ OpenSDK OAuth 流程):
          - openid: QQ OpenID
          - access_token: QQ access_token
          - refresh_token: QQ refresh_token
        """
        result = self.client.login_with_qq_oauth(
            openid=openid,
            access_token=access_token,
            refresh_token=refresh_token,
            music_id=self.client.uin,
            music_key=self.client.music_key,
            refresh_key=self.client.refresh_key,
            login_mode=2,
        )
        self.client.apply_login_result(result, LOGIN_TYPE_QQ_OPENSDK)
        return self.client

    # ---- 状态查询 ----

    def to_cookie_string(self) -> str:
        """导出为 Netscape cookie 格式字符串, 可直接用于浏览器或 curl"""
        uin = self.client.uin or self.client.encrypt_uin
        parts = []
        if uin:
            parts.append(f"qqmusic_uin={uin}")
        if self.client.music_key:
            parts.append(f"qqmusic_key={self.client.music_key}")
        return "; ".join(parts)

    @property
    def is_login(self) -> bool:
        return self.client.is_login

    def get_credentials(self) -> dict:
        """导出当前登录凭证"""
        return {
            "uin": self.client.uin,
            "encrypt_uin": self.client.encrypt_uin,
            "music_key": self.client.music_key,
            "refresh_key": self.client.refresh_key,
            "open_id": self.client.open_id,
            "access_token": self.client.access_token,
            "refresh_token": self.client.refresh_token,
            "union_id": self.client.union_id,
            "login_type": self.client.login_type,
            "device_id": self._device_id,
            "qimei36": self._qimei,
        }

    def import_credentials(self, creds: dict):
        """导入登录凭证"""
        self.client.uin = creds.get("uin", "")
        self.client.encrypt_uin = creds.get("encrypt_uin", "")
        self.client.music_key = creds.get("music_key", "")
        self.client.refresh_key = creds.get("refresh_key", "")
        self.client.open_id = creds.get("open_id", "")
        self.client.access_token = creds.get("access_token", "")
        self.client.refresh_token = creds.get("refresh_token", "")
        self.client.union_id = creds.get("union_id", "")
        self.client.login_type = creds.get("login_type", LOGIN_TYPE_WX)
        self._device_id = creds.get("device_id", self._device_id)
        self._qimei = creds.get("qimei36", self._qimei)


# ============================================================
# 错误类型
# ============================================================

class LoginError(Exception):
    """
    登录错误

    对应客户端: LoginErrorMessage

    常见错误码:
      1000  - 登录过期
      2010  - 登录过期 >= 30天
      20279 - 设备超限
      20450 - 需要验证/封禁
      101010 - 需要图形验证码
      104400/104401 - QQ 登录过期
    """

    def __init__(self, code: int, sub_code: int = 0, error_tips: str = "", feedback_url: str = ""):
        self.code = code
        self.sub_code = sub_code
        self.error_tips = error_tips
        self.feedback_url = feedback_url
        super().__init__(f"LoginError(code={code}, subCode={sub_code}, tips={error_tips})")


# ============================================================
# 命令行入口
# ============================================================

def main():
    """命令行扫码登录入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="QQ音乐扫码登录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 扫码后粘贴 deep link 一键登录:
  python main.py --scan-result "qqmusic://qq.com/other/scanLoginResult?p=..."

  # 从 HAR/浏览器复制 cookies JSON 导入:
  python main.py --cookies '{"qqmusic_uin":{"value":"123"},...}'

  # 获取扫码登录 URL:
  python main.py --get-qr-url

  # 使用微信 code 完成完整 OAuth 登录:
  python main.py --wx-code <微信授权码>

  # 尝试刷新 (需要 OAuth 凭证):
  python main.py --try-refresh --credentials creds.json

  # 导出当前凭证:
  python main.py --export-creds creds.json
        """,
    )

    parser.add_argument("--scan-result", type=str, help="qqmusic:// 协议的扫码结果 deep link")
    parser.add_argument("--cookies", type=str, help="HAR/浏览器 cookies JSON 字符串")
    parser.add_argument("--get-qr-url", action="store_true", help="获取扫码登录页面 URL")
    parser.add_argument("--wx-code", type=str, help="微信 OAuth 授权码")
    parser.add_argument("--openid", type=str, default="", help="OAuth OpenID (WX/QQ)")
    parser.add_argument("--try-refresh", action="store_true", help="尝试刷新 musicKey (需要 OAuth 凭证)")
    parser.add_argument("--credentials", type=str, help="登录凭证文件路径 (JSON)")
    parser.add_argument("--export-creds", type=str, help="导出凭证到文件 (JSON)")

    args = parser.parse_args()

    login = QQMusicScanLogin()

    # 导入凭证文件
    if args.credentials:
        with open(args.credentials, "r") as f:
            creds = json.load(f)
        login.import_credentials(creds)
        print(f"[凭证] 已导入: uin={login.client.uin[:12] if login.client.uin else 'N/A'}")

    # Deep Link 自动登录
    if args.scan_result:
        print("[DeepLink] 解析扫码结果并完成登录...")
        try:
            login.import_from_deep_link(args.scan_result, complete=True)
            login_type_name = {LOGIN_TYPE_WX: "微信", LOGIN_TYPE_QQ_OPENSDK: "QQ"}.get(
                login.client.login_type, "未知"
            )
            has_oauth = bool(login.client.refresh_token)
            print(f"[DeepLink] 登录成功!")
            print(f"  uin:          {login.client.uin}")
            print(f"  music_key:    {login.client.music_key[:32]}...")
            print(f"  登录方式:     {login_type_name} (type={login.client.login_type})")
            print(f"  open_id:      {login.client.open_id[:24] if login.client.open_id else 'N/A'}...")
            print(f"  refresh_token:{login.client.refresh_token[:24] if login.client.refresh_token else 'N/A'}...")
            print(f"  refresh_key:  {login.client.refresh_key[:24] if login.client.refresh_key else 'N/A'}...")
            print(f"  cookie:       {login.to_cookie_string()}")
            if has_oauth:
                print(f"  [OK] 已获得完整 OAuth 凭证, 支持长期刷新!")
            else:
                print(f"  [!] OAuth 凭证缺失, qrcode_id 可能已过期")

            if args.export_creds:
                creds = login.get_credentials()
                with open(args.export_creds, "w") as f:
                    json.dump(creds, f, indent=2, ensure_ascii=False)
                print(f"  凭证已导出到: {args.export_creds}")

        except Exception as e:
            print(f"[DeepLink] 失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    # Cookie 导入
    if args.cookies:
        print("[Cookie] 解析 cookies 并完成登录...")
        try:
            cookies_flat = QQMusicScanLogin.parse_cookies_raw(args.cookies)
            login.import_from_cookies(cookies_flat, complete=True)
            login_type_name = {LOGIN_TYPE_WX: "微信", LOGIN_TYPE_QQ_OPENSDK: "QQ"}.get(
                login.client.login_type, "未知"
            )
            has_oauth = bool(login.client.refresh_token)
            print(f"[Cookie] 导入成功!")
            print(f"  uin:          {login.client.uin}")
            print(f"  music_key:    {login.client.music_key[:32]}...")
            print(f"  登录方式:     {login_type_name}")
            if has_oauth:
                print(f"  [OK] 已获得完整 OAuth 凭证, 支持长期刷新!")
            else:
                print(f"  [!] OAuth 凭证缺失, qrcode_id 可能已过期")
        except Exception as e:
            print(f"[Cookie] 解析失败: {e}")
            return 1

    # 获取扫码 URL
    if args.get_qr_url:
        url = login.get_qr_login_url()
        print(f"扫码登录 URL:")
        print(f"  {url}")

    # 微信 code 登录
    if args.wx_code:
        print(f"[WX] 正在使用微信授权码登录...")
        try:
            client = login.login_with_wx_code(
                code=args.wx_code,
                openid=args.openid,
            )
            creds = login.get_credentials()
            print(f"[WX] 登录成功!")
            print(f"  uin:          {creds['uin'][:12]}...")
            print(f"  music_key:    {creds['music_key'][:32]}...")
            print(f"  refresh_key:  {creds['refresh_key'][:32] if creds['refresh_key'] else 'N/A'}...")
            print(f"  open_id:      {creds['open_id'][:16] if creds['open_id'] else 'N/A'}...")
            print(f"  refresh_token:{creds['refresh_token'][:16] if creds['refresh_token'] else 'N/A'}...")
            print()
            print("[OK] 已获得完整 OAuth 凭证, 支持后续刷新。")

            if args.export_creds:
                with open(args.export_creds, "w") as f:
                    json.dump(creds, f, indent=2, ensure_ascii=False)
                print(f"凭证已导出到: {args.export_creds}")

        except LoginError as e:
            print(f"[WX] 登录失败: {e}")
            return 1
        except Exception as e:
            print(f"[WX] 请求异常: {e}")
            return 1

    # 尝试刷新
    if args.try_refresh:
        if not login.is_login:
            print("[Refresh] 未登录, 请先导入凭证")
            return 1

        has_oauth = bool(login.client.refresh_token)
        if not has_oauth and login._qrcode_id:
            print("[Refresh] 尝试用 qrcode_id 换取 OAuth 凭证...")
            try:
                login.complete_qr_and_refresh()
                has_oauth = bool(login.client.refresh_token)
                if has_oauth:
                    print(f"[Refresh] QR 完成成功! 已获得 OAuth 凭证")
                    print(f"  open_id:      {login.client.open_id[:24]}...")
                    print(f"  refresh_token:{login.client.refresh_token[:24]}...")
                else:
                    print("[Refresh] QR 完成返回成功但未包含 refresh_token")
            except LoginError as e:
                print(f"[Refresh] QR 完成失败: {e}")
                print("    qrcode_id 可能已过期, 请重新扫码")
                return 1
            except Exception as e:
                print(f"[Refresh] QR 完成异常: {e}")
                return 1

        if has_oauth:
            print("[Refresh] 正在用 OAuth 凭证刷新 musicKey...")
            try:
                if login.client.login_type == LOGIN_TYPE_WX:
                    login.refresh_wx_music_key(
                        openid=login.client.open_id,
                        refresh_token=login.client.refresh_token,
                        union_id=login.client.union_id,
                    )
                else:
                    login.refresh_qq_music_key(
                        openid=login.client.open_id,
                        access_token=login.client.access_token,
                        refresh_token=login.client.refresh_token,
                    )
                print(f"[Refresh] 刷新成功!")
                print(f"  uin:          {login.client.uin}")
                print(f"  music_key:    {login.client.music_key[:32]}...")
                print(f"  refresh_key:  {login.client.refresh_key[:24] if login.client.refresh_key else 'N/A'}...")
                print(f"  login_type:   {login.client.login_type}")
                print(f"  cookie:       {login.to_cookie_string()}")

                if args.export_creds:
                    creds = login.get_credentials()
                    with open(args.export_creds, "w") as f:
                        json.dump(creds, f, indent=2, ensure_ascii=False)
                    print(f"  凭证已导出到: {args.export_creds}")
            except Exception as e:
                print(f"[Refresh] 刷新失败: {e}")
                return 1
        else:
            print("[Refresh] 缺少 OAuth 凭证且无 qrcode_id, 无法刷新")
            print("    请重新扫码登录: python main.py --scan-result \"<URL>\"")
            return 1

    # 仅导出凭证
    if args.export_creds and not any([args.wx_code, args.scan_result, args.try_refresh]):
        if not login.is_login:
            print("未登录, 无法导出凭证")
            return 1
        creds = login.get_credentials()
        with open(args.export_creds, "w") as f:
            json.dump(creds, f, indent=2, ensure_ascii=False)
        print(f"凭证已导出到: {args.export_creds}")

    if not any([args.scan_result, args.cookies, args.get_qr_url, args.wx_code, args.try_refresh]):
        parser.print_help()

    return 0


if __name__ == "__main__":
    exit(main())
