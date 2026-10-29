config {
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Baked into the dev image under TFLINT_PLUGIN_DIR; `tflint --init` is never needed.
plugin "azurerm" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}

# Everything is torn down after the cloud run (INT-001/AC14); prevent_destroy would block that.
rule "azurerm_resources_missing_prevent_destroy" {
  enabled = false
}
