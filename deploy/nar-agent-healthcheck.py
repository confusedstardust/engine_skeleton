"""Run inside Forge using stdin: verify private routing and shared credentials.

No model invocation or charge. A nonexistent task must return authenticated 404,
not an authentication error; ready alone would not check the shared token.
"""
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = os.environ["NAR_AGENT_URL"].rstrip("/")
token = os.environ["NAR_AGENT_SERVICE_TOKEN"]
with urlopen(base + "/ready", timeout=5) as response:
    assert response.status == 200
request = Request(base + "/v1/animations/" + "0" * 32, headers={"Authorization": "Bearer " + token, "X-User-ID": "deployment-readiness"})
try:
    urlopen(request, timeout=5)
except HTTPError as error:
    if error.code != 404:
        raise SystemExit(f"NarAgent authentication check failed: HTTP {error.code}") from None
else:
    raise SystemExit("Unexpected task response during authentication check")
print("Forge -> NarAgent readiness and service authentication passed (no model call)")
