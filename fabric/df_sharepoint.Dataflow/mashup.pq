section Section1;

// Parameters: the SharePoint site is set per environment by parameter.yml (U19); the pipeline passes
// its run ID so the Files destination lands under landing/sharepoint/<run_id>/.
shared site_url = "https://example.sharepoint.com/sites/clinic-chain" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true];

shared run_id = "manual" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true];

shared Sheet = (file as text, sheet as text) as table =>
    let
        Files = SharePoint.Files(site_url, [ApiVersion = 15]),
        Content = Table.SelectRows(Files, each [Name] = file){0}[Content],
        Data = Excel.Workbook(Content, true){[Item = sheet, Kind = "Sheet"]}[Data]
    in
        Data;

shared beds = Sheet("beds.xlsx", "beds");

shared staff = Sheet("rosters.xlsx", "staff");

shared roster = Sheet("rosters.xlsx", "roster");
