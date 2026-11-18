# Running with Docker

The same pipeline as `SETUP.md`, without installing Postgres, `psql` or Python on your machine. You only need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

| Service | What it is | Started by `up`? |
| --- | --- | --- |
| `db` | PostgreSQL 18, database `sor`. Creates the `cleaned` schema from `docs/database/schema.sql` the first time it starts. Data lives in the `pgdata` volume. | yes |
| `api` | The FastAPI app (`api/`) on http://localhost:8000 | yes |
| `pipeline` | Postgres 18 client + Python, for running the load/transform/removal scripts | no, use `docker compose run` |

## First time

1. Download the export from https://sor.dps.texas.gov and put the zip in `data/` (gitignored). Leave it zipped.
2. Start the database and API:
   ```
   docker compose up -d
   ```
3. Load and clean the data (the same three steps as `SETUP.md`):
   ```
   docker compose run --rm pipeline python3 load_registry_pg.py /data/20261007_DATA-CURRENT.zip
   docker compose run --rm pipeline python3 transform_to_cleaned.py
   docker compose run --rm pipeline python3 apply_removals.py --reapply
   ```
   You don't pass a connection string. The `pipeline` container points the scripts at `db` with the standard `PG*` variables.
4. Open http://localhost:8000 for the dashboard or http://localhost:8000/docs for the API.

## Every refresh

Put the new zip in `data/` and run step 3 again.

## Removal notices

Copy the `.eml` into `data/` (gitignored, along with `*.eml`). Apply it, then delete it:
```
docker compose run --rm pipeline python3 apply_removals.py /data/notice.eml --dry-run
docker compose run --rm pipeline python3 apply_removals.py /data/notice.eml
rm data/notice.eml
```

## Handy commands

```
docker compose exec db psql -U postgres sor                 # SQL shell
psql postgresql://postgres:postgres@localhost:5433/sor      # same, from your own psql (port 5433)
docker compose run --rm pipeline python3 -m unittest discover tests
docker compose logs -f api
docker compose down                                         # stop, keep data
docker compose down -v                                      # stop and DELETE the database volume
```

## Settings

You can override any of these in a `.env` file at the repo root (gitignored). Compose reads the file automatically.

| Variable | Default | |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `postgres` / `postgres` | Only takes effect on a fresh volume (`down -v`) |
| `DB_PORT` | `5433` | Host port for Postgres. Not 5432, so it doesn't clash with a Homebrew install. |
| `API_PORT` | `8000` | |
| `API_KEY` | empty (no key required) | Set it for anything shared |

Both ports bind to `127.0.0.1` only. The default password is fine for local use and nothing else.

Note: if your `.env` still has `DATABASE_URL=postgresql://localhost/sor` from the non-Docker setup, that's fine. Compose sets `DATABASE_URL` for the `api` container itself.
