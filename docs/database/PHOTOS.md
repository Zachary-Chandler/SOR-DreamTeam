# Registrant photos

Photos are **not stored in the database**. The DPS export has no image files, only a `Photo` table with photo IDs and dates. DPS serves each registrant's current photo from its public site, so the app links to it and the browser loads it straight from DPS.

## How to use it

View `cleaned.individual_photo` has one row per person:

| column | meaning |
|---|---|
| `ind_idn`, `dps_nbr` | who it is |
| `photo_url` | `https://sor.dps.texas.gov/Search/Rapsheet/CurrentPhoto?sid=<8-digit DPS number>` |
| `has_photo` | the export lists at least one photo for this person |
| `latest_photo_date` | date of their newest photo in the export |

```sql
SELECT photo_url FROM cleaned.individual_photo WHERE ind_idn = '...' AND has_photo;
```

In the page, put the URL in an image tag and hide it if DPS has no photo:

```html
<img src="{photo_url}" alt="Registrant photo" loading="lazy" onerror="this.style.display='none'">
```

## How this was worked out (2026-11-03)

- DPS's `Readme.pdf` in the export (dated 2013) gives `https://records.txdps.state.tx.us/SexOffender/PublicSite/Application/Search/GetPhoto.ashx?PhotoId={0}`. That host no longer responds, and the same path on `sor.dps.texas.gov` returns 404.
- The current public search at `sor.dps.texas.gov/Search` loads result photos from `/Search/Rapsheet/CurrentPhoto?sid={dps_nbr}`.
- Tested that URL directly: it returns a JPEG with no login or cookie, also when the request comes from another site, and 404 for a DPS number with no photo.
- Only the **current** photo is available this way. Older photos listed in `cleaned.photo` have no public URL.

## Things to know

- Every page view fetches from DPS's server. If DPS changes the URL, photos stop showing (the rest of the site still works); update the URL in the view in `schema.sql`.
- DPS decides what it serves. A person DPS has removed won't have a photo there, and anyone removed through `apply_removals.py` isn't in `cleaned` at all, so no link is built for them.
- Check with the sponsor that linking to DPS's photos is fine for how the site will be used. The registry's terms of use apply to the photos like the rest of the data.
