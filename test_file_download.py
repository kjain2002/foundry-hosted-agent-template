"""Option 2 file-download test: CLIENT-created container passed to the agent.

Config under test: hosted agent + Code Interpreter bound to a container_id that
THIS client (its own identity) pre-creates and passes in the request as
``USE_CONTAINER_ID=cntr_...``. The deployed managed identity never creates a
container (it only USES it), sidestepping the container-create RBAC 403.

Flow:
  1. Client creates a container at the project-scoped Containers API.
  2. Client invokes the agent, embedding USE_CONTAINER_ID=<id> in the prompt and
     asking it to GENERATE a .pptx via the code interpreter.
  3. Client enumerates that (client-created) container's files and downloads the
     .pptx bytes, then verifies it is a real Office/zip file.

Endpoint override: set AGENT_ENDPOINT to hit a local server
(http://localhost:8088/responses); otherwise the deployed agent is used.
"""

import json
import os
import re
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# Derived from your Foundry project endpoint inside main() (never hard-coded).
ACCOUNT_BASE = ""


def _load_azd_env() -> dict[str, str]:
    """Parse the azd .env (KEY="value" lines) for endpoint/model."""
    env_path = (
        Path(__file__).parent
        / ".azure"
        / "agent-framework-agent-basic-responses-dev"
        / ".env"
    )
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"')
    return values


def main() -> None:
    env = _load_azd_env()
    global ACCOUNT_BASE
    ACCOUNT_BASE = f"{(os.getenv('FOUNDRY_PROJECT_ENDPOINT') or env['FOUNDRY_PROJECT_ENDPOINT']).rstrip('/')}/openai/v1"
    responses_endpoint = os.getenv("AGENT_ENDPOINT") or env[
        "AGENT_AGENT_FRAMEWORK_AGENT_BASIC_RESPONSES_RESPONSES_ENDPOINT"
    ]
    model = env.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1")
    is_local = "localhost" in responses_endpoint or "127.0.0.1" in responses_endpoint

    credential = DefaultAzureCredential()
    get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    # 1. CLIENT creates the container (its own identity has permission; the
    #    managed identity does not). filename stays fixed for the download step.
    filename = "report.pptx"
    create = httpx.post(
        f"{ACCOUNT_BASE}/containers",
        headers={"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"},
        json={"name": "client-created-ci"},
        timeout=60.0,
    )
    print(f"Create container HTTP {create.status_code}")
    create.raise_for_status()
    container_id = create.json()["id"]
    print(f"Client-created container_id={container_id}")

    # 2. Invoke the agent, passing the client-created container id in the prompt.
    prompt = (
        f"USE_CONTAINER_ID={container_id}\n\n"
        f"Use the code interpreter tool to create a PowerPoint file named {filename} "
        "with a single slide whose title is 'Hello from Code Interpreter'. Use the "
        "python-pptx library and save it."
    )
    body = {"model": model, "input": prompt, "stream": False, "store": False}

    print(f"POST {responses_endpoint}")
    headers = {"Content-Type": "application/json"}
    if not is_local:
        headers["Authorization"] = f"Bearer {get_token()}"
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(responses_endpoint, headers=headers, json=body)
    print(f"HTTP {resp.status_code}")
    data = resp.json()
    (Path(__file__).parent / "response_dump.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    print(f"Response status: {data.get('status')}")
    if data.get("error"):
        print(f"Response error: {data['error'].get('message')}")

    text_parts = []
    for item in data.get("output", []):
        for c in item.get("content", []) or []:
            if c.get("type") == "output_text":
                text_parts.append(c.get("text", ""))
    print(f"Assistant text:\n{chr(10).join(text_parts)}\n")

    # 3. Download from the CLIENT-created container (we already know its id).
    token = get_token()
    api = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=120.0) as client:
        lst = client.get(f"{ACCOUNT_BASE}/containers/{container_id}/files", headers=api)
        print(f"List files HTTP {lst.status_code}")
        files = lst.json().get("data", [])
        print(f"Files in container: {[(f.get('id'), f.get('path'), f.get('source')) for f in files]}")
        target = next(
            (f for f in files if filename in (f.get("path") or "")),
            next((f for f in files if f.get("source") == "assistant"), None),
        )
        if not target:
            print("!! No matching file found in container (CI may not have generated it).")
            return
        fid = target["id"]
        content = client.get(
            f"{ACCOUNT_BASE}/containers/{container_id}/files/{fid}/content", headers=api
        )
        print(f"Download HTTP {content.status_code} bytes={len(content.content)}")
        out = Path(__file__).parent / "downloaded_report.pptx"
        out.write_bytes(content.content)
        magic = content.content[:2]
        print(f"Saved {out} ({len(content.content)} bytes); magic={magic!r} "
              f"({'VALID zip/pptx' if magic == b'PK' else 'NOT a zip/pptx'})")


if __name__ == "__main__":
    main()
