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
- **Server-side collection.** Some plugins send visitor data from the server, so
  no browser run sees it. The Microsoft Clarity plugin (seen in version 0.10.35)
  logs every GET request outside wp-admin on `shutdown`, REST calls included:
  the visitor's IP address, user agent and URL. It stores them in its
  `clarity_collect_events` table. A WP-Cron job removes them and posts them to
  `ai.clarity.ms/collect` in batches. The code asks for every 5 minutes, but
  WP-Cron runs only when a request reaches WordPress, so on a cached site the
  gaps are longer: one export held 15 requests from about 5 hours. It does not
  check consent or GPC first. To spot it, the probe's plugin list gives the
  version. On an export or a local copy, look for rows in
  `<prefix>clarity_collect_events`. The table holds only the requests since the
  last send.
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
- **Writes outside those hooks.** The rollback covers only the code the probe
  runs itself: the switch to a visitor and the head, footer, body-open and
  enqueue callbacks. Code that runs on every request, at `init` or on
  `shutdown`, still makes its usual writes. That is the same as for any visit,
  but it shows up if you compare table checksums before and after a probe call.
  On a local copy, make one plain request first (for example
  `/wp-json/wp/v2/users/me` with the same login) and compare against that. A
  request logger, such as the Clarity plugin's, still adds one row per call.
  The probe should add nothing beyond what the plain request added. A request
  can also add core's `theme_roots` transient, after a restore or once the
  cached theme list expires.
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

Keep every container off the internet. `WP_HTTP_BLOCK_EXTERNAL` only stops
WordPress's own web functions. A plugin that opens its own connection (PHP's
curl, `file_get_contents`) skips it, and a restored copy runs plugins that talk
to ad, analytics and CDN services. An internal podman network cuts the
containers off, while a port published on 127.0.0.1 still answers.

1. Make a folder for the copy, and an internal network:
   `podman network create --internal audit-net`.
2. Download the free All-in-One WP Migration zip from wordpress.org on the host,
   and get a paid extension zip from the client or from Eric. The free plugin
   (measured on 7.112) refuses `wp ai1wm restore`. The Unlimited Extension
   works, and so does a storage extension such as Google Drive. Do not copy any
   purchase link into a repo or a report.
3. Start `mariadb:10.6` on that network with a database, user and password.
4. Start `wordpress:php8.3-apache` on the same network, with the folder's docroot
   bind-mounted and `-p 127.0.0.1:<port>:80`. Run `wordpress:cli` against the
   same mount for WP-CLI, with `--user 0:0` so it can write to `wp-content`. Use
   `wp --allow-root`. That image's MariaDB client insists on TLS, so `wp db query`
   fails. Run SQL with `podman exec <db container> mariadb` instead.
5. Install WordPress, then both plugins from their zip files (mount the zips into
   the WP-CLI container). This works with no internet: measured with the Google
   Drive extension, through backup and restore.
6. Set `WP_HTTP_BLOCK_EXTERNAL` and `DISABLE_WP_CRON` to `true` in `wp-config.php`
   as well. They stop WordPress from trying, and they stop the client's
   scheduled jobs. Check the imported plugin list too: a copied database turns
   back on plugins that talk to backups, CDNs and ad services.
7. Run `wp ai1wm restore` on the backup file.
8. Check the cut-off before you load anything: from inside the web container,
   `curl https://1.1.1.1/` must fail with exit code 7.
9. Clean up when done: `podman rm --force --volumes` on every container, the
   WP-CLI ones too, since that image declares a volume. Then
   `podman network rm audit-net`, then delete the folder. Run `podman volume ls`
   to check.
