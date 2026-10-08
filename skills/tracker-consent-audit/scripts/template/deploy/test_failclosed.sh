#!/usr/bin/env bash
# Requests with no token, a junk token, and well-formed tokens with a bad
# signature must all get 403 and none of the report. Exits non-zero if any
# request gets another status or any report text.
#
# Usage: bash test_failclosed.sh <base URL>   (for example http://localhost:8790)
base="$1"
config="$(dirname "$0")/cloudflare.config.ts"
[ -f "$config" ] || { echo "No $config: keep this script next to cloudflare.config.ts."; exit 2; }
for i in $(seq 1 30); do curl -s -o /dev/null "$base/" && break; sleep 1; done
b64() { printf '%s' "$1" | base64 | tr -d '\n' | tr '+/' '-_' | tr -d '='; }
aud=$(sed -n 's/.*ACCESS_AUD: bindings\.text("\([^"]*\)").*/\1/p' "$config")
team=$(sed -n 's/.*ACCESS_TEAM: bindings\.text("\([^"]*\)").*/\1/p' "$config")
pay=$(b64 "{\"aud\":[\"$aud\"],\"iss\":\"$team\",\"exp\":9999999999}")
forged="$(b64 '{"alg":"RS256","kid":"test-key-id"}').$pay.$(b64 not-a-real-signature)"
nokid="$(b64 '{"alg":"RS256","kid":"unknown"}').$pay.$(b64 x)"
none="$(b64 '{"alg":"none"}').$pay."
failed=0
check() {
  local label="$1" path="$2"; shift 2
  local out code leak
  out=$(mktemp)
  code=$(curl -s -o "$out" -w '%{http_code}' "$@" "$base$path")
  leak=$(grep -c -E "Tracker Audit|<table" "$out")
  echo "$label $path -> $code | report text: $leak"
  if [ "$code" != 403 ] || [ "$leak" != 0 ]; then failed=1; fi
  rm -f "$out"
}
check "no token                " /
check "no token                " /fresh-home-top.jpg
check "junk token              " / -H "Cf-Access-Jwt-Assertion: junk"
check "forged sig, unknown key " / -H "Cf-Access-Jwt-Assertion: $forged"
check "unknown kid             " / -H "Cf-Access-Jwt-Assertion: $nokid"
check "alg none                " / -H "Cf-Access-Jwt-Assertion: $none"
# The cases above stop at the key lookup. This one reaches the signature check:
# a real key ID from the team's key list, the real aud and iss, and a junk
# signature. It needs ACCESS_TEAM and ACCESS_AUD filled in, so it runs only then.
case "$aud$team" in
  *__*)
    echo "forged sig, real key id  skipped: fill ACCESS_TEAM and ACCESS_AUD to test a forged signature with a real key id"
    ;;
  *)
    realkid=$(curl -s "$team/cdn-cgi/access/certs" | grep -o '"kid" *: *"[^"]*"' | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/')
    if [ -z "$realkid" ]; then
      echo "forged sig, real key id  FAILED: no kid in $team/cdn-cgi/access/certs"
      failed=1
    else
      realforged="$(b64 "{\"alg\":\"RS256\",\"kid\":\"$realkid\"}").$pay.$(b64 not-a-real-signature)"
      check "forged sig, real key id " / -H "Cf-Access-Jwt-Assertion: $realforged"
    fi
    ;;
esac
if [ "$failed" != 0 ]; then echo "FAIL: a request was not refused, or got report text"; fi
exit "$failed"
