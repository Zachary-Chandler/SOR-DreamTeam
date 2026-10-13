"""Load the Texas DPS public sex offender registry export zip into PostgreSQL.

Usage:
    python load_registry_pg.py path/to/20261007_DATA-CURRENT.zip [connection]

`connection` is anything psql accepts as a database argument, for example:
    postgresql://user:password@localhost:5432/sor
    "host=localhost dbname=sor user=me"
If omitted, psql's defaults and the standard PG* environment variables
(PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE) are used.

Requirements: Python 3.8+ (standard library only) and the `psql` command-line
client on your PATH (installed with Postgres). The target database must already exist.

How it works
- Reads tab-delimited .txt files straight from the zip.
- Column names and types come from the SqlBcpFormatFiles/*.xml files in the zip.
- Loads everything into a fresh schema `sor_new` using \\copy, then, in one
  transaction, renames it to `sor` (the old `sor` becomes `sor_old` and is dropped).
  Your app always sees either the complete old data or the complete new data.
- Re-run with each new twice-weekly export to refresh.
"""
import csv
import io
import posixpath
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

PG_TYPES = {
    "SQLINT": "integer",
    "SQLBIGINT": "bigint",
    "SQLSMALLINT": "smallint",
    "SQLTINYINT": "smallint",
    "SQLBIT": "smallint",
    "SQLFLT4": "real",
    "SQLFLT8": "double precision",
    "SQLDECIMAL": "numeric",
    "SQLNUMERIC": "numeric",
    "SQLMONEY": "numeric",
    "SQLMONEY4": "numeric",
    "SQLDATETIME": "timestamp",
    "SQLDATETIME2": "timestamp",
    "SQLSMALLDATETIME": "timestamp",
    "SQLDATE": "timestamp",
}
INT_KINDS = {"integer", "bigint", "smallint"}
FLOAT_KINDS = {"real", "double precision", "numeric"}


def psql_cmd(conn, *args):
    cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"] + list(args)
    if conn:
        cmd.append(conn)
    return cmd


def run_sql(conn, sql):
    r = subprocess.run(psql_cmd(conn, "-c", sql), capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"psql failed:\n{r.stderr.strip()}\nSQL was:\n{sql[:500]}")
    return r.stdout


def clean_name(name):
    return re.sub(r"\W", "_", name)


def parse_format(xml_bytes):
    """Return list of (zero_based_field_index, column_name, pg_type)."""
    root = ET.fromstring(xml_bytes)
    cols = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "COLUMN":
            src = int(el.attrib["SOURCE"]) - 1
            pg = PG_TYPES.get(el.attrib.get(XSI_TYPE, "").upper(), "text")
            cols.append((src, el.attrib["NAME"], pg))
    return cols


def decode(line):
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        return line.decode("cp1252", errors="replace")


def convert(value, pg_type):
    """Return a CSV-ready value; None becomes NULL."""
    if value == "":
        return None
    try:
        if pg_type in INT_KINDS:
            low = value.lower()
            if low in ("true", "false"):
                return 1 if low == "true" else 0
            return int(value)
        if pg_type in FLOAT_KINDS:
            float(value)  # validate only; keep original text for numeric precision
            return value
        if pg_type == "timestamp":
            # SQL Server writes 7 fractional digits; Postgres keeps 6.
            m = re.match(r"^(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?)(\.\d+)?$", value)
            if not m:
                raise ValueError("unrecognized timestamp")
            return m.group(1) + (m.group(2)[:7] if m.group(2) else "")
    except ValueError:
        raise
    return value


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    zip_path = sys.argv[1]
    conn = sys.argv[2] if len(sys.argv) > 2 else None
    start = time.time()

    run_sql(conn, "SELECT 1")  # fail fast if psql/connection is wrong
    run_sql(conn, "DROP SCHEMA IF EXISTS sor_new CASCADE; CREATE SCHEMA sor_new;")

    with zipfile.ZipFile(zip_path) as z:
        formats, data_files = {}, []
        for n in z.namelist():
            if n.startswith("__MACOSX") or n.endswith("/"):
                continue
            base = posixpath.basename(n)
            if base.startswith("._"):
                continue
            stem, ext = posixpath.splitext(base)
            parent = posixpath.basename(posixpath.dirname(n))
            if ext.lower() == ".xml" and parent == "SqlBcpFormatFiles":
                formats[stem.lower()] = n
            elif ext.lower() == ".txt" and "Documentation" not in n:
                data_files.append((stem, n))

        loaded = []
        for stem, n in sorted(data_files):
            fmt = formats.get(stem.lower())
            if not fmt:
                print(f"skip {n}: no matching format file")
                continue
            cols = parse_format(z.read(fmt))
            if not cols:
                print(f"skip {n}: format file has no columns")
                continue
            table = clean_name(stem)
            col_names = [clean_name(c[1]) for c in cols]
            # Pass 1: read every row (files are small enough to hold in memory).
            rows_raw, nul_fixed = [], 0
            with z.open(n) as f:
                for raw in f:
                    line = decode(raw).rstrip("\r\n")
                    if "\x00" in line:
                        # Postgres text cannot contain NUL; psql would truncate the row.
                        line = line.replace("\x00", "")
                        nul_fixed += 1
                    if not line:
                        continue
                    parts = line.split("\t")
                    rows_raw.append([parts[src] if src < len(parts) else "" for (src, _c, _t) in cols])

            # Check each typed column; any column with values that don't fit becomes text.
            col_types = [c[2] for c in cols]
            for ci, (src, cname, pgt) in enumerate(cols):
                if pgt == "text":
                    continue
                bad = 0
                first_bad = None
                for ri, r in enumerate(rows_raw):
                    try:
                        convert(r[ci], pgt)
                    except ValueError:
                        bad += 1
                        if first_bad is None:
                            first_bad = (ri + 1, r[ci])
                if bad:
                    col_types[ci] = "text"
                    print(f"  WARNING {table}.{cname}: {bad} value(s) don't fit {pgt} "
                          f"(first: row {first_bad[0]}, {first_bad[1]!r}); stored as text instead")

            ddl = ", ".join(f'"{cn}" {t}' for cn, t in zip(col_names, col_types))
            run_sql(conn, f'CREATE TABLE sor_new."{table}" ({ddl})')

            copy_sql = f'\\copy sor_new."{table}" from stdin with (format csv)'
            p = subprocess.Popen(
                psql_cmd(conn, "-c", copy_sql),
                stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            out = io.TextIOWrapper(p.stdin, encoding="utf-8", newline="")
            w = csv.writer(out, lineterminator="\n")
            count = 0
            try:
                for r in rows_raw:
                    w.writerow([
                        convert(v, t) if t == c[2] else (v if v != "" else None)
                        for v, t, c in zip(r, col_types, cols)
                    ])
                    count += 1
                out.close()
            except BrokenPipeError:
                pass
            err = p.stderr.read().decode("utf-8", errors="replace")
            if p.wait() != 0:
                sys.exit(f"psql \\copy failed for {table}:\n{err.strip()}")

            for cn in col_names:
                if cn.lower().endswith("id"):
                    run_sql(conn, f'CREATE INDEX "ix_{table}_{cn}" ON sor_new."{table}" ("{cn}")')
            loaded.append((table, count))
            note = f"  (removed NUL bytes from {nul_fixed} rows)" if nul_fixed else ""
            print(f"loaded {table}: {count:,} rows, {len(cols)} columns{note}")

    src_name = posixpath.basename(zip_path).replace("'", "''")
    run_sql(
        conn,
        "CREATE TABLE sor_new._load_info (source_zip text, loaded_at timestamptz DEFAULT now());"
        f"INSERT INTO sor_new._load_info (source_zip) VALUES ('{src_name}');"
        "ANALYZE;",
    )
    run_sql(
        conn,
        """BEGIN;
DROP SCHEMA IF EXISTS sor_old CASCADE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'sor') THEN
    ALTER SCHEMA sor RENAME TO sor_old;
  END IF;
END $$;
ALTER SCHEMA sor_new RENAME TO sor;
COMMIT;
DROP SCHEMA IF EXISTS sor_old CASCADE;""",
    )
    print(f"\nDone in {time.time() - start:.0f}s. Tables are in schema 'sor' (e.g. SELECT * FROM sor.\"PERSON\" LIMIT 5;)")


if __name__ == "__main__":
    main()
