"""Drive `8bms acp` over stdio like Zed / opencode would."""
import json
import subprocess
import sys
from pathlib import Path

from conftest import APP


class Client:
    def __init__(self, cwd):
        self.p = subprocess.Popen([sys.executable, str(APP), "acp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=cwd)
        self.updates = []

    def send(self, msg):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def call(self, i, method, params):
        self.send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
        while True:
            line = self.p.stdout.readline()
            assert line, self.p.stderr.read()
            m = json.loads(line)
            assert m.get("jsonrpc") == "2.0"
            if m.get("method") == "session/update":
                self.updates.append(m["params"])
            elif m.get("id") == i:
                return m

    def close(self):
        # communicate() closes stdin (EOF ends the server) and drains stdout/stderr
        # while waiting: Windows pipe buffers are small, so an
        # unread stderr can block the server on exit
        self.p.communicate(timeout=60)
        return self.p.returncode


def test_acp_initialize_new_prompt_load(tmp_path):
    c = Client(tmp_path)
    init = c.call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": False}}})["result"]
    assert init["protocolVersion"] == 1 and init["agentCapabilities"]["loadSession"] is True
    assert init["agentInfo"]["name"] == "8bms" and init["authMethods"] == []
    sid = c.call(2, "session/new", {"cwd": str(tmp_path), "mcpServers": []})["result"]["sessionId"]
    r = c.call(3, "session/prompt", {"sessionId": sid, "prompt": [
        {"type": "text", "text": "make an upbeat song 4 bars\n/render up.wav\n/export js up.js"}]})
    assert r["result"]["stopReason"] == "end_turn"
    kinds = [u["update"]["sessionUpdate"] for u in c.updates if u["sessionId"] == sid]
    assert "available_commands_update" in kinds and "plan" in kinds
    assert "tool_call" in kinds and "tool_call_update" in kinds and "agent_message_chunk" in kinds
    done = [u["update"] for u in c.updates if u["update"]["sessionUpdate"] == "tool_call_update" and u["update"].get("status") == "completed"]
    links = [b for u in done for b in u.get("content", []) if b.get("type") == "content" and b["content"].get("type") == "resource_link"]
    uris = {l["content"]["uri"] for l in links}
    assert (tmp_path / "up.wav").as_uri() in uris and (tmp_path / "up.js").as_uri() in uris
    assert (tmp_path / "up.wav").stat().st_size > 10000
    # unknown method -> JSON-RPC error, server keeps running
    err = c.call(4, "nope/x", {})
    assert err["error"]["code"] == -32601
    # load replays the history
    c.updates.clear()
    assert c.call(5, "session/load", {"sessionId": sid, "cwd": str(tmp_path), "mcpServers": []})["result"] == {}
    assert any(u["update"]["sessionUpdate"] == "user_message_chunk" for u in c.updates)
    assert c.close() == 0


def test_acp_cancel(tmp_path):
    c = Client(tmp_path)
    c.call(1, "initialize", {"protocolVersion": 1})
    sid = c.call(2, "session/new", {"cwd": str(tmp_path), "mcpServers": []})["result"]["sessionId"]
    lines = "\n".join(f"/render r{i}.wav" for i in range(12))
    c.call(3, "session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "make a boss song 16 bars"}]})
    c.send({"jsonrpc": "2.0", "id": 4, "method": "session/prompt", "params": {"sessionId": sid, "prompt": [{"type": "text", "text": lines}]}})
    c.send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": sid}})
    while True:
        m = json.loads(c.p.stdout.readline())
        if m.get("id") == 4:
            assert m["result"]["stopReason"] in ("cancelled", "end_turn")
            break
    assert len(list(Path(tmp_path).glob("r*.wav"))) < 12 or m["result"]["stopReason"] == "end_turn"
    c.close()
