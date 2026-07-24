# Provision a Foundry project with Bicep

Adds a **governed, agent-ready project** to an **existing** Foundry (AIServices) account:

- The project (child of the account, System-Assigned identity)
- An optional **model deployment** (default `gpt-4.1`) so agents can be created
- Optional **Application Insights** (+ Log Analytics) wired to the project for tracing / token usage
- Optional **RBAC** role assignments at account scope

> This mirrors the `terraform` branch's `infra/terraform`. It does **not** create the Foundry account itself — bring an existing account (or create one first).

## Prerequisites

- Azure CLI with Bicep (`az bicep install`)
- An existing Foundry account and its resource group
- Permission to create child resources + role assignments on that account

## Deploy

1. Copy the example params and fill in your values:
   ```powershell
   Copy-Item example.bicepparam my.bicepparam
   ```
   Set at least `existingAccountName`, `location`, and `projectName`.

2. Deploy at the resource group that holds the account:
   ```powershell
   az deployment group create `
     --resource-group <your-resource-group> `
     --template-file main.bicep `
     --parameters my.bicepparam
   ```

3. Read the outputs and wire them into the agent:
   ```powershell
   az deployment group show -g <your-resource-group> -n main --query properties.outputs.projectEndpoint.value -o tsv
   ```
   Put that value in `FOUNDRY_PROJECT_ENDPOINT` and the model name in `AZURE_AI_MODEL_DEPLOYMENT_NAME`.

## Notes

- **Model deployments are account-scoped** and shared by every project on the account. Re-deploying the same deployment name with the same properties is idempotent; if a different deployment already exists you can reuse it by setting `deployModel = false`.
- If your account lives in a **different resource group** than where you deploy, wrap `main.bicep` in a module targeting that RG, or run the deployment against the account's RG.
- Role definition IDs: `Cognitive Services User` = `a97b65f3-24c7-4388-baec-2e87135dc908`. Look up others with `az role definition list --name "<role>" --query "[].name" -o tsv`.
