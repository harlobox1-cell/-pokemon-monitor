# Pokémon Monitor Cloud v0.3

**Setup status:** Overnight watchlist configured; scheduled workflow enabled unless MONITOR_ENABLED=false. Read SETUP.md for coverage and limitations. Start with [SETUP.md](SETUP.md) for GitHub scheduled checks or dashboard hosting.

A phone-friendly, cloud-ready Pokémon stock monitor. It runs 24/7 on a cloud host and sends Discord alerts to your iPhone. You manage products and settings from a private web dashboard in Safari.

## What v0.3 does

- Mobile web dashboard
- Password-protected login
- Discord webhook setup and test button
- Exact product URL monitoring
- New-product discovery from retailer category/search pages
- Maximum-price rules
- Stock/restock and price-change alerts
- Supports retailer identification for:
  - BIG W AU
  - Kmart AU
  - Target AU
  - EB Games AU
  - JB Hi-Fi AU
  - Toymate AU
  - Pokémon Center AU
  - Pokémon Center US
  - Costco AU
- Stores the Discord webhook encrypted on disk
- Docker/cloud deployment files included
- Does **not** store card numbers, CVVs, bank details, or Discord account tokens

## Important limitation

v0.3 is **monitoring and alerts only**. It does not place orders or bypass CAPTCHAs, queues, 3-D Secure, purchase limits, or other retailer controls.

## Cloud requirements

The service needs:

1. A cloud host that can run a Docker web service.
2. One environment variable:
   - `ADMIN_PASSWORD` — choose a strong password you will use to open the dashboard.
3. A persistent disk/volume mounted at `/data` is strongly recommended so your watchlist survives restarts/redeploys.

`PORT` is read automatically from most cloud hosts. `DATA_DIR` defaults to `/data` in Docker.

## First-time setup from iPhone

Once the service is deployed:

1. Open the service URL in Safari.
2. Sign in with the `ADMIN_PASSWORD` you set on the cloud host.
3. Open **Settings**.
4. Paste your **new/private Discord webhook**.
5. Tap **Save settings**.
6. Tap **Send test Discord alert**.
7. Open **Products** to add exact product URLs.
8. Open **Discovery** to watch Pokémon category/search pages for new matching listings.

## Security

- The Discord webhook is encrypted before it is stored.
- The encryption key is generated locally inside the service and stored in the persistent data directory.
- The dashboard cookie is HTTP-only and SameSite=Strict.
- Do not put payment card details, Discord personal tokens, banking passwords, or retailer passwords into this app.
- If you accidentally shared a Discord webhook publicly, regenerate it in Discord before using the monitor.

## Local test (optional)

```bash
export ADMIN_PASSWORD='choose-a-password'
export DATA_DIR='./data'
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:8080`.

## Docker

```bash
docker build -t pokemon-monitor .
docker run --rm -p 8080:8080 -e ADMIN_PASSWORD='choose-a-password' -v pokemon-monitor-data:/data pokemon-monitor
```

## Notes on retailer monitoring

Retailer pages change frequently. The generic parser uses JSON-LD and visible stock/price wording. Some JavaScript-heavy pages may need **Use browser rendering** enabled in the dashboard. This is browser rendering only; it is not intended to bypass retailer challenges or access controls.
