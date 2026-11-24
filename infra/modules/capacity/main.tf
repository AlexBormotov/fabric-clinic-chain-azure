# F2 in its own resource group; the workspaces run on it. Billed per second while it exists and is
# not paused: suspend it between sittings, destroy it at the end.

resource "azurerm_resource_group" "capacity" {
  name     = "rg-${var.name}-capacity"
  location = var.location
}

resource "azurerm_fabric_capacity" "f2" {
  name                   = var.name
  resource_group_name    = azurerm_resource_group.capacity.name
  location               = azurerm_resource_group.capacity.location
  administration_members = [var.admin_upn]

  sku {
    name = "F2"
    tier = "Fabric"
  }
}
