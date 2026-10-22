# DPS removal notices

What `apply_removals.py` does, why it's built the way it is, and how it was verified. For the commands to run, see the root `SETUP.md`.

## Why this exists

Texas Code of Criminal Procedure Ch. 62.251 requires anyone who downloaded the public registry to remove a person from any publicly accessible copy once DPS sends notice that the person is off the registry. DPS sends these notices by email from `TxSOR@dps.texas.gov`, subject "Removal from Texas Sex Offender Registry". Each email lists records like this:

```
Record(s):
	LAST,FIRST MIDDLE   YYYY-MM-DD   DPS_NUMBER
```

## Where this fits

```
load_registry_pg.py       -->  schema `sor`
        |                          ^
        v                          | apply_removals.py --reapply (after each raw load)
transform_to_cleaned.py   -->  schema `cleaned`
        ^                          ^
        | ledger re-applied        | apply_removals.py NOTICE (when an email arrives)
        | to cleaned_new           |
        +---- schema `removals` (ledger of removed DPS numbers, never rebuilt)
```

`sor` and `cleaned` are both rebuilt from scratch on every refresh. The new DPS export usually no longer contains removed people, but it is not guaranteed to, and the export can lag the email. The ledger in `removals` is what keeps a removed person from coming back.

## How it works

1. **Read the notice.** Accepts a Gmail "Download message" `.eml`, a plain text body, or an HTML body, or stdin (`-`). For `.eml` files it decodes quoted-printable or base64 and prefers the `text/plain` part.
2. **Parse.** Only lines after `Record(s):` that match `NAME  YYYY-MM-DD  DIGITS` are used. The DPS number is zero-padded to 8 digits and duplicates are dropped.
3. **Sanity checks.**
   - Refuses more than `--max` people (default 1000) from one notice, as a guard against a bad parse or a forged email.
   - Reports how many people in the notice are present in `cleaned`, and warns when the surname in the email doesn't match the database. A mismatch is only a warning: the DPS number is the key, and DPS sometimes uses placeholder names such as `XX`.
4. **Ledger.** Writes the DPS numbers to `removals.removed_individual` and a SHA-256 of the sorted list to `removals.notice`. Names and dates of birth are never stored.
5. **Delete.** In one transaction, for each of `sor` and `cleaned`, it finds every table with a `dps_nbr`, `ind_idn` or `per_idn` column (any capitalization) and deletes the matching rows. Child tables go first, then `PERSON`, then `INDV`/`individual`. Lookup tables (`AGENCY`, `Counties`, `VAL`, ...) have no person keys and are left alone.
6. **`--dry-run`** runs all of the above, including the ledger insert, then rolls back.

`transform_to_cleaned.py` calls the same code on `cleaned_new` before the swap. The `sor` schema has to be cleared by hand with `--reapply` after each raw load (see `SETUP.md`). Until then, removed people can sit in `sor` for a short window, which is one more reason nothing public should read from `sor`.

## Verification (2026-10-22)

Run against a copy of the local database (2026-10-07 export), using the real DPS notice dated 2026-10-03 (158 records). The notice itself is not in the repo.

| check | result |
|---|---|
| Unit tests (`python3 -m unittest discover tests`) | 9 pass |
| Records parsed from the real `.eml` | 158 of 158 |
| People from the notice present in `cleaned` | 93 (the rest were already gone from the export) |
| Surname-mismatch warnings | 2 (placeholder / truncated surnames in the email; DPS number matched) |
| `--dry-run` | showed the deletes below, left the database unchanged, no `removals` schema created |
| Apply | deleted from 5 `cleaned` tables and 11 `sor` tables, for example 93 `individual`, 154 `offense`, 361 `name` |
| Same notice applied again | 0 rows deleted, ledger still 158 rows / 1 notice |
| Fresh `sor` + ledger, then `transform_to_cleaned.py` | 0 removed people in `cleaned`, 93 still in `sor` (expected) |
| `--reapply` | 0 removed people in `sor` |

## Known gaps

- When a notice is applied a second time, the script still prints "Ledger updated and rows removed." even though nothing changed. The per-table lines (none printed) are the real result.
- The ledger never expires. If someone removed earlier has to register again under the same DPS number, the ledger keeps deleting them from every refresh. The only fix today is by hand: `DELETE FROM removals.removed_individual WHERE dps_nbr = '...'`, then re-run the transform.
- Anything that copies registry data elsewhere (exports, caches, a deployed API database) is outside this script and needs its own removal step.
