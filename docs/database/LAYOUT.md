# `cleaned` schema vs the DPS table layout

The project sponsor wants the database to follow DPS's own table layout: `Documentation/Layout.pdf` inside the export zip. This file maps every box in that diagram to a table in schema `cleaned`, and lists the places where the data doesn't allow an exact match. The DDL is in `schema.sql`; `transform_to_cleaned.py` fills it.

## Table mapping

Table names are lowercase with underscores, like the original five `cleaned` tables. Column names are the raw DPS names in lowercase (`IND_IDN` -> `ind_idn`). IDs and codes are `text`; dates are `timestamp`.

| Layout box | `cleaned` table | Key | Links to (foreign key) |
|---|---|---|---|
| INDV | `individual` | `ind_idn` | |
| PERSON | `person` | `per_idn` | `individual` |
| NAME | `name` | `nam_idn` | `person` |
| BRTHDATE | `birth_date` | `dob_idn` | `person` |
| INDV_SOR | `individual_sor` | `ind_idn` | `individual` |
| Photo | `photo` | `photoid` | `individual` |
| Offense | `offense` | `offense_record_id` (surrogate) | `individual` |
| OFF_CODE_SOR | `off_code_sor` | `off_code_record_id` (surrogate) | none, see below |
| RegistrationEvent | `registration_event` | `eventid` | `individual_sor` |
| AddressEvent | `address_event` | `addresseventid` | `registration_event`, `address` |
| Address | `address` | `addressid` | `individual` |
| EducationEvent | `education_event` | `educationeventid` | `registration_event`, `education` |
| Education | `education` | `educationid` | `individual`, `institute_campus` |
| InstituteCampus | `institute_campus` | `campusid` | `institute` |
| Institute | `institute` | `instituteid` | |
| LicenseEvent | `license_event` | `licenseeventid` | `registration_event`, `license` |
| License | `license` | `licenseid` | `individual` |
| LicenseIssuers | `license_issuers` | `occupationallicenseissuersid` | |
| OccupationEvent | `occupation_event` | `occupationeventid` | `registration_event`, `occupation` |
| Occupation | `occupation` | `occupationid` | `individual` |
| TableCodes | `table_codes` | (`schemaname`, `tbl_cod`, `col_cod`, `val_cod`) | |
| COL / TBL / VAL / VAL_RELN | `col` / `tbl` / `val` / `val_reln` | `col_idn` / `tbl_idn` / `val_idn` / `vlr_idn` | `col` -> `tbl`, `val` -> `col` |
| PlaceCodeTypes / PlaceCodes | `place_code_types` / `place_codes` | `plt_cod` / (`plt_cod`, `plc_cod`) | |

The diagram's notes still apply: use `typ_cod = 'B'` in `name` and `birth_date` for the primary name and birth date, and `pdv_cod = 'VAL'` in the event tables marks a normal record (other values are described in `table_codes`).

The views the API uses (`individual_search`, `offense_summary`, `search_results`) are unchanged.

## Where it doesn't match exactly

- **License and occupation tables are empty.** The current export ships format files for them but no data. `transform_to_cleaned.py` fills them automatically if the source tables ever show up in `sor`. The old 2024 social-data folder in the zip has license data, but it is 2.5 years old and the loader skips it on purpose.
- **License -> LicenseIssuers has no direct key.** The diagram shows `ISS_COD`, but DPS's real columns go License -> OccupationalLicenseLicenses -> OccupationalLicenseCategories -> Issuers. Those two middle tables aren't in the layout, so `license` keeps `occupationallicenselicensesid` with no foreign key.
- **`place_code_types` is empty.** It isn't in the export, so `place_codes` has no foreign key to it.
- **Offense -> OFF_CODE_SOR has no foreign key.** `OFF_CODE_SOR` has 15 exact duplicate rows (removed) and some null code parts, and 3 offenses use codes it doesn't contain. Join on `coo_cod, coj_cod, joo_cod, off_cod, ver_nbr` (indexed).
- **`val_reln` has no foreign keys.** 102 of its references point at `VAL` rows DPS no longer ships. It's a lookup table, so all rows are kept.
- **The Photo <- Offense arrow** in the diagram has no shared column besides `ind_idn`, so both just link to `individual`.

## Open questions for the sponsor

Defaults above were chosen so nothing is blocked; these answers would only change details.

1. Where does the License and Occupation data come from? It isn't in the DPS export we download.
2. Is it OK that the links DPS's own data doesn't support (offense codes, license issuers, photo/offense) are joins rather than enforced foreign keys?
3. Are lowercase table names (`registration_event`) fine, or should they match the diagram exactly (`RegistrationEvent`)?
4. Should the 8 rows that point at people missing from `INDV` be surfaced somewhere, or is keeping them in `sor` enough?

## Rows left out

Same rule as the original address handling: a row whose parent is missing is left out of `cleaned` and counted in the transform's report, never invented. The raw row stays in `sor`. On the 2026-09-16 export:

| table | left out | why |
|---|---|---|
| `individual_sor` | 3 | `IND_IDN` not in `INDV` |
| `photo` | 2 | `IND_IDN` not in `INDV` |
| `registration_event` | 1 | belongs to one of the 3 above |
| `address_event`, `education_event` | 1 each | belong to that registration event |
| `address` | 1 | `IND_IDN` not in `INDV` (unchanged from before) |
| `offense` | 17 | exact duplicates (unchanged from before) |
| `off_code_sor` | 15 | exact duplicates |

A blank `addressid` or `educationid` on an event is normal (`pdv_cod = 'NON'`, no address/school) and those rows are kept.

## Removal notices

`apply_removals.py` needed no changes: it already deletes from every table with an `ind_idn`, `per_idn` or `dps_nbr` column, and every new person table has one. The new foreign keys are `DEFERRABLE INITIALLY DEFERRED`, so they are checked when the removal transaction commits, not after each table's delete.

## Verification (2026-11-02)

Run on a copy of the local database (2026-09-16 export):

| check | result |
|---|---|
| `transform_to_cleaned.py` | 27 tables, 27 primary keys, 23 foreign keys, about 35 s |
| Original 5 tables | same row counts as before (offense 161,334, address 107,804) |
| Real DPS notice (158 records) applied after the change | 93 people removed from `cleaned` and `sor`, including the new tables (93 `photo`, 112 `birth_date`, 93 `registration_event`), no foreign key errors |
| Re-run transform after the removal | 0 removed people back in `cleaned` |
| `python3 -m unittest discover tests` | 9 pass |
