# Raw-to-cleaned transform

What `transform_to_cleaned.py` does, why it's built the way it is, and how it was verified. Companion to `Database_Documentation.pdf` (which describes the `cleaned` schema itself) and the root `SETUP.md` (which covers running the whole pipeline).

## Where this fits

```
Texas SOR export (.zip, downloaded manually from sor.dps.texas.gov)
        |
        v
load_registry_pg.py   -->  schema `sor`      (raw, one table per source .txt file)
        |
        v
transform_to_cleaned.py -->  schema `cleaned`  (the relational model in schema.sql)
        |
        v
        Myles's API / UI
```

`sor` and `cleaned` are different schemas in the same `sor` database. Nothing downstream should ever query `sor` directly — it's a faithful dump of DPS's raw files, not a relational model (no foreign keys, duplicate IDs, inconsistent types). `cleaned` is what the application is built on.

## Column mapping

The raw export's column names turned out to be the literal source of the `cleaned` schema's column names (just upper- vs lowercase) — confirmed by reading the `SqlBcpFormatFiles/*.xml` inside the export zip, which is where `load_registry_pg.py` gets its column names and types from:

| `cleaned` table | raw table (`sor` schema) | notes |
|---|---|---|
| `individual` | `"INDV"` | 1:1, `IND_IDN` -> `ind_idn`, `DPS_NBR` -> `dps_nbr` |
| `person` | `"PERSON"` | 1:1, 9 columns each side |
| `name` | `"NAME"` | 1:1, 6 columns each side |
| `address` | `"Address"` | 1:1 column-wise, but see "Orphaned addresses" below |
| `offense` | `"Offense"` | deduplicated, see "Offense dedup" below |

All raw numeric/date columns are cast to `text` on the way into `cleaned`, matching how the existing `cleaned` schema declares those columns (per `Database_Documentation.pdf`: "Other listed cleaned source columns were observed as text... further typed conversions are optional future work").

## Offense dedup

`cleaned.offense` has a surrogate primary key (`offense_record_id`, an identity column) instead of using the raw `OffenseId`, because `OffenseId` is not unique — some rows share an `OffenseId` but differ in other fields (e.g. `aov_nbr`, `sov_cod`).

The transform's dedup rule is `SELECT DISTINCT` across every real column of `sor."Offense"`: only rows that are *exact* duplicates (every field identical) are collapsed. On the 2026-09-16 export this removed 17 rows (161,351 raw rows -> 161,334 cleaned rows), which matches the dedup count in `Database_Documentation.pdf` from the original Oct 3 development run — strong evidence this is the same rule that produced the documented schema.

## Orphaned addresses

A small number of `sor."Address"` rows reference an `IND_IDN` that doesn't exist in `sor."INDV"`. Since `cleaned.address.ind_idn` has a `FOREIGN KEY` constraint against `cleaned.individual`, these rows can't be inserted without either fabricating a fake individual or dropping the row.

Per the explicit guidance in `Database_Documentation.pdf` ("Do not silently invent an individual or discard the raw record"), the transform **excludes** these rows from `cleaned.address` but **prints a count** of how many were excluded every time it runs, so it's never a silent loss. On the 2026-09-16 export this was exactly 1 row — consistent with the "1 raw address row without a corresponding individual" the PDF documented. This is still an open decision for the team (does that address get surfaced some other way? Is the raw `sor` copy sufficient as the audit trail?) — the script doesn't try to resolve it, just makes sure it stays visible.

## Zero-downtime refresh

The transform builds a complete new copy of the schema under the name `cleaned_new` (DDL replayed from `docs/database/schema.sql`, so that file stays the single source of truth for the schema), populates it fully, then does the rename swap in one transaction:

```
cleaned -> cleaned_old (dropped)
cleaned_new -> cleaned
```

This mirrors the pattern `load_registry_pg.py` already uses for `sor`/`sor_new`/`sor_old`. The practical effect: anything querying `cleaned` (the API, a `psql` session, etc.) always sees either the complete previous dataset or the complete new one — never a half-populated table mid-refresh. Safe to re-run after every `load_registry_pg.py` run, per the biweekly cadence in `SETUP.md`.

## A loader bug found while testing this

While running `load_registry_pg.py` against a real export for the first time, it crashed with `relation "AGENCY" already exists`. Cause: the export zip ships the social-network dataset **twice** — once correctly as a nested `.zip` (which the loader already skips), and once as a literal unzipped duplicate folder (`20240327_DATA-SOCIAL/...txt`) sitting alongside the real data. The loader matched files by filename stem only, so it tried to load `AGENCY.txt` (and every other shared filename) twice.

Fixed in `load_registry_pg.py` by skipping any zip entry whose path contains `DATA-SOCIAL`, in addition to the existing nested-zip skip. Doesn't affect any of the 5 tables the `cleaned` transform reads from (none of them exist inside the social-data folder), but it blocked the loader from completing at all.

## Verification

Run against the real 2026-09-16 export (`20260916_DATA-CURRENT.zip`):

| check | result |
|---|---|
| `cleaned.individual` rows | 108,345 |
| `cleaned.person` rows | 108,159 |
| `cleaned.name` rows | 396,570 |
| `cleaned.offense` rows | 161,334 (17 exact duplicates removed from 161,351 raw) |
| `cleaned.address` rows | 107,804 (1 orphaned row excluded, reported) |
| All 9 documented PK/FK constraints present | yes |
| All 3 views (`individual_search`, `offense_summary`, `search_results`) build and query correctly | yes |

The offense-dedup count (17) and orphaned-address count (1) both match the numbers in `Database_Documentation.pdf` from the original by-hand development run, which is a good sign this transform reproduces the same cleaning logic rather than a different one that happens to also work.

## Known gap (not yet solved here)

This transform handles a one-time or one-off refresh. It does not yet handle the DPS removal-notice emails (Texas Code of Criminal Procedure Ch. 62.251) — people who must be deleted from `cleaned` (and ideally `sor`) outside the normal biweekly cycle. That's a separate script; see `SETUP.md`.
