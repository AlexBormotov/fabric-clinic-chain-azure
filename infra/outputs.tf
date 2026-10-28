output "storage_account_name" {
  value = module.azure_sources.storage_account_name
}

output "blob_endpoint" {
  value = module.azure_sources.blob_endpoint
}

output "sql_server_fqdn" {
  value = module.azure_sources.sql_server_fqdn
}

output "sql_database_name" {
  value = module.azure_sources.sql_database_name
}

output "workspace_ids" {
  description = "Workspace ID per environment (dev, test, prod), for fabric-cicd."
  value       = module.fabric.workspace_ids
}

output "item_ids" {
  description = "Item ID per environment and item name, for parameter.yml."
  value       = module.fabric.item_ids
}

output "deployment_pipeline_id" {
  value = module.fabric.deployment_pipeline_id
}

output "f2_capacity_id" {
  description = "Null unless enable_f2 is true."
  value       = one(module.capacity[*].id)
}
