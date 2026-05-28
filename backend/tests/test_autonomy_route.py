import asyncio

from backend.api.routes.autonomy import status, tick, audit


class _Audit:
    def recent(self, limit=100):
        return [{"action": "test", "ts": 1}]


class _Autonomy:
    def __init__(self):
        self.audit = _Audit()

    def status(self):
        return {"state": "idle", "last_tick": None}

    async def tick(self, reason, force=True, expensive_checks=False):
        return {"ok": True, "reason": reason, "force": force}


class _Runtime:
    def __init__(self):
        self.autonomy = _Autonomy()


def test_autonomy_status():
    rt = _Runtime()
    result = asyncio.run(status(rt=rt))
    assert result["state"] == "idle"
    assert result["last_tick"] is None


def test_autonomy_tick_defaults():
    rt = _Runtime()
    result = asyncio.run(tick(payload=None, rt=rt))
    assert result["ok"] is True
    assert result["reason"] == "manual"
    assert result["force"] is True


def test_autonomy_tick_with_payload():
    rt = _Runtime()
    result = asyncio.run(tick(payload={"reason": "test", "force": False}, rt=rt))
    assert result["ok"] is True
    assert result["reason"] == "test"
    assert result["force"] is False


def test_autonomy_audit():
    rt = _Runtime()
    result = asyncio.run(audit(limit=50, rt=rt))
    assert len(result["items"]) == 1
    assert result["items"][0]["action"] == "test"
