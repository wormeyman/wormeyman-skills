# WordPress: where trackers hide and how to see inside

## 1. Where trackers hide

Page source shows that a tracker loads. It does not show who added it. Look in
these places.

- **Plugins.** MonsterInsights (Google Analytics), Microsoft Clarity, Meta for
  WordPress (the Facebook pixel) and Jetpack (stats) are the usual ones.
- **Theme settings.** Genesis keeps header and footer scripts in the
  `genesis-settings` option, under `header_scripts` and `footer_scripts`. Many
  bloggers paste a Google tag there and forget it.
- **Code Snippets.** The plugin stores PHP and HTML snippets in its own table.
- **Leftover settings.** Insert Headers and Footers keeps its saved scripts after
  the plugin is deleted, and some other code may still print them.
- **Hosting.** Some hosts add analytics for you. Pressable adds Gauges. Some sites
  turn on Cloudflare Web Analytics at the edge, with no plugin at all.

The probe (section 3) reads these places and names the option or plugin behind
each tracker.

## 2. Consent plugins that do nothing

A consent plugin can be installed and active and still block nothing. Signs of
this: its saved options hold only bookkeeping values, such as a version number
or a "setup done" flag, and no list of blocked scripts or categories. The run
shows the same trackers firing before and after a click.

Older banner plugins leave settings behind too. A deactivated banner plugin with
saved options is a leftover, not a live control. Report which one it is, and
what you saw in the browser.

## 3. The probe

`tracker-audit-probe.php` is a small must-use plugin. It lets `fetch_inventory.py`
read the site's real head and footer output and its active plugins and options.

- **Single-site WordPress only.** That is the supported case. On a multisite
  network, a sub-site's administrator could see the whole network's plugin list
  through the probe, and network-wide plugins are not listed as active. Do not
  use it on multisite.
- **Upload.** Put it in `wp-content/mu-plugins/`. Create that folder if it is
  missing. It loads on its own and needs no activation.
- **Application Password.** In WordPress, open Users, then Profile, and add one
  under Application Passwords. WordPress shows it once. The script asks for it at
  a hidden prompt. Never paste it into a command line, a chat or a file.
- **48-hour expiry.** The probe stops answering 48 hours after the upload. The
  clock is the file's time on the server, and a time in the future also counts
  as expired. An upload tool that keeps file times (`rsync -a`, `scp -p`, some
  SFTP clients) can make a fresh copy look old, so re-save the file on the
  server. The password does not expire. It is a full admin login until someone
  revokes it.
- **Admin notice.** While it is installed, the probe shows a notice in the
  dashboard, so no one forgets it is there.
- **What it returns.** WordPress and PHP versions. The theme and parent theme
  (slug, name, version). Active plugins with versions. The file names of
  must-use plugins. Every head, footer, body-open and enqueue callback, with its
  file and owner. The third-party hosts and tracker IDs in what each callback
  prints. Enqueued script URLs. The first 300 characters of each callback's
  printed markup, which is the same markup any visitor sees in the page source.
  Option names with the tracker IDs they matched. Consent plugins' option names.
  It also lists what its rollback could not cover: tables that are not InnoDB,
  whether a `db.php` drop-in replaces the database layer, and any shutdown
  callbacks the site's code added, which the probe removed without running.
- **What it never returns.** Users, comments, subscribers, form entries, or
  option values beyond the matched tracker IDs. The markup excerpt is not
  filtered for secrets, so treat the output as you would page source.
- **Changes.** The probe makes no changes itself. It runs the head and footer
  code inside a database transaction and rolls it back. If the transaction cannot
  start, it runs no plugin code and returns an error. The rollback cannot undo:
  writes to the tables in `non_innodb_tables`, DDL (it commits on its own), code
  that commits its own transaction, persistent object caches, file writes and
  outbound requests. Shutdown work that the code queues is removed before it can
  run and listed in `removed_shutdown_callbacks`. WordPress records when the
  Application Password was last used.
- **Cached admin data.** The probe switches to an anonymous visitor before it
  runs any hook. A plugin that saved the administrator's details at `init`,
  before that switch, may still print them, so they can show up in an excerpt.
- **A limit.** It runs the head and footer hooks during a REST request, not a
  page view. Code that depends on which page is shown (the front page, a single
  post) may be missing. The browser audit shows what visitors actually get.
- **A callback that calls `exit`.** It ends the response early. The script then
  names the callback, from the `X-Tracker-Audit-Current` header.
- **Pretty permalinks off.** `/wp-json/` gives a 404. The script retries with
  `/?rest_route=`.
- **Security plugins.** Some turn off Application Passwords, so every call gets a
  401. The script says that is the likely cause.
- **Clean up.** Delete the file, then revoke the Application Password. Do both
  the same day.

## 4. Fallback: a database export

Use this when the client cannot upload a file.

1. Start MariaDB in podman, matched to the host's version, with `--network none`.
   The client's data must not reach the network.
2. Load the dump. Many dumps run `CREATE DATABASE` and `USE` themselves, so do
   not assume the database name.
3. Check the table prefixes. Some exports hold several sites. Pick the prefix
   whose `siteurl` matches the site.
4. Query `active_plugins` and the options that hold tracker IDs or scripts.
5. Clean up: `podman rm --force --volumes <container>`. Then run `podman volume ls`
   and confirm no anonymous volume is left. Delete the dump file too.

An export shows settings, not behavior. Mark anything you read from it as likely
until the browser run confirms it.

## 5. A local copy for testing

Use this when you want to test a change, such as a consent plugin, on a copy
instead of the live site. Use plain podman. DDEV does the same job where
podman's API can copy files into a container, but on a rootless podman where
that call fails (measured on podman 6.1.3), DDEV does not start. Bind mounts
avoid that path.

1. Make a folder for the copy, and a network: `podman network create audit-net`.
2. Start `mariadb:10.6` on that network with a database, user and password.
3. Start `wordpress:php8.3-apache` on the same network, with the folder's docroot
   bind-mounted. Run `wordpress:cli` against the same mount for WP-CLI. Use
   `wp --allow-root`.
4. Install All-in-One WP Migration and its Unlimited Extension **before** you
   block outbound requests. Both download and check themselves online. Get the
   extension from the client or from Eric. Do not copy any purchase link into a
   repo or a report.
5. Set `WP_HTTP_BLOCK_EXTERNAL` and `DISABLE_WP_CRON` to `true` in `wp-config.php`.
   Now the copy cannot call live services or run the client's scheduled jobs.
   Check the imported plugin list too: a copied database turns back on plugins
   that talk to backups, CDNs and ad services.
6. Run `wp ai1wm restore` on the backup file.
7. Clean up when done: `podman rm --force --volumes` on both containers, then
   `podman network rm audit-net`, then delete the folder. Run `podman volume ls`
   to check.
