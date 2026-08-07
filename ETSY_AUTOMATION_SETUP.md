# Etsy sync — setup and recovery

The site's product grids are generated from the live Etsy shop by
`scripts/sync_etsy.py`, run daily by `.github/workflows/etsy-sync.yml`
(12:00 UTC, plus a manual "Run workflow" button). It rewrites the three
marked blocks in `index.html` and commits the result if anything changed.

## Repo secrets it needs

Set at https://github.com/Carhandled/bkcamurhome.com/settings/secrets/actions

| Secret | What it is |
| --- | --- |
| `ETSY_API_KEY` | Etsy app keystring |
| `ETSY_SHARED_SECRET` | Etsy app shared secret |
| `ETSY_REFRESH_TOKEN` | OAuth refresh token — **self-rotating, see below** |
| `ETSY_SHOP_ID` | Numeric shop id for BKCAMURHOME |
| `GH_PAT` | Fine-grained PAT, this repo, **Secrets: write** — used only to write the rotated `ETSY_REFRESH_TOKEN` back |

If any are missing the script exits 0 with a "Skipping sync" message rather
than failing, so a half-finished setup doesn't send failure mail.

## The refresh-token chain (and how it breaks)

Etsy rotates the refresh token **on every use**. Each run, `sync_etsy.py`
spends the stored token, gets a new one back, and writes that new one into
the `ETSY_REFRESH_TOKEN` secret using `GH_PAT`. That's what keeps the sync
hands-off indefinitely — nobody has to re-authorize on a schedule.

Two things break the chain:

1. **`GH_PAT` expires or is wrong.** The rotated token can't be saved, so
   the next run spends a token Etsy has already retired.
2. **The workflow stops running long enough** that the stored token lapses.

Both end the same way — the sync fails with:

```
ERROR: Failed to refresh Etsy token: 400 Client Error: Bad Request
Response: {"error":"invalid_grant","error_description":"refresh_token is invalid"}
```

There is no way to repair this from the Etsy dashboard; the UI does not
show or regenerate refresh tokens. You have to re-authorize once by hand.

## Recovering: mint a new refresh token

Run this **on your own machine** (it needs a browser signed in as the shop
owner). Standard library only — nothing to install.

```bash
python3 scripts/get_refresh_token.py --client-id <keystring>
```

It prints an authorization URL. Open it, click **Allow Access**, and Etsy
redirects to `etsy-oauth-callback.html` on the live site, which displays a
`code` value. Paste that back into the script and it prints a new refresh
token.

Save that value as the `ETSY_REFRESH_TOKEN` secret, then run the **Sync
Etsy Listings** workflow to confirm. From there the chain is self-sustaining
again.

### If the code exchange is rejected

The redirect URI must match a URL registered under **Edit callback URLs**
in the Etsy app dashboard, character for character — including `https://`
and the `www.`. The script defaults to
`https://www.bkcamurhome.com/etsy-oauth-callback.html`; override with
`--redirect-uri` if the app has a different one registered.

Codes are single-use and short-lived — if one is rejected, just re-run the
script for a fresh one.

## Keeping it from breaking again

`GH_PAT` expiry is the thing to watch, since it fails silently for a while
before the chain lapses. When you rotate that PAT, update the secret the
same day. A failed run shows up in the Actions tab; the site keeps serving
the last synced grid in the meantime, so a broken sync is stale, not blank.
