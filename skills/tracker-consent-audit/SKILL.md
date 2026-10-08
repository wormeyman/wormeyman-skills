---
name: tracker-consent-audit
description: Use when a WordPress food blogger asks whether their site needs a consent banner, whether analytics or a session recorder runs before visitors agree, whether they are exposed to the "wiretapping" (CIPA) letters bloggers are getting, or what their Raptive or Mediavine ads do with Global Privacy Control. Also use for "is my blog compliant", "do I have a cookie banner", "what trackers are on my site", and before setting up a consent plugin, so its effect can be measured before and after. Measures what loads in a real browser, names the plugin or setting behind each tracker with a probe that makes no changes itself, and produces a private report and a plain-language reply. Not legal advice.
---

# Tracker and consent audit

Find out what a WordPress food blog sends to whom before a visitor agrees to
anything, who put each tracker there, and what Global Privacy Control changes.

## The core rule

**Measure what runs before consent in a real browser. Never infer it.** Plugin
lists, page source and the ad network's assurances all disagree with what a
browser actually loads. A consent plugin can be installed, switched on and still
block nothing. A sign-up form can be dead. A session recorder can honor GPC on
its own server. Only a logged run shows which.

## Sequence

1. **Scaffold.** `uv run scripts/new_audit.py https://www.example.com ~/Projects/example-privacy-audit --ad-network Mediavine --name "Example"`.
   The folder gets its own copy of every script, so a re-test months later runs the same code.
2. **Fill `scripts/site_config.py`.** Six real pages (home, a post, a category,
   search, contact, privacy policy), the fields a visitor can type into, and the
   trackers the site adds itself. Fetch the homepage with curl first and read the
   script tags: that tells you the ad network and the obvious trackers.
3. **Browser run, US.** Build the container, run `audit.py --visible` detached
   (commands in the folder's README). Six pages, plain and with GPC, about 12 minutes.
4. **Analyze.** `analyze.py`, then `form_test.py`, then `gpc_probe.py`.
5. **Site internals.** Ask the client (or Eric) to upload `tracker-audit-probe.php`
   to `wp-content/mu-plugins/` and create an Application Password. The **person**
   runs `fetch_inventory.py` in their own terminal and types the password at its
   hidden prompt, never on the command line. An agent's shell has no terminal for
   that prompt, so give the person the command. **Never ask for the Application
   Password in chat.** Then re-run `analyze.py`, and **delete the probe file and
   revoke the Application Password**. The probe stops answering 48 hours after
   upload; the password does not expire on its own and is a full admin login.
6. **Write findings.** Each finding is confirmed, likely, or an evidence gap. See
   `references/reporting.md`.
7. **Report.** Fill `report/template.html`, build it, run the accessibility audit
   on the built files, publish with the `publishing-behind-cloudflare-access` skill.
   The deploy folder already fails closed.
8. **Reply.** Plain language, answering the client's own questions first. Run the
   humanizer. Say it is not legal advice.

Background for the steps: `references/wordpress.md` (where trackers hide, the
probe, a database export, a local copy), `references/ad-networks.md` (Raptive,
Mediavine, GPC and GPP strings, UK and EU tests), `references/reporting.md`
(wording, outline, publishing).

## Ask, do not assume

- Whether to test UK and EU visitors (needs a VPN in an isolated VM or container, never machine-wide).
- Whether the probe may be uploaded, or a database export used instead (`references/wordpress.md`).
- Whether a report page is wanted, and who may open it.
- What may be removed. The audit itself changes nothing on the site apart from the probe and its Application Password.

## Safety

- The audit changes nothing on the live site except uploading and deleting the probe and adding and
  revoking its Application Password. The probe makes no changes itself and rolls back database writes
  made by the head and footer code it runs. It cannot undo file writes, cache writes, outbound requests,
  writes to non-InnoDB tables, DDL, or code that commits its own transaction; its response lists the
  non-InnoDB tables and the shutdown callbacks it removed. Like any visit, each call also runs the
  site's own per-request code, such as a request logger, which the probe does not roll back.
  Single-site WordPress only. WordPress also
  records when the Application Password was last used. Use containers for the browser and for any
  database copy.
- Delete the probe after use, and revoke the Application Password.
- Remove any database container with `podman rm --force --volumes`:
  without `--volumes`, the client's database survives in an anonymous volume.
- Never write policy or legal wording. Name what the policy misses; the wording is a lawyer's.

## Hazards from real runs

| Symptom | Cause | Fix |
|---|---|---|
| Container sits silent forever | `xvfb-run` as PID 1 waits for a signal | `podman run --init` |
| Run dies when the session restarts | background shell jobs die with it | `podman run --detach --name`, then `podman logs --follow` |
| Recorder uploads missing from the log | gzip bodies crash `post_data` | `body_text()` decompresses `post_data_buffer` |
| "Canary not found" | recorder sent nothing after the typing | `form_test.py` waits for an upload and reports the count |
| No sign-up field found | the newsletter form was deleted, its script still loads | test the comment form; report the dead embed |
| Recorder vanishes under GPC | the vendor's server returns a stub for `Sec-GPC: 1` | `gpc_probe.py` compares responses |
| Banner plugin active, no banner | installed, never configured | probe inventory lists its option names |
| Analytics in no plugin | pasted into theme settings (Genesis Header Scripts) | probe inventory names the option |
| Low ad counts | headless Chrome gets an ad-blocker flag | `--visible` under Xvfb for client numbers |
