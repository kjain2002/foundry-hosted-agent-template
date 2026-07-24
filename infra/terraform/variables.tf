###############################################################################
# Identify the EXISTING Foundry account
#
# Two ways to point at the account this project will live under:
#   (A) name + resource group -> resolved via the azurerm data source. Default,
#       cleanest for an account you do NOT otherwise manage in this state.
#   (B) full ARM resource ID  -> set existing_account_id for cross-subscription
#       or raw-ID cases. Bypasses the data source and REQUIRES `location`.
###############################################################################

variable "existing_account_name" {
  description = "Name of the existing Foundry account (Microsoft.CognitiveServices/accounts, kind=AIServices). Required unless existing_account_id is set."
  type        = string
  default     = null
}

variable "existing_resource_group" {
  description = "Resource group of the existing Foundry account. Required unless existing_account_id is set. Also used as the default RG for the App Insights / Log Analytics resources unless observability_resource_group is set."
  type        = string
  default     = null
}

variable "existing_account_id" {
  description = "Full ARM resource ID of the existing Foundry account. Alternative to name + resource group; use for cross-subscription or raw-ID scenarios. When set, `location` must also be provided."
  type        = string
  default     = null
}

variable "location" {
  description = "Azure region for the project + observability resources. Optional when using name + resource group (derived from the account); REQUIRED when using existing_account_id."
  type        = string
  default     = null
}

###############################################################################
# The NEW project
###############################################################################

variable "project_name" {
  description = "Resource name of the new project (a child of the existing account)."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9-]{1,62}[a-zA-Z0-9]$", var.project_name))
    error_message = "project_name must be 3-64 characters, alphanumeric or hyphens, and must not start or end with a hyphen."
  }
}

variable "display_name" {
  description = "Friendly display name shown in the Foundry portal. Defaults to project_name when null."
  type        = string
  default     = null
}

variable "description" {
  description = "Optional project description."
  type        = string
  default     = null
}

variable "identity_type" {
  description = "Managed identity for the project. One of: SystemAssigned, UserAssigned, \"SystemAssigned, UserAssigned\", None. Agents and connections need a managed identity, so SystemAssigned is the default."
  type        = string
  default     = "SystemAssigned"

  validation {
    condition     = contains(["SystemAssigned", "UserAssigned", "SystemAssigned, UserAssigned", "None"], var.identity_type)
    error_message = "identity_type must be one of: SystemAssigned, UserAssigned, \"SystemAssigned, UserAssigned\", None."
  }
}

variable "user_assigned_identity_ids" {
  description = "User-assigned managed identity resource IDs. Required when identity_type includes UserAssigned."
  type        = list(string)
  default     = []
}

variable "project_sku_name" {
  description = "SKU name for the project. The proven demo deploys \"S0\". Set to null to omit the sku from the request body (the Microsoft AzAPI sample omits it)."
  type        = string
  default     = "S0"
}

variable "ensure_project_management" {
  description = "When true, PATCH the account to set allowProjectManagement=true before creating the project. Leave false if the account is already a Foundry account (the usual case). Requires Cognitive Services Contributor on the account."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to the project and the observability resources."
  type        = map(string)
  default     = {}
}

###############################################################################
# Observability — Application Insights (the "LLM token usage" deliverable)
#
# When enabled this stands up a (workspace-based) Application Insights resource
# and wires it to the project as an AppInsights connection. Agent traces and
# token usage (prompt / completion / cached tokens per request) then flow into
# App Insights automatically once tracing is enabled in the agent/SDK.
###############################################################################

variable "enable_app_insights" {
  description = "When true, create/attach Application Insights and connect it to the project for tracing + token usage telemetry."
  type        = bool
  default     = true
}

variable "observability_resource_group" {
  description = "Resource group to create the Log Analytics workspace + App Insights in. Defaults to existing_resource_group. REQUIRED when enable_app_insights = true and you used existing_account_id (path B), because no RG can be derived in that mode."
  type        = string
  default     = null
}

variable "create_log_analytics" {
  description = "When true, create a Log Analytics workspace to back App Insights (App Insights is workspace-based). Set false to reuse existing_log_analytics_workspace_id."
  type        = bool
  default     = true
}

variable "existing_log_analytics_workspace_id" {
  description = "Resource ID of an existing Log Analytics workspace to back App Insights. Required when create_log_analytics = false."
  type        = string
  default     = null
}

variable "log_analytics_name" {
  description = "Name of the Log Analytics workspace to create. Defaults to \"<project_name>-law\"."
  type        = string
  default     = null
}

variable "log_analytics_sku" {
  description = "Log Analytics workspace SKU."
  type        = string
  default     = "PerGB2018"
}

variable "log_analytics_retention_days" {
  description = "Log Analytics retention in days."
  type        = number
  default     = 30
}

variable "app_insights_name" {
  description = "Name of the Application Insights resource to create. Defaults to \"<project_name>-appi\"."
  type        = string
  default     = null
}

variable "app_insights_connection_name" {
  description = "Name of the AppInsights connection created on the project."
  type        = string
  default     = "appinsights-connection"
}

###############################################################################
# Model deployment (so a fresh project is agent-ready)
#
# A model deployment lives on the ACCOUNT (shared by all projects), not the
# project. In the 6/26 cadence, an agent could only be created AFTER a model
# (gpt-4.1) was deployed — this block automates that prerequisite.
#
# To change the model (e.g. gpt-4.1 -> gpt-4o), edit model_name/model_version/
# model_sku_name. See MODEL-CHANGE.md for a step-by-step guide.
###############################################################################

variable "deploy_model" {
  description = "When true, deploy a model on the account so projects can create agents immediately."
  type        = bool
  default     = true
}

variable "adopt_existing_model_deployment" {
  description = "Model deployments are account-scoped and shared by every project on the account. When true (default), if a deployment with the same name already exists the module REUSES it instead of failing (outputs point at the existing one). Set false to force creation, which errors if the deployment already exists."
  type        = bool
  default     = true
}

variable "model_deployment_name" {
  description = "Name of the model deployment (the name agents reference). Defaults to model_name."
  type        = string
  default     = null
}

variable "model_name" {
  description = "Model to deploy (e.g. gpt-4.1, gpt-4o, gpt-4o-mini). See MODEL-CHANGE.md."
  type        = string
  default     = "gpt-4.1"
}

variable "model_version" {
  description = "Model version to pin (e.g. \"2025-04-14\"). Set null to let the service choose the default version."
  type        = string
  default     = null
}

variable "model_format" {
  description = "Model provider/format. \"OpenAI\" for Azure OpenAI models."
  type        = string
  default     = "OpenAI"
}

variable "model_sku_name" {
  description = "Deployment SKU: GlobalStandard, DataZoneStandard, Standard, ProvisionedManaged, etc."
  type        = string
  default     = "GlobalStandard"
}

variable "model_capacity" {
  description = "Deployment capacity in thousands of tokens-per-minute (TPM). Draws from the subscription x region x model quota pool."
  type        = number
  default     = 50
}

variable "model_rai_policy_name" {
  description = "Responsible AI content-filter policy to apply. Null uses the account default."
  type        = string
  default     = null
}

variable "model_version_upgrade_option" {
  description = "Auto-upgrade behavior: OnceNewDefaultVersionAvailable, OnceCurrentVersionExpired, or NoAutoUpgrade."
  type        = string
  default     = "OnceNewDefaultVersionAvailable"
}

###############################################################################
# RBAC role assignments (so users / Entra groups get access on deploy)
#
# Assign roles at the ACCOUNT scope and/or the PROJECT scope. Pass an Entra
# GROUP object ID as principal_id so every member gets access automatically
# (no manual per-email adds in the portal).
#
# Each assignment takes either role_definition_name OR role_definition_id.
# Use role_definition_id (a GUID) when the portal display name has been renamed
# (e.g. the Foundry/Azure AI roles) and the name lookup is ambiguous.
#
# NOTE: creating role assignments requires the Terraform principal to hold
# Owner or User Access Administrator at the target scope.
###############################################################################

variable "account_role_assignments" {
  description = "Role assignments scoped to the ACCOUNT (control-plane: deploy models, manage projects, account-wide data-plane like Cognitive Services User). Keyed by an arbitrary stable string."
  type = map(object({
    principal_id         = string
    role_definition_name = optional(string)
    role_definition_id   = optional(string)
    principal_type       = optional(string) # "User" | "Group" | "ServicePrincipal"
  }))
  default = {}
}

variable "project_role_assignments" {
  description = "Role assignments scoped to the PROJECT (data-plane: build agents, run evals, upload files). Keyed by an arbitrary stable string."
  type = map(object({
    principal_id         = string
    role_definition_name = optional(string)
    role_definition_id   = optional(string)
    principal_type       = optional(string) # "User" | "Group" | "ServicePrincipal"
  }))
  default = {}
}
