# Reporting

## 1. Finding wording

Give every finding one label.

- **Confirmed.** Seen in the run. Say which run and which page.
- **Likely.** Strong indirect evidence, such as a saved setting with no browser
  proof. Say what is missing.
- **Evidence gap.** It could not be tested. Say why.

Never write "none found" alone. Say what was tested: which pages, which
visitors, which dates.

## 2. Report outline

The template has a short top section and nine numbered sections.

1. **Trackers from the site's own setup.** Each tracker, the plugin or setting
   behind it, and how you know.
2. **Trackers from the ad network's code.** The same list for the network.
3. **What runs before any consent choice.** The table of requests that fire
   before a visitor clicks anything.
4. **What Global Privacy Control changes.** Plain run against GPC run, with the
   `differs` results.
5. **Consent tools on the site.** What is installed, and whether it blocks
   anything.
6. **Forms and typed information.** Which fields reach a recorder or tracker.
7. **The privacy policy.** What it names and what it leaves out. No new wording.
8. **Evidence.** Run folder, dates, tools.
9. **Open questions.** What the client must answer.

## 3. Numbers that go to a client

Use numbers from a `--visible` run. Headless Chrome gets an ad-blocker flag and
shows low ad counts. Ad counts also change from run to run. Give one run's
numbers, say which run, and say they vary.

## 4. Not legal advice

Put one line in the report header and one in the reply: this is a technical
measurement, not legal advice. Never draft policy text or say a site is
"compliant" or "not compliant". Say what runs, and let a lawyer say what it means.

## 5. The reply

Order it like this.

1. Answer the client's own questions first, in their words.
2. What runs before consent.
3. Suggested fixes, lowest risk first. Say which ones change how the site looks.
4. The report link.
5. The questions the client must answer.

Keep it short and plain. Run the humanizer on it before it goes out.

## 6. Publishing

1. Build the report. The built files land in
   `.cloudflare/output/v0/workers/default/assets/`.
2. Run the accessibility audit on those built files, not on the template.
3. Report Worker names are `wm-` plus six hex characters. Before the first
   deploy, run `cf workers list` and check for a clash. A clash would put the
   report behind another client's Access policy.
4. Publish with the `publishing-behind-cloudflare-access` skill. Run
   `test_failclosed.sh` and open the link as an allowed person and as a stranger.
5. Never put client names, tracker IDs or screenshots in the skill repo.
