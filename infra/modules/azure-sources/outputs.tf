output "storage_account_name" {
  value = azurerm_storage_account.raw.name
}

output "blob_endpoint" {
  value = azurerm_storage_account.raw.primary_blob_endpoint
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.billing.fully_qualified_domain_name
}

output "sql_database_name" {
  value = azapi_resource.billing_db.name
}
