from __future__ import annotations

import asyncio
import base64
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

REPLACEMENT_DOMAIN = "swamp.nicebrovip.xyz"
REPLACEMENT_IP = "144.31.157.131"


class SanaeiService:
    def __init__(self, api_key: str, base_url: str, sub_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.sub_url = sub_url.rstrip("/") if sub_url else self.base_url

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _replace_domain_in_link(link: str) -> str:
        if link.startswith("vmess://"):
            try:
                raw = link[len("vmess://"):]
                padded = raw + "=" * (-len(raw) % 4)
                decoded = base64.b64decode(padded).decode("utf-8")
                config = json.loads(decoded)
                addr = config.get("add", "")
                if addr == REPLACEMENT_DOMAIN:
                    config["add"] = REPLACEMENT_IP
                elif addr == f"https://{REPLACEMENT_DOMAIN}" or addr == f"http://{REPLACEMENT_DOMAIN}":
                    config["add"] = REPLACEMENT_IP
                json_str = json.dumps(config, separators=(",", ":"))
                encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8").rstrip("=")
                return f"vmess://{encoded}"
            except Exception:
                return link

        if REPLACEMENT_DOMAIN not in link:
            return link

        iif link.startswith("vless://") or link.startswith("trojan://"):
             protocol = "vless" if link.startswith("vless://") else "trojan"

             prefix = f"{protocol}://"
             rest = link[len(prefix):]

             fragment = ""
             if "#" in rest:
                 rest, fragment_part = rest.split("#", 1)
                 fragment = f"#{fragment_part}"

             query = ""
             if "?" in rest:
                 rest, query_part = rest.split("?", 1)
                 query = f"?{query_part}"

             if "@" not in rest:
                 return link

             user_info, host_port = rest.rsplit("@", 1)

             if ":" in host_port:
                 current_host, port = host_port.split(":", 1)
                 new_host_port = f"{REPLACEMENT_IP}:{port}"
             else:
                 new_host_port = REPLACEMENT_IP

             return (
                 f"{prefix}"
                 f"{user_info}@{new_host_port}"
                 f"{query}"
                 f"{fragment}"
             )

        if link.startswith("ss://"):
            rest = link[len("ss://"):]
            if "@" in rest:
                encoded_part, after_at = rest.split("@", 1)
                if ":" in after_at:
                    host_port, query_fragment = after_at.split(":", 1)
                    domain_part = host_port.split("?")[0] if "?" in host_port else host_port.split("#")[0] if "#" in host_port else host_port
                    if domain_part == REPLACEMENT_DOMAIN:
                        new_host_port = host_port.replace(REPLACEMENT_DOMAIN, REPLACEMENT_IP, 1)
                        new_after_at = new_host_port + after_at[len(host_port):]
                        return f"ss://{encoded_part}@{new_after_at}"
            return link

        if link.startswith("hysteria2://") or link.startswith("hy2://"):
            protocol = "hysteria2" if link.startswith("hysteria2://") else "hy2"
            rest = link[len(f"{protocol}://"):]
            if "@" in rest:
                auth_part, after_at = rest.split("@", 1)
                if ":" in after_at:
                    host_port, query_fragment = after_at.split(":", 1)
                    domain_part = host_port.split("?")[0] if "?" in host_port else host_port.split("#")[0] if "#" in host_port else host_port
                    if domain_part == REPLACEMENT_DOMAIN:
                        new_host_port = host_port.replace(REPLACEMENT_DOMAIN, REPLACEMENT_IP, 1)
                        new_after_at = new_host_port + after_at[len(host_port):]
                        return f"{protocol}://{auth_part}@{new_after_at}"
            return link

        return link

    @staticmethod
    def _replace_domain_in_links(links: list[str]) -> list[str]:
        return [SanaeiService._replace_domain_in_link(link) for link in links]

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

        await asyncio.sleep(2)
        sub_id = await self.get_client_sub_id(email)
        return {"email": email, "inbound_id": inbound_id, "sub_id": sub_id, "raw": data}

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
                    return self._replace_domain_in_links(links)
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

    async def get_client_by_email(self, email: str) -> dict | None:
        try:
            data = await asyncio.to_thread(
                self._request, "GET", f"/panel/api/clients/get/{email}"
            )
            logger.info("get_client_by_email response for %s: %s", email, data)
            if data.get("success"):
                obj = data.get("obj")
                logger.info("Client obj keys: %s", list(obj.keys()) if isinstance(obj, dict) else "not dict")
                if isinstance(obj, dict):
                    logger.info("Client subId: %s, uuid: %s", obj.get("subId"), obj.get("uuid"))
                return obj
        except Exception as e:
            logger.warning("get_client_by_email failed for %s: %s", email, e)
        return None

    async def get_client_sub_id(self, email: str) -> str:
        """Get client subId using /panel/api/clients/list (which includes subId)."""
        try:
            data = await asyncio.to_thread(
                self._request, "GET", "/panel/api/clients/list"
            )
            if data.get("success"):
                for client in data.get("obj", []):
                    if client.get("email") == email:
                        sub_id = client.get("subId", "")
                        if sub_id:
                            return sub_id
                        logger.warning("Client %s has empty subId, falling back to uuid=%s", email, client.get("uuid"))
                        return client.get("uuid", "")
            logger.warning("Client %s not found in clients list", email)
        except Exception as e:
            logger.warning("get_client_sub_id failed for %s: %s", email, e)
        return ""

    def get_sub_url(self, sub_id: str) -> str:
        return f"{self.sub_url}/sub/{sub_id}"
