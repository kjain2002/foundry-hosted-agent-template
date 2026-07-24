// Add a governed, agent-ready project to an EXISTING Foundry account.
// Mirrors infra/terraform: project + optional model deployment + optional
// Application Insights (wired to the project) + optional RBAC.
//
// A Foundry project is a CHILD of a Foundry account
// (Microsoft.CognitiveServices/accounts, kind=AIServices). This does NOT create
// a new account. Deploy at the resource group that holds the account:
//   az deployment group create -g <rg> -f main.bicep -p example.bicepparam

targetScope = 'resourceGroup'

@description('Name of the EXISTING Foundry (AIServices) account in this resource group.')
param existingAccountName string

@description('Azure region for the project + observability resources.')
param location string = resourceGroup().location

@description('Name of the new project (child of the account).')
param projectName string

@description('Friendly display name for the project.')
param displayName string = projectName

@description('Optional project description.')
param description string = ''

// --- Model deployment (account-scoped, shared by all projects on the account) ---
@description('Create a model deployment so agents can be created.')
param deployModel bool = true
@description('Model deployment name agents reference. Defaults to the model name.')
param modelDeploymentName string = ''
param modelName string = 'gpt-4.1'
param modelVersion string = '2025-04-14'
param modelFormat string = 'OpenAI'
param modelSkuName string = 'GlobalStandard'
param modelCapacity int = 1

// --- Observability ---
@description('Create Log Analytics + App Insights and connect them to the project.')
param enableAppInsights bool = true
param logAnalyticsRetentionDays int = 30

// --- RBAC ---
@description('Role assignments at ACCOUNT scope. Each: { principalId, principalType, roleDefinitionId }. roleDefinitionId is the GUID of the role (e.g. Cognitive Services User = a97b65f3-24c7-4388-baec-2e87135dc908).')
param accountRoleAssignments array = []

var modelDeploymentNameEffective = empty(modelDeploymentName) ? modelName : modelDeploymentName

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: existingAccountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: displayName
    description: empty(description) ? null : description
  }
}

// Model deployment — idempotent PUT (re-deploying an existing name with the same
// properties is a no-op; account-scoped deployments are shared across projects).
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployModel) {
  parent: account
  name: modelDeploymentNameEffective
  sku: {
    name: modelSkuName
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
  }
}

// --- Observability: Log Analytics + App Insights + project connection ---
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (enableAppInsights) {
  name: '${projectName}-law'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: logAnalyticsRetentionDays
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (enableAppInsights) {
  name: '${projectName}-appi'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
  }
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = if (enableAppInsights) {
  parent: project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

// --- RBAC at account scope (e.g. "Cognitive Services User" for agent creation) ---
resource accountRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for ra in accountRoleAssignments: {
    name: guid(account.id, ra.principalId, ra.roleDefinitionId)
    scope: account
    properties: {
      principalId: ra.principalId
      principalType: ra.principalType
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', ra.roleDefinitionId)
    }
  }
]

@description('Project endpoint to put in FOUNDRY_PROJECT_ENDPOINT.')
output projectEndpoint string = 'https://${existingAccountName}.services.ai.azure.com/api/projects/${projectName}'
output projectName string = projectName
output modelDeploymentName string = deployModel ? modelDeploymentNameEffective : ''
output projectPrincipalId string = project.identity.principalId
