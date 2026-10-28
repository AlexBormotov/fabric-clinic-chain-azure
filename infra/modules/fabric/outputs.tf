output "workspace_ids" {
  value = { for env, ws in fabric_workspace.env : env => ws.id }
}

output "item_ids" {
  value = {
    for env, ws in fabric_workspace.env : env => merge(
      { for key, lh in fabric_lakehouse.lh : lh.display_name => lh.id if startswith(key, "${env}.") },
      { wh_gold = fabric_warehouse.gold[env].id, eh_beds = fabric_eventhouse.beds[env].id },
    )
  }
}

output "deployment_pipeline_id" {
  value = fabric_deployment_pipeline.promotion.id
}
