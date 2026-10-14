"""No provider calls: check a real queued upload and persistence across Compose down/up."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"
STATE = Path("deployment-smoke-state.json")


def request(path, *, data=None, headers=None, opener=None):
    req = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    with (opener or urllib.request.build_opener()).open(req, timeout=15) as response:
        return json.load(response)


if sys.argv[1] == "create":
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    auth = request("/api/v2/auth/guest", data=b"{}", headers={"Content-Type": "application/json"}, opener=client)
    text = b"Career Memory deployment persistence smoke test."
    boundary = "career-memory-smoke-boundary"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke.txt"\r\n'
            'Content-Type: text/plain\r\n\r\n').encode() + text + f'\r\n--{boundary}--\r\n'.encode()
    attachment = request("/api/v2/attachments", data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-CSRF-Token": auth["csrf_token"],
    }, opener=client)
    state = {"attachment_id": attachment["id"], "cookie": "; ".join(f"{c.name}={c.value}" for c in jar),
             "hash": hashlib.sha256(text).hexdigest()}
    STATE.write_text(json.dumps(state), encoding="utf-8")
else:
    state = json.loads(STATE.read_text(encoding="utf-8"))

for attempt in range(60):
    attachment = request(f'/api/v2/attachments/{state["attachment_id"]}', headers={"Cookie": state["cookie"]})
    if attachment["status"] == "ready":
        assert attachment["content_hash"] == state["hash"]
        with urllib.request.urlopen(urllib.request.Request(
            BASE + f'/api/v2/attachments/{state["attachment_id"]}/download',
            headers={"Cookie": state["cookie"]},
        )) as original:
            assert hashlib.sha256(original.read()).hexdigest() == state["hash"]
        print("Worker processing and persisted attachment verified")
        break
    if attachment["status"] == "failed":
        raise RuntimeError(attachment)
    time.sleep(1)
else:
    raise TimeoutError("Worker did not complete upload")
