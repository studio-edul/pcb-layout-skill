#!/usr/bin/env python3
"""Placement checker for the pcb-layout-design skill.

Input JSON (mm, origin = board lower-left unless "origin" says otherwise, y up):
{
 "board": {"w": 42, "h": 42, "edge_clearance": 0.5, "grid": 0.25, "origin": [-21, -21]},
 "zones":    {"name": [x1, y1, x2, y2], ...},
 "keepouts": [{"name": "hole1", "rect": [x1,y1,x2,y2]} | {"name": "...", "circle": [cx, cy, r]}, "allow": ["U1"], "side": "top"|"bottom"|"both"}],
 "parts": [{"ref","x","y","w","h","rot"(0/90/180/270),"class","zone","allow_overhang","grid"}],
   x,y = courtyard centre; w,h = courtyard size at rot 0 (NOT body size)
   class: passive | power | ic | module | connector | mech
 "near":  [{"a","b","max","why"}],   courtyard edge-to-edge distance must be <= max
 "apart": [{"a","b","min","why"}],   courtyard edge-to-edge distance must be >= min
 "spacing": {"passive-passive": 0.3, ...}   optional overrides of the default table
}
ERROR: OVERLAP, SPACING, EDGE, OUTSIDE, KEEPOUT, FAR, CLOSE, ZONE.  WARN: grid, rotation.  INFO: occupancy.
Exit code 1 if any ERROR.  --png out.png draws the board (violating parts red).
Rotation must be 0 / 90 / 180 / 270: any other angle is checked as rot 0 (axis-aligned courtyard) and warned.
"""
import json, math, sys, itertools

# recommended part-to-part courtyard gap (mm). Lower bounds (JLC) are in the skill text, these are targets.
SPACING = {
    "passive-passive": 0.3, "passive-power": 0.5, "passive-ic": 0.5, "passive-module": 1.0, "passive-connector": 0.5,
    "power-power": 1.0, "power-ic": 1.0, "power-module": 1.0, "power-connector": 1.0,
    "ic-ic": 1.0, "ic-module": 1.0, "ic-connector": 1.0, "module-module": 1.0, "module-connector": 1.0,
    "connector-connector": 1.0,
}
EDGE_EXEMPT = {"connector", "module", "mech"}


def rect(p):
    w, h = p["w"], p["h"]
    if int(round(p.get("rot", 0))) % 180 == 90:
        w, h = h, w
    return (p["x"] - w / 2, p["y"] - h / 2, p["x"] + w / 2, p["y"] + h / 2)


def gap(a, b):
    """edge-to-edge distance between rectangles (0 when touching/overlapping)"""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return math.hypot(dx, dy)


def overlap(a, b):
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    return min(ox, oy) if ox > 1e-9 and oy > 1e-9 else 0.0


def rect_circle_dist(r, c):
    cx, cy, rad = c
    dx = max(r[0] - cx, 0, cx - r[2])
    dy = max(r[1] - cy, 0, cy - r[3])
    return math.hypot(dx, dy) - rad


def on_grid(v, g):
    k = v / g
    return abs(k - round(k)) < 1e-6


def spacing_of(table, ca, cb):
    for k in (f"{ca}-{cb}", f"{cb}-{ca}"):
        if k in table:
            return table[k]
    return 0.0


def check(d):
    b = d["board"]
    ox, oy = b.get("origin", [0, 0])
    bx = (ox, oy, ox + b["w"], oy + b["h"])
    ec, grid = b.get("edge_clearance", 0.0), b.get("grid", 0.25)
    table = dict(SPACING, **d.get("spacing", {}))
    parts = {p["ref"]: p for p in d["parts"]}
    R = {r: rect(p) for r, p in parts.items()}
    near_pairs = {frozenset((n["a"], n["b"])) for n in d.get("near", [])}
    errs, warns, bad = [], [], set()

    def same_side(pa, pb):
        sa, sb = pa.get("side", "top"), pb.get("side", "top")
        return sa == sb or "both" in (sa, sb)

    for a, b2 in itertools.combinations(parts, 2):
        if not same_side(parts[a], parts[b2]):
            continue
        o = overlap(R[a], R[b2])
        if o > 0:
            errs.append(f"OVERLAP {a}-{b2} {o:.2f} mm"); bad |= {a, b2}; continue
        if frozenset((a, b2)) in near_pairs:
            continue
        need = spacing_of(table, parts[a].get("class", "passive"), parts[b2].get("class", "passive"))
        g = gap(R[a], R[b2])
        if need and g < need - 1e-6:
            errs.append(f"SPACING {a}-{b2} {g:.2f} < {need:.2f} mm"); bad |= {a, b2}

    for r, p in parts.items():
        x1, y1, x2, y2 = R[r]
        if (x1 < bx[0] - 1e-6 or y1 < bx[1] - 1e-6 or x2 > bx[2] + 1e-6 or y2 > bx[3] + 1e-6) and not p.get("allow_overhang"):
            errs.append(f"OUTSIDE {r}"); bad.add(r); continue
        if p.get("class") not in EDGE_EXEMPT and not p.get("allow_overhang"):
            e = min(x1 - bx[0], y1 - bx[1], bx[2] - x2, bx[3] - y2)
            if e < ec - 1e-6:
                errs.append(f"EDGE {r} {e:.2f} < {ec} mm"); bad.add(r)
        zn = p.get("zone")
        if zn and zn in d.get("zones", {}):
            z = d["zones"][zn]
            if x1 < z[0] - 1e-6 or y1 < z[1] - 1e-6 or x2 > z[2] + 1e-6 or y2 > z[3] + 1e-6:
                errs.append(f"ZONE {r} outside '{zn}'"); bad.add(r)
        g_ = p.get("grid", grid)
        if not (on_grid(p["x"], g_) and on_grid(p["y"], g_)):
            warns.append(f"GRID {r} ({p['x']}, {p['y']}) not on {g_} mm")
        if int(round(p.get("rot", 0))) % 90 != 0:
            warns.append(f"ROT {r} {p.get('rot')} deg (use 90 deg steps)")
        if p.get("height", 0) > 5:
            low = [o for o in parts if o != r and parts[o].get("height", 1) <= 2 and gap(R[r], R[o]) < 1.0]
            if low:
                warns.append(f"TALL {r} {p['height']} mm within 1 mm of low parts {','.join(low[:4])} (reflow shadow)")

    for k in d.get("keepouts", []):
        allow = set(k.get("allow", []))
        for r in parts:
            if r in allow:
                continue
            ks = k.get("side", "both")
            if ks != "both" and parts[r].get("side", "top") not in (ks, "both"):
                continue
            hit = (overlap(R[r], k["rect"]) > 0) if "rect" in k else (rect_circle_dist(R[r], k["circle"]) < 0)
            if hit:
                errs.append(f"KEEPOUT {r} in '{k['name']}'"); bad.add(r)

    for n in d.get("near", []):
        if n["a"] in R and n["b"] in R:
            g = gap(R[n["a"]], R[n["b"]])
            if g > n["max"] + 1e-6:
                errs.append(f"FAR {n['a']}->{n['b']} {g:.2f} > {n['max']} mm" + (f" ({n['why']})" if n.get("why") else "")); bad.add(n["a"])
    for n in d.get("apart", []):
        if n["a"] in R and n["b"] in R:
            g = gap(R[n["a"]], R[n["b"]])
            if g < n["min"] - 1e-6:
                errs.append(f"CLOSE {n['a']}<->{n['b']} {g:.2f} < {n['min']} mm" + (f" ({n['why']})" if n.get("why") else "")); bad |= {n["a"], n["b"]}

    area = sum((R[r][2] - R[r][0]) * (R[r][3] - R[r][1]) for r, p in parts.items() if p.get("class") != "mech")
    occ = area / (b["w"] * b["h"]) * 100
    return errs, warns, occ, bad, R, bx


def draw(d, R, bx, bad, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle, Circle
    except ImportError:
        print("INFO matplotlib not installed, no PNG"); return
    fig, ax = plt.subplots(figsize=(8, 8 * (bx[3] - bx[1]) / (bx[2] - bx[0])))
    ax.add_patch(Rectangle((bx[0], bx[1]), bx[2] - bx[0], bx[3] - bx[1], fill=False, lw=2))
    for name, z in d.get("zones", {}).items():
        ax.add_patch(Rectangle((z[0], z[1]), z[2] - z[0], z[3] - z[1], fill=False, ls=":", ec="gray"))
        ax.text(z[0] + 0.2, z[3] - 0.6, name, fontsize=6, color="gray")
    for k in d.get("keepouts", []):
        if "rect" in k:
            r = k["rect"]; ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], color="orange", alpha=0.2))
        else:
            c = k["circle"]; ax.add_patch(Circle((c[0], c[1]), c[2], color="orange", alpha=0.25))
    colors = {"passive": "#4c9be8", "power": "#e8a44c", "ic": "#8a63d2", "module": "#55a868", "connector": "#777777", "mech": "#bbbbbb"}
    for p in d["parts"]:
        r = p["ref"]
        x1, y1, x2, y2 = R[r]
        bot = p.get("side") == "bottom"
        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fc="red" if r in bad else ("#f2c14e" if bot else colors.get(p.get("class"), "#4c9be8")),
                               ec="k", lw=0.4, alpha=0.55 if bot else 0.75, hatch="////" if bot else None))
        ax.text(p["x"], p["y"], r, ha="center", va="center", fontsize=5)
    ax.set_xlim(bx[0] - 1, bx[2] + 1); ax.set_ylim(bx[1] - 1, bx[3] + 1); ax.set_aspect("equal"); ax.grid(lw=0.2)
    fig.savefig(path, dpi=200, bbox_inches="tight"); print(f"INFO PNG written: {path}")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip()); print("usage: placement_check.py placement.json [--png out.png]"); return 0
    if not args:
        print(__doc__); sys.exit(2)
    d = json.load(open(args[0], encoding="utf-8"))
    errs, warns, occ, bad, R, bx = check(d)
    for e in errs: print("ERROR", e)
    for w in warns: print("WARN ", w)
    sides = {p.get("side", "top") for p in d["parts"]}
    if sides <= {"top"}:
        print(f"INFO top occupancy {occ:.0f}% (courtyard sum / board area)")
    else:
        for sd in ("top", "bottom"):
            a = sum((R[p["ref"]][2] - R[p["ref"]][0]) * (R[p["ref"]][3] - R[p["ref"]][1]) for p in d["parts"]
                    if p.get("class") != "mech" and p.get("side", "top") in (sd, "both"))
            print(f"INFO {sd} occupancy {a / (d['board']['w'] * d['board']['h']) * 100:.0f}%")
    print(f"SUMMARY ERROR {len(errs)}, WARN {len(warns)}")
    if "--png" in args:
        i = args.index("--png")
        out = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else args[0].rsplit(".", 1)[0] + ".png"
        draw(d, R, bx, bad, out)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
