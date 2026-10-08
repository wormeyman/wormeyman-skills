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

`gpc_probe.py` prints counts. It writes the decoded strings and the unparsed list
to `gpc-probe.json`, under the keys `gpp_plain`, `gpp_gpc`, `usp_plain`,
`usp_gpc`, `unparsed_plain` and `unparsed_gpc`.

- **`us_privacy`** has four characters: version, notice given, opted out of sale,
  and a legal agreement flag. `1YNY` means not opted out. `1YYY` means opted out.
- **GPP strings** hold fields for sale, sharing and targeted advertising, plus a
  GPC flag. The script reads them only if they match the real format. Anything
  else is listed as `unparsed`.
- **Placeholders** such as `[GPP]` or `${GPP}` are templates in a script's code.
  They are not values. Do not report them as strings.

`gpc_probe.py` also compares each site-vendor script. It fetches the script twice
without GPC and once with it. A `differs` result has a `basis`:

- **`exact`**: both plain copies are the same, byte for byte, and the GPC copy
  is different.
- **`size`**: the plain copies differ a little (a value that changes on every
  request) but are nearly the same size, and the GPC copy's size is far off.
  This is how Microsoft Clarity shows up: it sends a short stub instead of its
  recorder when GPC is on. Check every `size` result by hand before it becomes
  a finding. A short error page or a longer body can also cause it.

A script that changes on every fetch, with no clear size gap, is shown as
`unstable`. A failed or blocked fetch is shown as not comparable. A
`status_mismatch` (for example a 204 or a 403 only under GPC) is not counted as
`differs`, but it can be a real GPC effect: check it by hand too. Report
`differs` with basis `exact` as measured. Report a `size` result or a status
mismatch only after the hand check, and say what you checked.

## 5. UK and EU testing

Run this only after the client agrees.

1. Use an isolated VM or container with its own VPN tunnel. Never route the whole
   machine through a VPN.
2. Make three visits: leave the banner alone, press Accept All, and press Reject
   All. Log each one.
3. Read `__tcfapi` in the page to see what the consent record says.
4. Trust the result for the site's own trackers. Do not trust it for ad counts,
   because a VPN address changes which ads load.
