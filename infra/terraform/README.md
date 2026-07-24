# new-tf-setup — a governed, agent-ready Foundry project (Terraform / AzAPI)

Adds a **Foundry project** to an **existing Foundry account** and, in the same
apply, wires up a governed, agent-ready project:

- **Application Insights** connected to the project → agent **tracing + token
  usage** (prompt / completion / cached tokens per request) flows automatically.
- An optional **model deployment** (`gpt-4.1` by default) on the account, so a
  fresh project can **create agents immediately** — the prerequisite Sai hit.
- **RBAC role assignments** at **account** and **project** scope, **Entra-group
  friendly**, so a whole team gets access on deploy instead of per-email adds.

It builds on the proven `../project-on-existing-foundry` example (same AzAPI v2
pattern, same provider pins) and never creates a new account or resource group.

> Why a project is a child of an account, and why AzAPI (not
> `azurerm_ai_foundry_project`): see
> [`../foundry-resource-vs-project-and-terraform.md`](../foundry-resource-vs-project-and-terraform.md).

---

## What it creates

| Resource | Type | When |
|---|---|---|
| `azapi_resource.project` | `Microsoft.CognitiveServices/accounts/projects@2025-06-01` | always |
| `azapi_update_resource.enable_projects` | account PATCH `allowProjectManagement=true` | `ensure_project_management = true` |
| `azurerm_log_analytics_workspace.this` | `Microsoft.OperationalInsights/workspaces` | `enable_app_insights && create_log_analytics` |
| `azurerm_application_insights.this` | `Microsoft.Insights/components` (workspace-based) | `enable_app_insights` |
| `azapi_resource.appinsights_connection` | `…/accounts/projects/connections@2025-06-01` (category `AppInsights`) | `enable_app_insights` |
| `azapi_resource.model_deployment` | `…/accounts/deployments@2025-06-01` | `deploy_model` **and** not already present (see adoption below) |
| `azurerm_role_assignment.account[*]` | account-scoped role assignments | per `account_role_assignments` |
| `azurerm_role_assignment.project[*]` | project-scoped role assignments | per `project_role_assignments` |

---

## Files

```
new-tf-setup/
├── main.tf                     # project + App Insights + model + RBAC
├── variables.tf                # all inputs (commented by section)
├── outputs.tf                  # ids, endpoint, App Insights conn string, etc.
├── providers.tf / versions.tf  # azurerm ~> 4.37, azapi ~> 2.5
├── terraform.tfvars.example    # copy -> terraform.tfvars
├── environments/
│   ├── dev.tfvars.example      # broad dev access + model
│   └── prod.tfvars.example     # least standing access, pinned model
├── MODEL-CHANGE.md             # how to switch gpt-4.1 -> another model
└── README.md
```

---

## Quickstart — from scratch to finish (Windows / PowerShell)

End-to-end steps to go from an empty machine to a deployed, verified project.

### 0. Prerequisites (one-time per machine)

```powershell
# Terraform CLI
winget install --id Hashicorp.Terraform -e --accept-source-agreements --accept-package-agreements
# (open a NEW PowerShell window afterwards so PATH picks up terraform)

# Azure CLI (if not already installed)
winget install --id Microsoft.AzureCLI -e

# Confirm both resolve
terraform version
az version
```

### 1. Sign in and select the subscription

```powershell
az login
az account set --subscription "<your-subscription-id>"

# REQUIRED: the azurerm v4 provider needs the subscription id explicitly.
# Without this, terraform fails with "could not acquire access token ... Status_NoNetwork".
$env:ARM_SUBSCRIPTION_ID = "<your-subscription-id>"
```

> Tip: to make it permanent for your user, run once:
> `setx ARM_SUBSCRIPTION_ID "<your-subscription-id>"` (takes effect in new shells).
> Alternatively set `subscription_id` directly in `providers.tf`.

### 2. Find your existing Foundry account

The module adds a project to an **existing** Foundry account (kind `AIServices`).
List what you have and pick one:

```powershell
az cognitiveservices account list --query "[?kind=='AIServices'].{name:name, rg:resourceGroup, location:location}" -o table
```

Note the **name** and **resource group** — you'll put them in `terraform.tfvars`.

### 3. Configure your inputs

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set at minimum:

```hcl
existing_account_name   = "<your Foundry account name>"
existing_resource_group = "<its resource group>"
project_name            = "<new project name>"

# model (defaults to gpt-4.1; see MODEL-CHANGE.md to switch)
deploy_model  = true
model_name    = "gpt-4.1"
model_version = "2025-04-14"

# RBAC (optional but recommended) — use Entra GROUP object IDs
# account_role_assignments = { dev_cogsvc = { principal_id = "<group id>", role_definition_name = "Cognitive Services User", principal_type = "Group" } }
# project_role_assignments = { dev_aiuser = { principal_id = "<group id>", role_definition_name = "Azure AI User",        principal_type = "Group" } }
```

### 4. Initialize, review, apply

```powershell
terraform init
terraform plan      # review what will be created
terraform apply     # type 'yes' to confirm
```

Per environment (CI/CD): swap step 3/4 for a committed example file:

```powershell
terraform apply -var-file="environments\dev.tfvars"
terraform apply -var-file="environments\prod.tfvars"
```

### 5. Verify

```powershell
# the project exists under the account
az cognitiveservices account project show `
  --name <existing_account_name> -g <existing_resource_group> `
  --project-name <project_name>

# the model deployment is present on the account
az cognitiveservices account deployment list `
  --name <existing_account_name> -g <existing_resource_group> -o table

# handy outputs (endpoint, ids, whether the model was reused)
terraform output
```

### 6. (Optional) Tear down

Only run this if you want to remove what the module created. It deletes the
project, its App Insights/Log Analytics, the model deployment **created by this
module**, and the role assignments — the **account itself is untouched**.

```powershell
terraform destroy
```

> If the model deployment already existed and was **adopted** (reused), destroy
> will **not** delete it — it was never managed by this state.

---

## Usage (short form)

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars   # then edit it
$env:ARM_SUBSCRIPTION_ID = "<subscription-id>"
az login
terraform init
terraform plan
terraform apply
```

---

## RBAC — who needs what (role matrix)

Foundry RBAC separates **control-plane** (create deployments/projects) from
**data-plane** (build agents, run evals, upload files), and you can assign at the
**account** and the **project** scope. The cadence surfaced a specific gotcha:
a Foundry/Azure AI role on the project alone was **not enough** — a **Cognitive
Services** role on the account was also required before an agent could be created
(and a model had to be deployed).

| Persona | Scope | Role(s) | Why |
|---|---|---|---|
| **CI/CD deploy principal** | Account / RG | **Cognitive Services Contributor** (control-plane). Add **User Access Administrator** *only if* this config creates the role assignments below. | Create the project, deploy models, flip `allowProjectManagement`. |
| **Agent developer** (team Entra group) | **Project** + **Account** | **Azure AI User** on the project **and** **Cognitive Services User** on the account | The combo needed to actually **create agents** (the project role alone was insufficient). |
| **Project manager / lead** | Project | **Azure AI Project Manager** | Manage project members, connections, agents. |
| **Account owner / admin** | Account | **Azure AI Account Owner** | Governs every project under the account. |
| **Read-only / ops** | Project | **Reader** (+ data-plane read as needed) | View without modifying. |

Notes:
- Pass an **Entra group object ID** as `principal_id` (`principal_type = "Group"`)
  to grant the whole team in one assignment.
- The Foundry roles were **renamed** (Azure AI User/Owner/Account Owner/Project
  Manager ↔ Foundry …); **role IDs are unchanged**. If a name lookup is
  ambiguous after a portal rename, set **`role_definition_id`** (the GUID)
  instead of `role_definition_name`.
- Creating role assignments requires the Terraform principal to be **Owner** or
  **User Access Administrator** at the target scope. If your pipeline identity
  lacks that, leave `*_role_assignments = {}` and have an admin grant access out
  of band.

Example (in `.tfvars`):

```hcl
account_role_assignments = {
  dev_team_cogsvc = {
    principal_id         = "<dev Entra group objectId>"
    role_definition_name = "Cognitive Services User"
    principal_type       = "Group"
  }
}
project_role_assignments = {
  dev_team_ai_user = {
    principal_id         = "<dev Entra group objectId>"
    role_definition_name = "Azure AI User"
    principal_type       = "Group"
  }
}
```

---

## Observability — what App Insights captures

With `enable_app_insights = true`, the module creates (or reuses) a
workspace-based App Insights resource and attaches it to the project as an
`AppInsights` connection. Once **tracing is enabled** in the agent / SDK, App
Insights receives spans and **token-usage** telemetry — input (prompt), output
(completion), and cached tokens per request, plus latency and call metadata —
queryable in Log Analytics / the App Insights blade.

- To reuse an existing workspace: `create_log_analytics = false` +
  `existing_log_analytics_workspace_id = "<workspace ARM id>"`.
- The connection string is exposed as the (sensitive) `app_insights_connection_string`
  output for SDK-side tracing if you wire it manually.

---

## Model deployment

`deploy_model = true` deploys a model on the **account** so projects are
agent-ready. Default is `gpt-4.1`. **To change the model, see
[`MODEL-CHANGE.md`](MODEL-CHANGE.md)** — it's a three-variable edit
(`model_name` / `model_version` / `model_sku_name`) with quota/region checks.

**Already-deployed models are handled automatically.** Model deployments are
account-scoped and shared by every project on the account, so a second project
doesn't need its own copy. Before creating, the module lists the account's
deployments: if one with the same name already exists it is **reused** (the
outputs point at it and `model_deployment_adopted = true`) instead of failing
with "Resource already exists". Set `adopt_existing_model_deployment = false` to
force creation and get a clear error if it's already there.

---

## CI/CD notes

- Use a **remote backend** (e.g. azurerm state in a storage account) instead of
  local state for shared/pipeline runs.
- Drive environments with `-var-file=environments/<env>.tfvars`; keep secrets and
  principal IDs in the pipeline's variable store, not in committed `.tfvars`
  (only `*.tfvars.example` is committed; real `*.tfvars` are git-ignored).
- Give the pipeline identity **least privilege**: Cognitive Services Contributor
  to deploy, and User Access Administrator only if it must manage role
  assignments. In prod, prefer **no standing human data-plane access** — changes
  flow through the pipeline (`environments/prod.tfvars.example`).

---

## Inputs (key)

| Variable | Default | Notes |
|---|---|---|
| `existing_account_name` / `existing_resource_group` | `null` | Path A (recommended). |
| `existing_account_id` / `location` | `null` | Path B (raw ARM ID; `location` required). |
| `project_name` / `display_name` / `description` | — / `project_name` / `null` | The project. |
| `identity_type` | `SystemAssigned` | Agents/connections need an identity. |
| `enable_app_insights` | `true` | App Insights + project connection. |
| `create_log_analytics` / `existing_log_analytics_workspace_id` | `true` / `null` | Create vs. reuse the workspace. |
| `deploy_model` / `model_name` / `model_version` | `true` / `gpt-4.1` / `null` | See MODEL-CHANGE.md. |
| `adopt_existing_model_deployment` | `true` | Reuse an existing same-named account deployment instead of failing. |
| `model_sku_name` / `model_capacity` | `GlobalStandard` / `50` | Capacity = thousands of TPM. |
| `account_role_assignments` / `project_role_assignments` | `{}` / `{}` | Entra-group friendly RBAC. |
| `ensure_project_management` | `false` | PATCH `allowProjectManagement=true` first. |
| `tags` | `{}` | Applied to project + observability resources. |

## Outputs

`project_id`, `project_name`, `project_principal_id`, `project_internal_id`,
`project_endpoint`, `log_analytics_workspace_id`, `app_insights_id`,
`app_insights_connection_string` (sensitive), `app_insights_connection_id`,
`model_deployment_name`, `model_deployment_id`, `model_deployment_adopted`,
`account_role_assignment_ids`, `project_role_assignment_ids`.

---

## Gotchas

- The **azurerm v4 provider requires a subscription id**. Set
  `$env:ARM_SUBSCRIPTION_ID` (or `subscription_id` in `providers.tf`) before
  `plan`/`apply`, otherwise you get `could not acquire access token ...
  Status_NoNetwork`.
- `parent_id` is the **account** resource ID (model deployments are account-level
  and shared by all projects; the App Insights connection is **project**-level).
- AzAPI v2 object-`body` syntax (no `jsonencode`); `sku`/`identity` live inside
  `body`.
- App Insights is **workspace-based** (classic is retired) — a Log Analytics
  workspace is required (created here by default).
- Model deployments consume **quota** (subscription × region × model TPM). A new
  deployment does not grant new quota.
- `terraform destroy` removes the project, its App Insights/workspace, the model
  deployment **created by this module**, and the role assignments created here —
  the **account is untouched**. A model deployment that was **adopted** (already
  existed and was reused) is **not** deleted, since this state never managed it.
