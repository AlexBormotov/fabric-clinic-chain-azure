"""U16 PHI protection in Gold. The fast tests read `sql/gold/`; `stand` tests query the Gold built
by `make gold` as three local logins: one per role, and one with only db_datareader, which stands
in for a Fabric Viewer (ReadData). Fabric has no logins (Entra identities only), so the logins
exist only here, in test setup."""

import re
import secrets
from datetime import date
from pathlib import Path

import gold
import pytest

from clinic_chain import stand

GOLD = Path(__file__).resolve().parents[1] / "sql" / "gold"
# PHI in Gold: direct identifiers and the quasi-identifiers that narrow a person down (HIPAA Safe
# Harbor: names, dates of birth, phone numbers, postal codes). master_patient_id is a hash of
# the MPI cluster label, not of demographics; sex alone does not identify. Event dates in facts stay
# clear: the analysis needs them, and without the patient's demographics they do not identify.
PHI = {"dim_patient": {"given_name", "family_name", "birth_date", "phone", "postal_code"}}
NOT_PHI = {"dim_patient": {"master_patient_id", "sex", "home_clinic_id", "source_records"}}
# Column DENY is the access control: a mask alone leaks through predicates (WHERE birth_date = ...).
DENIED = PHI
MASKED_NAME = re.compile(r"^.xxxx$")


def tables() -> dict[str, dict[str, str]]:
    """Gold table → column → its definition line, from 00_tables.sql."""
    text = (GOLD / "00_tables.sql").read_text()
    return {
        name: dict(re.findall(r"^\s+(\w+) (.+?),?$", body, re.MULTILINE))
        for name, body in re.findall(r"CREATE TABLE gold\.(\w+) \((.*?)\n\);", text, re.DOTALL)
    }


def denied() -> dict[str, set[str]]:
    text = (GOLD / "30_security.sql").read_text()
    found: dict[str, set[str]] = {}
    for columns, table in re.findall(
        r"DENY SELECT \(([^)]+)\) ON gold\.(\w+) TO gold_reader", text
    ):
        found.setdefault(table, set()).update(c.strip() for c in columns.split(","))
    return found


def test_every_dim_patient_column_is_classified():
    assert set(tables()["dim_patient"]) == PHI["dim_patient"] | NOT_PHI["dim_patient"]


def test_phi_columns_appear_only_in_dim_patient():
    phi_names = set().union(*PHI.values())
    for table, columns in tables().items():
        if table not in PHI:
            assert not phi_names & set(columns), table


def test_no_gold_view_reads_phi():
    """A view owned like its tables skips their permission checks (ownership chaining), so a
    view over `phone` would bypass the DENY."""
    phi_names = set().union(*PHI.values())
    for path in GOLD.glob("*.sql"):
        text = path.read_text()
        if re.search(r"\bCREATE\s+(OR\s+ALTER\s+)?VIEW\b", text, re.IGNORECASE):
            assert not phi_names & set(re.findall(r"\w+", text)), path.name


def test_every_phi_column_is_masked():
    for table, columns in PHI.items():
        definitions = tables()[table]
        for column in columns:
            assert "MASKED WITH" in definitions[column], (table, column)


def test_cls_denies_the_documented_columns():
    assert denied() == DENIED


def test_security_sql_creates_no_principal_fabric_lacks():
    text = (GOLD / "30_security.sql").read_text()
    assert not re.search(r"\bCREATE\s+(USER|LOGIN)\b|\bADD\s+MEMBER\b", text, re.IGNORECASE)


# --- needs `make up` and `make gold` ------------------------------------------------------


def _password() -> str:
    return "Aa1-" + secrets.token_urlsafe(18)


def _drop(cur, login: str) -> None:
    """Drop the test login; the driver pools connections, so its sessions are killed first."""
    cur.execute("SELECT session_id FROM sys.dm_exec_sessions WHERE login_name = ?", login)
    for (session_id,) in cur.fetchall():
        cur.execute(f"KILL {session_id}")
    cur.execute(f"DROP USER IF EXISTS {login}")
    cur.execute(f"IF SUSER_ID('{login}') IS NOT NULL DROP LOGIN {login}")


ROLES = {
    "u16_reader": "gold_reader",
    "u16_phi_reader": "gold_phi_reader",
    "u16_datareader": "db_datareader",
}


@pytest.fixture(scope="module")
def logins():
    """login name → password, one login per entry in ROLES; dropped afterwards."""
    created = {}
    with stand.sql(gold.DATABASE) as conn:
        cur = conn.cursor()
        for login, role in ROLES.items():
            password = _password()
            _drop(cur, login)
            cur.execute(f"CREATE LOGIN {login} WITH PASSWORD = '{password}', CHECK_POLICY = OFF")
            cur.execute(f"CREATE USER {login} FOR LOGIN {login}")
            cur.execute(f"ALTER ROLE {role} ADD MEMBER {login}")
            created[login] = password
        yield created
        for login in created:
            _drop(cur, login)


def rows(query: str, user: str = "sa", password: str | None = None) -> list[tuple]:
    with stand.sql(gold.DATABASE, user, password) as conn:
        cur = conn.cursor()
        cur.execute(query)
        return [tuple(r) for r in cur.fetchall()]


PATIENT = (
    "SELECT master_patient_id, given_name, family_name, birth_date, postal_code"
    " FROM gold.dim_patient ORDER BY master_patient_id"
)


@pytest.mark.stand
def test_datareader_sees_phi_masked(logins):
    clear = rows(PATIENT)
    masked = rows(PATIENT, "u16_datareader", logins["u16_datareader"])
    assert [r[0] for r in masked] == [r[0] for r in clear]
    for (_, given, family, born, postal), (_, c_given, c_family, _, c_postal) in zip(
        masked, clear, strict=True
    ):
        assert given is None or (MASKED_NAME.match(given) and given != c_given)
        assert family is None or (MASKED_NAME.match(family) and family != c_family)
        assert born is None or born == date(1900, 1, 1)
        assert postal is None or postal == (c_postal[:3] + "xx")


@pytest.mark.stand
def test_reader_is_denied_every_phi_column(logins):
    queries = [f"SELECT {c} FROM gold.dim_patient" for c in sorted(DENIED["dim_patient"])]
    queries += [
        "SELECT * FROM gold.dim_patient",
        # Predicates are denied too, so masked values cannot be inferred.
        "SELECT COUNT(*) FROM gold.dim_patient WHERE birth_date = '1980-01-01'",
        "SELECT COUNT(*) FROM gold.dim_patient WHERE family_name LIKE 'A%'",
    ]
    for query in queries:
        with pytest.raises(Exception, match="SELECT permission was denied on the column"):
            rows(query, "u16_reader", logins["u16_reader"])


@pytest.mark.stand
def test_reader_reads_non_phi_columns_and_facts_but_not_silver(logins):
    login = ("u16_reader", logins["u16_reader"])
    columns = ", ".join(sorted(NOT_PHI["dim_patient"]))
    assert len(rows(f"SELECT {columns} FROM gold.dim_patient", *login)) == len(
        rows("SELECT master_patient_id FROM gold.dim_patient")
    )
    assert rows("SELECT COUNT(*) FROM gold.fact_claim", *login)[0][0]
    with pytest.raises(Exception, match="SELECT permission was denied"):
        rows("SELECT TOP 1 * FROM silver.patient_record", *login)


@pytest.mark.stand
def test_phi_reader_sees_clear_values(logins):
    query = PATIENT.replace("postal_code", "postal_code, phone")
    assert rows(query, "u16_phi_reader", logins["u16_phi_reader"]) == rows(query)
