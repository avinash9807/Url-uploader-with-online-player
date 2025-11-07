
# Mux Backend (Flask) — Deploy on Koyeb (buildpack, no Docker required)

## Required environment variables (set these in Koyeb service settings)
- MUX_TOKEN_ID
- MUX_TOKEN_SECRET
Optional:
- API_KEY          (if set, all endpoints require X-API-KEY header)
- CORS_ORIGINS     (default "*", set to your InfinityFree domain)

## Files
- app.py
- requirements.txt
- .env.example

## Koyeb (GitHub / Buildpack) deploy steps
1. Push repo to GitHub (root contains app.py & requirements.txt).
2. In Koyeb dashboard: Create Service → Web Service → Connect GitHub repo & branch.
3. Under "Run command" set:
   gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
4. Add Environment Variables in Koyeb UI:
   - MUX_TOKEN_ID, MUX_TOKEN_SECRET, optionally API_KEY and CORS_ORIGINS
5. Deploy. Koyeb will build using Python buildpack (detects requirements.txt).

## Local testing (optional)
1. python -m venv venv
2. pip install -r requirements.txt
3. export MUX_TOKEN_ID=...; export MUX_TOKEN_SECRET=...
4. python app.py
5. Visit http://localhost:8080/health

## Example curl
Create asset:
curl -X POST "https://<your-koyeb-url>/create_asset" -d "url=https://example.com/video.mp4"

List assets:
curl "https://<your-koyeb-url>/list_assets"

Delete:
curl -X POST "https://<your-koyeb-url>/delete_asset" -d "asset_id=clb123..."
