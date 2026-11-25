variable "prefix" {
  description = "Workspace name prefix."
  type        = string
}

variable "capacity_name" {
  description = "Display name of the capacity the workspaces use (the trial)."
  type        = string
}

variable "git_connection_id" {
  description = "Fabric connection ID with the GitHub credential; null skips Git integration."
  type        = string
}

variable "github_owner" {
  description = "GitHub repository owner."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name."
  type        = string
}

variable "git_branch" {
  description = "Branch the Dev workspace follows."
  type        = string
  default     = "main"
}

variable "git_directory" {
  description = "Repository folder holding the Fabric items."
  type        = string
  default     = "/fabric"
}

variable "tenant_id" {
  description = "Entra tenant ID of the OneLake security role members."
  type        = string
}

variable "phi_reader_group_id" {
  description = "Entra group object ID made a member of PhiReader on lh_silver; null skips the role."
  type        = string
}

variable "deployer_principal_id" {
  description = "Service principal object ID given Contributor on Test and Prod; null skips it."
  type        = string
}
