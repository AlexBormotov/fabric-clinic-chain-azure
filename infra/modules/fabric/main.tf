# Workspaces and the stateful item shells. Code items (notebooks, pipelines, dataflow, eventstream,
# model, report, dashboard, Activator) come from Git through fabric-cicd (U19), not from Terraform.

locals {
  environments = ["dev", "test", "prod"]

  # Notebooks write Tables/<name>, so lakehouses have no schemas.
  lakehouses = ["lh_bronze", "lh_silver"]

  lakehouse_pairs = {
    for pair in setproduct(local.environments, local.lakehouses) : "${pair[0]}.${pair[1]}" => {
      env  = pair[0]
      name = pair[1]
    }
  }
}

data "fabric_capacity" "trial" {
  display_name = var.capacity_name

  lifecycle {
    postcondition {
      condition     = self.state == "Active"
      error_message = "The Fabric capacity is not Active; start or resume it first."
    }
  }
}

resource "fabric_workspace" "env" {
  for_each = toset(local.environments)

  display_name = "${var.prefix}-${each.key}"
  description  = "Clinic chain analytics, ${each.key}."
  capacity_id  = data.fabric_capacity.trial.id
}

resource "fabric_lakehouse" "lh" {
  for_each = local.lakehouse_pairs

  display_name = each.value.name
  workspace_id = fabric_workspace.env[each.value.env].id

  configuration = {
    enable_schemas = false
  }
}

resource "fabric_warehouse" "gold" {
  for_each = fabric_workspace.env

  display_name = "wh_gold"
  workspace_id = each.value.id
}

# The eventhouse creates its default KQL database with the same name.
resource "fabric_eventhouse" "beds" {
  for_each = fabric_workspace.env

  display_name = "eh_beds"
  workspace_id = each.value.id
}

# GitHub needs a Fabric connection that holds the token; the owner creates it in the Fabric UI so the
# token never passes through Terraform.
resource "fabric_workspace_git" "dev" {
  count = var.git_connection_id == null ? 0 : 1

  workspace_id            = fabric_workspace.env["dev"].id
  initialization_strategy = "PreferRemote"

  git_provider_details = {
    git_provider_type = "GitHub"
    owner_name        = var.github_owner
    repository_name   = var.github_repository
    branch_name       = var.git_branch
    directory_name    = var.git_directory
  }

  git_credentials = {
    source        = "ConfiguredConnection"
    connection_id = var.git_connection_id
  }
}

resource "fabric_deployment_pipeline" "promotion" {
  display_name = "${var.prefix}-promotion"
  description  = "Dev to Test to Prod, for comparison with fabric-cicd."

  stages = [
    for env in local.environments : {
      display_name = env
      description  = "${env} stage"
      is_public    = false
      workspace_id = fabric_workspace.env[env].id
    }
  ]
}

resource "fabric_workspace_role_assignment" "deployer" {
  for_each = var.deployer_principal_id == null ? toset([]) : toset(["test", "prod"])

  workspace_id = fabric_workspace.env[each.key].id
  role         = "Contributor"

  principal = {
    id   = var.deployer_principal_id
    type = "ServicePrincipal"
  }
}

# OneLake security on lh_silver (U17, ADR 0005). Table classes and the classes each role reads are in
# lh_silver_roles.json, which tests/test_onelake_security.py checks against the notebooks.
# DefaultReader is the lakehouse's built-in role (everyone with ReadAll); it is narrowed to non-PHI.
# Workspace Admin, Member and Contributor bypass OneLake security: a reader who must not see PHI
# holds only item Read and ReadAll on lh_silver, never a workspace role.
locals {
  silver_roles = jsondecode(file("${path.module}/lh_silver_roles.json"))
  silver_paths = {
    for role, classes in local.silver_roles.roles : role => sort(flatten([
      for class in classes : [for table in local.silver_roles.tables[class] : "/Tables/${table}"]
    ]))
  }
  silver = { for env in local.environments : env => fabric_lakehouse.lh["${env}.lh_silver"] }
}

resource "fabric_onelake_data_access_security" "silver_default_reader" {
  for_each = local.silver

  workspace_id = each.value.workspace_id
  item_id      = each.value.id
  role_name    = "DefaultReader"

  decision_rules = [{
    effect = "Permit"
    permission = [
      { attribute_name = "Path", attribute_value_included_in = local.silver_paths["DefaultReader"] },
      { attribute_name = "Action", attribute_value_included_in = ["Read"] },
    ]
  }]

  members = {
    fabric_item_members = [{
      item_access = ["ReadAll"]
      source_path = "${each.value.workspace_id}/${each.value.id}"
    }]
  }
}

resource "fabric_onelake_data_access_security" "silver_phi_reader" {
  for_each = var.phi_reader_group_id == null ? {} : local.silver

  workspace_id = each.value.workspace_id
  item_id      = each.value.id
  role_name    = "PhiReader"

  decision_rules = [{
    effect = "Permit"
    permission = [
      { attribute_name = "Path", attribute_value_included_in = local.silver_paths["PhiReader"] },
      { attribute_name = "Action", attribute_value_included_in = ["Read"] },
    ]
  }]

  members = {
    microsoft_entra_members = [{
      object_id   = var.phi_reader_group_id
      object_type = "Group"
      tenant_id   = var.tenant_id
    }]
  }
}
