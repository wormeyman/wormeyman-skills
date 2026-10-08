# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Decode the privacy strings ad code passes to its partners.

GPP (Global Privacy Platform) strings carry a header listing section IDs, then
one segment per section. Only section 7, US National, is decoded here: the
sale, sharing and targeted-advertising opt-out fields and the GPC flag. The
older us_privacy string is four characters: version, notice, opt-out, LSPA.
"""

B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
OPT_OUT = {0: "not applicable", 1: "opted out", 2: "did not opt out"}
USP_FLAG = {"Y": "yes", "N": "no", "-": "not applicable"}


def _bits(segment: str) -> str:
    try:
        return "".join(format(B64.index(c), "06b") for c in segment)
    except ValueError as err:
        raise ValueError(f"not base64url: {segment!r}") from err


def _fib_int(b: str, i: int) -> tuple[int, int]:
    """One Fibonacci-coded integer starting at bit i; returns (value, next index)."""
    fib = [1, 2]
    value, prev, k = 0, "0", 0
    while True:
        if i >= len(b):
            raise ValueError("Fibonacci integer runs past the end")
        bit = b[i]
        if bit == "1" and prev == "1":
            return value, i + 1
        while len(fib) <= k:
            fib.append(fib[-1] + fib[-2])
        if bit == "1":
            value += fib[k]
        prev, k, i = bit, k + 1, i + 1


def _section_ids(header: str) -> list[int]:
    b = _bits(header)
    if len(b) < 24 or int(b[0:6], 2) != 3:
        raise ValueError("not a GPP header")
    count = int(b[12:24], 2)
    i, last, ids = 24, 0, []
    for _ in range(count):
        if i >= len(b):
            raise ValueError("header ends early")
        is_range = b[i] == "1"
        start, i = _fib_int(b, i + 1)
        start += last
        end = start
        if is_range:
            span, i = _fib_int(b, i)
            end = start + span
        ids.extend(range(start, end + 1))
        last = end
    return ids


def _usnat(section: str) -> dict:
    core, *subs = section.split(".")
    b = _bits(core)
    if len(b) < 24:
        raise ValueError("US National section too short")
    out = {
        "version": int(b[0:6], 2),
        "sale_opt_out": OPT_OUT.get(int(b[18:20], 2), "unknown"),
        "sharing_opt_out": OPT_OUT.get(int(b[20:22], 2), "unknown"),
        "targeted_advertising_opt_out": OPT_OUT.get(int(b[22:24], 2), "unknown"),
    }
    for sub in subs:
        sb = _bits(sub)
        if len(sb) >= 3 and int(sb[0:2], 2) == 1:
            out["gpc"] = sb[2] == "1"
    return out


def decode(gpp: str) -> dict:
    if not gpp or "~" not in gpp:
        raise ValueError(f"not a GPP string: {gpp!r}")
    header, *sections = gpp.split("~")
    if not all(sections):
        raise ValueError("empty GPP section")
    ids = _section_ids(header)
    result: dict = {"section_ids": ids}
    for sid, sec in zip(ids, sections):
        if sid == 7:
            result["usnat"] = _usnat(sec)
    return result


def decode_usp(s: str) -> dict:
    if len(s) != 4 or not s[0].isdigit() or any(c not in USP_FLAG for c in s[1:]):
        raise ValueError(f"not a us_privacy string: {s!r}")
    return {
        "version": int(s[0]),
        "notice_given": USP_FLAG[s[1]],
        "opted_out_of_sale": USP_FLAG[s[2]],
        "lspa_covered": USP_FLAG[s[3]],
    }
