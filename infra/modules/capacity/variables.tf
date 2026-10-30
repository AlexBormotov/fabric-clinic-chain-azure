variable "name" {
  description = "Capacity name: lowercase letters and digits, 3-63 characters."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "admin_upn" {
  description = "Capacity administrator's UPN."
  type        = string
}
