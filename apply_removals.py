"""Apply a DPS removal notice (Texas CCP Ch. 62.251) to the local registry database.

Usage:
    python3 apply_removals.py NOTICE_FILE [connection] [--dry-run] [--max N]
    python3 apply_removals.py -           [connection] [--dry-run] [--max N]   # notice on stdin
    python3 apply_removals.py --reapply   [connection]

`NOTICE_FILE` is the DPS email: a Gmail "Download message" .eml file, or just the body as
plain text or HTML. `connection` is anything
psql accepts as a database argument (see load_registry_pg.py).

How it works
- Parses lines of the form `LAST,FIRST   YYYY-MM-DD   DPS_NUMBER` from the email.
  The DPS number (zero-padded to 8 digits) is the only key used; name and date of birth
  are used for a sanity warning and are never stored.
- Records the DPS numbers in a durable ledger, `removals.removed_individual`. The ledger
  lives outside `sor` and `cleaned` because both schemas are rebuilt from scratch on every
  refresh; without it a removed person would reappear the next time the loader runs.
- In one transaction, deletes every row for those people from schema `cleaned` and from
  schema `sor` (every table with a dps_nbr, ind_idn or per_idn column).
- `--dry-run` does all of the above and rolls back, printing what would be deleted.
- `--reapply` re-applies the whole ledger without a new notice. transform_to_cleaned.py
  calls the same code on `cleaned_new` before swapping it in, so cleaned never exposes
  a removed person; run `--reapply` after load_registry_pg.py to cover `sor`.
- Refuses to remove more than --max people (default 1000) from one notice, as a guard
  against a parsing mistake or a forged email.
"""
import email
import email.policy
import hashlib
import html
import re
import subprocess
import sys

RECORD_RE = re.compile(r"^\s*(?P<name>\S.*?)\s+(?P<dob>\d{4}-\d{2}-\d{2})\s+(?P<dps>\d{5,9})\s*$")
DEFAULT_MAX = 1000

# Column/table names differ in case between the raw `sor` export and `cleaned`.
SCHEMA_CONFIG = {
    "sor": dict(indv='"INDV"', person='"PERSON"', ind='"IND_IDN"', per='"PER_IDN"', dps='"DPS_NBR"'),
    "cleaned": dict(indv="individual", person="person", ind="ind_idn", per="per_idn", dps="dps_nbr"),
}
# Staging schema built by transform_to_cleaned.py has the same layout as `cleaned`.
SCHEMA_CONFIG["cleaned_new"] = SCHEMA_CONFIG["cleaned"]

LEDGER_DDL = """
CREATE SCHEMA IF NOT EXISTS removals;
CREATE TABLE IF NOT EXISTS removals.removed_individual (
  dps_nbr text PRIMARY KEY,
  notice_hash text,
  added_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS removals.notice (
  notice_hash text PRIMARY KEY,
  record_count integer NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
"""

# Placeholders: @SCH@ schema, @INDV@/@PERSON@ table names, @IND@/@PER@/@DPS@ quoted column names.
DELETE_SQL = """
CREATE TEMP TABLE _rm_ind_@SCH@ ON COMMIT DROP AS
  SELECT @IND@::text AS k FROM @SCH@.@INDV@
  WHERE lpad(btrim(@DPS@::text), 8, '0') IN (SELECT dps_nbr FROM removals.removed_individual);
CREATE TEMP TABLE _rm_per_@SCH@ ON COMMIT DROP AS
  SELECT @PER@::text AS k FROM @SCH@.@PERSON@ WHERE @IND@::text IN (SELECT k FROM _rm_ind_@SCH@);
DO $$
DECLARE
  sch text := '@SCH@';
  t record; c record; conds text[]; n bigint;
BEGIN
  FOR t IN
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = sch AND table_type = 'BASE TABLE' AND table_name NOT LIKE '\\_%'
    ORDER BY CASE WHEN lower(table_name) IN ('individual', 'indv') THEN 2
                  WHEN lower(table_name) = 'person' THEN 1 ELSE 0 END, table_name
  LOOP
    conds := ARRAY[]::text[];
    FOR c IN
      SELECT column_name FROM information_schema.columns
      WHERE table_schema = sch AND table_name = t.table_name
        AND lower(column_name) IN ('dps_nbr', 'ind_idn', 'per_idn')
    LOOP
      conds := conds || CASE lower(c.column_name)
        WHEN 'dps_nbr' THEN format('lpad(btrim(%I::text), 8, ''0'') IN (SELECT dps_nbr FROM removals.removed_individual)', c.column_name)
        WHEN 'ind_idn' THEN format('%I::text IN (SELECT k FROM _rm_ind_@SCH@)', c.column_name)
        ELSE format('%I::text IN (SELECT k FROM _rm_per_@SCH@)', c.column_name)
      END;
    END LOOP;
    CONTINUE WHEN cardinality(conds) = 0;
    EXECUTE format('DELETE FROM %I.%I WHERE %s', sch, t.table_name, array_to_string(conds, ' OR '));
    GET DIAGNOSTICS n = ROW_COUNT;
    INSERT INTO _rm_log VALUES (sch, t.table_name, n);
  END LOOP;
END $$;
"""


def psql_cmd(conn, *args):
    cmd = ["psql", "-X", "-q", "-A", "-t", "-F", "|", "-v", "ON_ERROR_STOP=1"] + list(args)
    if conn:
        cmd.append(conn)
    return cmd


def run_sql(conn, sql, label="psql"):
    r = subprocess.run(psql_cmd(conn, "-f", "-"), input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"{label} failed:\n{r.stderr.strip()}\nSQL was:\n{sql[:800]}")
    return r.stdout


def read_notice(data):
    """Return the notice text from raw bytes: a Gmail .eml download, or plain text/HTML as-is."""
    head = data[:20000]
    if not (re.match(rb"[A-Za-z-]+:", data) and re.search(rb"^(From|Subject|Content-Type):", head, re.M | re.I)):
        return data.decode("utf-8", errors="replace")
    msg = email.message_from_bytes(data, policy=email.policy.default)
    parts = [p for p in msg.walk() if p.get_content_type() in ("text/plain", "text/html")
             and p.get_content_disposition() != "attachment"]
    parts.sort(key=lambda p: p.get_content_type() != "text/plain")  # prefer plain text
    for p in parts:
        body = p.get_content()
        if parse_notice(body):
            return body
    return parts[0].get_content() if parts else ""


def parse_notice(text):
    """Return [(name, dob, dps_nbr)] with dps_nbr zero-padded to 8 digits, de-duplicated."""
    if re.search(r"<(br|p|div|table|tr)\b", text, re.I):
        text = html.unescape(re.sub(r"<[^>]+>", "\n", re.sub(r"<br\s*/?>", "\n", text, flags=re.I)))
    marker = re.search(r"Record\(s\):", text)
    if marker:
        text = text[marker.end():]
    seen, records = set(), []
    for line in text.splitlines():
        m = RECORD_RE.match(line)
        if not m:
            continue
        dps = m["dps"].zfill(8)
        if dps not in seen:
            seen.add(dps)
            records.append((m["name"].strip(), m["dob"], dps))
    return records


def notice_hash(records):
    return hashlib.sha256(",".join(sorted(r[2] for r in records)).encode()).hexdigest()


def existing_schemas(conn, wanted):
    out = run_sql(conn, "SELECT nspname FROM pg_namespace WHERE nspname IN (%s);"
                  % ",".join(f"'{s}'" for s in wanted))
    return [s for s in wanted if s in out.split()]


def ledger_exists(conn):
    return run_sql(conn, "SELECT to_regclass('removals.removed_individual') IS NOT NULL;").strip() == "t"


def build_apply_sql(schemas, dry_run):
    parts = ["BEGIN;", "CREATE TEMP TABLE _rm_log (schema_name text, table_name text, rows_deleted bigint) ON COMMIT DROP;"]
    for sch in schemas:
        sql = DELETE_SQL
        for token, value in dict(SCHEMA_CONFIG[sch], SCH=sch).items():
            sql = sql.replace(f"@{token.upper()}@", value)
        parts.append(sql)
    parts.append("SELECT schema_name, table_name, rows_deleted FROM _rm_log "
                 "WHERE rows_deleted > 0 ORDER BY schema_name, table_name;")
    parts.append("ROLLBACK;" if dry_run else "COMMIT;")
    return "\n".join(parts)


def apply_ledger(conn, schemas, dry_run=False, extra_sql=""):
    """Delete everyone in the ledger from `schemas`. Returns [(schema, table, rows)]."""
    schemas = existing_schemas(conn, schemas)
    if not schemas:
        return []
    sql = build_apply_sql(schemas, dry_run)
    if extra_sql:  # runs inside the same transaction, before the deletes
        sql = sql.replace("BEGIN;", "BEGIN;\n" + extra_sql, 1)
    out = run_sql(conn, sql, "applying removals")
    return [(a, b, int(c)) for a, b, c in (line.split("|") for line in out.splitlines() if "|" in line)]


def reapply(conn, schemas):
    """Re-apply the stored ledger to `schemas` (used by transform_to_cleaned.py on cleaned_new)."""
    if not ledger_exists(conn):
        return []
    return apply_ledger(conn, schemas)


def check_against_cleaned(conn, records):
    """Print which notice entries are present in `cleaned` and warn on surname mismatches."""
    if run_sql(conn, "SELECT to_regclass('cleaned.individual') IS NOT NULL;").strip() != "t":
        print("schema `cleaned` not found; skipping pre-check")
        return
    in_list = ",".join(f"'{r[2]}'" for r in records)
    out = run_sql(conn, f"""
        SELECT lpad(btrim(i.dps_nbr), 8, '0'), coalesce(string_agg(DISTINCT upper(n.lna_txt), ';'), '')
        FROM cleaned.individual i
        LEFT JOIN cleaned.person p ON p.ind_idn = i.ind_idn
        LEFT JOIN cleaned.name n ON n.per_idn = p.per_idn
        WHERE lpad(btrim(i.dps_nbr), 8, '0') IN ({in_list})
        GROUP BY 1;""")
    found = {}
    for line in out.splitlines():
        dps, _, surnames = line.partition("|")
        found[dps] = surnames.split(";")
    print(f"{len(found)} of {len(records)} people in the notice are in cleaned "
          f"(the rest were probably already dropped from a newer export)")
    for name, _dob, dps in records:
        if dps in found:
            surname = name.split(",")[0].strip().upper()
            if not any(surname.startswith(s) or s.startswith(surname) for s in found[dps] if s):
                print(f"  WARNING dps {dps}: notice says {surname!r}, database has {found[dps]} (still removed; DPS number is the key)")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    max_n = DEFAULT_MAX
    if "--max" in args:
        i = args.index("--max")
        max_n = int(args[i + 1])
        del args[i:i + 2]
    args = [a for a in args if a not in ("--dry-run", "--reapply")]
    if "--reapply" in sys.argv[1:]:
        conn = args[0] if args else None
        if not ledger_exists(conn):
            sys.exit("no ledger found (removals.removed_individual); nothing to reapply")
        rows = apply_ledger(conn, ["sor", "cleaned"], dry_run)
        for sch, tbl, n in rows:
            print(f"deleted {n:>5} from {sch}.{tbl}")
        print("Done." if rows else "Done. Nothing to remove; everyone in the ledger is already gone.")
        return
    if not args:
        print(__doc__)
        sys.exit(1)
    raw = sys.stdin.buffer.read() if args[0] == "-" else open(args[0], "rb").read()
    text = read_notice(raw)
    conn = args[1] if len(args) > 1 else None

    records = parse_notice(text)
    if not records:
        sys.exit("no records found in the notice; nothing done")
    if len(records) > max_n:
        sys.exit(f"notice lists {len(records)} people, above --max {max_n}; refusing. "
                 f"Check the parse (and that the email is genuine), then re-run with a higher --max.")
    print(f"parsed {len(records)} records from the notice")
    check_against_cleaned(conn, records)

    h = notice_hash(records)
    values = ",".join(f"('{r[2]}','{h}')" for r in records)  # dps is digits only (regex)
    ledger_sql = (LEDGER_DDL + f"INSERT INTO removals.removed_individual (dps_nbr, notice_hash) VALUES {values} "
                  f"ON CONFLICT DO NOTHING;\n"
                  f"INSERT INTO removals.notice (notice_hash, record_count) VALUES ('{h}', {len(records)}) "
                  f"ON CONFLICT DO NOTHING;\n")
    # Ledger DDL must exist before the temp tables reference it, so it goes inside the same transaction.
    rows = apply_ledger(conn, ["sor", "cleaned"], dry_run, extra_sql=ledger_sql)
    verb = "would delete" if dry_run else "deleted"
    for sch, tbl, n in rows:
        print(f"{verb} {n:>5} from {sch}.{tbl}")
    print("Dry run: rolled back, nothing changed." if dry_run else "Done. Ledger updated and rows removed.")


if __name__ == "__main__":
    main()
