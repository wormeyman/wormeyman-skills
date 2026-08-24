# API and config recipes

Request shapes verified against the Cloudflare OpenAPI spec and the Workers
Access docs. Retrieve the current schema before relying on any field here.

## wrangler.jsonc, static page with no public route

`workers_dev: false` is the safety property, not a preference. Deploying with it
true before Access is attached publishes the page.

```jsonc
{
  "name": "my-doc",
  "compatibility_date": "2026-08-01",
  "assets": { "directory": "./public" },

  // Flip to true ONLY after the Access policy is attached and verified.
  "workers_dev": false,

  // Wrangler enables Preview URLs by default once workers_dev is true, which
  // is a second public hostname per version. Worker-scoped Access covers them,
  // but set this deliberately rather than inheriting it, and check one after
  // deploying. Set false if you do not want per-version URLs at all.
  "preview_urls": true,

  "observability": { "enabled": true }
}
```

```
npx wrangler deploy          # deploys, no URL
# ... attach Access, verify ...
# set workers_dev true
npx wrangler deploy          # URL now live, behind login
```

## Wrap artifact HTML for self-hosting

Artifact source has no document skeleton. Add one, plus a language and a
noindex, since the page is not meant to be found.

```python
head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow, noarchive">\n'
        '<style>*{margin:0;padding:0}</style>\n</head>\n<body>\n')
open("public/index.html", "w").write(head + artifact_html + "\n</body>\n</html>\n")
```

The `*{margin:0;padding:0}` reset matches what the artifact publisher applies,
so the page renders identically in both places.

## Protect one Worker

Covers the Worker's `workers.dev` hostname, routes, custom domains, and
previews. Preferred over hostname matching, which needs manual upkeep as routes
change.

```bash
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/access/apps" \
  --request POST \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{
    "type": "self_hosted",
    "name": "Access for my-doc",
    "destinations": [
      { "type": "worker", "worker_id": "<worker id>" }
    ],
    "policies": [
      {
        "decision": "allow",
        "include": [
          { "email": { "email": "someone@example.com" } },
          { "email": { "email": "someone-else@example.com" } }
        ]
      }
    ]
  }'
```

Destination types:

| Scope | `type` |
|---|---|
| One Worker, production and previews | `worker` |
| One Worker, previews only | `preview_worker` |
| All Workers in the account | `all_workers` |
| All Workers, previews only | `all_preview_workers` |

**`all_workers` locks every Worker in the account.** List existing Workers before
going anywhere near it.

For a hostname or path instead of a Worker, create the same `self_hosted`
application with the hostname as the application domain.

## Add one-time PIN as a login method

Needed when the recipient has no Cloudflare account. Not added automatically for
organizations created after June 2026.

```bash
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/access/identity_providers" \
  --request POST \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{ "name": "One-time PIN login", "type": "onetimepin", "config": {} }'
```

Requires the `Access: Organizations, Identity Providers, and Groups Write` token
permission. PINs expire 10 minutes after the request.

## Create the Zero Trust organization

Only works after Access is enabled in the dashboard. Included for completeness;
it is not a substitute for the button.

```
POST /accounts/{account_id}/access/organizations
{ "name": "...", "auth_domain": "yourteam.cloudflareaccess.com", "session_duration": "24h" }
```

Required fields are `name` and `auth_domain`. `session_duration` controls how
long a sign-in stays valid, which is also how long a removed user keeps access
until you revoke tokens.

## Permission probe

Run before planning any write path. Distinguishes a read-only token from a
broken one.

**Workers write and Access write are separate scopes, so probe both.** A
wrangler OAuth login commonly holds `workers (write)` with no Access scope
whatever: it deploys the page perfectly and cannot create the application. A
Workers probe that passes tells you nothing about Access.

```js
// Workers write
try {
  await cloudflare.request({
    method: "PUT",
    path: `/accounts/${accountId}/workers/scripts/zz-perm-probe`,
    body: JSON.stringify({}), contentType: "application/javascript", rawBody: true
  });
  await cloudflare.request({ method: "DELETE", path: `/accounts/${accountId}/workers/scripts/zz-perm-probe` });
} catch (e) { /* read-only */ }
```

```js
// Access write. Use a GROUP, not an application: a group gates nothing until a
// policy references it, and its body is too simple to fail validation, so the
// only thing it can test is permission.
const r = await cloudflare.request({
  method: "POST", path: `/accounts/${accountId}/access/groups`,
  body: { name: "zz-perm-probe-delete-me",
          include: [{ email: { email: "probe@example.invalid" } }] }
});
if (r.result?.id) {
  await cloudflare.request({ method: "DELETE", path: `/accounts/${accountId}/access/groups/${r.result.id}` });
}
```

Read the error code, not the shape of the failure:

| Code | Means |
|---|---|
| `10000: Authentication error` | Scope limit. The token cannot write here. |
| `1010` | Validation. The body was wrong, and this says nothing about permission. Probing with an *application* and an empty `destinations` list returns exactly this. |
| `9999: access.api.error.not_enabled` | The dashboard bootstrap has not been done. Reads fail too. |

## Turn the public URL off after the fact

If a Worker was deployed with a URL before Access existed, kill the route first,
then attach Access, then restore it.

```bash
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/$NAME/subdomain" \
  --request POST --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{ "enabled": false, "previews_enabled": false }'
```

Treat anything already served as disclosed. Turning the route off does not
un-publish what was fetched or indexed.

## Operations

| Task | Where |
|---|---|
| Who signed in | Zero Trust > Logs > Access authentication |
| Revoke one person | Remove from policy, then Revoke tokens on the application |
| Revoke everyone | `POST /accounts/{account_id}/access/apps/{app_id}/revoke_tokens` |
| Update the page | Rebuild `public/index.html`, `npx wrangler deploy` |
| Remove entirely | `npx wrangler delete <name>`, then delete the Access application |

Authentication is logged only once the user submits a code. Someone who enters
an email and stops never appears in the audit log.
