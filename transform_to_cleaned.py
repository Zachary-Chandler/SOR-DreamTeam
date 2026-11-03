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
    - the rest of the DPS table layout (birth dates, photos, registration events,
      education, licenses, occupations, code lookups) follows the same rule: rows
      whose parent is missing are left out and counted. See docs/database/LAYOUT.md.
- Prints raw vs cleaned row counts for every table, so nothing is dropped silently.
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

-- The rest of the DPS table layout (docs/database/LAYOUT.md). Same rule as address:
-- a row whose parent is missing is left out and counted in the report, never invented.
INSERT INTO cleaned_new.birth_date (dob_idn, per_idn, typ_cod, dob_dte)
SELECT b."DOB_IDN"::text, b."PER_IDN"::text, b."TYP_COD", b."DOB_DTE"
FROM sor."BRTHDATE" b
WHERE EXISTS (SELECT 1 FROM cleaned_new.person p WHERE p.per_idn = b."PER_IDN"::text);

INSERT INTO cleaned_new.individual_sor (ind_idn, dps_nbr, rsk_cod, ssz_cod, swd_cod, ert_cod, erd_dte, vrp_cod)
SELECT s."IND_IDN"::text, s."DPS_NBR", s."RSK_COD", s."SSZ_COD", s."SWD_COD", s."ERT_COD", s."ERD_DTE", s."VRP_COD"
FROM sor."INDV_SOR" s
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = s."IND_IDN"::text);

INSERT INTO cleaned_new.photo (photoid, ind_idn, pos_dte)
SELECT p."PhotoId"::text, p."IND_IDN"::text, p."POS_DTE"
FROM sor."Photo" p
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = p."IND_IDN"::text);

INSERT INTO cleaned_new.registration_event (eventid, ind_idn, evm_cod, evt_dte, evo_nbr, ori_txt)
SELECT r."EventId"::text, r."IND_IDN"::text, r."EVM_COD", r."EVT_DTE", r."EVO_NBR"::text, r."ORI_TXT"
FROM sor."RegistrationEvent" r
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual_sor s WHERE s.ind_idn = r."IND_IDN"::text);

-- A null AddressId is normal here (PDV_COD 'NON' = no address), so only a non-null
-- AddressId has to match.
INSERT INTO cleaned_new.address_event (addresseventid, eventid, ind_idn, pdv_cod, addressid)
SELECT e."AddressEventId"::text, e."EventId"::text, e."IND_IDN"::text, e."PDV_COD", e."AddressId"::text
FROM sor."AddressEvent" e
WHERE EXISTS (SELECT 1 FROM cleaned_new.registration_event r WHERE r.eventid = e."EventId"::text)
  AND (e."AddressId" IS NULL
       OR EXISTS (SELECT 1 FROM cleaned_new.address a WHERE a.addressid = e."AddressId"::text));

INSERT INTO cleaned_new.institute (instituteid, ins_cod, ins_txt)
SELECT "InstituteId"::text, "INS_COD", "INS_TXT" FROM sor."Institute";

INSERT INTO cleaned_new.institute_campus (campusid, instituteid, cam_txt)
SELECT c."CampusId"::text, c."InstituteId"::text, c."CAM_TXT"
FROM sor."InstituteCampus" c
WHERE EXISTS (SELECT 1 FROM cleaned_new.institute i WHERE i.instituteid = c."InstituteId"::text);

INSERT INTO cleaned_new.education (educationid, ind_idn, campusid, emp_flg, stu_flg, uin_txt, ucm_txt, uct_txt)
SELECT e."EducationId"::text, e."IND_IDN"::text, e."CampusId"::text, e."EMP_FLG", e."STU_FLG",
       e."UIN_TXT", e."UCM_TXT", e."UCT_TXT"
FROM sor."Education" e
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = e."IND_IDN"::text)
  AND (e."CampusId" IS NULL
       OR EXISTS (SELECT 1 FROM cleaned_new.institute_campus c WHERE c.campusid = e."CampusId"::text));

-- A null EducationId is normal here too (PDV_COD 'NON').
INSERT INTO cleaned_new.education_event (educationeventid, eventid, ind_idn, pdv_cod, educationid)
SELECT e."EducationEventId"::text, e."EventId"::text, e."IND_IDN"::text, e."PDV_COD", e."EducationId"::text
FROM sor."EducationEvent" e
WHERE EXISTS (SELECT 1 FROM cleaned_new.registration_event r WHERE r.eventid = e."EventId"::text)
  AND (e."EducationId" IS NULL
       OR EXISTS (SELECT 1 FROM cleaned_new.education d WHERE d.educationid = e."EducationId"::text));

-- Exact-duplicate-row dedup, as for offense.
INSERT INTO cleaned_new.off_code_sor
  (coo_cod, coj_cod, joo_cod, off_cod, ver_nbr, len_txt, sts_cod, cit_txt, begindate, enddate)
SELECT DISTINCT "COO_COD", "COJ_COD", "JOO_COD", "OFF_COD", "VER_NBR"::text, "LEN_TXT", "STS_COD",
       "CIT_TXT", "Begindate", "EndDate"
FROM sor."OFF_CODE_SOR";

INSERT INTO cleaned_new.table_codes (schemaname, tbl_cod, col_cod, val_cod, val_txt, fkref)
SELECT "SchemaName", "TBL_COD", "COL_COD", "VAL_COD", "VAL_TXT", "fkRef" FROM sor."TableCodes";

INSERT INTO cleaned_new.tbl (tbl_idn, tbl_cod, tbl_txt, inq_txt, upd_txt, batch_id)
SELECT "TBL_IDN"::text, "TBL_COD", "TBL_TXT", "INQ_TXT", "UPD_TXT", "BATCH_ID"::text FROM sor."TBL";

INSERT INTO cleaned_new.col (col_idn, tbl_idn, col_cod, col_txt, batch_id)
SELECT c."COL_IDN"::text, c."TBL_IDN"::text, c."COL_COD", c."COL_TXT", c."BATCH_ID"::text
FROM sor."COL" c
WHERE EXISTS (SELECT 1 FROM cleaned_new.tbl t WHERE t.tbl_idn = c."TBL_IDN"::text);

INSERT INTO cleaned_new.val (val_idn, col_idn, val_cod, val_txt, act_cod, lng_txt, app_cod, batch_id)
SELECT v."VAL_IDN"::text, v."COL_IDN"::text, v."VAL_COD", v."VAL_TXT", v."ACT_COD", v."LNG_TXT", v."APP_COD",
       v."BATCH_ID"::text
FROM sor."VAL" v
WHERE EXISTS (SELECT 1 FROM cleaned_new.col c WHERE c.col_idn = v."COL_IDN"::text);

INSERT INTO cleaned_new.val_reln (vlr_idn, val_idn, var_idn, cmb_cod, batch_id)
SELECT "VLR_IDN"::text, "VAL_IDN"::text, "VAR_IDN"::text, "CMB_COD", "BATCH_ID"::text FROM sor."VAL_RELN";

INSERT INTO cleaned_new.place_codes (plt_cod, plc_cod, plc_txt)
SELECT "PLT_COD", "PLC_COD", "PLC_TXT" FROM sor."PlaceCodes";
"""

# Layout tables the current DPS export has no data for. Each runs only when its source
# table exists in `sor`, so they fill in on their own if DPS starts shipping them.
# (source table in sor, insert)
OPTIONAL_POPULATE = [
    ("PlaceCodeTypes", """
INSERT INTO cleaned_new.place_code_types (plt_cod, plt_txt)
SELECT "PLT_COD", "PLT_TXT" FROM sor."PlaceCodeTypes";"""),
    ("OccupationalLicenseIssuers", """
INSERT INTO cleaned_new.license_issuers (occupationallicenseissuersid, oli_txt)
SELECT "OccupationalLicenseIssuersId"::text, "OLI_TXT" FROM sor."OccupationalLicenseIssuers";"""),
    ("OccupationalLicense", """
INSERT INTO cleaned_new.license (licenseid, ind_idn, occupationallicenselicensesid)
SELECT l."LicenseId"::text, l."IND_IDN"::text, l."OccupationalLicenseLicensesId"::text
FROM sor."OccupationalLicense" l
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = l."IND_IDN"::text);"""),
    ("OccupationalLicenseEvent", """
INSERT INTO cleaned_new.license_event (licenseeventid, eventid, ind_idn, pdv_cod, licenseid)
SELECT e."LicenseEventId"::text, e."EventId"::text, e."IND_IDN"::text, e."PDV_COD", e."LicenseId"::text
FROM sor."OccupationalLicenseEvent" e
WHERE EXISTS (SELECT 1 FROM cleaned_new.registration_event r WHERE r.eventid = e."EventId"::text)
  AND (e."LicenseId" IS NULL
       OR EXISTS (SELECT 1 FROM cleaned_new.license l WHERE l.licenseid = e."LicenseId"::text));"""),
    ("Occupation", """
INSERT INTO cleaned_new.occupation
  (occupationid, ind_idn, emp_txt, snu_nbr, sna_txt, cty_txt, sta_cod, zip_txt, occ_txt, occ_cod)
SELECT o."OccupationId"::text, o."IND_IDN"::text, o."EMP_TXT", o."SNU_NBR", o."SNA_TXT", o."CTY_TXT",
       o."STA_COD", o."ZIP_TXT", o."OCC_TXT", o."OCC_COD"
FROM sor."Occupation" o
WHERE EXISTS (SELECT 1 FROM cleaned_new.individual i WHERE i.ind_idn = o."IND_IDN"::text);"""),
    ("OccupationEvent", """
INSERT INTO cleaned_new.occupation_event (occupationeventid, eventid, ind_idn, pdv_cod, occupationid)
SELECT e."OccupationEventId"::text, e."EventId"::text, e."IND_IDN"::text, e."PDV_COD", e."OccupationId"::text
FROM sor."OccupationEvent" e
WHERE EXISTS (SELECT 1 FROM cleaned_new.registration_event r WHERE r.eventid = e."EventId"::text)
  AND (e."OccupationId" IS NULL
       OR EXISTS (SELECT 1 FROM cleaned_new.occupation o WHERE o.occupationid = e."OccupationId"::text));"""),
]

# Every cleaned table and the raw table it comes from, for the row-count report.
TABLE_SOURCES = [
    ("individual", "INDV"), ("person", "PERSON"), ("name", "NAME"), ("birth_date", "BRTHDATE"),
    ("individual_sor", "INDV_SOR"), ("photo", "Photo"), ("offense", "Offense"),
    ("off_code_sor", "OFF_CODE_SOR"), ("registration_event", "RegistrationEvent"),
    ("address", "Address"), ("address_event", "AddressEvent"),
    ("education", "Education"), ("education_event", "EducationEvent"),
    ("institute_campus", "InstituteCampus"), ("institute", "Institute"),
    ("license", "OccupationalLicense"), ("license_event", "OccupationalLicenseEvent"),
    ("license_issuers", "OccupationalLicenseIssuers"),
    ("occupation", "Occupation"), ("occupation_event", "OccupationEvent"),
    ("table_codes", "TableCodes"), ("col", "COL"), ("tbl", "TBL"), ("val", "VAL"), ("val_reln", "VAL_RELN"),
    ("place_code_types", "PlaceCodeTypes"), ("place_codes", "PlaceCodes"),
]

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


def run_sql(conn, sql, label="psql", rows=False):
    """Run sql; with rows=True, return bare `a|b|c` lines instead of psql's table format."""
    args = ["-A", "-t", "-f", "-"] if rows else ["-f", "-"]
    r = subprocess.run(psql_cmd(conn, *args), input=sql, capture_output=True, text=True)
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

    sor_tables = set(run_sql(conn, "SELECT table_name FROM information_schema.tables "
                                   "WHERE table_schema = 'sor';", "listing sor tables", rows=True).split())
    for source, sql in OPTIONAL_POPULATE:
        if source in sor_tables:
            run_sql(conn, sql, f"populating from sor.{source}")
    run_sql(conn, "".join(f"ANALYZE cleaned_new.{t};\n" for t, _ in TABLE_SOURCES))

    # Raw vs cleaned row counts. A gap is either exact-duplicate dedup (offense,
    # off_code_sor) or rows left out because their parent row is missing.
    counts = " UNION ALL ".join(
        f"SELECT '{t}', (SELECT count(*) FROM cleaned_new.{t}), "
        + (f'(SELECT count(*) FROM sor."{s}")' if s in sor_tables else "NULL")
        for t, s in TABLE_SOURCES)
    print(f"{'table':<20} {'raw':>8} {'cleaned':>8}  note")
    for line in run_sql(conn, counts + ";", "counting rows", rows=True).splitlines():
        if not line.strip():
            continue
        t, n_clean, n_raw = (x.strip() for x in line.split("|"))
        if not n_raw:
            note = "no source table in this export"
        elif n_raw == n_clean:
            note = ""
        else:
            note = f"{int(n_raw) - int(n_clean)} left out (duplicate or missing parent)"
        print(f"{t:<20} {n_raw or '-':>8} {n_clean:>8}  {note}")

    # People DPS has told us to remove (see apply_removals.py) must not come back with a refresh.
    for _sch, tbl, n in apply_removals.reapply(conn, ["cleaned_new"]):
        print(f"removal ledger: deleted {n} from cleaned_new.{tbl}")

    run_sql(conn, SWAP_SQL, "swapping cleaned_new into cleaned")
    print("Done. Tables are in schema 'cleaned'.")


if __name__ == "__main__":
    main()
