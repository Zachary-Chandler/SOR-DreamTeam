"""Read-only API for the Griffin365 cleaned PostgreSQL schema.

Run: uvicorn api.main:app --reload
Never deploy this publicly without reviewing DPS publication/removal obligations.
"""
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/sor")
API_KEY = os.getenv("API_KEY", "")
CORS_ORIGINS = [v.strip() for v in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if v.strip()]

pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row, "options": "-c default_transaction_read_only=on -c statement_timeout=5000"})

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    try:
        yield
    finally:
        pool.close()

app = FastAPI(title="Griffin365 Registry API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["GET"], allow_headers=["X-API-Key", "Content-Type"])


def authorize(x_api_key: Optional[str] = Header(default=None)):
    # Local development can omit API_KEY. Set it for any shared deployment.
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def fetch_all(sql, params=()):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
    except Exception:
        # Avoid leaking connection strings, SQL, or private internals.
        raise HTTPException(status_code=503, detail="Database unavailable or query failed")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/individuals", dependencies=[Depends(authorize)])
def search_individuals(
    name: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10000),
):
    """Search any name on file (aliases included); one row per person, shown under their base name.

    matched_names lists the names that matched the search, so the UI can show an alias
    like "SALLY,XX" under the person's real name.
    """
    term = name.replace("%", "").replace("_", "").strip()
    # Checked after stripping wildcards: "%%" would otherwise match every name (bulk listing).
    if len(term) < 2:
        raise HTTPException(status_code=422, detail="Enter at least two letters or digits")
    pattern = "%" + term + "%"
    rows = fetch_all("""
        WITH hits AS (
            SELECT ind_idn, array_agg(DISTINCT nam_txt ORDER BY nam_txt) AS matched_names,
                   min(sex_cod) AS sex_cod, min(total_offense_records) AS total_offense_records,
                   min(unique_offenses) AS unique_offenses
            FROM cleaned.search_results
            WHERE (nam_txt ILIKE %s OR (COALESCE(fna_txt, '') || ' ' || COALESCE(lna_txt, '')) ILIKE %s)
            GROUP BY ind_idn
        )
        SELECT h.ind_idn, COALESCE(b.nam_txt, h.matched_names[1]) AS nam_txt, b.fna_txt, b.lna_txt,
               h.sex_cod, h.total_offense_records, h.unique_offenses, h.matched_names
        FROM hits h
        LEFT JOIN LATERAL (
            SELECT n.nam_txt, n.fna_txt, n.lna_txt
            FROM cleaned.person p JOIN cleaned.name n ON n.per_idn = p.per_idn
            WHERE p.ind_idn = h.ind_idn AND n.typ_cod = 'B' LIMIT 1
        ) b ON true
        ORDER BY b.lna_txt NULLS LAST, b.fna_txt NULLS LAST, h.ind_idn
        LIMIT %s OFFSET %s
    """, (pattern, pattern, limit, offset))
    return {"items": rows, "limit": limit, "offset": offset, "has_more": len(rows) == limit}


@app.get("/api/individuals/{ind_idn}", dependencies=[Depends(authorize)])
def individual(ind_idn: str):
    if len(ind_idn) > 80:
        raise HTTPException(status_code=400, detail="Invalid ID")
    rows = fetch_all("""
        SELECT ind_idn, nam_txt, fna_txt, lna_txt, sex_cod, rac_cod,
               total_offense_records, unique_offenses,
               earliest_offense_date, latest_offense_date
        FROM cleaned.search_results s WHERE ind_idn = %s
        -- Base name (typ_cod 'B') first so the UI title isn't an alias like "JOE,XX".
        ORDER BY EXISTS (SELECT 1 FROM cleaned.name n WHERE n.nam_idn = s.nam_idn AND n.typ_cod = 'B') DESC,
                 nam_txt NULLS LAST LIMIT 100
    """, (ind_idn,))
    if not rows:
        raise HTTPException(status_code=404, detail="Record not found")
    # Photos aren't stored; this is a link to DPS's current photo (docs/database/PHOTOS.md).
    photo = fetch_all("""
        SELECT photo_url FROM cleaned.individual_photo WHERE ind_idn = %s AND has_photo
    """, (ind_idn,))
    return {"individual_id": ind_idn, "names": rows, "photo_url": photo[0]["photo_url"] if photo else None}


@app.get("/api/individuals/{ind_idn}/offenses", dependencies=[Depends(authorize)])
def offenses(ind_idn: str, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)):
    if len(ind_idn) > 80:
        raise HTTPException(status_code=400, detail="Invalid ID")
    rows = fetch_all("""
        SELECT offense_record_id, off_cod, cdd_dte, ost_cod
        FROM cleaned.offense WHERE ind_idn = %s
        ORDER BY cdd_dte DESC NULLS LAST, offense_record_id
        LIMIT %s OFFSET %s
    """, (ind_idn, limit, offset))
    return {"items": rows, "limit": limit, "offset": offset, "has_more": len(rows) == limit}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
