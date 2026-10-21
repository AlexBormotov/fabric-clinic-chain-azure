# Tenant and free-tier options, read 2026-10-21

Agent-gathered from Microsoft documentation. Items marked "unconfirmed" need a check before use.

| Option | Finding | Source |
|---|---|---|
| M365 Developer Program sandbox | Not open to individuals: only Visual Studio Pro/Enterprise subscribers, ISV Success / eligible partners, Premier/Unified Support customers | https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq |
| M365 Business Basic/Standard/Premium trial | Free 1 month, new tenant, 25 licences, card required. Renews to paid by default: set recurring billing Off on day one (Billing > Your products). Trial-only tenant: 30 days, 300 GB | https://learn.microsoft.com/en-us/microsoft-365/commerce/try-or-buy-microsoft-365 |
| SharePoint | Needs an M365 or SharePoint licence; a bare Entra tenant has none | — |
| Fabric trial | 60 days, F4 or F64, includes Power BI individual trial (PPU rights). Needs tenant settings "Users can try Microsoft Fabric paid features" and "Users can create Fabric items". No documented ban on trial tenants | https://learn.microsoft.com/en-us/fabric/fundamentals/fabric-trial |
| Azure free account | $200 / 30 days, card required, one per customer. Russia and Belarus not eligible | https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account |
| Cross-tenant Azure SQL | Fabric connector Basic (SQL) auth has no tenant tie; firewall rule for Fabric egress unconfirmed | https://learn.microsoft.com/en-us/fabric/data-factory/connector-azure-sql-database |
| `azurerm_fabric_capacity` | Subscription must be in the Fabric tenant; capacity admin must be a member (not B2B guest) | https://learn.microsoft.com/en-us/fabric/enterprise/buy-capacity |
| Service principal from CI | "Service principals can call Fabric public APIs" on by default; "...can create workspaces, connections, and deployment pipelines" off by default. Some items (warehouse, some notebook jobs) may fail under SP | https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer |
| Region | Home region set at tenant creation (country at sign-up, mapping unconfirmed). Pick an EU country with a full-Fabric region; avoid Power BI-only regions (Austria East, Belgium Central, Denmark East, France South, Germany North, Norway West) | https://learn.microsoft.com/en-us/fabric/admin/region-availability |
| Russia | Microsoft suspended new sales in Russia (2022); Russian card/address very likely fails sign-up (unconfirmed for Fabric specifically) | https://blogs.microsoft.com/on-the-issues/2022/03/04/microsoft-suspends-russia-sales-ukraine-conflict/ |
