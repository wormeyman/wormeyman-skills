// The tracker-audit report: static files, plus a small Worker (src/index.ts)
// that runs first on every request and returns 403 unless the request carries a
// valid Cloudflare Access token for this app. No secrets.
//
// The name IS the public hostname. Access hides the page, not the URL, so the
// name says nothing about the client or the subject. DO NOT RENAME once the link
// is shared: a rename creates a new Worker with no Access app.
//
// Order (see the publishing-behind-cloudflare-access skill):
// 0. Check this name is not already in `cf workers list`. A clash overwrites another
//    report Worker, which sits behind another client's Access policy.
// 1. Deploy with workersDev: false.  2. Create the Access app and policy.
// 3. Fill ACCESS_AUD and ACCESS_TEAM.  4. Set workersDev: true, deploy, and check
//    every path returns 302 to the login.
// If your cf login reaches more than one account, add accountId: "<id>" at the top level.
import { bindings, defineConfig } from "cf/config";
import * as entrypoint from "./src/index.ts" with { type: "cf-worker" };

export default defineConfig({
	worker: {
		name: "__WORKER_NAME__",
		compatibilityDate: "2026-10-07",
		entrypoint,
		assets: { notFoundHandling: "none", runWorkerFirst: true },
		env: {
			ASSETS: bindings.assets(),
			// The Access application's AUD tag. A recreated app has a new one.
			ACCESS_AUD: bindings.text("__ACCESS_AUD__"),
			// https://<team>.cloudflareaccess.com
			ACCESS_TEAM: bindings.text("__ACCESS_TEAM__"),
		},
		workersDev: false,
		// Off on purpose: each Preview URL is a second public hostname per version.
		previewUrls: false,
		observability: { enabled: true },
	},
});
