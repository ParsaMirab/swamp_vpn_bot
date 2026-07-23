import pytest
import json
import time
from unittest.mock import patch, MagicMock, call
from bot.services.sanaei_service import SanaeiService


@pytest.fixture
def sanaei_service():
    return SanaeiService(api_key="test_key", base_url="https://test-panel.com")


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    mock.raise_for_status = MagicMock()
    return mock


def _capture_payload():
    """Return a list that will capture the json= kwarg from requests.request calls."""
    captured = []

    def fake_request(method, path, headers=None, verify=False, timeout=None, **kwargs):
        captured.append({
            "method": method,
            "path": path,
            "json": kwargs.get("json"),
        })
        return _mock_response({"success": True, "obj": {}})

    return captured, fake_request


def _create_user_with_inbounds_mock(inbounds=None):
    """Create a mock that handles both create_user and list_inbounds calls."""
    if inbounds is None:
        inbounds = []

    def side_effect(method, path, headers=None, verify=False, timeout=None, **kwargs):
        if "/panel/api/clients/add" in path:
            return _mock_response({"success": True, "msg": "Client added", "obj": {}})
        elif "/panel/api/inbounds/list" in path:
            return _mock_response({"success": True, "obj": inbounds})
        return _mock_response({"success": True, "obj": {}})

    return side_effect


# ─── Headers & Config ────────────────────────────────────────────────

class TestHeaders:
    def test_bearer_token(self, sanaei_service):
        assert sanaei_service._headers() == {"Authorization": "Bearer test_key"}

    def test_base_url_trailing_slash_stripped(self):
        svc = SanaeiService(api_key="k", base_url="https://example.com/")
        assert svc.base_url == "https://example.com"

    def test_base_url_no_trailing_slash(self):
        svc = SanaeiService(api_key="k", base_url="https://example.com")
        assert svc.base_url == "https://example.com"


# ─── create_user (Client Creation) ──────────────────────────────────

class TestCreateUser:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        inbounds = [{"id": 3, "settings": '{"clients": [{"email": "test_client", "uuid": "test-uuid-123"}]}'}]
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)) as mock_req:
            result = await sanaei_service.create_user(
                inbound_id=3, traffic_gb=50, duration_days=30
            )

        assert result["email"].startswith("bot_")
        assert result["inbound_id"] == 3
        assert len(result["email"]) == 16  # "bot_" + 12 hex chars

        # Find the create_user call
        create_calls = [c for c in mock_req.call_args_list if "/panel/api/clients/add" in c[0][1]]
        assert len(create_calls) == 1
        payload = create_calls[0][1]["json"]

        # Validate payload structure matches 3x-ui API docs
        assert "client" in payload
        assert "inboundIds" in payload
        assert payload["inboundIds"] == [3]

        client = payload["client"]
        assert client["email"] == result["email"]
        assert client["totalGB"] == 50 * 1073741824  # 50 GB in bytes
        assert client["enable"] is True
        assert client["tgId"] == 0
        assert client["limitIp"] == 0
        assert "id" not in client  # Must NOT include id — panel generates it

    @pytest.mark.asyncio
    async def test_expiry_time_in_milliseconds(self, sanaei_service):
        inbounds = [{"id": 1, "settings": '{"clients": []}'}]
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)) as mock_req:
            await sanaei_service.create_user(
                inbound_id=1, traffic_gb=0, duration_days=7
            )

        create_calls = [c for c in mock_req.call_args_list if "/panel/api/clients/add" in c[0][1]]
        payload = create_calls[0][1]["json"]
        expiry_ms = payload["client"]["expiryTime"]
        now_ms = int(time.time() * 1000)
        expected_ms = now_ms + 7 * 86400 * 1000
        # Allow 5s tolerance for test execution
        assert abs(expiry_ms - expected_ms) < 5000

    @pytest.mark.asyncio
    async def test_zero_traffic(self, sanaei_service):
        inbounds = [{"id": 1, "settings": '{"clients": []}'}]
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)) as mock_req:
            await sanaei_service.create_user(inbound_id=1)

        create_calls = [c for c in mock_req.call_args_list if "/panel/api/clients/add" in c[0][1]]
        payload = create_calls[0][1]["json"]
        assert payload["client"]["totalGB"] == 0

    @pytest.mark.asyncio
    async def test_zero_duration_no_expiry(self, sanaei_service):
        inbounds = [{"id": 1, "settings": '{"clients": []}'}]
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)) as mock_req:
            await sanaei_service.create_user(
                inbound_id=1, duration_days=0
            )

        create_calls = [c for c in mock_req.call_args_list if "/panel/api/clients/add" in c[0][1]]
        payload = create_calls[0][1]["json"]
        assert payload["client"]["expiryTime"] == 0

    @pytest.mark.asyncio
    async def test_failure_raises_value_error(self, sanaei_service):
        resp = _mock_response({"success": False, "msg": "Inbound not found"})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            with pytest.raises(ValueError, match="Inbound not found"):
                await sanaei_service.create_user(inbound_id=999)

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, sanaei_service):
        import requests as req_lib
        resp = _mock_response({}, status_code=500)
        resp.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=resp)
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            with pytest.raises(req_lib.exceptions.HTTPError):
                await sanaei_service.create_user(inbound_id=1)

    @pytest.mark.asyncio
    async def test_email_format_unique(self, sanaei_service):
        inbounds = [{"id": 1, "settings": '{"clients": []}'}]
        emails = set()
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)) as mock_req:
            for _ in range(10):
                result = await sanaei_service.create_user(inbound_id=1)
                emails.add(result["email"])

        assert len(emails) == 10  # All emails should be unique


# ─── create_inbound ──────────────────────────────────────────────────

class TestCreateInbound:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        resp = _mock_response({
            "success": True,
            "obj": {"id": 5, "remark": "VMESS-443"},
        })
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            result = await sanaei_service.create_inbound(
                protocol="vmess", port=443, remark="VMESS-443"
            )

        assert result["id"] == 5
        assert result["protocol"] == "vmess"
        assert result["port"] == 443
        assert result["remark"] == "VMESS-443"

        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "/panel/api/inbounds/add" in call_args[0][1]
        payload = call_args[1]["json"]
        assert payload["port"] == 443
        assert payload["protocol"] == "vmess"
        assert payload["enable"] is True
        # settings, streamSettings, sniffing must be JSON strings
        assert isinstance(payload["settings"], str)
        assert isinstance(payload["streamSettings"], str)
        assert isinstance(payload["sniffing"], str)
        settings = json.loads(payload["settings"])
        assert settings["clients"] == []
        assert settings["decryption"] == "none"

    @pytest.mark.asyncio
    async def test_default_remark(self, sanaei_service):
        resp = _mock_response({"success": True, "obj": {"id": 1}})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            result = await sanaei_service.create_inbound(
                protocol="vless", port=8443
            )

        payload = mock_req.call_args[1]["json"]
        assert payload["remark"] == "VLESS - 8443"

    @pytest.mark.asyncio
    async def test_traffic_and_expiry_conversion(self, sanaei_service):
        resp = _mock_response({"success": True, "obj": {"id": 1}})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            await sanaei_service.create_inbound(
                protocol="vmess", port=443,
                total_gb=100, expire_days=30,
            )

        payload = mock_req.call_args[1]["json"]
        assert payload["total"] == 100 * 1073741824
        assert payload["ex"] == 30 * 86400

    @pytest.mark.asyncio
    async def test_ws_network_stream_settings(self, sanaei_service):
        resp = _mock_response({"success": True, "obj": {"id": 1}})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            await sanaei_service.create_inbound(
                protocol="vmess", port=443, network="ws",
            )

        payload = mock_req.call_args[1]["json"]
        stream = json.loads(payload["streamSettings"])
        assert stream["network"] == "ws"
        assert "wsSettings" in stream

    @pytest.mark.asyncio
    async def test_grpc_network_stream_settings(self, sanaei_service):
        resp = _mock_response({"success": True, "obj": {"id": 1}})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            await sanaei_service.create_inbound(
                protocol="vless", port=443, network="grpc",
            )

        payload = mock_req.call_args[1]["json"]
        stream = json.loads(payload["streamSettings"])
        assert stream["network"] == "grpc"
        assert "grpcSettings" in stream

    @pytest.mark.asyncio
    async def test_tls_security_stream_settings(self, sanaei_service):
        resp = _mock_response({"success": True, "obj": {"id": 1}})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            await sanaei_service.create_inbound(
                protocol="vless", port=443, security="tls",
            )

        payload = mock_req.call_args[1]["json"]
        stream = json.loads(payload["streamSettings"])
        assert stream["security"] == "tls"
        assert "tlsSettings" in stream

    @pytest.mark.asyncio
    async def test_failure_raises_value_error(self, sanaei_service):
        resp = _mock_response({"success": False, "msg": "Port in use"})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            with pytest.raises(ValueError, match="Port in use"):
                await sanaei_service.create_inbound(protocol="vmess", port=443)


# ─── get_config (Subscription Links) ────────────────────────────────

class TestGetConfig:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        links = ["vless://abc@test.com:443", "vmess://xyz@test.com:443"]
        resp = _mock_response({"success": True, "obj": links})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            result = await sanaei_service.get_config("user@email.com")

        assert result == links
        mock_req.assert_called_once()
        assert "/panel/api/clients/links/user@email.com" in mock_req.call_args[0][1]

    @pytest.mark.asyncio
    async def test_empty_links_retries(self, sanaei_service):
        empty_resp = _mock_response({"success": True, "obj": []})
        filled_resp = _mock_response({
            "success": True,
            "obj": ["vless://ok@test.com:443"],
        })

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return empty_resp
            return filled_resp

        with patch("bot.services.sanaei_service.requests.request", side_effect=side_effect):
            result = await sanaei_service.get_config("user@email.com")

        assert len(result) == 1
        assert call_count == 3  # Retried twice before success

    @pytest.mark.asyncio
    async def test_failure_raises(self, sanaei_service):
        resp = _mock_response({"success": False, "msg": "Client not found"})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            with pytest.raises(ValueError, match="Client not found"):
                await sanaei_service.get_config("unknown@email.com")

    @pytest.mark.asyncio
    async def test_connection_error_retries_then_raises(self, sanaei_service):
        import requests as req_lib

        def fail(*args, **kwargs):
            raise req_lib.exceptions.ConnectionError("Connection refused")

        with patch("bot.services.sanaei_service.requests.request", side_effect=fail):
            with pytest.raises(req_lib.exceptions.ConnectionError):
                await sanaei_service.get_config("user@email.com", retries=2)


# ─── Domain Replacement ─────────────────────────────────────────────

class TestDomainReplacement:
    def test_vless_link_replaces_domain(self):
        link = "vless://abc123@swamp.nicebrovip.xyz:443?type=tcp&security=none#MyServer"
        result = SanaeiService._replace_domain_in_link(link)
        assert "144.31.157.131" in result
        assert "swamp.nicebrovip.xyz" not in result
        assert result.startswith("vless://")
        assert ":443?" in result

    def test_trojan_link_replaces_domain(self):
        link = "trojan://password123@swamp.nicebrovip.xyz:8443?security=tls#TrojanServer"
        result = SanaeiService._replace_domain_in_link(link)
        assert "144.31.157.131" in result
        assert "swamp.nicebrovip.xyz" not in result
        assert result.startswith("trojan://")
        assert ":8443?" in result

    def test_vmess_link_replaces_domain(self):
        import base64
        import json
        config = {
            "v": "2",
            "ps": "MyVmess",
            "add": "swamp.nicebrovip.xyz",
            "port": "443",
            "id": "abc123-def456",
            "aid": "0",
            "net": "tcp",
            "type": "none",
            "host": "",
            "path": "",
            "tls": "tls",
        }
        encoded = base64.b64encode(json.dumps(config, separators=(",", ":")).encode()).decode().rstrip("=")
        link = f"vmess://{encoded}"
        result = SanaeiService._replace_domain_in_link(link)
        assert result.startswith("vmess://")
        padded = result[8:] + "=" * (-len(result[8:]) % 4)
        decoded_result = base64.b64decode(padded).decode()
        result_config = json.loads(decoded_result)
        assert result_config["add"] == "144.31.157.131"
        assert result_config["port"] == "443"

    def test_vmess_link_preserves_port(self):
        import base64
        import json
        config = {
            "v": "2",
            "ps": "Test",
            "add": "swamp.nicebrovip.xyz",
            "port": "8443",
            "id": "test-id",
            "aid": "0",
            "net": "ws",
            "type": "none",
            "host": "",
            "path": "/ws",
            "tls": "tls",
        }
        encoded = base64.b64encode(json.dumps(config, separators=(",", ":")).encode()).decode().rstrip("=")
        link = f"vmess://{encoded}"
        result = SanaeiService._replace_domain_in_link(link)
        padded = result[8:] + "=" * (-len(result[8:]) % 4)
        decoded_result = base64.b64decode(padded).decode()
        result_config = json.loads(decoded_result)
        assert result_config["port"] == "8443"

    def test_ss_link_replaces_domain(self):
        import base64
        auth = base64.b64encode(b"password:123").decode()
        link = f"ss://{auth}@swamp.nicebrovip.xyz:443#Shadowsocks"
        result = SanaeiService._replace_domain_in_link(link)
        assert "144.31.157.131" in result
        assert "swamp.nicebrovip.xyz" not in result

    def test_hysteria2_link_replaces_domain(self):
        link = "hysteria2://authkey@swamp.nicebrovip.xyz:443?insecure=1#Hysteria2"
        result = SanaeiService._replace_domain_in_link(link)
        assert "144.31.157.131" in result
        assert "swamp.nicebrovip.xyz" not in result
        assert result.startswith("hysteria2://")

    def test_no_domain_no_change(self):
        link = "vless://abc@other-domain.com:443#Test"
        result = SanaeiService._replace_domain_in_link(link)
        assert result == link

    def test_replace_multiple_links(self):
        links = [
            "vless://abc@swamp.nicebrovip.xyz:443#Server1",
            "trojan://pass@swamp.nicebrovip.xyz:8443#Server2",
            "vless://xyz@other.com:443#Server3",
        ]
        result = SanaeiService._replace_domain_in_links(links)
        assert len(result) == 3
        assert "144.31.157.131" in result[0]
        assert "144.31.157.131" in result[1]
        assert "swamp.nicebrovip.xyz" not in result[0]
        assert "swamp.nicebrovip.xyz" not in result[1]
        assert result[2] == links[2]

    @pytest.mark.asyncio
    async def test_get_config_applies_domain_replacement(self, sanaei_service):
        links = ["vless://abc@swamp.nicebrovip.xyz:443#Test"]
        resp = _mock_response({"success": True, "obj": links})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            result = await sanaei_service.get_config("user@email.com")
        assert "144.31.157.131" in result[0]
        assert "swamp.nicebrovip.xyz" not in result[0]


# ─── list_inbounds ───────────────────────────────────────────────────

class TestListInbounds:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        inbounds = [{"id": 1, "port": 443}, {"id": 2, "port": 8443}]
        resp = _mock_response({"success": True, "obj": inbounds})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            result = await sanaei_service.list_inbounds()

        assert len(result) == 2
        assert result[0]["port"] == 443

    @pytest.mark.asyncio
    async def test_failure(self, sanaei_service):
        resp = _mock_response({"success": False, "msg": "Auth failed"})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            with pytest.raises(ValueError, match="Auth failed"):
                await sanaei_service.list_inbounds()


# ─── get_inbound ─────────────────────────────────────────────────────

class TestGetInbound:
    @pytest.mark.asyncio
    async def test_found(self, sanaei_service):
        inbounds = [{"id": 1, "port": 443}, {"id": 2, "port": 8443}]
        resp = _mock_response({"success": True, "obj": inbounds})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            result = await sanaei_service.get_inbound(2)

        assert result is not None
        assert result["id"] == 2

    @pytest.mark.asyncio
    async def test_not_found(self, sanaei_service):
        inbounds = [{"id": 1, "port": 443}]
        resp = _mock_response({"success": True, "obj": inbounds})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            result = await sanaei_service.get_inbound(999)

        assert result is None


# ─── delete_inbound ──────────────────────────────────────────────────

class TestDeleteInbound:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        resp = _mock_response({"success": True})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp) as mock_req:
            assert await sanaei_service.delete_inbound(5) is True

        assert mock_req.call_args[0][0] == "POST"
        assert "/panel/api/inbounds/del/5" in mock_req.call_args[0][1]

    @pytest.mark.asyncio
    async def test_failure(self, sanaei_service):
        resp = _mock_response({"success": False})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            assert await sanaei_service.delete_inbound(5) is False


# ─── buy_service ─────────────────────────────────────────────────────

class TestBuyService:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        inbounds = [{"id": 2, "settings": '{"clients": []}'}]
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)):
            result = await sanaei_service.buy_service(
                user_data={"user_id": 123},
                product_data={
                    "inbound_id": 2,
                    "traffic_gb": 100,
                    "duration_days": 30,
                },
            )

        assert "email" in result
        assert result["inbound_id"] == 2

    @pytest.mark.asyncio
    async def test_defaults(self, sanaei_service):
        inbounds = [{"id": 1, "settings": '{"clients": []}'}]
        with patch("bot.services.sanaei_service.requests.request", side_effect=_create_user_with_inbounds_mock(inbounds)) as mock_req:
            await sanaei_service.buy_service(
                user_data={"user_id": 1},
                product_data={"inbound_id": 1},
            )

        create_calls = [c for c in mock_req.call_args_list if "/panel/api/clients/add" in c[0][1]]
        payload = create_calls[0][1]["json"]
        assert payload["client"]["totalGB"] == 0  # default
        assert payload["client"]["expiryTime"] > 0  # default 30 days


# ─── check_status ────────────────────────────────────────────────────

class TestCheckStatus:
    @pytest.mark.asyncio
    async def test_success(self, sanaei_service):
        resp = _mock_response({"cpu": 50, "mem": 60})
        with patch("bot.services.sanaei_service.requests.request", return_value=resp):
            status = await sanaei_service.check_status()

        assert status["cpu"] == 50
        assert status["mem"] == 60


# ─── get_sub_url ─────────────────────────────────────────────────────

class TestGetSubUrl:
    def test_builds_subscription_url(self, sanaei_service):
        url = sanaei_service.get_sub_url("550e8400-e29b-41d4-a716-446655440000")
        assert url == "https://test-panel.com/sub/550e8400-e29b-41d4-a716-446655440000"

    def test_strips_trailing_slash(self):
        svc = SanaeiService(api_key="k", base_url="https://panel.com/")
        url = svc.get_sub_url("550e8400-e29b-41d4-a716-446655440000")
        assert url == "https://panel.com/sub/550e8400-e29b-41d4-a716-446655440000"
