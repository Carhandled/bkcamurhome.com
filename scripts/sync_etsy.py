#!/usr/bin/env python3
"""
sync_etsy.py

Runs inside GitHub Actions (see .github/workflows/etsy-sync.yml) on an hourly
schedule. It:

  1. Exchanges the stored Etsy refresh token for a fresh access token
     (and a new refresh token, which Etsy rotates on every use).
  2. Fetches every ACTIVE listing in the bkCAMUR Home Etsy shop, including
     images and current quantity.
  3. Sorts each listing into one of three categories by keyword match on its
     title: Suzani Pillow Covers (Uzbekistan), Kilim Pillow Covers (Turkey),
     or Rugs & Kilims (Turkey) - see categorize() below.
  4. Regenerates each category's product grid in index.html between its own
     comment markers, so the site always mirrors exactly what's live on
     Etsy. A category with zero active listings gets a graceful
     "coming soon" placeholder instead of an empty grid.
  5. If Etsy issued a new refresh token, writes it back to the GitHub repo's
     Actions secret (ETSY_REFRESH_TOKEN) so the next run can use it - Etsy
     refresh tokens are valid 90 days but rotate on each use, so this keeps
     the chain alive indefinitely without any human re-authorizing.

Required environment variables (set as GitHub repo secrets, injected by the
workflow):
    ETSY_API_KEY       - Etsy app "keystring"
    ETSY_SHARED_SECRET - Etsy app "shared secret" (Etsy now requires both,
                          combined as "keystring:sharedsecret", in every
                          x-api-key header as of their Feb 2026 enforcement
                          - see https://github.com/etsy/open-api/discussions/1521)
    ETSY_REFRESH_TOKEN - current refresh token
    ETSY_SHOP_ID       - numeric Etsy shop id for BKCAMURHOME
    GH_PAT             - fine-grained PAT scoped to this repo with
                          "Secrets: write" permission, used only to update
                          the ETSY_REFRESH_TOKEN secret after rotation
    GITHUB_REPOSITORY  - "owner/repo", auto-provided by GitHub Actions
"""

import base64
import os
import sys
from pathlib import Path

import requests

ETSY_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
ETSY_API_BASE = "https://api.etsy.com/v3/application"
INDEX_HTML_PATH = Path("index.html")
SHOP_URL = "https://www.etsy.com/shop/BKCAMURHOME"

# Category key -> (start marker, end marker, meta label shown on each card,
# empty-state copy shown when this category has zero active listings)
CATEGORIES = {
    "suzani": {
        "start": "<!-- ETSY_SUZANI_START -->",
        "end": "<!-- ETSY_SUZANI_END -->",
        "meta": "Uzbekistan &middot; Hand-Embroidered",
    },
    "kilim_pillow": {
        "start": "<!-- ETSY_KILIM_PILLOW_START -->",
        "end": "<!-- ETSY_KILIM_PILLOW_END -->",
        "meta": "Turkey &middot; Flatwoven Kilim",
    },
    "rug": {
        "start": "<!-- ETSY_RUGS_START -->",
        "end": "<!-- ETSY_RUGS_END -->",
        "meta": "Turkey &middot; Hand-Loomed",
    },
}

EMPTY_STATE_TEMPLATE = (
    '<div class="cat-empty">\n'
    "{label} are being sourced and will appear here as soon as they're "
    'listed. In the meantime, browse the full shop on '
    f'<a href="{SHOP_URL}" target="_blank" rel="noopener">Etsy</a> or '
    '<a href="wholesale.html">inquire about trade access</a>.\n'
    "</div>"
)

EMPTY_STATE_LABELS = {
    "suzani": "Suzani pillow covers",
    "kilim_pillow": "Kilim pillow covers",
    "rug": "Rugs and kilims",
}


def env(name, required=True):
    val = os.environ.get(name, "").strip()
    if required and not val:
        print(f"ERROR: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return val


def categorize(title):
    """Sort a listing into suzani / kilim_pillow / rug by keyword match on
    its title. Adjust these keywords if real listing titles don't match -
    this is intentionally simple so it's easy to tune by hand."""
    t = (title or "").lower()
    if "suzani" in t:
        return "suzani"
    if "kilim" in t and ("pillow" in t or "cushion" in t or "cover" in t):
        return "kilim_pillow"
    return "rug"


def refresh_oauth_token(api_key, refresh_token):
    resp = requests.post(
        ETSY_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": api_key,
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["refresh_token"]


def fetch_active_listings(x_api_key, access_token, shop_id):
    listings = []
    limit = 100
    offset = 0
    while True:
        resp = requests.get(
            f"{ETSY_API_BASE}/shops/{shop_id}/listings/active",
            headers={
                "x-api-key": x_api_key,
                "Authorization": f"Bearer {access_token}",
            },
            params={"limit": limit, "offset": offset, "includes": "Images"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        listings.extend(results)
        offset += limit
        if offset >= data.get("count", 0) or not results:
            break
    return listings


def format_price(price):
    amount = price.get("amount", 0)
    divisor = price.get("divisor", 100) or 100
    return f"${amount / divisor:,.2f}"


def escape_html(text):
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_card(listing, meta_label):
    title = escape_html(listing.get("title", "").strip())
    url = listing.get("url", "#")
    quantity = listing.get("quantity", 1)
    price = format_price(listing.get("price", {}))

    images = listing.get("images") or []
    image_url = images[0].get("url_570xN") if images else ""

    if quantity and quantity > 1:
        badge = f"{quantity} Available"
    else:
        badge = "1 of 1 Available"

    return f"""
<div class="product-card">
<div class="product-photo"><img src="{escape_html(image_url)}" alt="{title}" loading="lazy" /></div>
<div class="product-info">
<span class="one-of-a-kind">{badge}</span>
<div class="product-name">{title}</div>
<div class="product-meta">{meta_label}</div>
<div class="product-price">{price} &middot; Free Shipping</div>
<a class="product-buy" href="{escape_html(url)}" target="_blank" rel="noopener">View &amp; Purchase</a>
</div>
</div>"""


def group_by_category(listings):
    grouped = {key: [] for key in CATEGORIES}
    for listing in listings:
        cat = categorize(listing.get("title", ""))
        grouped.setdefault(cat, []).append(listing)
    return grouped


def build_category_block(cat_key, cat_listings):
    meta_label = CATEGORIES[cat_key]["meta"]
    if not cat_listings:
        return EMPTY_STATE_TEMPLATE.format(label=EMPTY_STATE_LABELS[cat_key])
    return "\n".join(build_card(l, meta_label) for l in cat_listings)


def regenerate_index_html(listings):
    if not INDEX_HTML_PATH.exists():
        print(f"ERROR: {INDEX_HTML_PATH} not found", file=sys.stderr)
        sys.exit(1)

    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    grouped = group_by_category(listings)

    for cat_key, cfg in CATEGORIES.items():
        start, end = cfg["start"], cfg["end"]
        if start not in html or end not in html:
            print(
                f"ERROR: index.html is missing markers {start} / {end} "
                "for category '" + cat_key + "'.",
                file=sys.stderr,
            )
            sys.exit(1)

        block_html = build_category_block(cat_key, grouped.get(cat_key, []))
        new_block = f"{start}\n{block_html}\n{end}"

        pre, rest = html.split(start, 1)
        _, post = rest.split(end, 1)
        html = pre + new_block + post

    original = INDEX_HTML_PATH.read_text(encoding="utf-8")
    changed = html != original
    if changed:
        INDEX_HTML_PATH.write_text(html, encoding="utf-8")

    counts = {k: len(v) for k, v in grouped.items()}
    print(f"Listing counts by category: {counts}")

    return changed


def get_repo_public_key(gh_pat, repo):
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers={
            "Authorization": f"Bearer {gh_pat}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def encrypt_secret(public_key_b64, secret_value):
    from nacl import encoding, public

    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def update_github_secret(gh_pat, repo, secret_name, secret_value):
    key_info = get_repo_public_key(gh_pat, repo)
    encrypted_value = encrypt_secret(key_info["key"], secret_value)
    resp = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        headers={
            "Authorization": f"Bearer {gh_pat}",
            "Accept": "application/vnd.github+json",
        },
        json={"encrypted_value": encrypted_value, "key_id": key_info["key_id"]},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    # Soft-skip (exit 0, no failure email) until all four secrets exist -
    # lets the workflow run hourly from day one without spamming failures
    # while the human setup steps in ETSY_AUTOMATION_SETUP.md are pending.
    required = [
        "ETSY_API_KEY",
        "ETSY_SHARED_SECRET",
        "ETSY_REFRESH_TOKEN",
        "ETSY_SHOP_ID",
        "GH_PAT",
    ]
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        print(
            "Skipping sync - setup not finished yet. Missing secret(s): "
            + ", ".join(missing)
            + ". See ETSY_AUTOMATION_SETUP.md."
        )
        sys.exit(0)

    api_key = env("ETSY_API_KEY")
    shared_secret = env("ETSY_SHARED_SECRET")
    refresh_token = env("ETSY_REFRESH_TOKEN")
    shop_id = env("ETSY_SHOP_ID")
    gh_pat = env("GH_PAT")
    repo = env("GITHUB_REPOSITORY")

    # Etsy requires x-api-key to be "keystring:sharedsecret" as of their
    # Feb 2026 enforcement - see module docstring.
    x_api_key = f"{api_key}:{shared_secret}"

    print("Refreshing Etsy OAuth token...")
    access_token, new_refresh_token = refresh_oauth_token(api_key, refresh_token)

    print("Fetching active listings...")
    listings = fetch_active_listings(x_api_key, access_token, shop_id)
    print(f"Found {len(listings)} active listing(s).")

    changed = regenerate_index_html(listings)
    print("index.html updated." if changed else "No changes to index.html.")

    if new_refresh_token != refresh_token:
        print("Refresh token rotated - updating GitHub secret...")
        update_github_secret(gh_pat, repo, "ETSY_REFRESH_TOKEN", new_refresh_token)
        print("ETSY_REFRESH_TOKEN secret updated.")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == "__main__":
    main()
