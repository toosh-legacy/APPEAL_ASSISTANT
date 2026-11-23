// Phase C entry point (stub). Deploy with `azd up` ONLY in Phase C.
targetScope = 'resourceGroup'
param env string
param location string = resourceGroup().location

module network 'modules/network.bicep' = { name: 'network', params: { env: env, location: location } }
module monitoring 'modules/monitoring.bicep' = { name: 'monitoring', params: { env: env, location: location } }
module identity 'modules/identity.bicep' = { name: 'identity', params: { env: env, location: location } }
module keyvault 'modules/keyvault.bicep' = { name: 'keyvault', params: { env: env, location: location } }
module appconfig 'modules/appconfig.bicep' = { name: 'appconfig', params: { env: env, location: location } }
module postgres 'modules/postgres.bicep' = { name: 'postgres', params: { env: env, location: location } }
module storage 'modules/storage.bicep' = { name: 'storage', params: { env: env, location: location } }
module redis 'modules/redis.bicep' = { name: 'redis', params: { env: env, location: location } }
module servicebus 'modules/servicebus.bicep' = { name: 'servicebus', params: { env: env, location: location } }
module acr 'modules/acr.bicep' = { name: 'acr', params: { env: env, location: location } }
module openai 'modules/openai.bicep' = { name: 'openai', params: { env: env, location: location } }
module search 'modules/search.bicep' = { name: 'search', params: { env: env, location: location } }
module docintel 'modules/docintel.bicep' = { name: 'docintel', params: { env: env, location: location } }
module language 'modules/language.bicep' = { name: 'language', params: { env: env, location: location } }
module contentsafety 'modules/contentsafety.bicep' = { name: 'contentsafety', params: { env: env, location: location } }
module ml 'modules/ml.bicep' = { name: 'ml', params: { env: env, location: location } }
module functions 'modules/functions.bicep' = { name: 'functions', params: { env: env, location: location } }
module containerapps 'modules/containerapps.bicep' = { name: 'containerapps', params: { env: env, location: location } }
module frontdoor 'modules/frontdoor.bicep' = { name: 'frontdoor', params: { env: env, location: location } }
