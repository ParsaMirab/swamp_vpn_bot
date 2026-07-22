from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

import requests
import urllib3

urllib3.disable_warnings()
logger = logging.getLogger(__name__)

LINKS_TIMEOUT = 60
DEFAULT_TIMEOUT = 30


class SanaeiService:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _request(self, method: str, path: str, timeout: int = DEFAULT_TIMEOUT, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(),
                verify=False,
                timeout=timeout,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error("Panel API HTTP error %s %s: status=%s body=%s",
                         method, path, e.response.status_code if e.response else None,
                         e.response.text[:500] if e.response and e.response.text else None)
            raise
        except Exception as e:
            logger.error("Panel API error %s %s: %s", method, path, e)
            raise

    async def list_inbounds(self) -> list[dict]:
        data = await asyncio.to_thread(self._request, "GET", "/panel/api/inbounds/list")
        if not data.get("success"):
            raise ValueError(data.get("msg", "خطا در دریافت لیست inbounds"))
        return data.get("obj", [])

    async def get_inbound(self, inbound_id: int) -> dict | None:
        inbounds = await self.list_inbounds()
        for ib in inbounds:
            if ib.get("id") == inbound_id:
                return ib
        return None

    async def create_inbound(
        self,
        protocol: str,
        port: int,
        remark: str = "",
        network: str = "tcp",
        security: str = "none",
        total_gb: int = 0,
        expire_days: int = 0,
    ) -> dict:
        stream_settings = {
            "network": network,
            "security": security,
        }
        if network == "ws":
            stream_settings["wsSettings"] = {
                "acceptProxyProtocol": False,
                "path": "/",
                "headers": {"Host": ""},
            }
        elif network == "grpc":
            stream_settings["grpcSettings"] = {
                "acceptProxyProtocol": False,
                "serviceName": "",
            }
        elif network == "h2":
            stream_settings["httpSettings"] = {
                "acceptProxyProtocol": False,
                "path": "/",
                "host": [""],
            }
        else:
            stream_settings["tcpSettings"] = {
                "acceptProxyProtocol": False,
                "header": {"type": "none"},
            }

        if security == "tls":
            stream_settings["tlsSettings"] = {
                "serverName": "",
                "fingerprint": "chrome",
            }
        elif security == "reality":
            stream_settings["realitySettings"] = {
                "show": False,
                "dest": "www.google.com:443",
                "xver": 0,
                "serverNames": ["www.google.com"],
                "privateKey": "",
                "shortIds": [""],
                "maxTimeDiff": 0,
            }

        payload = {
            "listen": "",
            "port": port,
            "protocol": protocol,
            "remark": remark or f"{protocol.upper()} - {port}",
            "settings": json.dumps({
                "clients": [],
                "decryption": "none",
            }),
            "sniffing": json.dumps({
                "enabled": False,
                "destOverride": [],
            }),
            "streamSettings": json.dumps(stream_settings),
            "enable": True,
            "ex": expire_days * 86400 if expire_days > 0 else 0,
            "total": total_gb * 1073741824 if total_gb > 0 else 0,
        }

        logger.info("Creating inbound: port=%d protocol=%s remark=%s", port, protocol, remark)
        data = await asyncio.to_thread(
            self._request, "POST", "/panel/api/inbounds/add", json=payload
        )

        if not data.get("success"):
            raise ValueError(data.get("msg", "خطا در ساخت inbound"))

        obj = data.get("obj", {})
        logger.info("Inbound created: id=%s", obj.get("id"))
        return {
            "id": obj.get("id"),
            "remark": payload["remark"],
            "protocol": protocol,
            "port": port,
            "raw": data,
        }

    async def delete_inbound(self, inbound_id: int) -> bool:
        data = await asyncio.to_thread(
            self._request, "POST", f"/panel/api/inbounds/del/{inbound_id}"
        )
        return data.get("success", False)

    async def create_user(
        self,
        inbound_id: int,
        traffic_gb: int = 0,
        duration_days: int = 30,
        limit_ip: int = 0,
    ) -> dict:
        email = f"bot_{uuid4().hex[:12]}"
        traffic_bytes = traffic_gb * 1073741824 if traffic_gb > 0 else 0
        expiry_ms = int((time.time() + duration_days * 86400) * 1000) if duration_days > 0 else 0

        payload = {
            "client": {
                "email": email,
                "totalGB": traffic_bytes,
                "expiryTime": expiry_ms,
                "tgId": 0,
                "limitIp": limit_ip,
                "enable": True,
            },
            "inboundIds": [inbound_id],
        }

        logger.info("Creating client: email=%s inbound_id=%d traffic_bytes=%d expiry_ms=%d limit_ip=%d",
                     email, inbound_id, traffic_bytes, expiry_ms, limit_ip)

        data = await asyncio.to_thread(
            self._request, "POST", "/panel/api/clients/add", json=payload
        )

        if not data.get("success"):
            logger.error("Panel create_user failed: %s", data.get("msg", data))
            raise ValueError(data.get("msg", "خطا در ساخت اکانت کاربر"))

        return {"email": email, "inbound_id": inbound_id, "raw": data}

    async def buy_service(self, user_data: dict, product_data: dict) -> dict:
        return await self.create_user(
            inbound_id=product_data["inbound_id"],
            traffic_gb=product_data.get("traffic_gb", 0),
            duration_days=product_data.get("duration_days", 30),
            limit_ip=product_data.get("limit_ip", 0),
        )

    async def get_config(self, email: str, retries: int = 3) -> list[str]:
        last_error = None
        for attempt in range(retries):
            try:
                data = await asyncio.to_thread(
                    self._request, "GET", f"/panel/api/clients/links/{email}",
                    timeout=LINKS_TIMEOUT,
                )
                if not data.get("success"):
                    raise ValueError(data.get("msg", "خطا در دریافت کانفیگ"))
                links = data.get("obj", [])
                if links:
                    return links
                logger.warning("get_config empty links for email=%s (attempt %d)", email, attempt + 1)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                logger.warning("get_config connection error for email=%s (attempt %d): %s",
                               email, attempt + 1, e)
            except ValueError:
                raise
            if attempt < retries - 1:
                await asyncio.sleep(3)
        raise last_error or ValueError("خطا در دریافت کانفیگ پس از چند تلاش")

    async def check_status(self) -> dict:
        return await asyncio.to_thread(
            self._request, "GET", "/panel/api/server/status"
        )

    def get_sub_url(self, email: str) -> str:
        return f"{self.base_url}/sub/{email}"
