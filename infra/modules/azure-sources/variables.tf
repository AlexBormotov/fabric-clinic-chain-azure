variable "prefix" {
  description = "Name prefix."
  type        = string
}

variable "suffix" {
  description = "Random suffix for globally unique names."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "owner_upn" {
  description = "Owner's UPN, the SQL Entra admin login."
  type        = string
}

variable "owner_object_id" {
  description = "Owner's Entra object ID."
  type        = string
}

variable "client_ip_addresses" {
  description = "IPv4 addresses allowed through the SQL firewall."
  type        = list(string)
}

variable "free_limit_exhaustion" {
  description = "AutoPause or BillOverUsage."
  type        = string
}

variable "database_name" {
  description = "Billing database name; matches the local stand."
  type        = string
  default     = "clinic_billing"
}

variable "containers" {
  description = "Blob containers; match the local stand."
  type        = list(string)
  default     = ["fhir", "lab", "adt"]
}
