"""Generates the Phase C Bicep stub modules and parameter files. Nothing here deploys anything."""

from pathlib import Path

HERE = Path(__file__).parent
MODULES = [
    "network", "monitoring", "identity", "keyvault", "appconfig", "postgres", "storage", "redis", "servicebus",
    "acr", "openai", "search", "docintel", "language", "contentsafety", "ml", "functions", "containerapps", "frontdoor",
]

STUB = """// Phase C stub: {m}. NOT deployed in Phases A/B (no cloud resources are created).
// TODO(phase-c):
//  - define resources for '{m}' with managed identity and diagnostic settings
//  - disable public network access / add private endpoints where supported
//  - required tags: app, env, owner, cost-center
//  - outputs consumed by containerapps.bicep (endpoint URLs, resource IDs)
targetScope = 'resourceGroup'

@description('Environment name: dev | staging | prod')
param env string

@description('Azure region')
param location string = resourceGroup().location

@description('Common tags applied to every resource')
param tags object = {{
  app: 'appeal-assistant'
  env: env
}}

output moduleName string = '{m}'
output region string = location
output tagSet object = tags
"""

if __name__ == "__main__":
    (HERE / "modules").mkdir(exist_ok=True)
    (HERE / "parameters").mkdir(exist_ok=True)
    for m in MODULES:
        (HERE / "modules" / f"{m}.bicep").write_text(STUB.format(m=m), encoding="utf-8")
    main = ["// Phase C entry point (stub). Deploy with `azd up` ONLY in Phase C.", "targetScope = 'resourceGroup'", "param env string", "param location string = resourceGroup().location", ""]
    for m in MODULES:
        main.append(f"module {m} 'modules/{m}.bicep' = {{ name: '{m}', params: {{ env: env, location: location }} }}")
    (HERE / "main.bicep").write_text("\n".join(main) + "\n", encoding="utf-8")
    for e in ["dev", "staging", "prod"]:
        (HERE / "parameters" / f"{e}.parameters.json").write_text(
            '{\n  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",\n'
            f'  "contentVersion": "1.0.0.0",\n  "parameters": {{ "env": {{ "value": "{e}" }} }}\n}}\n',
            encoding="utf-8",
        )
    print(f"wrote {len(MODULES)} modules")
