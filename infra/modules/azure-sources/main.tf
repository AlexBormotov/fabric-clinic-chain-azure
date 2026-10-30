# Raw files (Blob) and the billing source (Azure SQL free offer). Entra-only access: no keys, no
# SQL password, nothing secret in state.

resource "azurerm_resource_group" "sources" {
  name     = "rg-${var.prefix}-sources"
  location = var.location
}

resource "azurerm_storage_account" "raw" {
  name                            = "st${replace(var.prefix, "-", "")}${var.suffix}"
  resource_group_name             = azurerm_resource_group.sources.name
  location                        = azurerm_resource_group.sources.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  access_tier                     = "Hot"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
}

# The owner uploads with `az login`; Fabric connects with its own Entra identity.
resource "azurerm_role_assignment" "owner_blob" {
  scope                = azurerm_storage_account.raw.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.owner_object_id
}

resource "azurerm_storage_container" "raw" {
  for_each = toset(var.containers)

  name                  = each.key
  storage_account_id    = azurerm_storage_account.raw.id
  container_access_type = "private"
}

resource "azurerm_mssql_server" "billing" {
  name                          = "sql-${var.prefix}-${var.suffix}"
  resource_group_name           = azurerm_resource_group.sources.name
  location                      = azurerm_resource_group.sources.location
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true

  azuread_administrator {
    login_username              = var.owner_upn
    object_id                   = var.owner_object_id
    azuread_authentication_only = true
  }
}

# 0.0.0.0 is Azure's "allow Azure services" rule: Fabric pipelines reach the server through it.
resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.billing.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_firewall_rule" "client" {
  for_each = toset(var.client_ip_addresses)

  name             = "client-${replace(each.key, ".", "-")}"
  server_id        = azurerm_mssql_server.billing.id
  start_ip_address = each.key
  end_ip_address   = each.key
}

# azurerm 5.9.0 has no free-offer arguments (hashicorp/terraform-provider-azurerm#23438), so the
# database goes through the ARM API directly. The free offer can be set only at creation.
resource "azapi_resource" "billing_db" {
  type      = "Microsoft.Sql/servers/databases@2025-01-01"
  name      = var.database_name
  parent_id = azurerm_mssql_server.billing.id
  location  = azurerm_resource_group.sources.location

  body = {
    sku = {
      name     = "GP_S_Gen5"
      tier     = "GeneralPurpose"
      family   = "Gen5"
      capacity = 2
    }
    properties = {
      useFreeLimit                     = true
      freeLimitExhaustionBehavior      = var.free_limit_exhaustion
      maxSizeBytes                     = 34359738368
      requestedBackupStorageRedundancy = "Local"
    }
  }
}
