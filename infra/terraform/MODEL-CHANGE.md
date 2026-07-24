# Changing the model (gpt-4.1 → something else)

This template deploys a model on the **account** so a fresh project is
**agent-ready** (in the 6/26 cadence an agent could only be created *after* a
model was deployed). The default is **`gpt-4.1`**. Swapping models is a
three-variable change — no edits to `main.tf` are required.

> Model deployments live on the **account** (`Microsoft.CognitiveServices/accounts/deployments`),
> shared by every project under it. Capacity draws from the
> **subscription × region × model** token-per-minute (TPM) quota pool — a new
> deployment does not grant new quota.

---

## TL;DR — edit these in your `.tfvars`

```hcl
model_name     = "gpt-4o"          # the model to deploy
model_version  = "2024-11-20"      # or null to use the service default
model_sku_name = "GlobalStandard"  # GlobalStandard | DataZoneStandard | Standard | ProvisionedManaged
model_capacity = 50                # thousands of TPM (subject to quota)
```

Then:

```bash
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

The deployment **name** that your agents/SDK reference defaults to `model_name`.
To keep the reference name stable while changing the underlying model, set
`model_deployment_name` explicitly:

```hcl
model_deployment_name = "chat"      # agents always call "chat"
model_name            = "gpt-4o"    # swap the model behind it later without breaking callers
```

---

## All model knobs

| Variable | Purpose | Example values |
|---|---|---|
| `deploy_model` | Turn the deployment on/off | `true` / `false` |
| `model_name` | Model to deploy | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| `model_version` | Pin a version, or `null` for the service default | `"2025-04-14"`, `null` |
| `model_format` | Provider/format | `OpenAI` (Azure OpenAI models) |
| `model_sku_name` | Deployment SKU / tier | `GlobalStandard`, `DataZoneStandard`, `Standard`, `ProvisionedManaged` |
| `model_capacity` | Capacity in **thousands of TPM** | `50` |
| `model_rai_policy_name` | Content-filter policy | `null` (account default) or a policy name |
| `model_version_upgrade_option` | Auto-upgrade behavior | `OnceNewDefaultVersionAvailable`, `OnceCurrentVersionExpired`, `NoAutoUpgrade` |
| `model_deployment_name` | Deployment name agents reference | `null` (= `model_name`) or e.g. `"chat"` |

---

## Before you switch — quick checks

1. **Is the model available in your account's region?** A model deployment
   inherits the account's region (one region per account). Confirm availability:

   ```bash
   az cognitiveservices account list-models \
     --name <account_name> -g <resource_group> \
     --query "[].{name:name, version:version, format:format}" -o table
   ```

   Or `az cognitiveservices model list --location <region> -o table` for the
   region-wide catalog.

2. **Do you have quota?** Check / request capacity for the target model:

   ```bash
   az cognitiveservices usage list --location <region> -o table
   ```

   If `model_capacity` exceeds your remaining TPM, the apply fails with a quota
   error — lower the capacity or request more quota (per subscription × region ×
   model).

3. **Does the SKU support the model?** Not every model offers every SKU.
   `GlobalStandard` is the broadest for chat models; some models are
   `Standard`/`DataZoneStandard`-only. The `list-models` output above shows the
   supported deployment SKUs per model.

---

## Pinning vs. floating versions

- **Dev:** `model_version = null` + `OnceNewDefaultVersionAvailable` keeps you on
  the latest default — convenient for experimentation.
- **Prod:** pin `model_version` to a known-good value and set
  `model_version_upgrade_option = "NoAutoUpgrade"` so a model refresh never
  changes behavior under you. (See `environments/prod.tfvars.example`.)

---

## Deploying more than one model

This template deploys a single model for simplicity. To run several (e.g. a
chat model **and** an embeddings model), either:

- run the module twice with different `model_deployment_name` / `model_name`, or
- ask and we can convert `model_deployment` into a `for_each` over a
  `map(object({...}))` so one apply deploys the whole set.

---

## What changes on apply

Switching `model_name` or `model_version` **replaces** the deployment (Azure
keeps the deployment name; the model behind it changes). Agents that reference
the deployment **by name** keep working as long as the deployment name is
unchanged — which is exactly why `model_deployment_name` lets you decouple the
caller-facing name from the underlying model.
