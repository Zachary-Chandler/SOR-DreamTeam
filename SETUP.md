# Local setup

This covers getting a full local copy of the pipeline running: raw export -> `sor` schema -> `cleaned` schema, with DPS removal notices applied to both. Three scripts, three owners:

1. **Raw load** (`load_registry_pg.py`, Roman) — loads the DPS export zip into schema `sor`.
2. **Cleaning transform** (`transform_to_cleaned.py`, Zach) — builds the `cleaned` schema from `sor`.
3. **Removal notices** (`apply_removals.py`, Kavan) — deletes people DPS says must be removed, and keeps a ledger so they stay removed. How it works: `docs/database/REMOVALS.md`.

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

# 2. Cleaning transform - rebuilds schema `cleaned` from the latest `sor` data, zero downtime.
#    Also re-applies the removal ledger, so removed people never come back into `cleaned`.
python3 transform_to_cleaned.py postgresql://localhost/sor

# 3. Re-apply the removal ledger to `sor` (step 1 rebuilt it from the export)
python3 apply_removals.py --reapply postgresql://localhost/sor
```

Step 3 prints `no ledger found` until the first removal notice has been applied; that's fine.

## Verify

```
psql sor -c '\dt sor.*'
psql sor -c '\dt cleaned.*'
psql sor -c 'SELECT COUNT(*) FROM cleaned.individual'
psql sor -c 'SELECT COUNT(*) FROM cleaned.offense'
psql sor -c 'SELECT * FROM sor._load_info'
psql sor -c 'SELECT count(*) FROM removals.removed_individual'   # after the first removal notice
psql sor -c 'SELECT * FROM removals.notice ORDER BY applied_at'
```

Tests (no database needed): `python3 -m unittest discover tests`

## Removing people per DPS removal notices

DPS emails a list of people who must be removed from any registry copy we maintain (Texas Code of Criminal Procedure Ch. 62.251). The email comes from `TxSOR@dps.texas.gov` with the subject "Removal from Texas Sex Offender Registry". Apply each one as soon as it arrives; don't wait for the next refresh.

1. Download the email from Gmail (⋮ → Download message, gives a `.eml`) to somewhere **outside the repo**, such as `~/Downloads`. It lists real names and dates of birth; `.gitignore` excludes `*.eml` as a backstop. Saving just the body as a `.txt` also works.
2. Preview, then apply:

```
python3 apply_removals.py ~/Downloads/notice.eml postgresql://localhost/sor --dry-run   # preview, changes nothing
python3 apply_removals.py ~/Downloads/notice.eml postgresql://localhost/sor             # apply
```

3. Check the output. Expect `N of M people in the notice are in cleaned`, where N is usually lower than M (people already gone from the export). A `WARNING ... notice says ...` line means the surname in the email doesn't match the database for that DPS number. The person is still removed; glance at it in case the email is wrong.
4. Delete the `.eml` once it's applied, or keep it somewhere private if the team needs a paper trail.

- Keyed on `dps_nbr` only (zero-padded to 8 digits). Names and dates of birth in the email are used for a warning on mismatch and are never stored.
- Deletes from `cleaned` and `sor` in one transaction, and records the DPS numbers in a ledger, `removals.removed_individual`, which lives outside both rebuilt schemas.
- `transform_to_cleaned.py` re-applies the ledger to `cleaned_new` before the swap, so a refresh never brings a removed person back into `cleaned`. After each raw load, run `python3 apply_removals.py --reapply postgresql://localhost/sor` to clear them from `sor` as well.
- Safe to re-run with the same notice. Refuses a notice listing more than 1000 people (`--max N` to override).
- Tests: `python3 -m unittest discover tests`.
- Anything outside this database that holds registry data (exports, a deployed copy for the API) needs the same notice applied there too.
