import io
import json
import threading
import urllib.request

import eightbit_studio as bms


def mcp(lines):
    out = io.StringIO()
    bms.run_mcp(io.StringIO("".join(json.dumps(m) + "\n" for m in lines)), out)
    return [json.loads(l) for l in out.getvalue().splitlines()]


def test_mcp_tools(tmp_path):
    res = mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "render", "arguments": {"src": "demo", "out": str(tmp_path / "m.wav"), "bars": "1-1"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "studio", "arguments": {"text": "bpm 77"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "render", "arguments": {}}},
    ])
    by = {m["id"]: m for m in res}
    assert by[1]["result"]["serverInfo"]["name"] == "8bms"
    names = {t["name"] for t in by[2]["result"]["tools"]}
    assert {"studio", "render", "export", "gen", "info"} <= names
    assert json.loads(by[3]["result"]["content"][0]["text"])["path"].endswith("m.wav")
    assert "77" in by[4]["result"]["content"][0]["text"]
    assert by[5]["result"]["isError"] is True


def test_http_api(tmp_path):
    srv = bms.make_http_server("127.0.0.1", 0)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert json.loads(urllib.request.urlopen(base + "/health").read())["ok"]
        assert "render" in json.loads(urllib.request.urlopen(base + "/ops").read())
        req = urllib.request.Request(base + "/ops/info", data=json.dumps({"src": "demo"}).encode(), headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req).read())["title"]
        req = urllib.request.Request(base + "/prompt", data=json.dumps({"text": "bpm 101"}).encode(), headers={"Content-Type": "application/json"})
        assert "101" in json.dumps(json.loads(urllib.request.urlopen(req).read()))
        jobs = [{"id": "a", "op": "compose", "args": {"context": "town", "bars": 4, "seed": 2}, "fields": "handle"},
                {"op": "critique", "args": {"src": "$a"}, "fields": "score"}]
        req = urllib.request.Request(base + "/batch", data=json.dumps({"jobs": jobs}).encode(), headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req).read())["results"]
        assert [r["ok"] for r in res] == [True, True] and set(res[1]["result"]) == {"score"}
    finally:
        srv.shutdown()


def test_midi_mapping_events():
    events = []
    mc = bms.MidiController(lambda kind, *a: events.append((kind, *a)))
    mc.mapping_name, mc.mapping = "apc-mini", bms.MIDI_MAPPINGS["apc-mini"]

    class M:
        def __init__(self, type, **kw):
            self.type = type
            self.channel = kw.pop("channel", 0)
            self.__dict__.update(kw)
    mc.handle(M("note_on", note=0, velocity=127))      # bottom-left pad
    mc.handle(M("control_change", control=48, value=64))
    mc.handle(M("control_change", control=56, value=127))
    kinds = [e[0] for e in events]
    assert "grid" in kinds and "fader" in kinds and "master" in kinds
