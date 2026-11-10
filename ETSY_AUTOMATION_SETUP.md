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
| `ETSY_REFRESH_TOKEN` | Bootstrap OAuth refresh token — only read when `.etsy-token` is missing or rejected |
| `ETSY_SHOP_ID` | Numeric shop id for BKCAMURHOME |

If any are missing the script exits 0 with a "Skipping sync" message rather
than failing, so a half-finished setup doesn't send failure mail.

## The refresh-token chain (and how it breaks)

Etsy rotates the refresh token **on every use**. Each run, `sync_etsy.py`
spends the stored token, gets a new one back, and saves it encrypted to
`.etsy-token` in this repo. The workflow commits that file with the built in
`GITHUB_TOKEN`, so there is **no personal access token to expire**. The file
is encrypted with a key derived from `ETSY_SHARED_SECRET`, so the public repo
never exposes a usable token.

The token is saved the moment Etsy issues it and the commit step runs even
if a later step fails, so a partial failure can't lose it.

Token lookup order: `.etsy-token` first; if Etsy rejects it, the
`ETSY_REFRESH_TOKEN` secret. That means recovery is always just "paste a new
token into the secret". The next run uses it and takes over the file.

One thing still breaks the chain:

1. **The workflow stops running for 90+ days**, or the Etsy app is
   disconnected from the shop. The daily commit of the rotated token also
   keeps GitHub from auto disabling the schedule for inactivity.

It fails with:

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

Nothing to rotate on a calendar. If a run fails, the Actions tab shows it and
the site keeps serving the last synced grid, so a broken sync is stale, not
blank. If you ever change the Etsy shared secret, `.etsy-token` can no longer
be decrypted; paste a fresh refresh token into `ETSY_REFRESH_TOKEN` and it
recovers on the next run. `GH_PAT` is no longer used and can be deleted.
