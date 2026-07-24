# Foundry Skills — Hands-On Journey

> Living log of trying skills in Microsoft Foundry, for the the client skills session.
> Format: one-line summary per step → expand for details. Broad → narrow.

## Goal
Build and use a **Foundry skill** (a `SKILL.md`) — likely a **PPT-from-template** skill
for Siddarth — to understand, demo, and present skills in Foundry. Add a custom tool later
if the skill alone isn't enough.

## Chosen route
**Agents-as-code with `azd` + a Foundry toolbox** (most production-friendly for the client;
reusable across their foundational-agent fleet; fits CI/CD). Simpler "direct injection"
route is the alternative we try later.

---

## Key Q&A (concepts)

**Q: Configure via code or the portal UI?** → Mostly **code**.
<details><summary>details</summary>

- Skill is a `SKILL.md` file authored in VS Code.
- Wired with the `azd` CLI (`azd ai agent init`, toolbox commands).
- Portal is used lightly (view project, test the deployed agent).
- Great deck contrast: Foundry = edit file + CLI; Copilot Studio = portal + Azure Bot Service.
</details>

**Q: Can the agent call/use the skill in the platform after?** → **Yes.**
<details><summary>details</summary>

- **Direct injection:** `SKILL.md` bundled with the deployed agent; read at startup, applied automatically.
- **Toolbox (MCP):** skill published to a toolbox endpoint; discovered/loaded on demand.
- After deploy you can test/invoke in the Foundry portal playground or via CLI/API.
- Demo arc: show file → deploy → ask agent "make a deck from the template" → it uses the skill.
</details>

**Q: Can the skill be passed via the platform too?** → **Partly.**
<details><summary>details</summary>

- Skill content **lives on the platform** (Foundry Skills API + toolbox store/serve it).
- But authoring/attaching is currently **code/CLI-first**; no confirmed full portal "add skill" UI in preview.
- Net: skills are served *through* the platform, but wired up via code. (To re-verify vs latest docs.)
</details>

---

## Step Log

**Step 1 — `azd` is installed (v1.23.8).** ✅
<details><summary>details</summary>

- `azd version` → 1.23.8 (latest is 1.27.0).
- Installed and working; just slightly behind.
</details>

**Step 1b — `azd ai` command group NOT available in 1.23.8.** ⚠️
<details><summary>details</summary>

- `azd ai --help` → `unknown command "ai"`.
- The Foundry agent/skill commands come from a newer `azd` + its extension system.
</details>

**Step 2 — Upgraded `azd` to 1.27.1; already logged into az + azd.** ✅
<details><summary>details</summary>

- `winget upgrade Microsoft.Azd` → now `azd version 1.27.1`.
- Ran the Foundry skill's `verify-environment.ps1`: az + azd installed and logged in
  (subscription `MCAPS-Hybrid-REQ-137983-2025-khushijain`).
- But `azd ai` still missing — it ships as **azd extensions**, flagged 3 to install.
</details>

**Step 3 — Installed the 3 Foundry `azd` extensions.** ✅
<details><summary>details</summary>

- `azd extension install azure.ai.agents azure.ai.projects microsoft.foundry`.
- `microsoft.foundry` pulled in dependencies including **`azure.ai.skills`** and
  **`azure.ai.toolboxes`** — the ones we need for skills.
</details>

**Step 4 — Confirmed `azd ai` works, with a dedicated `skill` command group.** ✅
<details><summary>details</summary>

- `azd ai --help` now lists: `agent`, `connection`, `inspector`, `project`, `routine`,
  **`skill`** (“reusable agent behavioral guidelines”), **`toolbox`**.
- Environment is ready to start building the PPT-from-template skill.
</details>

**Step 5 — Explored `azd ai skill` subcommands.** ✅
<details><summary>details</summary>

- Commands: `create`, `update` (new default version), `show`, `list`, `download`, `delete`.
- A skill carries **inline JSON** (description + Markdown instructions) OR a **packaged ZIP**
  (SKILL.md + sibling assets).
- Skills live **inside a Foundry project** (needs `--project-endpoint`).
- **Implication:** we need a Foundry **project** before we can `skill create`.
</details>

**Step 6 — Located the private target project `YOUR_PROJECT` under `YOUR_FOUNDRY_ACCOUNT`.** ✅
<details><summary>details</summary>

- RG `YOUR_RESOURCE_GROUP` has two AIServices accounts: `YOUR_FOUNDRY_ACCOUNT`, `SECONDARY_ACCOUNT`.
- Target account `YOUR_FOUNDRY_ACCOUNT` is **private/network-isolated**.
- Project: `YOUR_PROJECT`.
- **Project endpoint:** `https://YOUR_FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/YOUR_PROJECT`
- Finding the project = control-plane (no VPN). Talking to the endpoint = **needs VPN**.
</details>

**Step 7 — Connectivity test (`azd ai skill list`): VPN OK, but RBAC 403.** ✅/⚠️
<details><summary>details</summary>

- `azd ai skill list` reached the private endpoint → **VPN works** (403 is app-layer, not network).
- **403:** calling identity (obj `AGENT_MI_OBJECT_ID…`, your microsoft.com id via `azd`) lacks
  `Microsoft.CognitiveServices/accounts/AIServices/agents/read`.
- Note: `az` sees you as a **guest** (`…#EXT#@fdpo.onmicrosoft.com`, obj `GUEST_IDENTITY_ID…`) — different id, hence graph lookup failed.
</details>

**Step 8 — RBAC: your roles are insufficient for skills.** ⚠️ (decision needed)
<details><summary>details</summary>

- On `YOUR_FOUNDRY_ACCOUNT` you have only **`Cognitive Services OpenAI User`**.
- Missing: **`Azure AI User`** (grants `…AIServices/agents/*` data actions) — needed for skills.
- Subscription `YOUR_SUBSCRIPTION_ID`, RG `YOUR_RESOURCE_GROUP`.
- **Decision:** assigning it needs Owner/User Access Administrator + edits customer private-prod
  RBAC → confirm before proceeding, or use a non-prod/personal project.
</details>

**Step 8b — Granted `Foundry User` on `YOUR_PROJECT`.** ✅ (approved)
<details><summary>details</summary>

- This tenant has **no "Azure AI User"** role; the equivalent is **`Foundry User`**
  (dataActions `Microsoft.CognitiveServices/*`, covers agents/skills). Broader alts:
  `Cognitive Services User`, `Foundry Project Manager`/`Owner`.
- Assigned to guest identity **`GUEST_IDENTITY_ID…`** (exists in resource tenant `YOUR_TENANT_ID`), scope `YOUR_PROJECT`.
  `AGENT_MI_OBJECT_ID…` (home microsoft.com id) can't be assigned — not in that directory.
</details>

**Step 9 — Re-login `azd` to the resource tenant so its token = the granted identity.** ⏳ (user runs)
<details><summary>details</summary>

- Root cause of 403: `azd` was authed in your **home** tenant (id `AGENT_MI_OBJECT_ID…`), but the role is
  on the **guest** id `GUEST_IDENTITY_ID…` in tenant `YOUR_TENANT_ID`.
- Fix: `azd auth login --tenant-id YOUR_TENANT_ID`, then retry `azd ai skill list`.
</details>

**Step 9b — `azd` STILL uses home id `AGENT_MI_OBJECT_ID` after re-login + `AZURE_TENANT_ID`.** ⚠️
<details><summary>details</summary>

- `azd ai skill list` still 403 with `AGENT_MI_OBJECT_ID`. Neither `--tenant-id` login nor `AZURE_TENANT_ID`
  moved azd off the home-tenant token → `azd` auth is the blocker, not RBAC.
- Decoded `az` token for `https://ai.azure.com`: **oid `GUEST_IDENTITY_ID`, tid `YOUR_TENANT_ID`** = the granted,
  authorized identity. So `az` works; `azd` doesn't.
</details>

**Step 10 — ✅ WORKING RELIABLE PATH: REST + `az` token (bypass azd).**
<details><summary>details</summary>

- `GET https://YOUR_FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/YOUR_PROJECT/skills?api-version=v1`
- Headers: `Authorization: Bearer <az token for https://ai.azure.com>` **and**
  `Foundry-Features: Skills=V1Preview` (required preview opt-in).
- Result: **HTTP 200**, `{"object":"list","data":[]}` → authorized, 0 skills yet.
- api-version = **`v1`** (dated versions returned UnsupportedApiVersion).
- This is the route we'll use to create the PPT skill. `azd` CLI = revisit later (tenant fix).
</details>

**Step 11 — Author the PPT-from-template `SKILL.md` and create it via REST.** ⏳ (next)
<details><summary>details</summary>

- Reuse the SKILL.md drafted in `skills_experiment/foundry-skill/`; POST to `…/skills?api-version=v1`.
</details>

**Step 11 — Cracked the create contract; write blocked by storage private endpoint.** ✅ contract / ⚠️ blocked
<details><summary>details</summary>

- Correct route: **`POST …/skills/{name}/versions?api-version=v1`** (found via `azd … --debug`).
  `POST /skills` = 405; `POST /skills/{name}` = update-only (404 if not exist).
- Correct body: **`{ "inline_content": { "description": "...", "instructions": "..." } }`** (`instructions` required).
- Auth + RBAC + payload all validated → then **403 "Public access is disabled. Please
  configure private endpoint"** on the write.
- DNS: endpoint resolves to **192.168.1.7** (private) → VPN path fine; block is the **storage
  account backing skill content** (public access disabled, no reachable PE for writes).
- Reads (GET/list) work; **writes need the storage private endpoint** on YOUR_FOUNDRY_ACCOUNT.
</details>

**Step 12 — Decision: fix storage PE, demo on a public project, or use direct injection.** ⏳
<details><summary>details</summary>

- A: configure private endpoint / storage networking on the customer prod Foundry (careful).
- B: create the skill on a non-private Foundry project to demo the write; use YOUR_FOUNDRY_ACCOUNT for read/list.
- C: skip publish — **direct injection** (SKILL.md bundled in agent project), no write needed.
</details>

**Step 13 — Investigated end-to-end PN: blob path is correctly wired; write is a mgmt-plane gap.** ✅ diagnosed
<details><summary>details</summary>

- `YOUR_FOUNDRY_ACCOUNT` = **BYO VNet injection** (scenario `agent`, subnet `agent-vnet-test/agent-subnet`,
  `useMicrosoftManagedNetwork=false`).
- Storage `YOUR_FOUNDRY_STORAGE` (StorageV2, not HNS): blob **PE approved**, `bypass=AzureServices`,
  `privatelink.blob.core.windows.net` **DNS zone linked to `agent-vnet-test`**. Only a **blob** PE exists.
- So agent RUNTIME reaches blob privately → reads/list/attach/download work.
- But skill **create-version WRITE** still 403 "public access disabled" → a **management-plane
  write from the Foundry service side** that doesn't traverse the injected VNet. No missing sub-resource
  PE to add (blob already wired). **Likely a preview gap: authoring skills INTO a network-isolated project.**
- Docs: end-to-end PN needs PEs to connected resources; skills feature-support table doesn't call out
  isolation support → confirm with Foundry PG.
- Real-world: author skills from a less-restricted context, then consume (attach/read) from the isolated
  project (runtime works); or confirm supported authoring pattern with the PG; demo publish on a public project.
</details>

**Step 14 — RBAC ruled out; everything customer-controls is correct → preview gap confirmed.** ✅ conclusion
<details><summary>details</summary>

- `YOUR_PROJECT` MI = **`PROJECT_MI_OBJECT_ID…`**, HAS **Storage Blob Data Contributor** on `YOUR_FOUNDRY_STORAGE` → data-plane RBAC OK.
- (Account MI `ACCOUNT_MI_OBJECT_ID…` has no storage role, but the PROJECT MI is the writer — correct.)
- Verified-correct stack: az token · project `Foundry User` · `inline_content` contract · VNet injection
  `agent-vnet-test` · blob PE + DNS zone link · `bypass=AzureServices` · project MI blob-data role.
- Write STILL 403 "public access disabled" → **skill authoring into a network-isolated project = preview gap**
  (mgmt-plane write doesn't traverse the injected VNet). Runtime consume (attach/list/read/download) works.
- Next: demo publish on a public project; raise the isolation-authoring gap with the Foundry PG.
</details>

## Ways to publish a Foundry skill (for diagram)
- **Tools:** azd CLI (`azd ai skill create`) · REST (`POST /skills/{name}/versions`) · toolbox
  (`azd ai toolbox skill add` → `publish`) · direct injection (bundle SKILL.md, no API).
- **Content source:** inline (`inline_content{description,instructions}`) · SKILL.md file · zip · directory.
- **Preview reqs:** `api-version=v1` + header `Foundry-Features: Skills=V1Preview`.
- **Gotchas:** azd home-tenant auth 403 · private-Foundry write needs storage private endpoint.

**Step 15 — Scaffolded a direct-injection hosted agent (isolation-friendly path).** ✅
<details><summary>details</summary>

- Route: bundle the skill INSIDE the agent container (no skills-API write) → immune to the isolation authoring gap.
- Scaffolded sample "Basic agent (Responses, Agent Framework, Python)" →
  `skills/hosted-agent-pptx/agent-framework-agent-basic-responses/` (deploy-mode=code).
- Bundled `skills/pptx-from-template/SKILL.md`; edited `main.py` `load_skills()` to read it at startup and
  append to the system instructions.
- Pre-flight (all ✅): ACR `acrtranslator64dp` public access ENABLED + registry PE; `gpt-4.1` deployed;
  agent subnet `192.168.0.0/24` delegated `Microsoft.App/environments`.
</details>

**Step 16 — Deploy succeeded — hosted agent live in private `YOUR_PROJECT` (3m12s).** ✅
<details><summary>details</summary>

- `azd deploy --no-prompt` → SUCCESS; the azd home-tenant auth risk did NOT bite (code-push path ≠ skills-API path).
- Agent `agent-framework-agent-basic-responses` deployed to the isolated project.
- Proves the isolation-friendly path: hosted agent + direct injection works where skills-API authoring failed.
</details>

**Step 17 — Verified: agent answered verbatim from the bundled skill.** ✅
<details><summary>details</summary>

- `azd ai agent invoke` asked for the skill's Step 1 + bullet limits → agent replied with content that lives
  ONLY in the bundled `SKILL.md` (≤5 bullets/slide, ~8 words/bullet).
- ⇒ Direct-injected skill loaded + used at runtime inside the network-isolated project. Full path proven.
</details>

**Step 18 — Added Starburst MCP directly in code (v2) → OAuth consent couldn't render.** ⚠️
<details><summary>details</summary>

- Attached the MCP tool directly (`project_connection_id: starburst`); `azd deploy` → v2.
- Empty responses. Logs: agent emits `oauth_consent_request`, but the hosted Responses runtime logs
  **"Content type 'oauth_consent_request' is not supported yet"** → drops consent → tool never authorizes.
- (Red herring: `Agent365.Observability.OtelWrite` 403 = telemetry role, harmless.)
- Lesson: direct in-code MCP attach was the **wrong path** for OAuth passthrough.
</details>

**Step 19 — Correction: the right path is a Foundry Toolbox, not direct attach.** ✅
<details><summary>details</summary>

- MS Learn: consume a **Foundry Toolbox** (managed MCP endpoint) with a client-side Entra bearer token via
  `header_provider`; `CONSENT_REQUIRED` is handled at `agent.run()` runtime.
- ⇒ Hosted agents CAN use OAuth-passthrough MCP — via a **toolbox**, not a direct code attach.
</details>

**Step 20 — Toolbox attempt (v3) → 401.** ⚠️
<details><summary>details</summary>

- Created toolbox `your-toolbox`, rewired `main.py` to consume the toolbox MCP endpoint with a Bearer
  `ai.azure.com/.default` token. Deploy OK, but runtime `POST …/toolboxes/your-toolbox/mcp → 401`.
- First hypothesis (later corrected): MI ≠ user for OAuth passthrough.
</details>

**Step 21 — Correction: v3 diagnosis was unvalidated; real cause was missing RBAC + ping.** ✅
<details><summary>details</summary>

- Decisive test: POST MCP `initialize` to the toolbox endpoint with Khushi's authorized `az` user token → **200**.
  ⇒ the toolbox endpoint WORKS under isolation; the 401 was the **hosted agent's own identity** being rejected.
- Confirmed via `az role assignment list`: the agent's managed identities had **NO** Foundry role → 401.
- My earlier "remove the MI token / MI≠user" idea was WRONG — the MI-token + `MCPStreamableHTTPTool` is the
  documented pattern; the agent MI just needed the **Foundry User** role.
</details>

**Step 22 — 🎉 v5 WORKS: hosted agent + skill + Starburst MCP (OAuth) end-to-end under isolation.** ✅
<details><summary>details</summary>

Three fixes made it work (confirmed in portal playground):
1. **Grant `Foundry User`** to the agent's runtime MIs (project MI `PROJECT_MI_OBJECT_ID` + account MI `ACCOUNT_MI_OBJECT_ID`) on `YOUR_PROJECT` — the missing piece behind the 401.
2. **No-op `send_ping`** on the MCP `ClientSession` (the Foundry toolbox doesn't implement `ping` → 500 "Cancelled via cancel scope"); Microsoft's documented workaround.
3. Env var `FOUNDRY_TOOLBOX_ENDPOINT` → `TOOLBOX_MCP_ENDPOINT` (platform overwrites the `FOUNDRY_` prefix) + `httpx` timeout=120 + bearer auth + `load_prompts=False`.
- ⇒ Deck: hosted agent + per-user OAuth MCP via toolbox IS achievable, even fully private.
</details>

**Step 23 — Added Code Interpreter to the toolbox → 500 for all code.** ❌
<details><summary>details</summary>

- Added `code_interpreter` (container:auto) to `your-toolbox` (toolbox v3) to complete skill + tool + CI.
- Direct MCP `tools/call` with even `print(2**100)` → `ServerError[500]` 3/3 (req IDs `9bb92641…`, `6306c97d…`, `12cf8e4b…`).
- ⇒ NOT python-pptx, NOT transient — the **toolbox** code-interpreter path 500s under isolation.
</details>

**Step 24 — `container_id` workaround (the doc's hack) → still 500.** ❌
<details><summary>details</summary>

- Doc says: file upload/download unsupported under isolation; workaround = SDK-create a container, pass `container_id`.
- Container **creation** works (project-scoped `POST {proj}/openai/v1/containers` → 200).
- But binding CI to an explicit `container_id` (toolbox v4) and running `print(2**100)` → still `500` (req `f474a7da…`).
- ⇒ The hack only addresses **input files**, not the execution 500 on the toolbox path. Reverted toolbox to v1.
</details>

**Step 25 — 🎯 DECISIVE: direct (non-toolbox) Code Interpreter WORKS under isolation — incl. file download.** ✅
<details><summary>details</summary>

- `POST {proj}/openai/v1/responses` (NO api-version — `/openai/v1/*` rejects it) with `code_interpreter` + `container:auto`,
  asking it to write `report.txt` → **200, `status: completed`**, code executed.
- `GET .../containers/{cid}/files` → 200 lists the file; `GET .../files/{fileId}/content` → **200, bytes = `hello from CI under isolation`**.
- ⇒ CI execution **and** file download both work under isolation via the **direct** path. The earlier 500 was the
  **toolbox** wrapper, NOT CI and NOT isolation. Script: `_ci_download_test.ps1`.
- Implications: a **prompt agent** (native CI) will likely generate+download files under isolation; hosted agents should
  use the **direct `HostedCodeInterpreterTool`**, not CI-via-toolbox.
</details>

**Step 26 — Open next tests.** ⏳
<details><summary>details</summary>

- Is `python-pptx` preinstalled in the CI sandbox? (outbound net blocked → can't `pip install`) → generate a real `.pptx` + download.
- Wire the **direct** `HostedCodeInterpreterTool` into the hosted agent (skill + Starburst MCP + CI in ONE agent) and redeploy.
- Optional control: run CI in the **public** `sample_project` as the isolation baseline.
</details>

---

## Bottom line for the deck (current)
- **Skill (direct injection) + Starburst MCP (OAuth via toolbox) = work fully private, end-to-end** (hosted agent v5).
- **Authoring a skill via the skills API INTO an isolated project = blocked** (preview gap) → bundle the skill instead.
- **Code Interpreter works under isolation via the DIRECT path** (exec + file download); the **toolbox** CI path 500s.
- ⇒ The blocker was never "isolation kills CI" — it was the **toolbox wrapper**. Native/direct CI is fine.

---

## Published hosted-agent versions (`agent-framework-agent-basic-responses`)

> Each `azd deploy` creates a new agent version, so the version counter includes
> incremental redeploys (v4, v6, v8 were minor fix redeploys between the notable
> versions below). Table first, then one-liner + expander per notable version.

| Ver | What it added | Result | Why we moved on |
|---|---|---|---|
| v1 | Direct-injection skill only | ✅ works | Needed Starburst data too |
| v2 | + Starburst MCP direct in-code attach | ❌ consent dropped | Hosted runtime can't surface `oauth_consent_request` |
| v3 | + Starburst via Foundry **toolbox** | ❌ 401 | Agent MI had no Foundry role |
| v5 | Skill + Starburst toolbox (OAuth) | ✅ works | Wanted Code Interpreter (file gen) too |
| v7 | + Code Interpreter (dict tool) | ⚠️ false positive | CI never actually executed |
| v9 | `ci_container_toolbox` (startup container-create) | ❌ 424 | Sync container-create blocked readiness |
| v10 | Lazy container-create | ❌ 403 | Agent MI can't create containers |
| v11 | `ci_client_container` (client creates container) | ✅ works | Wanted toolbox + consent in same agent |
| v12 | `ci_client_container` + toolbox + custom UI | ✅ current | — |

**v1 — Direct-injection skill only (first hosted deploy).** ✅
<details><summary>details</summary>

- Bundled `pptx-from-template/SKILL.md` inside the agent container; `load_skills()` appends it to system instructions at startup (no skills-API write → immune to the isolation authoring gap).
- `azd deploy --no-prompt` → live in private `YOUR_PROJECT` (~3m12s).
- Verified via `azd ai agent invoke`: agent answered verbatim from the bundled skill (≤5 bullets/slide, ~8 words/bullet — content that lives ONLY in the SKILL.md).
- **Moved on:** a skill alone can't fetch the client data — needed Starburst.
</details>

**v2 — + Starburst MCP attached directly in code.** ❌
<details><summary>details</summary>

- Attached the MCP tool directly (`project_connection_id: starburst`).
- Empty responses. Logs: agent emits `oauth_consent_request`, but the hosted Responses runtime logs **"Content type 'oauth_consent_request' is not supported yet"** → drops consent → tool never authorizes.
- **Root cause / why we moved on:** direct in-code MCP attach on a HOSTED agent can't surface OAuth consent (preview gap). The right path is a Foundry **toolbox**, which brokers consent server-side.
</details>

**v3 — + Starburst via a Foundry toolbox (`your-toolbox`).** ❌
<details><summary>details</summary>

- Rewired `main.py` to consume the toolbox MCP endpoint with a Bearer `ai.azure.com/.default` token. Deploy OK, but runtime `POST …/toolboxes/your-toolbox/mcp → 401`.
- Decisive test: the SAME endpoint with Khushi's authorized `az` user token → 200. So the endpoint works; the 401 was the **agent's own managed identity** being rejected.
- **Why we moved on:** the agent's runtime MIs had **no Foundry role**. (Intermediate v4 = toolbox fix redeploys.)
</details>

**v5 — 🎉 Skill + Starburst toolbox (OAuth) end-to-end under isolation.** ✅
<details><summary>details</summary>

Three fixes made it work (confirmed in portal playground):
1. **Granted `Foundry User`** to the agent's runtime MIs (project MI `PROJECT_MI_OBJECT_ID` + account MI `ACCOUNT_MI_OBJECT_ID`) on `YOUR_PROJECT` — the missing piece behind the v3 401.
2. **No-op `send_ping`** on the MCP `ClientSession` (the toolbox doesn't implement `ping` → 500 "Cancelled via cancel scope") — Microsoft's documented workaround.
3. Env var `FOUNDRY_TOOLBOX_ENDPOINT` → `TOOLBOX_MCP_ENDPOINT` (platform overwrites the `FOUNDRY_` prefix) + `httpx` timeout=120 + bearer auth + `load_prompts=False`.
- **Moved on:** wanted Code Interpreter (real file generation, e.g. `.pptx`) in the same agent.
</details>

**v7 — + Code Interpreter (dict tool), deployed via code.** ⚠️ FALSE POSITIVE
<details><summary>details</summary>

- Added `tools = [{"type":"code_interpreter","container":{"type":"auto"}}]`. `2**100` "passed" remotely (~39s cold start), so it looked like CI worked.
- **Later disproven (2026-07-20):** asked it to run `hashlib.sha256('client_ci_probe_20260720')`. Expected `9eb0e06d…079db5`; agent returned a **fabricated** digest → CI never executed. `2**100` only "worked" because it's derivable. A `.pptx` request returned a FAKE `sandbox:/mnt/data/report.pptx` link, empty annotations, no `container_id`.
- **Root cause:** the REAL `client.get_code_interpreter_tool()` crashes the observability layer (`AutoCodeInterpreterToolParam` not JSON serializable); the dict "fix" serializes but agent_framework doesn't register a raw dict as a tool → silent no-op → model hallucinates.
- **Fix (adopted going forward):** use the REAL SDK tool **+** `disable_instrumentation()` (execution and tracing are separate paths). Verified with sha256 → EXACT match.
- **Why we moved on:** false positive; also `container:auto` doesn't expose downloadable file citations.
</details>

**v9 — `ci_container_toolbox`: real CI bound to a pre-created container + toolbox.** ❌ 424
<details><summary>details</summary>

- Real CI tool bound to an explicit project-scoped `container_id` (so files are downloadable) + Starburst toolbox.
- Deployed → invoke → **HTTP 424 `session_not_ready`**.
- **Root cause:** container is created SYNCHRONOUSLY in `main()` BEFORE `server.run()`; the blocking network call delays `/readiness`. Local was instant (user identity/VPN); hosted (managed identity + private network) hangs → readiness times out.
- **Why we moved on:** need lazy container-create so readiness passes.
</details>

**v10 — Lazy container-create (`_LazyAgent`).** ❌ 403
<details><summary>details</summary>

- `_LazyAgent` defers agent build + container-create to the FIRST request (inside async `__aenter__`), so `/readiness` passes immediately. 424 fixed.
- New blocker: **HTTP 403** — `Identity(object id AGENT_MI_OBJECT_ID-…-21337c6467cb) does not have permissions for …/agents/write`. That object id is the deployed agent's **managed identity**; local worked only because it ran as MY user identity.
- Granted `Foundry Project Manager` to the MI at account + project scope → response-level check passed, **but inner `POST …/openai/v1/containers` stayed 403** even after >30 min propagation + a cold redeploy.
- **Why we moved on:** MI container-create RBAC never resolved → sidestep it entirely.
</details>

**v11 — `ci_client_container`: the CLIENT creates the container.** ✅
<details><summary>details</summary>

- The client (user identity, which CAN create containers) creates the container and passes `USE_CONTAINER_ID=cntr_…` in the prompt. `_ClientContainerAgent` reads it per request and binds `CodeInterpreterTool(container=<id>)` → the deployed MI only **uses** the container, never creates one. No container-create permission needed.
- **VERIFIED deployed** in the private project: create container HTTP 200, agent HTTP 200 `status=completed`, CI wrote `report.pptx`, downloaded **28,251 bytes**, `PK` zip magic (real Office file).
- Key insight: the MI can use a container created by a different (user) identity.
- **Moved on:** wanted Starburst toolbox + Code Interpreter + consent in ONE agent.
</details>

**v12 — `ci_client_container` + toolbox + custom UI (current).** ✅
<details><summary>details</summary>

- `main.py`: `ci_client_container` with `CI_INCLUDE_TOOLBOX=1` → `_ClientContainerToolboxAgent`. Toolbox MCP connects ONCE in async `__aenter__` (so consent surfaces via the host as `oauth_consent_request`); the CI tool is injected PER REQUEST via `Agent.run(tools=[toolbox, CI])` (keyword-only `tools`, verified).
- `ui/app.py`: Flask UI (port 5005) in front of the DEPLOYED endpoint — creates the container (caller identity), passes `USE_CONTAINER_ID`, renders `oauth_consent_request` as a clickable Sign-in link, lists CI files + serves downloads, keeps conversation memory + New chat, and shows an **Observed response activity** panel (raw output-item types).
- Raw deployed probe returned a real `oauth_consent_request` with a Logic Apps/API Hub consent link; user completed consent.
- **Observed (2026-07-22):** a multi-turn Starburst → PPT run surfaced **50 `function_call`/`function_call_output`** items (`starburst___executeQuery`) but **no `code_interpreter_call`** item, even though a `conversation_summary.pptx` appeared. ⇒ next step is to surface CI evidence from the **container file delta** (new assistant file after the turn) + `.pptx` `PK` validation, not the assistant's narration.
- **Open risk:** the deployed toolbox is called with the MANAGED IDENTITY token, not a per-user OBO token — so even after consent the toolbox call may not authorize as the user. If so, forward a per-user token (separate wiring).
</details>

**v13 — Custom-UI observability + formatting hardening.** ✅
<details><summary>details</summary>

- Fixed a UI submit-handler regression that dropped the user's own message bubble (`add('user', esc(text))` restored) — sent text renders immediately again.
- Restored **top-level error surfacing** in `_parse_response` (the zip build had it; the current one silently showed `(no content)` on service errors). The UI now prints the real error text.
- **Response activity** panel now renders each output item (`type · name/server_label · status`) instead of only a count — MCP `function_call`s, consent requests, etc. are visible.
- Added lightweight, XSS-safe **Markdown formatting** for the bot text (`**bold**`, `` `code` ``) and a **"Skill used"** badge parsed from the `SKILL_USED:` marker.
- **Toolbox guardrails** baked into instructions: pass ONLY the SQL query — never an `authorization` arg, token, or container id — and always `SHOW SCHEMAS FROM sample` (fully qualified). This stopped the model stuffing `USE_CONTAINER_ID=cntr_…` into a fabricated `authorization` field (which had returned `Error: Function failed`).
- Architecture captured in `v13-architecture-diagram.html` / `v13-simple-infographic.html`.
</details>

**v14 — Dependency drift breaks every tool call: "Encrypted content is not supported".** ❌
<details><summary>details</summary>

- After a routine redeploy, every tool-using turn began failing; the UI showed `(no content)`. With the v13 error fix, the real error surfaced: `HTTP 400 — "Encrypted content is not supported with this model." (param: include)`.
- **Root cause = unpinned dependency.** `requirements.txt` pinned nothing for `agent-framework-foundry`, so the redeploy pulled the newest prerelease (**1.10.3**, published the same day). In `RawOpenAIChatClient._prepare_options`, a stateless request (`store=false`, no `previous_response_id`/`conversation`) now **unconditionally appends** `include=["reasoning.encrypted_content"]`. `gpt-4.1` (non-reasoning) rejects it → 400 → the tool loop dies before returning data.
- Confirmed via the per-turn debug log (`error.code=server_error`, wrapped `BadRequestError`) and PyPI release dates (1.10.1 07-10, 1.10.2 07-21, **1.10.3 07-23** = the day it broke).
- **Stopgap:** pin `agent-framework-foundry==1.10.2` and redeploy → works. But pinning ages out, so we kept digging for a forward fix.
</details>

**v15 — Forward fix: `_EncryptedReasoningSafeFoundryChatClient` (stays on latest).** ✅
<details><summary>details</summary>

- Microsoft already solved this on the **FoundryAgent** path (`RawFoundryAgentChatClient._prepare_options` strips `reasoning.encrypted_content` unless the caller explicitly requested it), but the **FoundryChatClient** path we use does not. We mirrored the fix: a `FoundryChatClient` subclass overrides `_prepare_options`, calls `super()`, then removes `reasoning.encrypted_content` from `include` unless the caller opted in.
- Reverted the pin → `requirements.txt` tracks the latest `agent-framework-foundry` again, now protected by the override. Redeployed (**azd build version 15**).
- **Verified:** schemas/tables/columns return again and a real `.pptx` is generated by Code Interpreter. For this hosted config the Responses output often contains only a `message` item — **no `code_interpreter_call`** — so the trustworthy CI signal is the **container file delta** (a new `source=assistant` file) + `PK` zip validation (per v12). Uploaded templates land as `source=user` files in the same container.
- Note: `store=True` alone would NOT fix it (the include is gated on `previous_response_id`/`conversation`, not `store`); a reasoning model (gpt-5/o-series) would accept the include instead. The override keeps `gpt-4.1` + `store=false` working and lets callers opt back in on capable models.
</details>

## Version takeaways for the deck
- The hard blockers were **never** "isolation" — they were, in order: (1) hosted runtime can't surface OAuth consent → use a **toolbox**; (2) agent MI missing **Foundry role** → 401; (3) dict CI tool = **silent no-op** → use real tool + `disable_instrumentation()`; (4) sync container-create → **424 readiness** → lazy build; (5) MI can't **create** containers → **client** creates it and passes `container_id`; (6) an **unpinned** `agent-framework-foundry` upgrade auto-added `include=["reasoning.encrypted_content"]` on stateless requests → **400** on non-reasoning `gpt-4.1` → fixed with a `FoundryChatClient` subclass that strips it.
- Observability: skills and Code Interpreter runs are otherwise invisible — surface skills via a `SKILL_USED:` marker and CI via the **container file delta** (new `source=assistant` file) + `PK` validation, not the model's narration or a `code_interpreter_call` item (often absent).
- Current shape that works fully private: **hosted agent + bundled skill + Starburst toolbox (OAuth) + client-created-container Code Interpreter + custom UI for consent/downloads.**
