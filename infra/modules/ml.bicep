// Phase C stub: ml. NOT deployed in Phases A/B (no cloud resources are created).
// TODO(phase-c):
//  - define resources for 'ml' with managed identity and diagnostic settings
//  - disable public network access / add private endpoints where supported
//  - required tags: app, env, owner, cost-center
//  - outputs consumed by containerapps.bicep (endpoint URLs, resource IDs)
targetScope = 'resourceGroup'

@description('Environment name: dev | staging | prod')
param env string

@description('Azure region')
param location string = resourceGroup().location

@description('Common tags applied to every resource')
param tags object = {
  app: 'appeal-assistant'
  env: env
}

output moduleName string = 'ml'
output region string = location
output tagSet object = tags
