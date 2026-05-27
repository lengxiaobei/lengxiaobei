from pathlib import Path
import json

from backend.agents.local import LocalAgentHub
from backend.tools.registry import ToolRegistry


def test_local_agent_discovery_from_marker(tmp_path: Path):
    agent_root = tmp_path / "workspace-coding"
    agent_root.mkdir()
    (agent_root / "AGENTS.md").write_text("# Coding Agent\n\nUse this agent for code work.\n")

    hub = LocalAgentHub(roots=[tmp_path], config_path=tmp_path / "missing.json", max_depth=2)

    agents = hub.list_agents()

    discovered = [agent for agent in agents if agent["name"] == "Coding Agent"]
    assert len(discovered) == 1
    assert discovered[0]["callable"] is False
    assert discovered[0]["markers"] == ["AGENTS.md"]


def test_configured_agent_can_be_called(tmp_path: Path):
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    config = tmp_path / "local_agents.json"
    config.write_text(
        """
        {
          "agents": [
            {
              "id": "echo-agent",
              "name": "Echo Agent",
              "root": "%s",
              "command": ["python3", "-c", "import sys; print(sys.argv[1])"]
            }
          ]
        }
        """
        % str(agent_root)
    )
    hub = LocalAgentHub(roots=[], config_path=config)

    result = hub.run_agent("echo-agent", "hello")

    assert result["ok"] is True
    assert result["stdout"].strip() == "hello"


def test_local_agent_tools_are_registered(tmp_path: Path):
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    (agent_root / "SOUL.md").write_text("# Soul Agent\n")
    hub = LocalAgentHub(roots=[tmp_path], config_path=tmp_path / "missing.json")
    tools = ToolRegistry(tmp_path, agent_hub=hub)

    assert "local_agent_list" in tools.list()
    assert "local_agent_describe" in tools.list()
    assert "local_agent_run" in tools.list()
    assert any(agent["name"] == "Soul Agent" for agent in tools.get("local_agent_list")())


def test_controlled_agents_are_available(tmp_path: Path):
    (tmp_path / ".openhuman").mkdir()
    hub = LocalAgentHub(roots=[], config_path=tmp_path / "local_agents.json", home=tmp_path)

    agents = hub.list_controlled_agents()

    assert [agent["id"] for agent in agents] == ["openclaw", "hermes", "openhuman"]
    assert agents[0]["kind"] == "gateway"
    assert agents[0]["callable"] is False
    assert agents[0]["health"]["gateway_online"] is False
    assert agents[0]["health"]["gateway_compatible"] is False
    assert agents[2]["callable"] is True


def test_assign_task_to_openhuman_writes_state(tmp_path: Path):
    openhuman = tmp_path / ".openhuman"
    user_dir = openhuman / "users" / "user-1"
    user_dir.mkdir(parents=True)
    (openhuman / "active_user.toml").write_text('user_id = "user-1"\n')
    hub = LocalAgentHub(roots=[], config_path=tmp_path / "local_agents.json", home=tmp_path)

    result = hub.assign_task("sync my personal memory", target="openhuman", execute=True)

    assert result["ok"] is True
    assert result["target"]["id"] == "openhuman"
    state_path = user_dir / "lengxiaobei_tasks.json"
    assert state_path.exists()
    tasks = json.loads(state_path.read_text())["tasks"]
    assert tasks[0]["task"] == "sync my personal memory"


def test_controlled_agent_tools_are_registered(tmp_path: Path):
    hub = LocalAgentHub(roots=[], config_path=tmp_path / "local_agents.json", home=tmp_path)
    tools = ToolRegistry(tmp_path, agent_hub=hub)

    assert "controlled_agent_list" in tools.list()
    assert "controlled_agent_status" in tools.list()
    assert "controlled_agent_assign" in tools.list()
    assert "controlled_agent_tasks" in tools.list()
