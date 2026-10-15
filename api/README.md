# Dream Team REST API

This FastAPI app reads **existing** `cleaned` PostgreSQL tables and views. It does **not** create or load the database.

## Start

From the repository root, after completing `SETUP.md` and loading/transformation:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r api/requirements.txt
cp api/.env.example .env   # Windows: copy api\.env.example .env
# Edit .env for your PostgreSQL URL, UI origin, and API key
uvicorn api.main:app --reload
```

Open http://127.0.0.1:8000/docs to test the endpoints.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Server liveness (does not test database) |
| GET | `/api/individuals?name=Smith&limit=20&offset=0` | Paginated name search |
| GET | `/api/individuals/{ind_idn}` | Person names and offense summary |
| GET | `/api/individuals/{ind_idn}/offenses` | Paginated offense codes/dates |

### UI example (JavaScript)

```js
const response = await fetch('http://localhost:8000/api/individuals?name=Smith', {
  headers: { 'X-API-Key': 'your-dev-key' }
});
if (!response.ok) throw new Error(`API returned ${response.status}`);
const { items } = await response.json();
console.log(items);
```

**Security and data handling:** The API does not return street addresses, coordinates, or bulk exports. It has no write routes. For any deployment outside a trusted local environment, add server-side authentication, rate limiting, logging, HTTPS, and a removal/suppression workflow that prevents DPS removal-notice records from being served, including after each refresh. A browser-visible API key is **not** a secret; do not rely on `X-API-Key` in public frontend JavaScript as access control. Prefer a backend-for-frontend session or another server-side authorization mechanism. Limit database privileges to `SELECT` on the required `cleaned` views/tables. Review DPS terms and applicable laws before public use. The current project does not yet implement the removal-notice process.

**Notes:** `cleaned.search_results` may contain multiple name variants per individual. Search `offset` paginates rows, not unique individuals. `off_cod` and `ost_cod` are raw codes, not human-readable labels. The transform recreates the `cleaned` schema, so database grants may need reapplication after a refresh.

## Browser testing dashboard

Run the same API server and open **http://127.0.0.1:8000/** to use the built-in dashboard. It supports name search, result pagination, individual details, and offense pagination. The UI is served by FastAPI, so it does not require Node.js, a frontend build, or additional CORS setup. Enter your development API key under the expandable option if `API_KEY` is set in `.env`. The dashboard does not store the key, but it is visible to the browser, so only use it for local testing. Database loading is still required before searches return data.
