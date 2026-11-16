# photo-labeler (Cloudflare Worker)

Human + bot image labeling for municipal photo training data, on the free
Cloudflare Workers + KV tier. One Worker serves:

- a Hebrew RTL labeling web page (phone-first, responsive for desktop) with
  per-image verdict buttons and tap-to-mark points on offending cars;
- a hosted MCP endpoint (Streamable HTTP, stateless) so review bots can label
  the same pools: tools `get_next_unlabeled`, `submit_label`, `get_progress`;
- per-source label storage in KV (`label:<set>:<source>:<id>`), so human and
  bot labels never overwrite each other and exports keep them separate.

Privacy: no photos, labels, keys or namespace ids live in this repository.
Crosswalk photos are served from KV only with the bearer key; Mapillary
images (CC BY-SA, plates pre-blurred by Mapillary) load from their own CDN.
The bearer key is a Worker secret (`LABEL_KEY`), never committed.

## Deploy (owner, one time)

1. Create a KV namespace: `npx wrangler kv namespace create photo-labeler`.
2. `cp wrangler.toml wrangler.local.toml` and fill in `account_id` and the
   namespace `id`.
3. `npx wrangler secret put LABEL_KEY -c wrangler.local.toml` (generate a
   random key; it is the shared bearer for the page, API and MCP).
4. `npx wrangler deploy -c wrangler.local.toml`.
5. Load manifests into KV (`manifest:<set>` = JSON array of `{id, url?}`) and
   any privately served images (`img:<set>:<id>`, JPEG bytes).

## Use

- Web page: `https://<worker>.workers.dev/?set=<set>` - a key-entry screen
  stores the key in the browser; verdict keys 1-4, arrows navigate.
- MCP: `POST https://<worker>.workers.dev/mcp` with
  `Authorization: Bearer <key>`. The `?key=` query form is accepted only by the browser page's own routes (never `/mcp` or `/api/export`); MCP callers must use the header and must not use source `human` (the page is the only writer of `human` labels).
- Export: `GET /api/export?set=<set>` with the `Authorization: Bearer` header returns labels grouped by
  source.

## Test

`python3 -m unittest discover tests` from the repository root (static checks
on the worker source; no Cloudflare access needed).
