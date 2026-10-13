# Local setup

This covers getting a full local copy of the pipeline running: raw export -> `sor` schema -> `cleaned` schema. Two stages, two owners:

1. **Raw load** (`load_registry_pg.py`, Roman) — loads the DPS export zip into schema `sor`.
2. **Cleaning transform** (`transform_to_cleaned.py`, Zach) — builds the `cleaned` schema from `sor`.

## Requirements

- macOS with [Homebrew](https://brew.sh)
- PostgreSQL 18 (matches the version `docs/database/schema.sql` was dumped from — an older major version will reject some of its `SET` options): `brew install postgresql@18 && brew services start postgresql@18`
- `psql` on your PATH:
  ```
  echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc
  source ~/.zshrc
  ```
- Python 3.8+ (standard library only, nothing to `pip install`)
- A free TxDPS Public Website account, to download the export zip from https://sor.dps.texas.gov (Download Registry)

## First-time setup

```
createdb sor
psql sor -f docs/database/schema.sql          # creates the `cleaned` schema
```

## Every refresh cycle (~every 2 weeks)

```
# 1. Raw load (Roman's loader) - replaces schema `sor` with the new export, zero downtime
python3 load_registry_pg.py 20261007_DATA-CURRENT.zip postgresql://localhost/sor

# 2. Cleaning transform - rebuilds schema `cleaned` from the latest `sor` data, zero downtime
python3 transform_to_cleaned.py postgresql://localhost/sor
```

## Verify

```
psql sor -c '\dt sor.*'
psql sor -c '\dt cleaned.*'
psql sor -c 'SELECT COUNT(*) FROM cleaned.individual'
psql sor -c 'SELECT COUNT(*) FROM cleaned.offense'
psql sor -c 'SELECT * FROM sor._load_info'
```

## Removing people per DPS removal notices

DPS periodically emails a list of people who must be removed from any registry copy we maintain (Texas Code of Criminal Procedure Ch. 62.251). That's a separate script (Kavan) keyed on `dps_nbr` — it should run against `cleaned.individual` (and ideally `sor` too, so a later re-run of the raw loader doesn't resurrect someone already removed) after each raw load.
