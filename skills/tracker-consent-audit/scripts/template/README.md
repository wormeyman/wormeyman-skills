# __SITE_NAME__ tracker and consent audit

Site: __SITE__ (ads by __AD_NETWORK__). Started __DATE__.

**Start here.** Scaffolded by the tracker-consent-audit skill. Everything below runs from this folder.

## Where things stand

- [ ] `scripts/site_config.py` filled in (pages, form fields, site vendors)
- [ ] Browser audit run: `results/<run-id>/`
- [ ] Probe inventory fetched, probe file deleted from the site, Application Password revoked
- [ ] Findings written, report built and audited for accessibility
- [ ] Report published behind Access, link checked
- [ ] Reply sent

## How to re-run

    podman build --tag tracker-audit --file container/Containerfile container
    podman run --detach --name tracker-audit-us --init --shm-size=2g --volume "$PWD":/work tracker-audit \
      xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" uv run scripts/audit.py --visible
    podman logs --follow tracker-audit-us
    uv run scripts/analyze.py results/<run-id>
    podman run --rm --init --shm-size=2g --volume "$PWD":/work tracker-audit \
      xvfb-run --auto-servernum uv run scripts/form_test.py results/<run-id> --visible
    uv run scripts/gpc_probe.py results/<run-id>
    uv run scripts/fetch_inventory.py results/<run-id> --user <admin>   # type the password at the prompt

Then delete the probe file from the site and revoke the Application Password.

`--init` is required: `xvfb-run` hangs when it is the container's first process.

## Things not in this folder

- Any site export or database dump. If one was used, say where it was and when it was deleted.
