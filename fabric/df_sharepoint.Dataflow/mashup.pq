section Section1;

// Parameters: the SharePoint site is set per environment by parameter.yml (U19). run_id is passed by
// the pipeline but unused: the file destination is the fixed folder landing/sharepoint/, overwritten
// on each refresh (Dataflow Gen2 file destinations take no folder parameter).
shared site_url = "https://example.sharepoint.com/sites/clinic-chain" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true];

shared run_id = "manual" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true];

shared Sheet = (file as text, sheet as text) as table =>
    let
        Files = SharePoint.Files(site_url, [ApiVersion = 15]),
        Content = Table.SelectRows(Files, each [Name] = file){0}[Content],
        Data = Excel.Workbook(Content, true){[Item = sheet, Kind = "Sheet"]}[Data]
    in
        Data;

[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "beds_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "File", TransformationQueryName = "beds_DataDestinationTransform"]]]}]
shared beds = Sheet("beds.xlsx", "beds");

[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "staff_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "File", TransformationQueryName = "staff_DataDestinationTransform"]]]}]
shared staff = Sheet("rosters.xlsx", "staff");

// Excel.Workbook returns week_start as the workbook's date serial; the contract wants an ISO date.
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "roster_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "File", TransformationQueryName = "roster_DataDestinationTransform"]]]}]
shared roster = Table.TransformColumns(
    Sheet("rosters.xlsx", "roster"),
    {{"week_start", each Date.ToText(Date.From(_), [Format = "yyyy-MM-dd"]), type text}}
);

// File destinations: lh_bronze Files/landing/sharepoint/<table>.csv. The zero GUIDs are replaced by
// parameter.yml with the target workspace and its lh_bronze.
shared beds_DataDestination = let
  Pattern = Lakehouse.Contents([HierarchicalNavigation = true, EnableVorder = true, OutputMetadataRefresh = true, CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "00000000-0000-0000-0000-000000000000"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "00000000-0000-0000-0000-000000000000"]}[Data],
  Navigation_3 = Navigation_2{[Id = "Files", ItemKind = "Folder"]}[Data],
  Navigation_4 = Navigation_3{[Name = "landing"]}[Content],
  Navigation_5 = Navigation_4{[Name = "sharepoint"]}[Content],
  FileNavigation = Navigation_5{[Name = "beds.csv"]}?[Content]?
in
  FileNavigation;

shared beds_DataDestinationTransform = Csv.OutputConfiguration([Encoding = 65001, Delimiter = ","]);

shared staff_DataDestination = let
  Pattern = Lakehouse.Contents([HierarchicalNavigation = true, EnableVorder = true, OutputMetadataRefresh = true, CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "00000000-0000-0000-0000-000000000000"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "00000000-0000-0000-0000-000000000000"]}[Data],
  Navigation_3 = Navigation_2{[Id = "Files", ItemKind = "Folder"]}[Data],
  Navigation_4 = Navigation_3{[Name = "landing"]}[Content],
  Navigation_5 = Navigation_4{[Name = "sharepoint"]}[Content],
  FileNavigation = Navigation_5{[Name = "staff.csv"]}?[Content]?
in
  FileNavigation;

shared staff_DataDestinationTransform = Csv.OutputConfiguration([Encoding = 65001, Delimiter = ","]);

shared roster_DataDestination = let
  Pattern = Lakehouse.Contents([HierarchicalNavigation = true, EnableVorder = true, OutputMetadataRefresh = true, CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "00000000-0000-0000-0000-000000000000"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "00000000-0000-0000-0000-000000000000"]}[Data],
  Navigation_3 = Navigation_2{[Id = "Files", ItemKind = "Folder"]}[Data],
  Navigation_4 = Navigation_3{[Name = "landing"]}[Content],
  Navigation_5 = Navigation_4{[Name = "sharepoint"]}[Content],
  FileNavigation = Navigation_5{[Name = "roster.csv"]}?[Content]?
in
  FileNavigation;

shared roster_DataDestinationTransform = Csv.OutputConfiguration([Encoding = 65001, Delimiter = ","]);
