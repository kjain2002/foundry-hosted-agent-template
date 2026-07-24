# Foundry Hosted Agent — MCP Tools + Skills Template

A reusable template for publishing your own **Microsoft Foundry hosted agent** that:

- Calls **your own MCP tools** (via a Foundry **toolbox**) with **OAuth identity passthrough**,
- Runs **Code Interpreter** (real Python sandbox) using a **client-created container** so the agent's managed identity never needs container-create permissions,
- Bakes in **skills** (Markdown instruction packs) — ships with a working PowerPoint (`.pptx`) generation skill,
- Comes with a small **local test UI** to chat with the deployed agent, complete OAuth consent, view tool activity, and download generated files.

> You bring your **own Foundry project + model deployment + MCP toolbox**. Everything environment-specific is supplied through config — no endpoints are hard-coded. The bundled Starburst/PPTX pieces are just a working example you can swap out.

> **Full build + troubleshooting history** lives in [foundry-skills-journey.md](foundry-skills-journey.md) — every dead end, error, and fix that produced this template. Read it when something breaks.

---

## What's in the box

| Path | Purpose |
|---|---|
| `src/agent-framework-agent-basic-responses/main.py` | The hosted agent: tool modes, MCP toolbox wiring, Code Interpreter container hack, skill injection, encrypted-reasoning fix |
| `src/.../skills/pptx-from-template/SKILL.md` | Example skill (build a `.pptx`, with or without an uploaded template) |
| `ui/app.py` | Local Flask test UI (chat, consent, activity, downloads) |
| `azure.yaml` | `azd` service/host definition for the hosted agent |
| `toolbox.yaml` | Example toolbox shape (bring your own) |
| `test_file_download.py` | Optional smoke test: generate a `.pptx` and verify it's a real file |
| `foundry-skills-journey.md` | The complete R&D + troubleshooting log |

---

## Prerequisites

**You need an Azure subscription, a Foundry project + model deployment, and the `azd` CLI.**

<details><summary>details</summary>

- **Azure Developer CLI (`azd`)** with the Foundry extension: `azd ext install microsoft.foundry`
- **Azure CLI (`az`)** for sign-in and token acquisition
- **Python 3.12+** (the agent container uses 3.13; the local UI works on 3.12+)
- An existing **Foundry project** and a **model deployment** (e.g. `gpt-4.1`). If you don't have one, `azd ai agent init` can guide you through creating it.
- (For toolbox mode) a **Foundry toolbox** exposing your MCP tools with OAuth identity passthrough.
</details>

---

## Setup — step by step

### Step 1 — Get the template into your workspace.

<details><summary>details</summary>

Copy this folder to your machine (or init it as its own git repo). Keep the structure intact — `azure.yaml` at the root and the agent under `src/agent-framework-agent-basic-responses/`.
</details>

### Step 2 — Sign in to Azure.

<details><summary>details</summary>

```powershell
az login
azd auth login
```
If your Foundry project lives in a **different tenant** than your home tenant, sign in against that tenant: `azd auth login --tenant-id <your-tenant-id>` (see the journey doc, "guest vs home identity", for why this matters).
</details>

### Step 3 — Point the agent at YOUR Foundry project + model.

<details><summary>details</summary>

Copy the example env and fill in your values:

```powershell
Copy-Item src/agent-framework-agent-basic-responses/.env.example src/agent-framework-agent-basic-responses/.env
```

Set at least:

- `FOUNDRY_PROJECT_ENDPOINT` — `https://<your-foundry-account>.services.ai.azure.com/api/projects/<your-project>`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` — your model deployment (e.g. `gpt-4.1`)

`azd` also stores these under `.azure/<env>/.env` after `azd env set` / provision. The UI reads that azd env automatically.
</details>

### Step 4 — Wire YOUR MCP tool endpoint + auth.

<details><summary>details</summary>

Set `TOOLBOX_MCP_ENDPOINT` to your toolbox's MCP URL and pick a tool mode via `AGENT_TOOL_MODE` (see the table below). Authentication is **OAuth identity passthrough**: the agent injects a fresh Entra bearer token (`https://ai.azure.com/.default`) on every toolbox request — no secrets in code.

To adapt the tool to your data source, edit the tool name/description and instructions in `main.py` (search for `starburst_toolbox`). The universal guardrail — *never pass an `authorization` argument or container id to the toolbox* — should stay; it prevents the model from mis-wiring credentials.
</details>

### Step 5 — (Optional) Add or edit skills.

<details><summary>details</summary>

Skills are **Markdown instructions injected into the system prompt at build time** — not tool calls. Drop a `skills/<name>/SKILL.md` under `src/agent-framework-agent-basic-responses/skills/`. `load_skills()` reads each file, strips YAML frontmatter, appends it to the agent instructions, and asks the model to emit a `SKILL_USED: <name>` marker when it applies one (the UI surfaces that as a badge).
</details>

### Step 6 — Deploy the hosted agent.

<details><summary>details</summary>

```powershell
azd deploy
```
First time, run `azd ai agent init` / `azd provision` if you don't already have the project + deployment. Deploy pulls dependencies fresh — see `requirements.txt`; pin versions there if you want reproducible builds (the journey doc explains a real breakage caused by an unpinned dependency).
</details>

### Step 7 — Run the local test UI.

**Create an environment (conda OR venv), install `ui/requirements.txt`, then `python ui/app.py` and open http://localhost:5005.**

<details><summary>Option A — Conda</summary>

Create Conda Environment:
```
conda create -n hosted-agent-ui python=3.12 ipykernel -y
```
Then:
```powershell
conda activate hosted-agent-ui
pip install -r ui/requirements.txt
python ui/app.py
```
</details>

<details><summary>Option B — venv</summary>

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r ui/requirements.txt
python ui/app.py
```
(macOS/Linux: `source .venv/bin/activate`.)
</details>

<details><summary>Using the UI</summary>

- Make sure `az login` is done and (for private networking) your VPN is on — the UI calls the deployed agent + the containers API with your identity.
- On the first turn after a deploy you'll see a **Sign in** link (toolbox OAuth consent) — complete it in the browser, then re-send.
- Attach files with the **+** button (they upload into the Code Interpreter container); the agent can read them.
- Generated files appear as **(new)** download chips. Expand **Response activity** to see tool calls.
</details>

### Step 8 — Smoke-test file generation (optional).

<details><summary>details</summary>

```powershell
python test_file_download.py
```
It creates a container, asks the agent to generate a `.pptx` via Code Interpreter, downloads it, and checks the `PK` zip signature (proof a real Office file was produced, not just claimed).
</details>

### Step 9 — When something breaks.

<details><summary>details</summary>

Read [foundry-skills-journey.md](foundry-skills-journey.md). It documents the RBAC 401/403s, the container-create sidestep, readiness 424s, the encrypted-reasoning 400 and its fix, and more — with the exact symptoms and resolutions.
</details>

---

## Tool modes (`AGENT_TOOL_MODE`)

| Mode | What runs |
|---|---|
| `toolbox` | Your MCP tools via the Foundry toolbox only (default). |
| `code_interpreter` | Foundry Code Interpreter (`container:auto`), no toolbox. |
| `ci_container_toolbox` | Code Interpreter with an explicit pre-created container + toolbox. |
| `ci_client_container` | Code Interpreter bound to a **client-created** container (+ toolbox when `CI_INCLUDE_TOOLBOX=1`). The managed identity never creates a container. Recommended. |

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | yes | Your Foundry project endpoint. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | yes | Your model deployment name (e.g. `gpt-4.1`). |
| `AGENT_TOOL_MODE` | no | One of the modes above. |
| `CI_INCLUDE_TOOLBOX` | no | `1` to add the toolbox alongside Code Interpreter. |
| `TOOLBOX_MCP_ENDPOINT` | for toolbox modes | Your toolbox MCP URL. |
| `AGENT_ENDPOINT` | UI only | Deployed agent Responses endpoint (falls back to the azd env). |

---

## Security notes

- **Nothing environment-specific is committed.** Endpoints, project/account names, subscription/tenant IDs, and managed-identity object IDs are all replaced with placeholders or supplied via config.
- `.azure/`, `.env`, `ui/logs/`, `*.log`, and generated `*.pptx` are git-ignored — do not commit them; they can contain your endpoints, tokens, or data.
- Toolbox auth is **per-request Entra tokens** (OAuth passthrough); there are no static secrets in the code.

---

## Non-goals / notes

- **Infrastructure:** provisioning is handled by `azd` + the Foundry extension — there is **no committed Bicep/Terraform** in this template. Bring your own Foundry project, or provision one with your preferred IaC.
- The bundled **Starburst** toolbox and **PPTX** skill are illustrative. Replace them with your own MCP tools and skills.
