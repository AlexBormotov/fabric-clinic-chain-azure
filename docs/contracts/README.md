# Source contracts

Schemas of the source systems produced by `make sources` (U03) under `data/sources/`. Each YAML
file lists, per table, the file it lives in, the primary key and the columns in order.

- Types: `string`, `int`, `decimal`, `date` (`YYYY-MM-DD`), `datetime` (`YYYY-MM-DD HH:MM:SS`, UTC).
- CSV: UTF-8, comma-separated, header row, empty field = null. Excel: header row on each sheet;
  `file#sheet` names the sheet.
- `nullable` defaults to false.
- Patient demographics are noisy by design (typos, day/month swaps, phone formats, duplicate
  records). `ground_truth` is the only place where local patient IDs meet the person they belong to.
- Billing is loaded into SQL Server (U04) with `billing.sql`; a test keeps it in step with
  `billing.yaml`.

| File | System | Lands via |
|---|---|---|
| `billing.yaml`, `billing.sql` | billing and claims (Azure SQL) | Data Pipeline |
| `lab.yaml` | lab results (CSV on Blob) | Data Pipeline |
| `adt.yaml` | bed management: ADT events, ED visits | Eventstream replay (U11) and batch |
| `sharepoint.yaml` | bed reference and staff rosters (Excel) | Dataflow Gen2 |
| `ground_truth.yaml` | generator truth for MPI and metric references | never loaded as a source |
