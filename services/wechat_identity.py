import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import settings
from utils.phone import normalize_phone


class WeChatAPIError(RuntimeError):
    """A sanitized error from a WeChat server-side API call."""


class WeChatIdentityClient:
    CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    PHONE_URL = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"

    def __init__(self, app_id=None, app_secret=None, timeout=10):
        self.app_id = app_id if app_id is not None else settings.WECHAT_APP_ID
        self.app_secret = app_secret if app_secret is not None else settings.WECHAT_APP_SECRET
        self.timeout = timeout

    def _ensure_configured(self):
        if not self.app_id or not self.app_secret:
            raise WeChatAPIError("微信登录暂不可用")

    def _request_json(self, url, *, params=None, payload=None):
        request_url = url
        if params:
            request_url += "?" + urlencode(params)
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = Request(request_url, data=body, headers=headers, method="POST" if body else "GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, ValueError):
            raise WeChatAPIError("微信服务暂不可用") from None
        if not isinstance(result, dict):
            raise WeChatAPIError("微信凭证无效或服务暂不可用")
        try:
            error_code = int(result.get("errcode", 0) or 0)
        except (TypeError, ValueError):
            raise WeChatAPIError("微信凭证无效或服务暂不可用") from None
        if error_code != 0:
            raise WeChatAPIError("微信凭证无效或服务暂不可用")
        return result

    def exchange_login_code(self, code):
        self._ensure_configured()
        result = self._request_json(
            self.CODE2SESSION_URL,
            params={
                "appid": self.app_id,
                "secret": self.app_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
        openid = result.get("openid")
        if not isinstance(openid, str) or not openid:
            raise WeChatAPIError("微信凭证无效或服务暂不可用")
        unionid = result.get("unionid")
        return openid, unionid if isinstance(unionid, str) and unionid else None

    def exchange_phone_code(self, code):
        self._ensure_configured()
        token_result = self._request_json(
            self.TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
            },
        )
        access_token = token_result.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise WeChatAPIError("微信手机号授权暂不可用")
        phone_result = self._request_json(
            self.PHONE_URL,
            params={"access_token": access_token},
            payload={"code": code},
        )
        phone_info = phone_result.get("phone_info") or {}
        if not isinstance(phone_info, dict):
            raise WeChatAPIError("未能取得微信授权手机号")
        phone = phone_info.get("phoneNumber") or phone_info.get("purePhoneNumber")
        if not isinstance(phone, str) or not phone:
            raise WeChatAPIError("未能取得微信授权手机号")
        try:
            return normalize_phone(phone)
        except ValueError:
            raise WeChatAPIError("微信返回的手机号格式无效") from None
