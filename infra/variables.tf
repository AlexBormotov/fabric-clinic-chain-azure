# Defaults are the cheapest path: no paid capacity, SQL free offer that pauses at its limit.

variable "subscription_id" {
  description = "Azure subscription ID. Null falls back to ARM_SUBSCRIPTION_ID."
  type        = string
  default     = null
}

variable "owner_upn" {
  description = "Owner's Entra user principal name: SQL Entra admin and F2 capacity admin."
  type        = string
}

variable "location" {
  description = "Azure region for every Azure resource."
  type        = string
  default     = "westeurope"
}

variable "prefix" {
  description = "Name prefix for resources and workspaces."
  type        = string
  default     = "clinic-chain"
}

variable "client_ip_addresses" {
  description = "Public IPv4 addresses allowed through the SQL firewall (the owner's machine)."
  type        = list(string)
  default     = []
}

variable "sql_free_limit_exhaustion" {
  description = "AutoPause stops at the monthly free limit; BillOverUsage bills overage and cannot be undone."
  type        = string
  default     = "AutoPause"

  validation {
    condition     = contains(["AutoPause", "BillOverUsage"], var.sql_free_limit_exhaustion)
    error_message = "Must be AutoPause or BillOverUsage."
  }
}

variable "fabric_capacity_name" {
  description = "Display name of the Fabric trial capacity the workspaces run on."
  type        = string
}

variable "git_connection_id" {
  description = "Fabric connection ID holding the GitHub credential. Null skips Git integration of Dev."
  type        = string
  default     = null
}

variable "github_owner" {
  description = "GitHub owner of the repository connected to the Dev workspace."
  type        = string
  default     = "AlexBormotov"
}

variable "github_repository" {
  description = "Repository connected to the Dev workspace."
  type        = string
  default     = "fabric-clinic-chain-azure"
}

variable "deployer_principal_id" {
  description = "Object ID of the service principal fabric-cicd deploys with (U19). Null skips its role."
  type        = string
  default     = null
}

variable "enable_f2" {
  description = "Create the F2 capacity ($0.44/h in West Europe). Apply true, check, apply false."
  type        = bool
  default     = false
}
