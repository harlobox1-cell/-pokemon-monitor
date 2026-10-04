# Overnight monitor status — 5 October 2026

26 exact English-product URLs cover all requested sets: Ascended Heroes, Phantasmal Flames, Mega Evolution, Black Bolt, White Flare, Destined Rivals, Journey Together, Prismatic Evolutions, Surging Sparks, Paldean Fates and 151.

Kmart, Target and Toymate are in the current watchlist. Marketplace offers are excluded; unknown sellers and unknown purchase controls cannot alert. The live page checks found marketplace substitutions at Kmart and disabled buy buttons despite InStock structured data on Toymate and Target. Those results are suppressed.

Prices are fixed conservative ceilings from directly observed retailer listings, NOT independently certified manufacturer MSRP. They exclude shipping. Caps are per exact product and currency, never a retailer-wide ETB/pack allowance. They do not increase automatically if a retailer raises its price. Each row retains its source and SKU. Kmart's older direct-retail ceilings remain capped even when the page now serves a marketplace seller. Check the final delivered price before buying.

The scheduled workflow is enabled unless the repository Actions variable `MONITOR_ENABLED` is set to `false`. It requests a run every 15 minutes; GitHub may delay or skip runs. A code/configuration push also triggers a check. The first run sends a labelled connection test and a first-cycle report; neither is a stock alert. Stock alerts follow only if all checks qualify. Alerts are deduplicated using cached snapshots; cache eviction can cause a repeat initial message.

Still pending: EB Games returns HTTP 403; Japanese and Chinese equivalents need exact regional products and verified regional price caps. No import alerts or automatic purchases are enabled. Coverage does not include every product format or every retailer for each set.

To pause: Settings → Secrets and variables → Actions → Variables → set `MONITOR_ENABLED` to `false`. To resume: remove that variable or set it to `true`. The webhook stays exclusively in the `DISCORD_WEBHOOK_URL` Actions secret.

---

# Finish setup from your phone

The code being in GitHub does not mean alerts are running. Choose one mode.

## Option 1: GitHub scheduled checks (no dashboard hosting needed)

1. In this repository, go to Settings → Secrets and variables → Actions → Secrets → New repository secret.
2. Name it `DISCORD_WEBHOOK_URL` and paste your private Discord webhook as its value. Never put the webhook in a code file, issue, or commit.
3. Edit `watchlist.json` and add exact product URLs to `products`, for example:

```json
{
  "settings": {"notify_on_first_in_stock": true, "require_price_for_alert": true},
  "products": [
    {"url": "REPLACE_WITH_REAL_HTTPS_PRODUCT_URL", "max_price": 100, "browser": false}
  ]
}
```

The placeholder must be replaced. Use `null` for no maximum price. Prices are in the product's currency. Use `browser: true` for a page that needs JavaScript rendering. This does not bypass queues or retailer access restrictions.

4. Under Settings → Secrets and variables → Actions → Variables, create `MONITOR_ENABLED` with value `true`.
5. Open Actions → Stock monitor → Run workflow. Review that run before relying on alerts.

The requested schedule is every 15 minutes. GitHub may delay or skip scheduled jobs; this is not a real-time stock service. Monitoring is enabled for this configured watchlist unless the variable is false. Set the variable to `false` to pause. Enable Actions if GitHub prompts you.

Only product snapshots are cached, not the webhook or dashboard database. A missing/expired cache can cause first-seen alerts to repeat. Stock parsing is generic and has not been validated live across all retailers. Check each listing before purchase. Scheduled checks do not provide a dashboard or auto-checkout.

## Option 2: Continuous monitor and private mobile dashboard

Use the supplied Dockerfile on a Docker-capable cloud host. Set a strong `ADMIN_PASSWORD` privately in the host settings, mount persistent storage at `/data`, and use HTTPS. Open the deployed dashboard to add your webhook and products. See README.md for details. Hosting is not provisioned by uploading this repository and may cost money.

Use one mode at a time to avoid duplicate alerts.
