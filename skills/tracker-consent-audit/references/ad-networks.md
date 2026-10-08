# Ad networks, GPC and GPP

## 1. What the network covers and what it does not

An ad network handles its own ads. That means its US opt-out link, how its code
treats Global Privacy Control (GPC), and a consent box for visitors in the UK
and EU.

It does not cover the blogger's own trackers. Analytics, a session recorder, a
pixel or a sign-up form that the blogger added sit outside the network's
promises. Most of the exposure in an audit sits in that gap. Test the network's
claims and the blogger's own tools as two separate lists.

## 2. Raptive

- UK and EU visitors get a consent box from consentmanager.net (CMP 31). "Reject
  All" is on the second screen.
- Under GPC, the `us_privacy` string changes from `1YNY` to `1YYY`. The third
  letter is the opt-out of sale. Read it in the logged requests.
- Pressable hosting adds Gauges analytics. That one is the host's, not Raptive's.

## 3. Mediavine

- UK and EU visitors get a consentmanager box.
- Grow is Mediavine's tool. Check what it loads.
- The "Do Not Sell or Share" link is injected by Mediavine's script. It is not in
  the theme.
- Mediavine uses GPP US National strings (section 4).

## 4. Reading GPP and us_privacy

`gpc_probe.py` prints the strings it finds for the plain run and the GPC run.

- **`us_privacy`** has four characters: version, notice given, opted out of sale,
  and a legal agreement flag. `1YNY` means not opted out. `1YYY` means opted out.
- **GPP strings** hold fields for sale, sharing and targeted advertising, plus a
  GPC flag. The script reads them only if they match the real format. Anything
  else is listed as `unparsed`.
- **Placeholders** such as `[GPP]` or `${GPP}` are templates in a script's code.
  They are not values. Do not report them as strings.

`gpc_probe.py` also compares each site-vendor script. It fetches the script twice
without GPC and once with it. It reports `differs` only when both plain copies
match each other and the GPC copy is different. A script that changes on every
fetch is shown as `unstable`. A failed or blocked fetch is shown as not
comparable. Treat only `differs` as a finding. This is how a vendor that hides
its recorder from GPC requests shows up.

## 5. UK and EU testing

Run this only after the client agrees.

1. Use an isolated VM or container with its own VPN tunnel. Never route the whole
   machine through a VPN.
2. Make three visits: leave the banner alone, press Accept All, and press Reject
   All. Log each one.
3. Read `__tcfapi` in the page to see what the consent record says.
4. Trust the result for the site's own trackers. Do not trust it for ad counts,
   because a VPN address changes which ads load.
