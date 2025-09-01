# trading_bot/trading_core/auth.py
import json
import requests
import pyotp
import hashlib
import base64
import jwt
import os
from urllib import parse
from datetime import datetime, timezone
from pathlib import Path


class FyersAuthClient:
    """
    Handles the Fyers authentication process, including token validation,
    refreshing, and the full login flow if necessary.
    """
    BASE_URL = "https://api-t2.fyers.in/vagator/v2"
    BASE_URL_2 = "https://api-t1.fyers.in/api/v3"

    def __init__(self, fy_id, app_id, app_type, app_secret, totp_key, pin, redirect_uri, token_file="tokens.json"):
        self.fy_id = fy_id
        self.app_id = app_id
        self.app_type = app_type
        self.app_secret = app_secret
        self.totp_key = totp_key
        self.pin = pin
        self.redirect_uri = redirect_uri
        self.token_file = Path(token_file)
        self.app_id_hash = hashlib.sha256(f"{app_id}-{app_type}:{app_secret}".encode('utf-8')).hexdigest()

    def _post(self, url, payload, headers=None, expected_status=200):
        resp = requests.post(url, json=payload, headers=headers or {})
        if resp.status_code != expected_status:
            raise RuntimeError(f"API Error {resp.status_code}: {resp.text}")
        return resp.json()

    @staticmethod
    def _is_jwt_valid(token):
        try:
            payload_data = jwt.decode(token, options={"verify_signature": False})
            exp_timestamp = payload_data.get('exp')
            if not exp_timestamp:
                return False
            exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            return exp_datetime > datetime.now(timezone.utc)
        except Exception:
            return False

    def _load_tokens(self):
        if self.token_file.exists():
            with open(self.token_file, 'r') as f:
                return json.load(f)
        return None

    def _save_tokens(self, tokens):
        with open(self.token_file, 'w') as f:
            json.dump(tokens, f)

    def refresh_access_token(self, refresh_token):
        try:
            data = self._post(f"{self.BASE_URL_2}/validate-authcode", {
                "grant_type": "refresh_token",
                "appIdHash": self.app_id_hash,
                "refresh_token": refresh_token
            })
            tokens = {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token)
            }
            self._save_tokens(tokens)
            return tokens
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return None

    def send_login_otp(self):
        data = self._post(f"{self.BASE_URL}/send_login_otp", {"fy_id": self.fy_id, "app_id": "2"})
        return data["request_key"]

    def generate_totp(self):
        return pyotp.TOTP(self.totp_key).now()

    def verify_totp(self, request_key, totp):
        data = self._post(f"{self.BASE_URL}/verify_otp", {"request_key": request_key, "otp": totp})
        return data["request_key"]

    def verify_pin(self, request_key):
        data = self._post(f"{self.BASE_URL}/verify_pin", {
            "request_key": request_key,
            "identity_type": "pin",
            "identifier": self.pin
        })
        return data["data"]["access_token"]

    def get_auth_code(self, access_token):
        payload = {
            "fyers_id": self.fy_id, "app_id": self.app_id, "redirect_uri": self.redirect_uri,
            "appType": self.app_type, "code_challenge": "", "state": "sample_state",
            "scope": "", "nonce": "", "response_type": "code", "create_cookie": True
        }
        data = self._post(f"{self.BASE_URL_2}/token", payload,
                          headers={'Authorization': f'Bearer {access_token}'},
                          expected_status=308)
        url = data["Url"]
        return parse.parse_qs(parse.urlparse(url).query)['auth_code'][0]

    def validate_auth_code(self, auth_code):
        data = self._post(f"{self.BASE_URL_2}/validate-authcode", {
            "grant_type": "authorization_code",
            "appIdHash": self.app_id_hash,
            "code": auth_code
        })
        return {"access_token": data["access_token"], "refresh_token": data["refresh_token"]}

    def get_access_token(self):
        tokens = self._load_tokens()
        if tokens and self._is_jwt_valid(tokens["access_token"]):
            return tokens["access_token"]
        if tokens and "refresh_token" in tokens:
            refreshed = self.refresh_access_token(tokens["refresh_token"])
            if refreshed and self._is_jwt_valid(refreshed["access_token"]):
                return refreshed["access_token"]

        print("Performing full OTP login flow...")
        request_key = self.send_login_otp()
        totp = self.generate_totp()
        request_key_2 = self.verify_totp(request_key, totp)
        trade_access_token = self.verify_pin(request_key_2)
        auth_code = self.get_auth_code(trade_access_token)
        tokens = self.validate_auth_code(auth_code)
        self._save_tokens(tokens)
        return tokens["access_token"]