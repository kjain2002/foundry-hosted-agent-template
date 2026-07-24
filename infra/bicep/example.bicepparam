using './main.bicep'

// Copy to your own .bicepparam and fill in YOUR values.
param existingAccountName = 'your-foundry-account'
param location = 'eastus2'
param projectName = 'my-agent-project'
param displayName = 'My Agent Project'
param description = 'Foundry project for the hosted agent'

// Model deployment (agent-ready)
param deployModel = true
param modelName = 'gpt-4.1'
param modelVersion = '2025-04-14'
param modelSkuName = 'GlobalStandard'
param modelCapacity = 1

// Observability
param enableAppInsights = true
param logAnalyticsRetentionDays = 30

// RBAC (example — grant your Entra user/group the role to create agents).
// Cognitive Services User roleDefinitionId = a97b65f3-24c7-4388-baec-2e87135dc908
// param accountRoleAssignments = [
//   {
//     principalId: '<your-object-id>'
//     principalType: 'User'
//     roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
//   }
// ]
param accountRoleAssignments = []
