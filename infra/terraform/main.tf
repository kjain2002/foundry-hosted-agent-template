###############################################################################
# Add a GOVERNED, AGENT-READY project to an EXISTING Foundry account.
#
# Builds on the proven `project-on-existing-foundry` example and adds the items
# a governed, agent-ready project typically needs:
#   - Application Insights wired to the project (token usage / tracing)
#   - An optional model deployment (gpt-4.1 by default) so agents can be created
#   - RBAC role assignments at account + project scope (Entra-group friendly)
#
# A Foundry project is a CHILD of a Foundry account
# (Microsoft.CognitiveServices/accounts, kind=AIServices). This config creates
# the project + its supporting resources; it does NOT create a new account.
#
# azapi v2 object-body syntax (no jsonencode). sku + identity live INSIDE body.
###############################################################################

# ---------------------------------------------------------------------------
# (A) Default path: resolve the existing account by name + resource group.
#     Skipped when existing_account_id is provided (path B).
# ---------------------------------------------------------------------------
data "azurerm_cognitive_account" "foundry" {
  count               = var.existing_account_id == null ? 1 : 0
  name                = var.existing_account_name
  resource_group_name = var.existing_resource_group
}

locals {
  # Account ARM ID + region, from either the data source or the raw-ID input.
  account_id = coalesce(var.existing_account_id, try(data.azurerm_cognitive_account.foundry[0].id, null))
  location   = coalesce(var.location, try(data.azurerm_cognitive_account.foundry[0].location, null))

  # Account name, used to build the project endpoint. Parsed from the raw ID
  # (last path segment) when path B is used.
  account_name = var.existing_account_id == null ? var.existing_account_name : element(split("/", var.existing_account_id), length(split("/", var.existing_account_id)) - 1)

  # RG to host App Insights / Log Analytics. Defaults to the account RG (path A).
  observability_rg = coalesce(var.observability_resource_group, var.existing_resource_group)

  # Identity object (azapi v2 keeps identity INSIDE body). Omitted when None.
  identity = (
    var.identity_type == "None" ? null :
    merge(
      { type = var.identity_type },
      strcontains(var.identity_type, "UserAssigned")
      ? { userAssignedIdentities = { for id in var.user_assigned_identity_ids : id => {} } }
      : {},
    )
  )

  # Project request body. Keys present only when set (merge drops empty maps).
  body = merge(
    {
      properties = merge(
        { displayName = coalesce(var.display_name, var.project_name) },
        var.description == null ? {} : { description = var.description },
      )
    },
    var.project_sku_name == null ? {} : { sku = { name = var.project_sku_name } },
    local.identity == null ? {} : { identity = local.identity },
  )

  # Resolved names for the observability resources.
  log_analytics_name = coalesce(var.log_analytics_name, "${var.project_name}-law")
  app_insights_name  = coalesce(var.app_insights_name, "${var.project_name}-appi")

  # Workspace ID backing App Insights (created vs. reused).
  log_analytics_workspace_id = var.create_log_analytics ? try(azurerm_log_analytics_workspace.this[0].id, null) : var.existing_log_analytics_workspace_id
}

# ---------------------------------------------------------------------------
# (Optional) Make the account a Foundry account if it isn't already. Idempotent.
# Most existing Foundry accounts already have allowProjectManagement=true.
# ---------------------------------------------------------------------------
resource "azapi_update_resource" "enable_projects" {
  count       = var.ensure_project_management ? 1 : 0
  type        = "Microsoft.CognitiveServices/accounts@2025-06-01"
  resource_id = local.account_id
  body = {
    properties = {
      allowProjectManagement = true
    }
  }
}

# ---------------------------------------------------------------------------
# The new project — a child of the existing account via parent_id (key line).
# ---------------------------------------------------------------------------
resource "azapi_resource" "project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = var.project_name
  parent_id                 = local.account_id
  location                  = local.location
  schema_validation_enabled = false

  body = local.body
  tags = var.tags

  response_export_values = [
    "identity.principalId",
    "properties.internalId",
  ]

  depends_on = [azapi_update_resource.enable_projects]

  lifecycle {
    precondition {
      condition     = local.account_id != null
      error_message = "Set either existing_account_name + existing_resource_group, or existing_account_id."
    }
    precondition {
      condition     = local.location != null
      error_message = "location is required when existing_account_id is set (it cannot be derived without the data source)."
    }
    precondition {
      condition     = !strcontains(var.identity_type, "UserAssigned") || length(var.user_assigned_identity_ids) > 0
      error_message = "user_assigned_identity_ids must be non-empty when identity_type includes UserAssigned."
    }
    precondition {
      condition     = !var.enable_app_insights || local.observability_rg != null
      error_message = "observability_resource_group is required when enable_app_insights = true and existing_account_id (path B) is used."
    }
    precondition {
      condition     = !(var.enable_app_insights && !var.create_log_analytics) || var.existing_log_analytics_workspace_id != null
      error_message = "existing_log_analytics_workspace_id is required when enable_app_insights = true and create_log_analytics = false."
    }
  }
}

###############################################################################
# Observability — Log Analytics + Application Insights + project connection
###############################################################################

# Workspace-based App Insights requires a Log Analytics workspace.
resource "azurerm_log_analytics_workspace" "this" {
  count               = var.enable_app_insights && var.create_log_analytics ? 1 : 0
  name                = local.log_analytics_name
  resource_group_name = local.observability_rg
  location            = local.location
  sku                 = var.log_analytics_sku
  retention_in_days   = var.log_analytics_retention_days
  tags                = var.tags
}

resource "azurerm_application_insights" "this" {
  count               = var.enable_app_insights ? 1 : 0
  name                = local.app_insights_name
  resource_group_name = local.observability_rg
  location            = local.location
  application_type    = "web"
  workspace_id        = local.log_analytics_workspace_id
  tags                = var.tags
}

# Connect App Insights to the project. Once connected, agent tracing (enabled in
# the agent/SDK) emits spans + token-usage metrics into this App Insights.
resource "azapi_resource" "appinsights_connection" {
  count                     = var.enable_app_insights ? 1 : 0
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                      = var.app_insights_connection_name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "AppInsights"
      target        = azurerm_application_insights.this[0].id
      authType      = "ApiKey"
      isSharedToAll = true
      credentials = {
        key = azurerm_application_insights.this[0].connection_string
      }
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_application_insights.this[0].id
      }
    }
  }
}

###############################################################################
# Model deployment (account scope) — makes the project agent-ready
#
# Model deployments are ACCOUNT-scoped and shared by every project on the
# account. If a deployment with the same name already exists, a plain create
# fails with "Resource already exists". To handle that gracefully we first LIST
# the account's deployments, then only create when the target name is absent
# (adopt_existing_model_deployment = true, the default). When it already exists
# we skip creation and the outputs point at the existing deployment instead.
###############################################################################

# Read the account's current deployments so we can decide create-vs-reuse.
data "azapi_resource_list" "existing_deployments" {
  count                  = var.deploy_model ? 1 : 0
  type                   = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  parent_id              = local.account_id
  response_export_values = ["*"]
}

locals {
  # Effective deployment name (what agents reference).
  model_deployment_name_effective = coalesce(var.model_deployment_name, var.model_name)

  # The account's existing deployments (empty list when deploy_model = false).
  existing_deployment_list = try(data.azapi_resource_list.existing_deployments[0].output.value, [])

  # Any existing deployment whose name matches the one we want.
  existing_deployment_matches = [
    for d in local.existing_deployment_list : d.id
    if try(d.name, null) == local.model_deployment_name_effective
  ]

  model_already_exists   = length(local.existing_deployment_matches) > 0
  existing_deployment_id = local.model_already_exists ? local.existing_deployment_matches[0] : null

  # Create only when requested AND (we are not adopting OR it isn't there yet).
  create_model_deployment = var.deploy_model && !(var.adopt_existing_model_deployment && local.model_already_exists)
}

resource "azapi_resource" "model_deployment" {
  count                     = local.create_model_deployment ? 1 : 0
  type                      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name                      = local.model_deployment_name_effective
  parent_id                 = local.account_id
  schema_validation_enabled = false

  body = {
    sku = {
      name     = var.model_sku_name
      capacity = var.model_capacity
    }
    properties = merge(
      {
        model = merge(
          {
            format = var.model_format
            name   = var.model_name
          },
          var.model_version == null ? {} : { version = var.model_version },
        )
      },
      var.model_rai_policy_name == null ? {} : { raiPolicyName = var.model_rai_policy_name },
      var.model_version_upgrade_option == null ? {} : { versionUpgradeOption = var.model_version_upgrade_option },
    )
  }

  response_export_values = ["*"]

  # Account-scoped deployments serialize on the server; create the project first.
  depends_on = [azapi_resource.project]

  lifecycle {
    precondition {
      condition     = var.adopt_existing_model_deployment || !local.model_already_exists
      error_message = "A model deployment named '${local.model_deployment_name_effective}' already exists on this account (deployments are account-scoped and shared across projects). Set adopt_existing_model_deployment = true to reuse it, or terraform import it."
    }
  }
}

###############################################################################
# RBAC role assignments
#
# account_role_assignments -> scoped to the account (control-plane + account-wide
#   data-plane, e.g. "Cognitive Services User" which the cadence showed is needed
#   on top of the Foundry role before an agent can be created).
# project_role_assignments -> scoped to the project (data-plane: agents/evals).
#
# Pass an Entra GROUP object ID as principal_id to grant a whole team at once.
###############################################################################

resource "azurerm_role_assignment" "account" {
  for_each = var.account_role_assignments

  scope                = local.account_id
  principal_id         = each.value.principal_id
  principal_type       = each.value.principal_type
  role_definition_name = each.value.role_definition_id == null ? each.value.role_definition_name : null
  role_definition_id   = each.value.role_definition_id
}

resource "azurerm_role_assignment" "project" {
  for_each = var.project_role_assignments

  scope                = azapi_resource.project.id
  principal_id         = each.value.principal_id
  principal_type       = each.value.principal_type
  role_definition_name = each.value.role_definition_id == null ? each.value.role_definition_name : null
  role_definition_id   = each.value.role_definition_id
}
