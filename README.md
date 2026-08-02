# 🤖 Foundry Hosted Agent — Template

### 🎯 Purpose

> *A ready-to-use template for a **Microsoft Foundry hosted agent** with a **baked-in skill** and **MCP tools (with OAuth consent)**: build it → **deploy to Foundry** → **test the live endpoint locally via the Flask UI**.*
>
> *Publish to teams after? That's a **separate hand-off** to the [end-to-end publishing repo](https://github.com/kjain2002/foundry_to_teams_E2E_isolation_updated) — **this** current repo gets your hosted agent built, deployed, and working first.*

<details>
<summary>ℹ️ <strong>What's in this repo & how you test it</strong></summary>

<br>

It bundles a fully working sample agent — application code, infrastructure (Bicep), a local test UI, and this step-by-step guide — and is for **anyone who wants to stand up a Foundry hosted agent** that runs Python, calls their own tools, and follows custom instructions.

A PPT making **skill** (Markdown instruction pack) is baked in to the sample agent in this repo during deployment. Code used to generate/read the ppt files (aka. Code Interpreter) will run in **a container spun up by Foundry**. It also enables you to add **your MCP tools** via a Foundry **toolbox** (with **OAuth identity passthrough**).

The hosted agent is deployed to Foundry and you test the respective **live Foundry endpoint** from your laptop via the **Flask UI**. It should also be testable via the Foundry UI and the Foundry Toolkit extension — but if you include Code Interpreter specifically for file uploads and downloads, neither of those options works, and you can only use a custom UI like the one in this repo.

**This repo stops at a working, tested Foundry agent** — publishing it to **Teams** is a separate hand-off to the [end-to-end repo](https://github.com/kjain2002/foundry_to_teams_E2E_isolation_updated).

</details>

---

## 🗺️ The whole journey

| # | Stage | Do you need it? |
|---|---|---|
| **0** | [Set up your machine](#stage-0) | ✅ First — install CLIs + Python env |
| **1** | [Get the right Foundry resource](#stage-1) | ⏭️ Skip if you already have a project |
| **2** | [Roles & permissions](#stage-2) | ✅ Almost always — this is what breaks |
| **3** | [Smoke test](#stage-3) | 🧪 Optional but recommended — catch errors early |
| **4** | [Design your agent](#stage-4) | ✅ Tools, personality, skills |
| **5** | [Deploy the hosted agent](#stage-5) | ✅ Always |
| **6** | [Edit, test locally, publish to Teams](#stage-6) | ✅ Always |

<details>
<summary>🧭 <strong>New here / overwhelmed? Read this first</strong> (30‑second mental model)</summary>

<br>

**In one sentence:** you're building a chat agent that lives in *your* Foundry project, can run Python + call *your* tools, and knows how to do a task (like making a PowerPoint) — and you test it from a small web page on your laptop.

```
YOU (browser test UI)  ─►  YOUR AGENT (hosted in Foundry)  ─►  your tools + Python sandbox
```

**Two phases — that's the key concept:**

| | Phase | Plain English | Done by |
|---|---|---|---|
| 🏗️ | **Provision** | Make sure the Azure "house" exists (project + model). *Most people already have this.* | Stage 1 |
| 🚀 | **Deploy** | Ship your agent code into that house. *Always required.* | Stage 5 |

**The one thing to remember:** *point agent at your project → deploy → test.* Everything else is detail you pick up as you go.

</details>

---

<a id="stage-0"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">0️⃣ Stage 0 — Set up your machine</h2></summary>

> [!IMPORTANT]
> Do this **first.** You need the CLIs to deploy, and a **Python environment** to run the local UI, the smoke tests, and any Foundry Python you paste from VS Code agent mode.

### <span style="color:#58a6ff">0.1 — Install the CLIs & sign in</span>

<div style="margin-left:1.5em">

<details open>
<summary>🧰 <strong>azd + Azure CLI</strong></summary>

<br>

| Tool | Install | Why |
|---|---|---|
| **Azure Developer CLI (`azd`)** | [install](https://aka.ms/azd-install), then `azd ext install microsoft.foundry` | Provision + deploy the agent |
| **Azure CLI (`az`)** | [install](https://learn.microsoft.com/cli/azure/install-azure-cli) | Sign-in + tokens |
| **Python 3.12+** | [install](https://www.python.org/downloads/) | Local UI + scripts |

Then sign in:

```powershell
az login
azd auth login
```

> [!NOTE]
> If your Foundry project is in a **different tenant**, sign in against it: `az login --tenant <tenant-id>` and `azd auth login --tenant-id <tenant-id>`.

</details>

</div>

### <span style="color:#58a6ff">0.2 — Create a Python environment</span>

<div style="margin-left:1.5em">

> [!TIP]
> Needed for the local UI (Stage 6), the smoke tests, and any Python you run from VS Code agent mode. **Conda and venv are equivalent — pick either one.**

<details open>
<summary>🅰️ <strong>Conda</strong></summary>

<br>

```powershell
conda create -n foundry-agent python=3.12 ipykernel -y
conda activate foundry-agent
pip install -r ui/requirements.txt
```

</details>

<details>
<summary>🅱️ <strong>venv</strong> — same thing, use this instead of Conda</summary>

<br>

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r ui/requirements.txt
```
*(macOS/Linux: `source .venv/bin/activate`)*

</details>

> [!NOTE]
> This installs the **local UI** deps ([ui/requirements.txt](ui/requirements.txt)). The **agent's own** deps ([src/…/requirements.txt](src/agent-framework-agent-basic-responses/requirements.txt)) are baked into the container at deploy — you don't install those locally.

</div>

</details>

<a id="stage-1"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">1️⃣ Stage 1 — Get the right Foundry resource</h2></summary>

> [!NOTE]
> **Already have a Foundry project + model deployment?** ⏭️ **Skip to [Stage 2](#stage-2).** You only do Stage 1 to create a brand‑new one.

### <span style="color:#58a6ff">1.1 — Pick your setup type</span>

<div style="margin-left:1.5em">

Foundry has **3 setups**. They differ only in **where your agent's data lives**.

| If you want… | Pick | Storage/data |
|---|---|---|
| To get started fast, no data-residency rules | **Basic** | Microsoft‑managed (nothing in your subscription) |
| To **own** the data (compliance, CMK) | **Standard** | Your Storage + Cosmos + AI Search |
| Standard **+ no public network** at all | **Standard + Private** | Yours, inside your VNet |

<details>
<summary>🔍 <strong>How to decide in 10 seconds</strong></summary>

<br>

- **Demo / PoC / internal tool?** → **Basic**. Done.
- **Regulated data, need CMK, or "data must stay in our tenant"?** → **Standard**.
- **"No public endpoints, everything in our VNet"?** → **Standard + Private**.

> [!IMPORTANT]
> **Basic vs Standard is separate from networking.** "Bring your own network" does **not** force "bring your own storage." You can run Basic with managed storage *and* a private inbound endpoint.

📚 Official docs: [Choose your setup](https://learn.microsoft.com/azure/foundry/agents/environment-setup#choose-your-setup) · [Where is data stored?](https://learn.microsoft.com/azure/foundry/agents/faq#where-is-this-data-stored)

</details>

</div>

### <span style="color:#58a6ff">1.2 — Provision it</span>

<div style="margin-left:1.5em">

> [!TIP]
> This branch's [`infra/terraform/`](infra/terraform/README.md) adds a **project + model** to an **existing Foundry account**. It does **not** create the account or the Standard storage/Cosmos — use the official templates below for those.

<details>
<summary>🅰️ <strong>Basic setup</strong> — add a project + model to an existing account</summary>

<br>

**Step 1 — Copy the example vars:**

```powershell
Copy-Item infra/terraform/example.tfvars infra/terraform/my.tfvars
```

**Step 2 — Fill in `my.tfvars`** (at least these):

```
existing_account_name   = "your-foundry-account"
existing_resource_group = "your-resource-group"
project_name            = "my-agent-project"
model_name              = "gpt-4.1"
```

**Step 3 — Init & apply (from the terraform folder):**

```powershell
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply -var-file=my.tfvars
```

**Step 4 — Grab the project endpoint** (you'll need it soon):

```powershell
terraform -chdir=infra/terraform output -raw project_endpoint
```

> Prefer **Bicep**? Same thing lives on the **`main` branch** → `infra/bicep/`.

</details>

<details>
<summary>🅱️ <strong>Standard setup</strong> — bring your own Storage / Cosmos / Search</summary>

<br>

Use Microsoft's official Bicep template (it wires up your resources for you):

📦 [`43-standard-agent-setup-with-customization`](https://github.com/azure-ai-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/43-standard-agent-setup-with-customization)

You provide the ARM resource IDs of your existing **Storage**, **Cosmos DB (NoSQL)**, and **AI Search**. Get a resource ID like this:

```powershell
az storage account show -g <rg> -n <storage-account> --query id -o tsv
```

> [!IMPORTANT]
> Standard means **you** must later grant the agent's identity data‑plane roles on those resources — that's [Stage 2](#stage-2).

</details>

<details>
<summary>🅲 <strong>Standard + Private (network‑isolated)</strong></summary>

<br>

Start from the standard template above, then follow the network‑secured guide to add your VNet, private endpoints, and DNS:

📚 [Network‑secured agent setup](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks)

</details>

</div>

</details>

<a id="stage-2"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">2️⃣ Stage 2 — Roles & permissions</h2></summary>

> [!WARNING]
> **90% of failures are here.** If you skip this you'll hit `401 / 403 / 500` errors the moment the agent runs. Do it before deploying.

### <span style="color:#58a6ff">2.1 — Which roles</span>

<div style="margin-left:1.5em">

<details open>
<summary>✅ <strong>Everyone needs (Basic & Standard)</strong></summary>

<br>

Each identity below needs **`Azure AI User`** on the **project** (some tenants show it as **`Foundry User`** — same id `53ca6127‑db72‑4b80‑b1b0‑d745d6d5456d`; use the id, not the name).

| Identity | What it is | Role | Scope | Find its object id |
|---|---|---|---|---|
| **You** (deployer) | Your login (may be a guest if the project is in a different tenant) | `Azure AI User` | the **project** | `az ad signed-in-user show --query id -o tsv` |
| **Agent project MI** | Runs the deployed agent | `Azure AI User` | the **project** | Printed **in the 500/403 error text** |
| **Foundry account MI** | The AIServices account identity | `Azure AI User` | the **project** | `az cognitiveservices account show -n <acct> -g <rg> --query identity.principalId -o tsv` |

> [!NOTE]
> This one role fixes the common `401 / 403 / 500` on model + toolbox + history calls.

</details>

<details>
<summary>➕ <strong>Standard setup ONLY</strong> — extra data‑plane roles</summary>

<br>

Because the storage/Cosmos are **yours**, the agent MI must be allowed to touch them:

| Identity | Role | Scope |
|---|---|---|
| Agent project MI | **`Storage Blob Data Contributor`** | your **storage account** |
| Agent project MI | **`Cosmos DB Operator`** | your **Cosmos account** |

> [!IMPORTANT]
> On **Basic** there is **no storage account in your subscription**, so there's nothing to grant here — skip it. (Files the agent *generates* live in the Code Interpreter sandbox; uploads/history use Microsoft‑managed storage.)

</details>

</div>

### <span style="color:#58a6ff">2.2 — Assign the roles</span>

<div style="margin-left:1.5em">

<details>
<summary>🖱️ <strong>Portal (click‑by‑click)</strong></summary>

<br>

1. Open your **Foundry project** → **Access control (IAM)**
2. **+ Add** → **Add role assignment**
3. Pick role **`Azure AI User`** → **Next**
4. **Assign access to** → *User* (for you) or *Managed identity / Service principal* (for the MIs)
5. Select the member → **Review + assign**
6. Repeat for all three identities.

</details>

<details>
<summary>⌨️ <strong>Commands (copy‑paste)</strong></summary>

<br>

**Fill in once:**

```powershell
$SUB   = "<subscription-id>"
$RG    = "<resource-group>"
$ACCT  = "<foundry-account-name>"
$PROJ  = "<project-name>"
$AIUSER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"   # Azure AI User (use the id, not the name)
$PROJECT_SCOPE = "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCT/projects/$PROJ"
```

**You (deployer):**

```powershell
$ME = az ad signed-in-user show --query id -o tsv
az role assignment create --assignee-object-id $ME --assignee-principal-type User `
  --role $AIUSER --scope $PROJECT_SCOPE
```

**Both managed identities:**

```powershell
$AGENT_MI = "<object-id-from-the-error-text>"
$ACCT_MI  = az cognitiveservices account show -n $ACCT -g $RG --query identity.principalId -o tsv
az role assignment create --assignee-object-id $AGENT_MI --assignee-principal-type ServicePrincipal --role $AIUSER --scope $PROJECT_SCOPE
az role assignment create --assignee-object-id $ACCT_MI  --assignee-principal-type ServicePrincipal --role $AIUSER --scope $PROJECT_SCOPE
```

<details>
<summary>Standard‑only: storage + Cosmos</summary>

```powershell
$STORAGE = "<storage-account>"
$COSMOS  = "<cosmos-account>"
az role assignment create --assignee-object-id $AGENT_MI --assignee-principal-type ServicePrincipal `
  --role "Storage Blob Data Contributor" `
  --scope "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Storage/storageAccounts/$STORAGE"
az role assignment create --assignee-object-id $AGENT_MI --assignee-principal-type ServicePrincipal `
  --role "Cosmos DB Operator" `
  --scope "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS"
```

</details>

</details>

<details>
<summary>🤖 <strong>Or ask VS Code agent mode (Azure MCP)</strong></summary>

<br>

> Using Azure MCP, assign the **Azure AI User** role (id `53ca6127-db72-4b80-b1b0-d745d6d5456d`) to object id `<id>` at scope of my Foundry project `<project>` in resource group `<rg>`.

</details>

> [!NOTE]
> ⏱️ Role changes take **5–30 min** to propagate. If it still 403s after that, redeploy cold.

</div>

### <span style="color:#58a6ff">2.3 — (Optional) Smoke‑test your permissions early</span>

<div style="margin-left:1.5em">

> [!TIP]
> Catch `401/403/500` **before** you build your real agent by deploying a throwaway one. → See [Stage 3](#stage-3).

</div>

</details>

<a id="stage-3"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">3️⃣ Stage 3 — Smoke test (optional)</h2></summary>

> [!TIP]
> Before you customize anything, deploy the **bundled sample agent as‑is** to flush out `401 / 403 / 500` role errors early. The repo already ships a ready‑to‑go agent — **no code required.**

### <span style="color:#58a6ff">3.1 — Set the required env values</span>

<div style="margin-left:1.5em">

<details open>
<summary>📝 <strong>Point the sample at your project + model</strong></summary>

<br>

> [!IMPORTANT]
> **Config lives in the azd environment — not the `.env` file.** `azd deploy` substitutes the `${...}` values in [azure.yaml](azure.yaml) from **azd env values**, and the local UI reads the same store ([`.azure/<env>/.env`](ui/app.py)). The `src/.../.env` file is read **only** when you run `main.py` directly. So set your values with **`azd env set`**:

**Set these — your project endpoint + model deployment name:**

```powershell
azd env set FOUNDRY_PROJECT_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "gpt-4.1"
azd env set AGENT_TOOL_MODE "code_interpreter"
```

> [!NOTE]
> No azd environment yet? Create one first: `azd env new` (or run `azd ai agent init`). Running `main.py` directly instead? Then `Copy-Item src/agent-framework-agent-basic-responses/.env.example src/agent-framework-agent-basic-responses/.env` and set the same values there.

<details>
<summary>🔎 <strong>Where do I find the endpoint + model name?</strong></summary>

<br>

- **Portal** — your **Foundry project** → **Overview / Settings** = the **endpoint**; **Models + endpoints** = the **model deployment name**.
- **VS Code agent mode (Azure MCP)** — paste:
  > Using Azure MCP, show the **project endpoint** and **model deployment names** for my Foundry project `<project-name>`.

</details>

> [!IMPORTANT]
> The sample **defaults to `toolbox` mode**, which needs a real toolbox URL you don't have yet. For the smoke test, **temporarily set `AGENT_TOOL_MODE=code_interpreter`** so the agent just talks to the model — no toolbox, no OAuth. You'll change it back in Stage 4 if you add tools.

</details>

</div>

### <span style="color:#58a6ff">3.2 — Deploy the sample, invoke it, then tear it down</span>

<div style="margin-left:1.5em">

<details open>
<summary>🧪 <strong>Temporary deploy → invoke → clean up</strong></summary>

<br>

```powershell
# 1. Deploy the ready-to-go sample agent
azd deploy

# 2. Invoke it — a plain reply means model access + roles are OK
azd ai agent invoke "hello, are your permissions working?"
```

**Read the result:**

- ✅ **Got a reply** → model access + roles are good. Continue to Stage 4.
- ❌ **500 "identity does not have permissions"** → redo [2.2](#22--assign-the-roles) for the **agent MI**, wait 5–30 min, retry.
- ❌ **401 / 403** → your **deployer** role or tenant sign‑in is off (see [Errors](#errors)).

**Clean up the throwaway:**

```powershell
azd down --purge
```

> [!CAUTION]
> `azd down --purge` deletes **everything in this azd environment.** Only run it if `azd` **created** the project. If you deployed into a **pre‑existing / shared** project, skip it — delete just the test agent, or use a **separate azd environment** for the smoke test.

</details>

</div>

</details>

<a id="stage-4"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">4️⃣ Stage 4 — Design your agent</h2></summary>

Everything you customize lives in **one file** (`main.py`) plus your **skill** folder.

> [!TIP]
> Change **skills** for *task* behavior and **base instructions** for *personality*. You rarely need to touch anything else.

### <span style="color:#58a6ff">4.1 — Point agent at your project + model</span>  ⭐ *(required)*

<div style="margin-left:1.5em">

<details open>
<summary>📝 <strong>Set 2 values in <code>.env</code></strong></summary>

<br>

> [!NOTE]
> **Did the Stage 3 smoke test?** These azd env values are already set — just **confirm** them and skip to 4.2. (You'll also flip `AGENT_TOOL_MODE` back from `code_interpreter` if you add tools.)

**Set your project endpoint + model deployment name as azd env values** — this is what `azd deploy` and the local UI read (the `src/.../.env` file is only for running `main.py` directly):

```powershell
azd env set FOUNDRY_PROJECT_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "gpt-4.1"
```

> [!TIP]
> Confirm what's set with `azd env get-values`.

<details>
<summary>🔎 <strong>Where do I find the endpoint + model name?</strong></summary>

<br>

- **Portal** — your **Foundry project** → **Overview / Settings** = the **endpoint**; **Models + endpoints** = the **model deployment name**.
- **VS Code agent mode (Azure MCP)** — paste:
  > Using Azure MCP, show the **project endpoint** and **model deployment names** for my Foundry project `<project-name>`.

</details>

</details>

</div>

### <span style="color:#58a6ff">4.2 — Add your MCP tool(s)</span>  *(optional — skip if you only want skills)*

<div style="margin-left:1.5em">

<details>
<summary>🔌 <strong>If you want your own tool(s) → put them in a toolbox, then point the agent at it</strong></summary>

<br>

> [!NOTE]
> A **toolbox** is one Foundry-managed MCP endpoint that can expose **many tools/connections** at once. Add as many tools as you like to a single toolbox — the agent reaches them all through **one** `TOOLBOX_MCP_ENDPOINT`. (Truly need separate endpoints? See *Advanced* at the bottom.)

> [!IMPORTANT]
> **What goes in a toolbox — and what doesn't.** A toolbox is **only** for **external MCP tools / data connections that need OAuth** (e.g. a SQL/database source, SharePoint, Logic Apps, a custom MCP server…).

<div style="margin:1.25em 0;color:#f85149">

**Do NOT** put Foundry's **built-in runtime tools** in a toolbox — most importantly **Code Interpreter**.

</div>

In this template Code Interpreter is wired **separately** as a native SDK tool bound to a **client-created container** (that's what `AGENT_TOOL_MODE=ci_client_container` + `CI_INCLUDE_TOOLBOX=1` do) — it runs Python *inside* Foundry, it isn't an MCP data connection, and it needs the container/RBAC flow that a toolbox can't provide. See the [architecture diagrams](hosted_agent%20_overview_and_sample_architecture/presentation.html).

**Part A — Create a toolbox and add one or more tools.** Pick whichever way you like:

<details>
<summary>🖱️ <strong>Foundry portal (UI)</strong></summary>

<br>

1. Foundry portal → your project → **Toolboxes** → **Create toolbox**
2. **Add a tool/connection** (your data source, Logic Apps, a custom MCP server…) → finish the wizard
3. **Repeat step 2** for every tool you want in this toolbox
4. Open the toolbox → copy its **MCP endpoint URL**:
   `https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<toolbox>/mcp?api-version=v1`

</details>

<details>
<summary>🧰 <strong>Foundry Toolkit (AI Toolkit) in VS Code</strong></summary>

<br>

1. Install the **AI Toolkit / Foundry Toolkit** extension.
2. Open the **Foundry** view → **Toolboxes** → create / manage a toolbox.
3. **Add tool** for each tool you want and wire its connection.
4. Copy the toolbox's **MCP endpoint URL** from its details.

</details>

<details>
<summary>⌨️ <strong>Code / CLI (azd)</strong></summary>

<br>

```powershell
azd ai toolbox --help          # discover the toolbox commands
# create a toolbox + add tools/connections, then read its MCP endpoint:
azd ai toolbox show <toolbox-name>
```

</details>

<details>
<summary>🤖 <strong>VS Code agent mode (find + add for you)</strong></summary>

<br>

Paste into **VS Code agent mode** (Azure / Foundry MCP enabled):

> Using the Foundry MCP tools, find a tool/connection for **&lt;what you need — e.g. "a SQL database", "SharePoint", "Logic App X"&gt;** in my Foundry project `<project>`, add it to a toolbox named `<toolbox>` (create the toolbox if it doesn't exist), and return the toolbox's **MCP endpoint URL**.

</details>

**Part B — Point the agent at your toolbox.** Set the endpoint as an azd env value, then name the tool in code:

```
src/
└─ agent-framework-agent-basic-responses/
   └─ main.py    ← name the tool
```

Set the toolbox endpoint + tool mode (these flow to `azd deploy` and the local UI):

```powershell
azd env set TOOLBOX_MCP_ENDPOINT "<the MCP URL you copied>"
azd env set AGENT_TOOL_MODE "ci_client_container"
azd env set CI_INCLUDE_TOOLBOX "1"
```

*(The bundled sample wires up **Starburst** — one specific SQL data source — purely as an example. You'll rename it to your own tool below.)*

In **`main.py`** — `Ctrl+F` for `starburst_toolbox` (≈3 spots) and change each:

- `name="starburst_toolbox"` → a name for this toolbox (e.g. `"data_tools"` — it fronts **all** tools in the toolbox)
- `description="Starburst data tools…"` → what the toolbox's tools do
- Rewrite the schema hints (`SHOW SCHEMAS FROM sample`…) for your data source (or delete them if not SQL)

> [!TIP]
> **One toolbox, many tools:** everything you added in Part A is already exposed through that single endpoint — no extra code. The model picks the right tool per request.

> [!CAUTION]
> **Keep the guardrail** *never pass an `authorization` arg, token, or container id to the toolbox.* It stops the model from mis‑wiring credentials.

<details>
<summary>➕ <strong>Advanced — when (and how) to use <em>multiple</em> toolboxes</strong></summary>

<br>

**One toolbox usually covers you** — it can hold many tools behind a single endpoint. Reach for a **second toolbox only** when:

- The tools need **different OAuth consent / identity scopes** (separate sign-ins).
- They're **owned or governed by different teams** and you want separate permissions/lifecycle.
- You're combining connections that **can't share one toolbox** (different providers/regions).

Otherwise, just add more tools to the **same** toolbox (Part A) — no code change.

**To wire a second endpoint,** add another MCP tool in `main.py` next to the existing one (in the toolbox builder), and a matching env var:

```python
tools.append(
    MCPStreamableHTTPTool(
        name="second_toolbox",
        description="What this second toolbox does",
        url=os.getenv("TOOLBOX2_MCP_ENDPOINT"),
        http_client=httpx.AsyncClient(auth=_ToolboxAuth(get_token), timeout=120.0),
        load_prompts=False,
    )
)
```

Then `azd env set TOOLBOX2_MCP_ENDPOINT "<url>"` **and** add a matching `- name: TOOLBOX2_MCP_ENDPOINT` / `value: ${TOOLBOX2_MCP_ENDPOINT}` entry under `environmentVariables` in [azure.yaml](azure.yaml) so it reaches the deployed container. Repeat for each extra endpoint.

</details>

</details>

</div>

### <span style="color:#58a6ff">4.3 — OAuth consent</span>  *(only if your toolbox needs sign‑in)*

<div style="margin-left:1.5em">

<details>
<summary>🔐 <strong>If your tool requires user sign‑in → nothing to code, just know the flow</strong></summary>

<br>

Auth is **automatic** — the agent injects a fresh Entra token on every toolbox call (no secrets in code). When a toolbox needs consent, the agent returns a **Sign in** link. Click it, complete consent, then re-send your request.

> [!NOTE]
> The **Foundry playground can handle OAuth consent** for normal toolbox testing. Use the **local UI** when you need this template's Code Interpreter **file upload/download** flow too — it creates the container and transfers its files. See [Stage 6](#stage-6).

</details>

</div>

### <span style="color:#58a6ff">4.4 — Personality / base instructions</span>  *(optional)*

<div style="margin-left:1.5em">

<details>
<summary>🎭 <strong>If you want to change the agent's persona/tone → edit <code>base_instructions</code> in <code>main.py</code></strong></summary>

<br>

The final prompt is **assembled in code**:

```
final prompt = base_instructions (persona + tool rules)   ← main.py
             + your SKILL.md text (the task recipe)        ← 4.5, appended by load_skills()
             + SKILL_USED marker note                      ← added automatically
```

**Edit this file:**

```
src/
└─ agent-framework-agent-basic-responses/
   └─ main.py   ← edit the base_instructions string
```

There are several `base_instructions` blocks — edit the one matching your `AGENT_TOOL_MODE` (default `ci_client_container`):

| `AGENT_TOOL_MODE` | Block to edit |
|---|---|
| `ci_client_container` *(default)* | `instructions = (...)` inside `_ClientContainerToolboxAgent` |
| `ci_container_toolbox` | `base_instructions = (...)` in the `_build_ci_container_agent` branch |
| `code_interpreter` | `base_instructions = (...)` in the `code_interpreter` branch |
| toolbox‑only (`else`) | `base_instructions = (...)` in the final `else` branch |

**How:** `Ctrl+F` for `"You are a friendly assistant"` → rewrite the persona.

> [!CAUTION]
> Keep the functional lines: the `CONTAINER_ID=… FILE=…` download marker, `_TOOLBOX_GUARDRAILS`, and `+ load_skills(...)` — or file download / tool auth break.

<div style="margin:1.25em 0">

<details>
<summary>🤖 <strong>Optional — ask VS Code agent mode to perform this step for you</strong></summary>

<br>

Paste this into **VS Code agent mode**, replacing the bracketed parts:

> In `src/agent-framework-agent-basic-responses/main.py`, update the base instructions for `AGENT_TOOL_MODE="<your-mode>"` to make the agent: **<describe the persona, tone, and behavior you want>**. Keep the existing tool-use instructions and functional wiring intact. Do not remove or change `_TOOLBOX_GUARDRAILS`, `+ load_skills(...)`, or the `CONTAINER_ID=... FILE=...` download marker. Show me the exact change before applying it.

</details>

</div>

</details>

</div>

### <span style="color:#58a6ff">4.5 — Skills = your task recipe</span>  *(this is where YOUR task lives)*

<div style="margin-left:1.5em">

<details open>
<summary>📄 <strong>Replace/edit the example SKILL.md</strong></summary>

<br>

A **skill** is plain Markdown that gets baked into the agent's prompt — not a tool call.

**Edit this file:**

```
src/
└─ agent-framework-agent-basic-responses/
   └─ skills/
      └─ pptx-from-template/
         └─ SKILL.md   ← replace/edit as needed
```

- **Replace its contents** with your task steps ("When the user asks for X, do 1–4…"). Keep it focused.
- No code change — on deploy, `load_skills()` reads every `skills/*/SKILL.md` and appends it.
- The agent emits `SKILL_USED: <name>` when it applies a skill; the UI shows a **"Skill used"** badge.

> [!TIP]
> Want multiple skills? Add more `skills/<name>/SKILL.md` folders — each is auto‑loaded.

</details>

<div style="margin:1.25em 0">

<details>
<summary>🤖 <strong>Optional — ask VS Code agent mode to generate a skill for you</strong></summary>

<br>

Paste this into **VS Code agent mode**, replacing the bracketed parts:

> In this repository, create a bundled agent skill named `<skill-name>` for this task: **<describe exactly what the agent should do>**. Add it at `src/agent-framework-agent-basic-responses/skills/<skill-name>/SKILL.md`. Write a concise Markdown task recipe with clear triggers, ordered steps, required inputs, constraints, and the expected result. Follow the style of the existing `pptx-from-template` skill. Do not edit `main.py`; skills are loaded automatically on deploy. Show me the proposed `SKILL.md` before creating it.

</details>

</div>

</div>

</details>

<a id="stage-5"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">5️⃣ Stage 5 — Deploy the hosted agent</h2></summary>

<details open>
<summary>🚀 <strong>One command</strong></summary>

<br>

Run this from the **repository root** — the folder that contains `azure.yaml`:

```
foundry-hosted-agent-template/
├─ azure.yaml   ← run azd deploy here
├─ src/
└─ ui/
```

```powershell
azd deploy
```

*(First time with no project yet: run `azd ai agent init` then `azd provision` first.)*

</details>

<details>
<summary>🛟 <strong>If deploy fails on ACR → use the zip/source path</strong></summary>

<br>

On locked‑down accounts the container push to ACR fails. This template already uses the **source/zip** path:

1. Confirm [`azure.yaml`](azure.yaml) uses `codeConfiguration.entryPoint: main.py` + `runtime: python_3_13` and has **no** `docker:`/`image:` block. *(Already set.)*
2. Re‑run `azd deploy` — Foundry builds it server‑side, no ACR push.
3. If azd still routes to ACR: temporarily enable the ACR's public network access, deploy, re‑disable.

</details>

> [!WARNING]
> **First real turn 500s?** That's almost always missing roles → go back to [Stage 2](#stage-2), grant `Azure AI User` to the **agent MI**, wait, redeploy.

</details>

<a id="stage-6"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">6️⃣ Stage 6 — Edit, test locally & publish to Teams</h2></summary>

> [!CAUTION]
> Use the **local UI** in this repo for Code Interpreter **file uploads and downloads**. The Foundry portal playground is still useful for ordinary chat and OAuth-consent testing.

<details open>
<summary>❓ <strong>When you need the local UI instead of the playground</strong></summary>

<br>

1. **Someone must create the Code Interpreter container** — the agent's MI can't (RBAC 403). The local UI creates it with *your* identity and passes the id in.
2. **File upload/download needs that container** — the local UI uploads your attachments into it and exposes generated files as download links.
3. **OAuth consent is not the limitation** — the Foundry playground can show the **Sign in** flow for toolbox calls. The local UI also renders it, so it covers both toolbox consent and files in one place.

> [!NOTE]
> This isn't a networking limitation. The Playground can exercise the agent's normal chat and toolbox/OAuth path, but it doesn't supply this template's client-created container or its file-transfer UI. Separately, a **private** Foundry resource requires VPN / private-endpoint connectivity for *any* client — including the Playground, Foundry Toolkit, `az`/`azd`, and this local UI.

</details>

### <span style="color:#58a6ff">6.1 — Run the local test UI</span>

<div style="margin-left:1.5em">

<details open>
<summary>▶️ <strong>Activate your Stage 0 environment + run</strong></summary>

<br>

You already installed the local UI dependencies in **Stage 0**. Open a new terminal in the repository root, activate that same environment, then run the UI.

**Conda:**

```powershell
conda activate foundry-agent
python ui/app.py
```

<details>
<summary>Prefer venv?</summary>

```powershell
.venv\Scripts\Activate.ps1
python ui/app.py
```
*(macOS/Linux: `source .venv/bin/activate`)*

</details>

Then open **http://localhost:5005**.

</details>

<details>
<summary>💬 <strong>First‑run walkthrough</strong></summary>

<br>

1. In another terminal: `az login` (+ VPN if the project is private).
2. Send a message. On the **first turn after a deploy**, click the **Sign in** link (toolbox consent), finish in the browser, come back, **re‑send**.
3. Attach a file (e.g. a PPTX template) with **+** — it uploads into the container.
4. Generated files appear as **(new)** download chips. Expand **Response activity** to see tool calls.

> If the UI can't reach the agent: check `az login`, VPN (private projects), and that `AGENT_ENDPOINT` points at the deployed agent.

</details>

</div>

### <span style="color:#58a6ff">6.2 — (Optional) Smoke‑test file generation</span>

<div style="margin-left:1.5em">

<details>
<summary>🧪 <strong>Prove a real file came out</strong></summary>

<br>

```
test_file_download.py   ← python this
```

```powershell
python test_file_download.py
```

Creates a container, asks the agent to generate a `.pptx`, downloads it, and checks the `PK` zip signature (proof it's a real Office file).

</details>

</div>

### <span style="color:#58a6ff">6.3 — 🎉 Working? Publish to Teams</span>

<div style="margin-left:1.5em">

> [!TIP]
> Once the local UI behaves the way you want, take it to production in Teams.

➡️ **Go to the end‑to‑end publishing repo:** [foundry_to_teams_E2E_isolation_updated](https://github.com/kjain2002/foundry_to_teams_E2E_isolation_updated)

</div>

</details>

<a id="errors"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">🚑 Errors you'll probably hit</h2></summary>

<details open>
<summary>① <strong>ACR deploy fails</strong> → use zip/source deploy</summary>

The image push to a private/locked ACR fails. This template already uses the source path — confirm `azure.yaml` has no `docker:`/`image:` block and re‑run `azd deploy`. See [Stage 5](#stage-5).

</details>

<details open>
<summary>② <strong>HTTP 500 / 401 "identity does not have permissions"</strong></summary>

The **agent MI** has no Foundry role. Grant **`Azure AI User`** to the agent MI + account MI on the project ([Stage 2](#stage-2)), wait 5–30 min, redeploy. **The single most common blocker.**

</details>

| Error | Cause | Fix |
|---|---|---|
| **424 `session_not_ready`** | Container created synchronously blocks readiness | Use `ci_client_container` (default) |
| **403 on container create** | MI can't create CI containers | Use `ci_client_container` — client creates it |
| **400 "Encrypted content is not supported"** | Unpinned `agent-framework-foundry` adds encrypted reasoning; `gpt-4.1` rejects it | Already patched in `main.py`; if it returns, pin the package in `requirements.txt` |
| **`oauth_consent_request` dropped** | Playground can't surface consent | Use the local UI |
| Toolbox **500 "Cancelled via cancel scope"** | Toolbox MCP server has no `ping` | Already patched in `main.py` |
| **Storage write 403** (*Standard + Private only*) | Blob private endpoint / role missing | See private‑setup note below |

Full history + fixes: [foundry-skills-journey.md](foundry-skills-journey.md).

<details>
<summary>🔒 <strong>Extra networking — ONLY for Standard + Private setups</strong></summary>

<br>

> [!NOTE]
> **Skip this entirely on Basic or Standard‑public.** It applies only when you brought your own storage **and** disabled public network access.

- **Storage blob private endpoint** (+ `privatelink.blob.core.windows.net` DNS zone linked to your VNet, `bypass=AzureServices`) — else agent writes 403.
- Same for **Cosmos** (`privatelink.documents.azure.com`) if history writes 403.
- **Client side:** connect the **VPN** so the private endpoint resolves; the UI runs on your machine ([6.1](#61--run-the-local-test-ui)).
- **Skill authoring caveat:** publishing skills *into* an isolated project via the write API 403s (a preview gap) — **you don't hit this**, because this template **bundles** `SKILL.md` locally ([4.5](#45--skills--your-task-recipe-this-is-where-your-task-lives)). Keep using bundled skills.

Details: [foundry-skills-journey.md](foundry-skills-journey.md#L193).

</details>

</details>

<a id="project-structure"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">📁 Project structure</h2></summary>

```
foundry-hosted-agent-template/
├── src/
│   └── agent-framework-agent-basic-responses/   # The hosted agent (what gets deployed)
│       ├── main.py             # Tool modes, toolbox wiring, CI container, skill injection
│       ├── requirements.txt    # Python deps baked into the container image
│       ├── Dockerfile          # Container build (installs deps, runs main.py)
│       ├── .env.example        # Copy to .env and fill in your values
│       ├── .azdignore          # Files azd should NOT upload when deploying
│       ├── .dockerignore       # Files excluded from the image build context
│       └── skills/
│           └── pptx-from-template/
│               └── SKILL.md    # Example skill (build a .pptx) — copy to make your own
├── ui/
│   ├── app.py                  # Local Flask test UI (chat, consent, activity, downloads)
│   └── requirements.txt        # Python deps for the UI
├── infra/
│   └── terraform/
│       ├── main.tf             # Adds project + model (+ App Insights + RBAC) to an account
│       ├── variables.tf        # Input variables (account, project, model, RBAC…)
│       ├── outputs.tf          # Outputs (project_endpoint, model name, etc.)
│       ├── example.tfvars      # Copy to your own .tfvars and fill in values
│       └── README.md           # How to deploy the Terraform
├── azure.yaml                  # azd service/host definition (Foundry hosted agent)
├── toolbox.yaml                # Example toolbox shape — bring your own
├── test_file_download.py       # Optional smoke test — make a .pptx and verify it's real
├── foundry-skills-journey.md   # Full R&D + troubleshooting log
├── hosted_agent _overview_and_sample_architecture/
│   ├── presentation.html       # Open this to browse the architecture walkthrough
│   └── *.html / *.png          # Supporting hosted-agent and container diagrams
├── AGENTS.md / CLAUDE.md       # Instructions for AI coding assistants in this repo
├── .gitignore                  # Keeps secrets/artifacts (.env, .azure/, *.pptx) out of git
└── README.md                   # You are here
```

</details>

<a id="reference"></a>
<details>
<summary style="margin:1.4em 0 .4em;padding-bottom:.3em;border-bottom:1px solid #484848;"><h2 style="display:inline;border:0;padding:0;">🔧 Reference</h2></summary>

<details>
<summary><strong>Tool modes (<code>AGENT_TOOL_MODE</code>)</strong></summary>

<br>

| Mode | What runs |
|---|---|
| `toolbox` | Your MCP tools via the Foundry toolbox only |
| `code_interpreter` | Foundry Code Interpreter (`container:auto`), no toolbox |
| `ci_container_toolbox` | Code Interpreter with a pre‑created container + toolbox |
| `ci_client_container` | Code Interpreter bound to a **client‑created** container (+ toolbox if `CI_INCLUDE_TOOLBOX=1`). **Recommended.** |

</details>

<details>
<summary><strong>Environment variables</strong></summary>

<br>

| Variable | Required | Meaning |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | ✅ | Your Foundry project endpoint |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | ✅ | Model deployment name (e.g. `gpt-4.1`) |
| `AGENT_TOOL_MODE` | – | One of the modes above |
| `CI_INCLUDE_TOOLBOX` | – | `1` to add the toolbox alongside Code Interpreter |
| `TOOLBOX_MCP_ENDPOINT` | for toolbox modes | Your toolbox MCP URL |
| `AGENT_ENDPOINT` | UI only | Deployed agent endpoint (falls back to azd env) |

</details>

<details>
<summary><strong>Security notes</strong></summary>

<br>

- Nothing environment‑specific is committed — endpoints, IDs, and names are placeholders or config.
- `.azure/`, `.env`, `ui/logs/`, `*.log`, generated `*.pptx` are git‑ignored — don't commit them.
- Toolbox auth is **per‑request Entra tokens** (OAuth passthrough) — no static secrets.

</details>

</details>
