#!/usr/bin/env bash
# Requests with no token, a junk token, and a well-formed token with a bad
# signature must all get 403 and none of the report.
base="$1"
for i in $(seq 1 30); do curl -s -o /dev/null "$base/" && break; sleep 1; done
b64() { printf '%s' "$1" | base64 -w0 | tr '+/' '-_' | tr -d '='; }
kid=test-key-id
hdr=$(b64 "{\"alg\":\"RS256\",\"kid\":\"$kid\"}")
pay=$(b64 '{"aud":["__ACCESS_AUD__"],"iss":"__ACCESS_TEAM__","exp":9999999999}')
forged="$hdr.$pay.$(b64 not-a-real-signature)"
nokid="$(b64 '{"alg":"RS256","kid":"unknown"}').$pay.$(b64 x)"
none="$(b64 '{"alg":"none"}').$pay."
check() {
  local label="$1" path="$2"; shift 2
  local out code leak
  out=$(mktemp)
  code=$(curl -s -o "$out" -w '%{http_code}' "$@" "$base$path")
  leak=$(grep -c -E "Tracker Audit|<table" "$out")
  echo "$label $path -> $code | report text: $leak"
  rm -f "$out"
}
check "no token     " /
check "no token     " /fresh-home-top.jpg
check "junk token   " / -H "Cf-Access-Jwt-Assertion: junk"
check "forged sig   " / -H "Cf-Access-Jwt-Assertion: $forged"
check "unknown kid  " / -H "Cf-Access-Jwt-Assertion: $nokid"
check "alg none     " / -H "Cf-Access-Jwt-Assertion: $none"
