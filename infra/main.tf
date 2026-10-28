data "azurerm_client_config" "current" {}

# Storage account and SQL server names are global; the suffix keeps them unique.
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

module "azure_sources" {
  source = "./modules/azure-sources"

  prefix                = var.prefix
  suffix                = random_string.suffix.result
  location              = var.location
  owner_upn             = var.owner_upn
  owner_object_id       = data.azurerm_client_config.current.object_id
  client_ip_addresses   = var.client_ip_addresses
  free_limit_exhaustion = var.sql_free_limit_exhaustion
}

module "fabric" {
  source = "./modules/fabric"

  prefix                = var.prefix
  capacity_name         = var.fabric_capacity_name
  git_connection_id     = var.git_connection_id
  github_owner          = var.github_owner
  github_repository     = var.github_repository
  deployer_principal_id = var.deployer_principal_id
}

module "capacity" {
  source = "./modules/capacity"
  count  = var.enable_f2 ? 1 : 0

  name      = "${replace(var.prefix, "-", "")}${random_string.suffix.result}"
  location  = var.location
  admin_upn = var.owner_upn
}
