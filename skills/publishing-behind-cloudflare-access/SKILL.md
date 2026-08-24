---
name: publishing-behind-cloudflare-access
description: Use when a page, artifact, report, or static site must go online but stay restricted to named people - someone asks to "password protect" a page, share a document with specific emails only, gate a preview or staging site, put authentication in front of something that has no backend, or keep a confidential deliverable off the public internet. Also use when a published Claude artifact needs an audit trail of who opened it, and whenever a private page is about to be deployed before its access controls exist.
---

# Publishing behind Cloudflare Access

Put a login in front of a static page using Cloudflare Access, without buying a
domain, moving DNS, or writing auth code.

## The core hazard

**Deploying the page and adding the login are two steps, and doing them in that
order publishes the document.** A confidential page on a live URL is exposed for
however long the second step takes, and that window is indexable and
unrecoverable.

Deploy with the public URL switched **off**, attach Access, then switch it on.
Every other instruction here is detail; this is the one that matters.

## Answer the question they actually asked

People ask for a password. Access does not do shared passwords, and that is a
better outcome. Say so plainly and move on:

| They want | Give them | Why |
|---|---|---|
| A password on the page | Email allowlist | A password gets forwarded, can't be revoked per person, and leaves no trace of who used it |
| Only certain people | Access policy listing addresses | Exactly the feature |
| To know who read it | Zero Trust > Logs > Access authentication | Records every sign-in |
| To cut someone off | Remove from policy **and** revoke tokens | Removal alone leaves live sessions running |

Free for up to 50 users. Two recipients costs nothing.

## Sequence

1. **Enable Access once, in the dashboard.** Zero Trust > Enable Access. Pick a
   team domain (`yourteam.cloudflareaccess.com`). Not automatable, see below.
2. **Deploy with no public route.** `"workers_dev": false` in `wrangler.jsonc`.
   The Worker exists and is unreachable. Pick the Worker name here, and pick a
   meaningless one: it becomes the public hostname.
3. **Attach Access to the Worker.** Workers & Pages > your Worker > Access >
   Protect this Worker behind Access > All traffic. Policy: sign-in by email
   address, listing each person.
4. **Turn the URL on.** Set `"workers_dev": true`, redeploy.
5. **Verify before sending the link.** See below.

Attaching Access **to the Worker** rather than to a hostname covers its
`workers.dev` URL, every route, custom domains, and previews at once, and keeps
covering them when routes change. It also means **no domain is required**, which
removes the whole DNS question.

**Previews matter more than they look, because they switch themselves on.** With
`workers_dev` true and no `preview_urls` setting, wrangler enables Preview URLs
by default and says so in a warning that is easy to scroll past:

```
▲ [WARNING] Because your 'workers.dev' route is enabled and your 'preview_urls'
  setting is not in your Wrangler file, Preview URLs will be enabled by default.
```

That is a second public hostname, one per deployed version, that nobody chose.
Worker-scoped Access does cover it - measured, both the current and a previous
version redirect to the login with no content served:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<version>-<worker>.<subdomain>.workers.dev
# 302, and the body carries none of the document
```

Had Access been attached to the hostname instead, every preview URL would have
been an open door. Check one after deploying rather than assuming.

## What you cannot automate, and how to find out fast

**The Access bootstrap is dashboard-only.** Before it is done, every Access API
call returns `9999: access.api.error.not_enabled`, including reads. Creating the
organization over the API does not substitute for the button.

**Cloudflare MCP tokens are commonly read-only.** Reads succeed and writes fail
with `10000: Authentication error`, which reads like a broken credential rather
than a scope limit. Probe before planning around it:

```
POST /accounts/{account_id}/access/groups   # then DELETE it
{ "name": "zz-perm-probe-delete-me",
  "include": [{ "email": { "email": "probe@example.invalid" } }] }
```

**Probe with something that cannot fail validation.** An Access group gates
nothing until a policy references it, and its body is too simple to be rejected,
so the only thing it can test is permission. Probing with an *application*
instead returns `1010` when the destination list is empty - a validation error,
not a permission one - and reading that as "no write access" is wrong in a way
that changes the whole plan. Only `10000: Authentication error` means scope.

If the probe fails, deployment has to run through `npx wrangler` under the user's
own login, and `npx wrangler login` is an interactive browser flow you cannot
complete for them. Establish this before writing any deploy code.

Worth knowing the two tokens fail differently. A wrangler OAuth login typically
carries `workers (write)` and no Access scope at all, so it deploys happily and
cannot create the application. Check with `npx wrangler whoami`, which prints the
scope list.

## Gotchas that cost real time

| Gotcha | What to do |
|---|---|
| **The hostname is public even though the page is not.** Access gates the content, not the URL | Name the Worker so it reveals nothing. `acme-2027-pricing.workers.dev` announces the subject in every link, proxy log, mail scanner and browser history. Use something opaque. |
| **"Protect all Workers"** locks every Worker in the account, including unrelated ones | Protect the single Worker. Check what else is in the account first. |
| Moving a business domain to Cloudflare to host one page | Nameserver change moves MX too, risking email. Use `*.workers.dev` instead. |
| One-time PIN is no longer the default login method | Since June 2026 new orgs get the Cloudflare IdP. Add OTP explicitly if the recipient has no Cloudflare account. |
| **`allowed_idps: []` read back from the API looks like "no logins allowed"** | It means the opposite: unrestricted, so every configured provider is offered. The per-Worker dashboard flow leaves it empty, and an app created another way may have OTP pinned - so two apps on one account can differ here and both be right. Compare the rendered login pages before changing anything; with OTP configured they came back identical. Do not "fix" the empty one. |
| Reading a config back is not the same as testing it | Policies are the gate, not the app record. An application can exist, be bound to the right Worker, and admit nobody, because the policies live on a separate endpoint (`/access/apps/{id}/policies`). Fetch those too. |
| Blocked users still see "a code has been emailed to you" | By design. Judge by whether the code works, never by the message. |
| Removing someone from the policy leaves their session alive | Sessions last `session_duration` (24h default). Use Revoke tokens for immediate cutoff. |
| Artifact HTML has no `<!doctype>`, `<html>`, `<head>`, or `<body>` | The artifact publisher injects them. Self-hosting does not. Wrap it, and add `<html lang="en">` plus `<meta name="robots" content="noindex, nofollow, noarchive">`. |
| Email scanners consume the PIN before the user does | Symptom is "This One-Time PIN has already been used". Allowlist `noreply@notify.cloudflare.com`. |

## Verify before sending the link

Do all three. The first two are the ones people skip.

1. Private window on the URL: the login page appears, not the document.
2. An address **not** on the allowlist: refused.
3. Your own address: code arrives, page loads.

Only then share the link.

Check 1 can be automated and should be, because it also proves nothing leaks
before the redirect:

```bash
curl -s -o /tmp/b -D /tmp/h -w "%{http_code}\n" "$URL"     # expect 302
grep -i '^location:' /tmp/h                                 # expect cloudflareaccess.com
grep -qiE "<a distinctive phrase from the document>" /tmp/b && echo EXPOSED || echo clean
```

**Checks 2 and 3 cannot be automated and must not be skipped**, because they are
the only ones that test the policy rather than the plumbing. Check 1 passes
identically whether the policy admits the right five people or the wrong five
hundred. If you are an agent, hand these two back explicitly rather than
reporting the page verified.

## When not to use this

For a single recipient and a one-off document, a share menu on whatever already
hosts the page is proportionate and takes no setup. Access earns its setup when
you want the audit trail, per-person revocation, or expect to publish this way
again.

## Reference

`references/api-recipes.md` carries exact request shapes for the Access application,
Worker destination types, one-time PIN provider, and the wrangler config, plus
the rollback commands.
