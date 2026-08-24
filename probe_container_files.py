"""Diagnose a 404 on the Code Interpreter container FILES endpoint.

Run this in the SAME environment (identity + network) where the UI fails, e.g.:

    python probe_container_files.py

It creates a Code Interpreter container, then tries to upload a tiny file to the
container's /files subresource at several candidate URLs (project scope vs account
scope, with and without api-version) and prints the HTTP status of each. The one
that returns 200/201 is the scope your environment expects.

Reads FOUNDRY_PROJECT_ENDPOINT from the environment or the azd .env, exactly like
the UI does.
"""

import os
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

_HERE = Path(__file__).resolve().parent


def _load_env_value(key: str) -> str:
    if os.getenv(key):
        return os.environ[key]
    env_path = _HERE / ".azure" / "agent-framework-agent-basic-responses-dev" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.split("=", 1)[0].strip() == key:
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def main() -> None:
    project_endpoint = _load_env_value("FOUNDRY_PROJECT_ENDPOINT").rstrip("/")
    if not project_endpoint:
        raise SystemExit("Set FOUNDRY_PROJECT_ENDPOINT (or put it in the azd .env).")

    # project endpoint looks like: https://<acct>.services.ai.azure.com/api/projects/<name>
    # account base is everything before /api/projects/...
    account_base = project_endpoint.split("/api/projects/")[0]
    project_base = project_endpoint

    get_token = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    auth = {"Authorization": f"Bearer {get_token()}"}

    print(f"project_base = {project_base}")
    print(f"account_base = {account_base}\n")

    conn_failed = {"any": False}

    def create_container(base: str) -> str | None:
        url = f"{base}/openai/v1/containers"
        try:
            r = httpx.post(url, headers={**auth, "Content-Type": "application/json"},
                           json={"name": "probe-ci"}, timeout=60.0)
            print(f"CREATE {url} -> {r.status_code}")
            if r.status_code in (200, 201):
                return r.json().get("id")
        except (httpx.ConnectError, ConnectionError, OSError) as exc:
            conn_failed["any"] = True
            print(f"CREATE {url} -> CONNECTION FAILED ({exc})  [network/VPN, not an API result]")
        except Exception as exc:  # noqa: BLE001
            print(f"CREATE {url} -> EXC {exc}")
        return None

    # Create at BOTH scopes so we can test files against a container made at each.
    winners = []
    for create_scope, base in (("project", project_base), ("account", account_base)):
        print(f"=== container created at {create_scope} scope ===")
        cid = create_container(base)
        if not cid:
            print("  (create failed at this scope; skipping file upload tests)\n")
            continue
        print(f"  container_id = {cid}")
        candidates = [
            ("project", "", f"{project_base}/openai/v1/containers/{cid}/files"),
            ("project", "v1", f"{project_base}/openai/v1/containers/{cid}/files?api-version=v1"),
            ("account", "", f"{account_base}/openai/v1/containers/{cid}/files"),
            ("account", "v1", f"{account_base}/openai/v1/containers/{cid}/files?api-version=v1"),
        ]
        for files_scope, apiver, url in candidates:
            av = apiver or "none"
            try:
                r = httpx.post(url, headers=auth,
                               files={"file": ("probe.txt", b"hello", "text/plain")},
                               timeout=60.0)
                ok = r.status_code in (200, 201)
                print(f"  FILES [files@{files_scope}, api-version={av}] -> {r.status_code}{'  <-- WORKS' if ok else ''}")
                if ok:
                    winners.append((create_scope, files_scope, apiver))
            except Exception as exc:  # noqa: BLE001
                print(f"  FILES [files@{files_scope}, api-version={av}] -> EXC {exc}")
        print()

    # ── VERDICT (send THIS whole output for comparison) ──────────────────────
    print("=" * 64)
    if conn_failed["any"] and not winners:
        print("VERDICT: COULD NOT CONNECT (WinError 10061 / connection refused).")
        print("         This is a NETWORK/VPN problem (e.g. a local subnet colliding")
        print("         with the private-endpoint IPs) — NOT an API result. Fix")
        print("         networking (VPN on + non-colliding subnet) and re-run.")
    elif not winners:
        print("VERDICT: NO combination worked -> container files API appears")
        print("         UNAVAILABLE in this environment (platform/region gap).")
    else:
        print("VERDICT: file upload/download WORKS with:")
        for create_scope, files_scope, apiver in winners:
            av = f"?api-version={apiver}" if apiver else "(no api-version)"
            print(f"  - create@{create_scope} + files@{files_scope} {av}")
        best = winners[0]
        rec = f"CONTAINER_API_SCOPE={best[1]}" + (f" + api-version={best[2]}" if best[2] else "")
        print(f"  => this env expects: {rec}")
    print("=" * 64)


if __name__ == "__main__":
    main()
