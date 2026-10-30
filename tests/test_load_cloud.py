"""U20: the cloud loader reaches Azure SQL and Blob with the owner's `az login` token only."""

from azure.identity import AzureCliCredential

from clinic_chain import stand


def test_cloud_connections_use_the_cli_login(monkeypatch):
    calls = {}

    def connect(conn_str, **kwargs):
        calls["sql"] = (conn_str, kwargs)

    monkeypatch.setattr(stand.mssql_python, "connect", connect)
    stand.sql(server="sql-x.database.windows.net")
    conn_str, kwargs = calls["sql"]
    assert conn_str.startswith("Server=sql-x.database.windows.net,1433;Database=clinic_billing;")
    assert "PWD" not in conn_str and "UID" not in conn_str
    assert isinstance(kwargs["token_provider"], AzureCliCredential)

    service = stand.blobs("https://stx.blob.core.windows.net/")
    assert service.url == "https://stx.blob.core.windows.net/"
    assert isinstance(service.credential, AzureCliCredential)
