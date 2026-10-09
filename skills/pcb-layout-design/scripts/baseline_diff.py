#!/usr/bin/env python3
"""Compare two placement JSON files and report changes to the parts that must not move.

    baseline_diff.py baseline.json current.json [--refs J1,H1] [--classes connector,mech] [--all]
                     [--tol-mm 0.01] [--tol-deg 0.5] [--list-others]

Save the importer output (placement_from_kicad.py / placement_from_easyeda.js) as baseline.json once the fixed items
are confirmed, and set "locked": true on them. Take current.json the same way after script runs, part replacements,
syncs and bulk moves. Watched: parts with "locked": true, plus --refs, plus every part of --classes (none by default),
or everything with --all. Compared for watched parts: position, rotation (rot_actual when the importer wrote one),
side and courtyard size. Always compared: board size and origin, and the keep-outs (removed, moved, resized or
loosened through a longer "allow" list; an added keep-out is INFO). Not compared: stackup, rules, zones.

ERROR  MOVED / ROTATED / SIDE / SIZE / REMOVED / OUTLINE / KEEPOUT   restore it, or re-save the baseline after the
                                                                    user confirms the change
INFO   changes of unwatched parts, added parts and keep-outs
Exit code 1 when an ERROR is reported, 2 for unusable input (unreadable file, duplicate refs, non-numeric values) and
when no part is watched - a comparison that watches nothing would always pass.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter

NUM = ("x", "y", "w", "h", "rot", "rot_actual")


class InputError(ValueError):
    pass


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise InputError(f"{what} is not a finite number: {v!r}")
    return float(v)


def validate(d, name):
    """Raise InputError for anything compare() could not handle reliably."""
    if not isinstance(d, dict) or not isinstance(d.get("parts"), list):
        raise InputError(f"{name}: no 'parts' list")
    refs = []
    for i, p in enumerate(d["parts"]):
        if not isinstance(p, dict) or not isinstance(p.get("ref"), str) or not p["ref"]:
            raise InputError(f"{name}: part #{i} has no 'ref'")
        for k in ("x", "y"):
            _num(p.get(k), f"{name}: {p['ref']}.{k}")
        for k in NUM[2:]:
            if p.get(k) is not None:
                _num(p[k], f"{name}: {p['ref']}.{k}")
        if p.get("side") not in (None, "top", "bottom", "both"):
            raise InputError(f"{name}: {p['ref']}.side must be top, bottom or both")
        if "locked" in p and not isinstance(p["locked"], bool):
            raise InputError(f"{name}: {p['ref']}.locked must be true or false")
        refs.append(p["ref"])
    dup = sorted(r for r, n in Counter(refs).items() if n > 1)
    if dup:
        raise InputError(f"{name}: duplicate refs {', '.join(dup[:10])} - give them unique names (the importers do)")
    b = d.get("board")
    if b is not None:
        if not isinstance(b, dict):
            raise InputError(f"{name}: 'board' is not an object")
        for k in ("w", "h"):
            if k in b:
                _num(b[k], f"{name}: board.{k}")
        if "origin" in b and (not isinstance(b["origin"], list) or len(b["origin"]) != 2):
            raise InputError(f"{name}: board.origin must be [x, y]")
        for v in b.get("origin", []):
            _num(v, f"{name}: board.origin")
    ks = d.get("keepouts", [])
    if not isinstance(ks, list):
        raise InputError(f"{name}: 'keepouts' is not a list")
    for k in ks:
        if not isinstance(k, dict):
            raise InputError(f"{name}: keep-out {k!r} is not an object")
        kn = k.get("name", "unnamed")
        if not isinstance(kn, str):
            raise InputError(f"{name}: keep-out name {kn!r} is not a string")
        if ("rect" in k) == ("circle" in k):
            raise InputError(f"{name}: keep-out {kn} needs exactly one of rect [x1,y1,x2,y2] or circle [cx,cy,r]")
        geo, n = (k["rect"], 4) if "rect" in k else (k["circle"], 3)
        if not isinstance(geo, list) or len(geo) != n:
            raise InputError(f"{name}: keep-out {kn} needs rect [x1,y1,x2,y2] or circle [cx,cy,r]")
        for v in geo:
            _num(v, f"{name}: keep-out {kn}")
        if k.get("side") not in (None, "top", "bottom", "both"):
            raise InputError(f"{name}: keep-out {kn}.side must be top, bottom or both")
        if "allow" in k and (not isinstance(k["allow"], list) or not all(isinstance(r, str) for r in k["allow"])):
            raise InputError(f"{name}: keep-out {kn}.allow must be a list of refs")


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        validate(d, path)
        return d
    except (OSError, ValueError) as e:
        print(f"unusable input: {e}", file=sys.stderr)
        raise SystemExit(2)


def adiff(a, b):
    """smallest angle between two rotations in degrees"""
    d = (a - b) % 360.0
    return min(d, 360.0 - d)


def _keepouts(d):
    """name -> keep-out; unnamed or repeated names get an index so none collapses into another."""
    out, seen = {}, Counter()
    for k in d.get("keepouts", []):
        n = k.get("name") or "unnamed"
        seen[n] += 1
        out[n if seen[n] == 1 else f"{n}#{seen[n]}"] = k
    return out


def watched_refs(base, refs=(), classes=(), watch_all=False):
    bp = {p["ref"]: p for p in base["parts"]}
    if watch_all:
        return set(bp)
    return (set(refs) & set(bp)) | {r for r, p in bp.items() if p.get("locked") is True or p.get("class") in classes}


def _rot(p):
    return p["rot_actual"] if p.get("rot_actual") is not None else (p.get("rot") or 0)


def compare(base, cur, tol_mm=0.01, tol_deg=0.5, refs=(), classes=(), watch_all=False):
    """-> (errors, infos). base / cur are validated placement dicts."""
    bp = {p["ref"]: p for p in base["parts"]}
    cp = {p["ref"]: p for p in cur["parts"]}
    watched = watched_refs(base, refs, classes, watch_all)
    errors, infos = [], []
    unknown = sorted(set(refs) - set(bp))
    if unknown:
        infos.append(f"--refs not in the baseline: {', '.join(unknown)}")
    for r in sorted(bp):
        if r not in cp:
            (errors if r in watched else infos).append(f"REMOVED {r}")
            continue
        b, c = bp[r], cp[r]
        msgs = []
        dx, dy = c["x"] - b["x"], c["y"] - b["y"]
        if math.hypot(dx, dy) > tol_mm:
            msgs.append(f"MOVED {r} by ({dx:+.3f}, {dy:+.3f}) mm to ({c['x']:.3f}, {c['y']:.3f})")
        rb, rc = _rot(b), _rot(c)
        if adiff(rc, rb) > tol_deg:
            msgs.append(f"ROTATED {r} {rb:g} -> {rc:g} deg")
        sb, sc = b.get("side") or "top", c.get("side") or "top"
        if sb != sc:
            msgs.append(f"SIDE {r} {sb} -> {sc}")
        if any(abs((c.get(k) or 0) - (b.get(k) or 0)) > tol_mm for k in ("w", "h")):
            msgs.append(f"SIZE {r} {b.get('w')} x {b.get('h')} -> {c.get('w')} x {c.get('h')} mm")
        if msgs:
            (errors if r in watched else infos).extend(msgs)
    added = sorted(set(cp) - set(bp))
    if added:
        infos.append(f"{len(added)} part(s) not in the baseline: {', '.join(added[:12])}{' ...' if len(added) > 12 else ''}")
    bb, cb = base.get("board"), cur.get("board")
    if bb is not None and cb is None:
        errors.append("OUTLINE board missing from the current file")
    elif bb and cb:
        for k in ("w", "h"):
            if k in bb and abs(bb[k] - cb.get(k, float("nan"))) <= tol_mm:
                continue
            if k in bb:
                errors.append(f"OUTLINE {k} {bb[k]:g} -> {cb.get(k)} mm")
        if "origin" in bb and ("origin" not in cb or max(abs(a - c) for a, c in zip(bb["origin"], cb["origin"])) > tol_mm):
            errors.append(f"OUTLINE origin {bb['origin']} -> {cb.get('origin')}")
    kb, kc = _keepouts(base), _keepouts(cur)
    for n in sorted(set(kb) | set(kc)):
        if n not in kc:
            errors.append(f"KEEPOUT {n} removed")
        elif n not in kb:
            infos.append(f"KEEPOUT {n} added")
        else:
            gb, gc = kb[n].get("rect", kb[n].get("circle")), kc[n].get("rect", kc[n].get("circle"))
            if len(gb) != len(gc) or any(abs(x - y) > tol_mm for x, y in zip(gb, gc)):
                errors.append(f"KEEPOUT {n} changed {gb} -> {gc}")
            if (kb[n].get("side") or "both") != (kc[n].get("side") or "both"):
                errors.append(f"KEEPOUT {n} side {kb[n].get('side') or 'both'} -> {kc[n].get('side') or 'both'}")
            loosened = sorted(set(kc[n].get("allow", [])) - set(kb[n].get("allow", [])))
            if loosened:
                errors.append(f"KEEPOUT {n} now allows {', '.join(loosened)}")
    return errors, infos


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 2)[2])
    ap.add_argument("baseline")
    ap.add_argument("current")
    ap.add_argument("--tol-mm", type=float, default=0.01)
    ap.add_argument("--tol-deg", type=float, default=0.5)
    ap.add_argument("--refs", default="", help="comma separated references to watch in addition to locked parts")
    ap.add_argument("--classes", default="", help="watch every part of these classes too, e.g. connector,mech")
    ap.add_argument("--all", action="store_true", help="watch every part")
    ap.add_argument("--list-others", action="store_true", help="print each INFO change instead of a count")
    a = ap.parse_args(argv)
    if a.tol_mm < 0 or a.tol_deg < 0:
        ap.error("tolerances must not be negative")
    base, cur = load(a.baseline), load(a.current)
    refs = [r.strip() for r in a.refs.split(",") if r.strip()]
    classes = tuple(c.strip() for c in a.classes.split(",") if c.strip())
    n_watched = len(watched_refs(base, refs, classes, a.all))
    if not n_watched:
        print('nothing to watch: set "locked": true on the confirmed parts in the baseline, or pass --refs, --classes '
              'or --all', file=sys.stderr)
        return 2
    errors, infos = compare(base, cur, a.tol_mm, a.tol_deg, refs, classes, a.all)
    for e in errors:
        print("ERROR", e)
    if a.list_others:
        for i in infos:
            print("INFO ", i)
    elif infos:
        print(f"INFO  {len(infos)} other change(s) (unwatched parts, additions) - --list-others prints them")
    print(f"SUMMARY baseline changes {len(errors)} ({n_watched} watched part(s), {len(base.get('keepouts', []))} keep-out(s))"
          + (" - restore them, or re-save the baseline after the user confirms" if errors else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
