// Fail closed: serve the report only to requests that carry a valid Cloudflare
// Access token for this Worker's Access application.
//
// Access normally stops strangers before they reach this code. This check is
// for the day the Access app is missing: a static-only Worker whose Access app
// is deleted serves the report to anyone, and keeps no request log to show who
// saw it. With this check, a missing app means 403, not a public page.

interface Env {
	ASSETS: Fetcher;
	/** The Access application's AUD tag. */
	ACCESS_AUD: string;
	/** The Access team URL, e.g. https://<team>.cloudflareaccess.com */
	ACCESS_TEAM: string;
}

interface Jwk extends JsonWebKey {
	kid: string;
}

let keyCache: { keys: Map<string, CryptoKey>; fetched: number } | undefined;
const KEY_CACHE_MS = 60 * 60 * 1000;
let lastForcedFetch = 0;

async function accessKeys(team: string, force = false): Promise<Map<string, CryptoKey>> {
	if (!force && keyCache && Date.now() - keyCache.fetched < KEY_CACHE_MS) return keyCache.keys;
	const res = await fetch(`${team}/cdn-cgi/access/certs`);
	if (!res.ok) throw new Error(`certs ${res.status}`);
	const { keys } = (await res.json()) as { keys: Jwk[] };
	const map = new Map<string, CryptoKey>();
	for (const jwk of keys) {
		const key = await crypto.subtle.importKey(
			"jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"],
		);
		map.set(jwk.kid, key);
	}
	keyCache = { keys: map, fetched: Date.now() };
	return map;
}

function b64url(part: string): Uint8Array {
	const b64 = part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "=");
	return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

async function validAccessToken(token: string, env: Env): Promise<boolean> {
	const parts = token.split(".");
	if (parts.length !== 3) return false;
	const [h, p, s] = parts;
	const header = JSON.parse(new TextDecoder().decode(b64url(h))) as { alg?: string; kid?: string };
	if (header.alg !== "RS256" || !header.kid) return false;
	let key = (await accessKeys(env.ACCESS_TEAM)).get(header.kid);
	// Access rotates its keys; refetch before rejecting an unknown key id, at most once a minute.
	if (!key && Date.now() - lastForcedFetch > 60_000) {
		lastForcedFetch = Date.now();
		key = (await accessKeys(env.ACCESS_TEAM, true)).get(header.kid);
	}
	if (!key) return false;
	const signed = new TextEncoder().encode(`${h}.${p}`);
	if (!(await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64url(s), signed))) return false;
	const claims = JSON.parse(new TextDecoder().decode(b64url(p))) as {
		aud?: string | string[]; iss?: string; exp?: number; nbf?: number;
	};
	const now = Math.floor(Date.now() / 1000);
	const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
	return (
		aud.includes(env.ACCESS_AUD) &&
		claims.iss === env.ACCESS_TEAM &&
		typeof claims.exp === "number" && claims.exp > now &&
		(claims.nbf === undefined || claims.nbf <= now + 60)
	);
}

export default {
	async fetch(request, env) {
		const token = request.headers.get("Cf-Access-Jwt-Assertion");
		let ok = false;
		if (token) {
			try {
				ok = await validAccessToken(token, env);
			} catch {
				ok = false; // a broken token or an unreachable key list never opens the door
			}
		}
		if (!ok) {
			return new Response("Forbidden", {
				status: 403,
				headers: { "content-type": "text/plain", "cache-control": "no-store" },
			});
		}
		const res = await env.ASSETS.fetch(request);
		const out = new Response(res.body, res);
		out.headers.set("cache-control", "private, no-store");
		return out;
	},
} satisfies ExportedHandler<Env>;
