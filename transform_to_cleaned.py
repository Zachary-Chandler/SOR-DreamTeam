"""Build the `cleaned` schema from the raw `sor` schema loaded by load_registry_pg.py.

Usage:
    python3 transform_to_cleaned.py [connection]

`connection` is anything psql accepts as a database argument (see load_registry_pg.py
for examples). Requires the raw export already loaded into schema `sor`
(run load_registry_pg.py first) and docs/database/schema.sql present, which is the
single source of truth for the cleaned schema's DDL.

How it works
- Reads docs/database/schema.sql and replays it into a fresh schema `cleaned_new`
  (same tables, views, constraints and indexes as `cleaned`, just staged under a
  different name).
- Populates cleaned_new from sor, applying the cleaning rules documented in
  docs/database/Database_Documentation.pdf:
    - individual, person and name load straight across (their field counts match
      the raw INDV/PERSON/NAME tables exactly).
    - offense rows are deduplicated on exact full-row matches; offense_record_id
      is a surrogate identity key, not the original (non-unique) OffenseId.
    - address rows whose IND_IDN has no matching individual are excluded from
      cleaned_new and reported at the end, never silently discarded (see
      "The unmatched address needs a documented handling decision" in the docs).
- Re-applies the DPS removal ledger (apply_removals.py) to cleaned_new so removed
  people never reappear after a refresh.
- In one transaction, renames cleaned -> cleaned_old (dropped) and
  cleaned_new -> cleaned, so the app always sees either the complete old or
  complete new cleaned data, never a half-built one.
- Re-run after every refresh of `sor` (load_registry_pg.py), per SETUP.md.
"""
import re
import subprocess
import sys
from pathlib import Path

import apply_removals

SCHEMA_SQL = Path(__file__).parent / "docs" / "database" / "schema.sql"

POPULATE_SQL = """
INSERT INTO cleaned_new.individual (ind_idn, dps_nbr)
SELECT "IND_IDN"::text, "DPS_NBR" FROM sor."INDV";

INSERT INTO cleaned_new.person (ind_idn, per_idn, sex_cod, rac_cod, hgt_qty, wgt_qty, hai_cod, eye_cod, eth_cod)
SELECT "IND_IDN"::text, "PER_IDN"::text, "SEX_COD", "RAC_COD", "HGT_QTY"::text, "WGT_QTY"::text, "HAI_COD", "EYE_COD", "ETH_COD"
FROM sor."PERSON";

INSERT INTO cleaned_new.name (nam_idn, per_idn, typ_cod, nam_txt, lna_txt, fna_txt)
SELECT "NAM_IDN"::text, "PER_IDN"::text, "TYP_COD", "NAM_TXT", "LNA_TXT", "FNA_TXT"
FROM sor."NAME";

-- Exact-duplicate-row dedup; offense_record_id (identity column) is the surrogate
-- key because the original OffenseId is not unique (see docs).
INSERT INTO cleaned_new.offense
  (ind_idn, offenseid, coo_cod, coj_cod, joo_cod, off_cod, ver_nbr, goc_cod,
   dis_flg, ost_cod, cpr_cod, cdd_dte, aov_nbr, sov_cod, cpr_val)
SELECT DISTINCT
  "IND_IDN"::text, "OffenseId"::text, "COO_COD", "COJ_COD", "JOO_COD", "OFF_COD",
  "VER_NBR"::text, "GOC_COD", "DIS_FLG", "OST_COD", "CPR_COD", "CDD_DTE",
  "AOV_NBR"::text, "SOV_COD", "CPR_VAL"
FROM sor."Offense";

-- Addresses whose individual has no matching record are excluded here and
-- counted separately below; see docs/database/Database_Documentation.pdf
-- ("The unmatched address needs a documented handling decision. Do not
-- silently invent an individual or discard the raw record").
INSERT INTO cleaned_new.address
  (addressid, ind_idn, snu_nbr, sna_txt, sud_cod, sud_nbr, cty_txt, plc_cod, zip_txt, cou_cod, lat_nbr, lon_nbr)
SELECT a."AddressId"::text, a."IND_IDN"::text, a."SNU_NBR", a."SNA_TXT", a."SUD_COD", a."SUD_NBR",
       a."CTY_TXT", a."PLC_COD", a."ZIP_TXT", a."COU_COD", a."LAT_NBR"::text, a."LON_NBR"::text
FROM sor."Address" a
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = a."IND_IDN"::text);

ANALYZE cleaned_new.individual;
ANALYZE cleaned_new.person;
ANALYZE cleaned_new.name;
ANALYZE cleaned_new.offense;
ANALYZE cleaned_new.address;
"""

SWAP_SQL = """BEGIN;
DROP SCHEMA IF EXISTS cleaned_old CASCADE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'cleaned') THEN
    ALTER SCHEMA cleaned RENAME TO cleaned_old;
  END IF;
END $$;
ALTER SCHEMA cleaned_new RENAME TO cleaned;
COMMIT;
DROP SCHEMA IF EXISTS cleaned_old CASCADE;"""


def psql_cmd(conn, *args):
    cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"] + list(args)
    if conn:
        cmd.append(conn)
    return cmd


def run_sql(conn, sql, label="psql"):
    r = subprocess.run(psql_cmd(conn, "-f", "-"), input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"{label} failed:\n{r.stderr.strip()}\nSQL was:\n{sql[:800]}")
    return r.stdout


def main():
    conn = sys.argv[1] if len(sys.argv) > 1 else None
    if not SCHEMA_SQL.exists():
        sys.exit(f"missing {SCHEMA_SQL}")

    run_sql(conn, 'SELECT 1 FROM sor."INDV" LIMIT 1;', "sanity check (is `sor` loaded?)")

    run_sql(conn, "DROP SCHEMA IF EXISTS cleaned_new CASCADE;")

    ddl = SCHEMA_SQL.read_text()
    ddl = ddl.replace("CREATE SCHEMA cleaned;", "CREATE SCHEMA cleaned_new;")
    ddl = re.sub(r"\bcleaned\.", "cleaned_new.", ddl)
    run_sql(conn, ddl, "building cleaned_new schema")

    run_sql(conn, POPULATE_SQL, "populating cleaned_new")

    print(run_sql(conn, """
        SELECT 'individual' AS table_name, count(*) FROM cleaned_new.individual
        UNION ALL SELECT 'person', count(*) FROM cleaned_new.person
        UNION ALL SELECT 'name', count(*) FROM cleaned_new.name
        UNION ALL SELECT 'address', count(*) FROM cleaned_new.address
        UNION ALL SELECT 'offense', count(*) FROM cleaned_new.offense;
    """))

    orphans = run_sql(conn, '''
        SELECT count(*) FROM sor."Address" a
        WHERE NOT EXISTS (
          SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = a."IND_IDN"::text
        );
    ''').strip()
    print(f"Address rows excluded from cleaned_new (no matching individual): {orphans}")

    # People DPS has told us to remove (see apply_removals.py) must not come back with a refresh.
    for _sch, tbl, n in apply_removals.reapply(conn, ["cleaned_new"]):
        print(f"removal ledger: deleted {n} from cleaned_new.{tbl}")

    run_sql(conn, SWAP_SQL, "swapping cleaned_new into cleaned")
    print("Done. Tables are in schema 'cleaned'.")


if __name__ == "__main__":
    main()
