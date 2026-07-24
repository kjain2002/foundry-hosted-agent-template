###############################################################################
# Project
###############################################################################

output "project_id" {
  description = "ARM resource ID of the new project."
  value       = azapi_resource.project.id
}

output "project_name" {
  description = "Resource name of the new project."
  value       = azapi_resource.project.name
}

output "project_principal_id" {
  description = "System-assigned managed identity principal ID of the project (null when identity_type = None)."
  value       = try(azapi_resource.project.output.identity.principalId, null)
}

output "project_internal_id" {
  description = "Foundry internal project ID (properties.internalId)."
  value       = try(azapi_resource.project.output.properties.internalId, null)
}

output "project_endpoint" {
  description = "Foundry project endpoint."
  value       = "https://${local.account_name}.services.ai.azure.com/api/projects/${azapi_resource.project.name}"
}

output "account_name" {
  description = "Name of the existing Foundry account the project was created under (used for az verification)."
  value       = local.account_name
}

output "account_resource_group" {
  description = "Resource group of the existing Foundry account. Null when referenced by raw ARM ID (path B)."
  value       = var.existing_resource_group
}

###############################################################################
# Observability
###############################################################################

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace backing App Insights (created or reused). Null when App Insights is disabled."
  value       = var.enable_app_insights ? local.log_analytics_workspace_id : null
}

output "app_insights_id" {
  description = "Application Insights resource ID. Null when App Insights is disabled."
  value       = try(azurerm_application_insights.this[0].id, null)
}

output "app_insights_connection_string" {
  description = "Application Insights connection string (use for SDK tracing if you wire it manually)."
  value       = try(azurerm_application_insights.this[0].connection_string, null)
  sensitive   = true
}

output "app_insights_connection_id" {
  description = "ARM ID of the project's AppInsights connection. Null when App Insights is disabled."
  value       = try(azapi_resource.appinsights_connection[0].id, null)
}

###############################################################################
# Model deployment
###############################################################################

output "model_deployment_name" {
  description = "Name of the deployed model (the value agents reference). Null when deploy_model = false."
  value       = var.deploy_model ? local.model_deployment_name_effective : null
}

output "model_deployment_id" {
  description = "ARM resource ID of the model deployment (the newly created one, or the existing one when adopted). Null when deploy_model = false and none exists."
  value       = try(azapi_resource.model_deployment[0].id, local.existing_deployment_id)
}

output "model_deployment_adopted" {
  description = "True when an existing account-scoped deployment was reused instead of created. False when this run created it (or deploy_model = false)."
  value       = var.deploy_model && var.adopt_existing_model_deployment && local.model_already_exists
}

###############################################################################
# RBAC
###############################################################################

output "account_role_assignment_ids" {
  description = "Map of account-scoped role assignment keys to their ARM IDs."
  value       = { for k, v in azurerm_role_assignment.account : k => v.id }
}

output "project_role_assignment_ids" {
  description = "Map of project-scoped role assignment keys to their ARM IDs."
  value       = { for k, v in azurerm_role_assignment.project : k => v.id }
}
