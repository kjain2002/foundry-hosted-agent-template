# Example values — copy to terraform.tfvars and fill in YOUR account + RG.
existing_account_name   = "your-foundry-account"
existing_resource_group = "your-resource-group"

project_name = "my-agent-project"
display_name = "My Agent Project"
description  = "Foundry project for the hosted agent"

identity_type    = "SystemAssigned"
project_sku_name = "S0"

tags = {
  environment = "dev"
  workload    = "hosted-agent"
}

enable_app_insights          = true
create_log_analytics         = true
log_analytics_retention_days = 30

deploy_model   = true
model_name     = "gpt-4.1"
model_version  = "2025-04-14"
model_sku_name = "GlobalStandard"
model_capacity = 1

# Grant your Entra user/group the roles needed to create agents (example):
# account_role_assignments = {
#   me = { principal_id = "<your-object-id>", principal_type = "User", role_definition_name = "Cognitive Services User" }
# }
account_role_assignments = {}
project_role_assignments = {}
