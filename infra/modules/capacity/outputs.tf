output "id" {
  value = azurerm_fabric_capacity.f2.id
}

# Read from the resource, so the workspaces wait for the capacity and are destroyed before it.
output "name" {
  value = azurerm_fabric_capacity.f2.name
}
