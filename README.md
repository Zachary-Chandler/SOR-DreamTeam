# Texas Sex Offender Registry: Local Postgres Loader

Loads the Texas Department of Public Safety (DPS) public sex offender registry bulk export into a local PostgreSQL database. A full load of the 2026-10-07 export (about 108,000 registrants) takes about 10 seconds.

## Read this first

- **Do not commit the registry data.** Each person downloads it themselves from DPS. The `.gitignore` in this repo excludes zip and database files; keep it that way.
- Texas law restricts how registry information may be used, including a ban on using it to commit a crime or harass registrants. Read the terms you accept when you create your DPS account before sharing or republishing anything.
- Not every registrant is in the public data. DPS says only fingerprint verification positively links a person to a record, and it disclaims responsibility for errors in secondary dissemination. The export changes twice a week, so keep the download date with the data.

## Requirements

- PostgreSQL 16 or later (Postgres.app or Homebrew on a Mac)
- The `psql` command-line client on your PATH (the loader calls it)
- Python 3.8 or later (standard library only; nothing to install)
- A free TxDPS Public Website account to download the export

## Setup

1. **Download the export** from https://sor.dps.texas.gov (Download Registry). You get a zip like `20261007_DATA-CURRENT.zip`. Leave it zipped.
2. **Install PostgreSQL.** Postgres.app (postgresapp.com): move it to Applications, open it, click Initialize. Or with Homebrew: `brew install postgresql@16` then `brew services start postgresql@16`.
3. **Put `psql` on your PATH** (Postgres.app example):
   ```
   echo 'export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   psql --version
   ```
4. **Create the database:**
   ```
   createdb sor
   ```
5. **Run the loader:**
   ```
   python3 load_registry_pg.py 20261007_DATA-CURRENT.zip postgresql://localhost/sor
   ```

The loader prints one line per table. Re-running it with a newer export replaces the data without downtime: it builds a new schema, then swaps it in within one transaction.

## Verify

```
psql sor -c '\dt sor.*'
psql sor -c 'SELECT count(*) FROM sor."PERSON"'
psql sor -c 'SELECT * FROM sor._load_info'
```

Always write `sor."TableName"` with double quotes and exact capitalization. Tables live in the schema `sor`, not `public`. For the 2026-10-07 export expect about 30 tables, 108,280 rows in `PERSON` and 161,562 in `Offense`.

## How the loader works

- Reads the tab-delimited `.txt` files straight from the zip.
- Takes column names and types from the `SqlBcpFormatFiles/*.xml` files in the zip.
- Removes NUL bytes from rows (Postgres text cannot store them) and reports how many rows it changed.
- Stores a column as text, with a `WARNING`, if any of its values do not fit the type DPS declares for it.
- Skips macOS junk files and the two nested zips (documentation and social-network data).
- Indexes every column whose name ends in `id`, and writes a `_load_info` table with the source zip name and load time.

## Known open checks

- NUL bytes appear in a very large share of rows in some tables (for example 112,717 of 161,562 `Offense` rows). If NUL is used as a real value, such as a flag, stripping it turns a 0 into a blank. Not yet verified.
- 18 rows in `OFF_CODE_SOR` have a date in `VER_NBR`, which DPS declares as an integer, so that column is stored as text. Check that those rows are not shifted.
- `OFF_CODE_SOR.txt` has 8,219 lines but 8,213 rows load; the 6 skipped lines have not been inspected.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `command not found: createdb` or `psql` | Postgres tools are not on your PATH; redo setup step 3 |
| `could not connect to server` | Start the server in Postgres.app |
| `relation "sor.PERSON" does not exist` | Add the double quotes, and confirm the loader printed `Done` |
| `extra data after last expected column` | You have an old copy of the loader; use the current one (it strips NUL bytes) |

A failed run leaves a half-built schema `sor_new`; the next run drops it automatically.

## Next steps

Map the table relationships and build a joined view with one record per registrant, then a read-only API on top of that view. Decide what the site is for and who uses it before building anything public.
