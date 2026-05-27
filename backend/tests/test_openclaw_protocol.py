import json

from backend.agents.integrations import OpenClawIntegration


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, raw: str):
        self.sent.append(json.loads(raw))


def test_openclaw_connect_payload_supports_protocol_versions():
    integration = OpenClawIntegration()
    params = integration._connect_params(3)

    assert params["minProtocol"] == 3
    assert params["maxProtocol"] == 3
    assert "protocol" not in params
    assert "capabilities" not in params
    assert "agent_turn" in params["caps"]
    assert "agent_turn" in params["scopes"]
    assert params["client"]["id"] == "gateway-client"


def test_openclaw_connect_payload_includes_config_token(tmp_path):
    state = tmp_path / ".openclaw"
    state.mkdir()
    (state / "openclaw.json").write_text(json.dumps({"gateway": {"auth": {"token": "test-token"}}}))
    integration = OpenClawIntegration(home=tmp_path)

    params = integration._connect_params(3)

    assert params["auth"] == {"token": "test-token"}


def test_openclaw_agent_method_prefers_advertised_agent_turn():
    integration = OpenClawIntegration()

    assert integration._agent_method({"payload": {"methods": ["agent_turn", "agent"]}}) == "agent_turn"
    assert integration._agent_method({"payload": {"methods": ["agent.turn"]}}) == "agent.turn"
    assert integration._agent_method({"payload": {"methods": ["agent"]}}) == "agent"
    assert integration._agent_method({"payload": {}}) == "agent"
