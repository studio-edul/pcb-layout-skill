#!/usr/bin/env python3
"""Build a placement_check.py input from a KiCad board file (.kicad_pcb; KiCad 6-9 syntax, the older `module` form is read too).

    python placement_from_kicad.py board.kicad_pcb -o placement.json [--grid 0.25] [--edge 0.5]

What it fills in: board size and origin (Edge.Cuts bounding box), every footprint as a part with its courtyard
(F.CrtYd / B.CrtYd graphics, else the pad extent + 0.25 mm), rotation, side, and a guessed class from the
reference prefix. What it cannot know: zones, keep-outs, near/apart pairs and classes that the prefix gets
wrong - edit the JSON before trusting the checker. Coordinates are converted to mm with y up.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys

TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')


def parse(text):
    stack, cur = [], []
    for t in TOKEN.findall(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return cur[0] if cur else []


def kids(node, name):
    return [n for n in node if isinstance(n, list) and n and n[0] == name]


def kid(node, name):
    k = kids(node, name)
    return k[0] if k else None


def xy(node, name):
    k = kid(node, name)
    return (float(k[1]), float(k[2])) if k else None


def layer_of(node):
    k = kid(node, "layer")
    return k[1] if k else ""


def shape_points(g):
    """Points of a graphic item (start/end/center/pts/arc mid), enough for a bounding box."""
    pts = [p for p in (xy(g, "start"), xy(g, "end"), xy(g, "mid"), xy(g, "center")) if p]
    if g[0] in ("fp_circle", "gr_circle") and xy(g, "center") and xy(g, "end"):
        (cx, cy), (ex, ey) = xy(g, "center"), xy(g, "end")
        r = math.hypot(ex - cx, ey - cy)
        pts += [(cx - r, cy - r), (cx + r, cy + r)]
    if g[0] in ("fp_rect", "gr_rect") and xy(g, "start") and xy(g, "end"):
        (x1, y1), (x2, y2) = xy(g, "start"), xy(g, "end")
        pts += [(x1, y2), (x2, y1)]
    poly = kid(g, "pts")
    if poly:
        pts += [(float(p[1]), float(p[2])) for p in kids(poly, "xy")]
    return pts


def guess_class(ref, area):
    p = re.match(r"[A-Za-z]+", ref)
    p = p.group(0).upper() if p else ""
    if p in ("J", "P", "CN", "CON", "USB", "SW", "BT"):
        return "connector"
    if p in ("H", "MH", "MK", "FID", "TP", "LOGO", "REF"):
        return "mech"
    if p in ("U", "IC"):
        return "module" if area > 150 else "ic"
    if p in ("Q", "K", "F", "PS") or (p == "L" and area > 9) or (p == "C" and area > 25):
        return "power"
    return "passive"


def rot_pt(x, y, deg):
    """KiCad stores footprint-local geometry unrotated; rotation is counter-clockwise on screen (y down)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def convert(text, grid=0.25, edge=0.5):
    pcb = parse(text)
    notes = []
    edges = [p for g in pcb if isinstance(g, list) and g and g[0].startswith("gr_") and layer_of(g) == "Edge.Cuts"
             for p in shape_points(g)]
    fps = kids(pcb, "footprint") + kids(pcb, "module")
    parts = []
    for fp in fps:
        at = kid(fp, "at")
        fx, fy, rot = float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0
        side = "bottom" if layer_of(fp).startswith("B.") else "top"
        ref = None
        for p in kids(fp, "property"):
            if p[1] == "Reference":
                ref = p[2]
        for t in kids(fp, "fp_text"):
            if t[1] == "reference":
                ref = t[2]
        ref = ref or "?"
        crt = [p for g in fp if isinstance(g, list) and g and g[0].startswith("fp_") and layer_of(g).endswith("CrtYd")
               for p in shape_points(g)]
        src = "courtyard"
        if not crt:                                            # no courtyard: pads + 0.25 mm (0.15 for 0402/0603 sizes)
            pad_pts = []
            for pad in kids(fp, "pad"):
                pa, sz = kid(pad, "at"), kid(pad, "size")
                if not pa or not sz:
                    continue
                px, py = float(pa[1]), float(pa[2])
                hx, hy = float(sz[1]) / 2, float(sz[2]) / 2
                prot = (float(pa[3]) if len(pa) > 3 else 0.0) - rot   # pad angle in the file includes the footprint's
                for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
                    pad_pts.append((px + dx * math.cos(math.radians(prot)) + dy * math.sin(math.radians(prot)),
                                    py - dx * math.sin(math.radians(prot)) + dy * math.cos(math.radians(prot))))
            if pad_pts:
                ext = max(max(p[0] for p in pad_pts) - min(p[0] for p in pad_pts), max(p[1] for p in pad_pts) - min(p[1] for p in pad_pts))
                m = 0.15 if ext <= 1.6 else 0.25
                src = f"pads+{m}"
                xs, ys = [p[0] for p in pad_pts], [p[1] for p in pad_pts]
                crt = [(min(xs) - m, min(ys) - m), (max(xs) + m, max(ys) + m)]
        if not crt:
            notes.append(f"{ref}: no courtyard and no pads, skipped")
            continue
        x0, x1 = min(p[0] for p in crt), max(p[0] for p in crt)
        y0, y1 = min(p[1] for p in crt), max(p[1] for p in crt)
        w, h = x1 - x0, y1 - y0
        if abs(rot / 90 - round(rot / 90)) < 1e-6:
            ox, oy = rot_pt((x0 + x1) / 2, (y0 + y1) / 2, rot)
            cx, cy, prot = fx + ox, -(fy + oy), int(round(rot)) % 360
        else:                                                   # odd angle: board-frame bounding box, rot 0
            corners = [rot_pt(px, py, rot) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            bx0, bx1 = min(c[0] for c in corners), max(c[0] for c in corners)
            by0, by1 = min(c[1] for c in corners), max(c[1] for c in corners)
            cx, cy, w, h, prot = fx + (bx0 + bx1) / 2, -(fy + (by0 + by1) / 2), bx1 - bx0, by1 - by0, 0
            notes.append(f"{ref}: rotation {rot:g} deg is not a 90 deg step, used its bounding box")
        part = {"ref": ref, "x": round(cx, 4), "y": round(cy, 4), "w": round(w, 4), "h": round(h, 4), "rot": prot,
                "class": guess_class(ref, w * h), "side": side}
        if prot == 0 and abs(rot / 90 - round(rot / 90)) >= 1e-6:
            part["rot_actual"] = round(rot % 360, 3)        # baseline_diff.py compares this
        if src != "courtyard":
            part["note"] = src
        parts.append(part)
    seen = {}
    for p in parts:                                             # unannotated (REF**) or repeated refs get #2, #3 ...
        seen[p["ref"]] = seen.get(p["ref"], 0) + 1
        if seen[p["ref"]] > 1:
            notes.append(f"{p['ref']}: repeated reference, renamed to {p['ref']}#{seen[p['ref']]}")
            p["ref"] = f"{p['ref']}#{seen[p['ref']]}"
    if edges:
        X0, X1 = min(p[0] for p in edges), max(p[0] for p in edges)
        Y0, Y1 = min(-p[1] for p in edges), max(-p[1] for p in edges)
    else:
        notes.append("no Edge.Cuts geometry: board taken as the part extent + 2 mm")
        X0 = min(p["x"] - p["w"] for p in parts) - 2; X1 = max(p["x"] + p["w"] for p in parts) + 2
        Y0 = min(p["y"] - p["h"] for p in parts) - 2; Y1 = max(p["y"] + p["h"] for p in parts) + 2
    board = {"w": round(X1 - X0, 4), "h": round(Y1 - Y0, 4), "origin": [round(X0, 4), round(Y0, 4)],
             "edge_clearance": edge, "grid": grid}
    data = {"board": board, "zones": {}, "keepouts": [], "parts": parts, "near": [], "apart": []}
    return data, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("board")
    ap.add_argument("-o", "--out", default="placement.json")
    ap.add_argument("--grid", type=float, default=0.25)
    ap.add_argument("--edge", type=float, default=0.5, help="board edge clearance (mm)")
    a = ap.parse_args(argv)
    with open(a.board, encoding="utf-8") as f:
        data, notes = convert(f.read(), a.grid, a.edge)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write('{"board": ' + json.dumps(data["board"]) + ',\n "zones": {}, "keepouts": [],\n "parts": [\n  '
                + ",\n  ".join(json.dumps(p) for p in data["parts"]) + '],\n "near": [], "apart": []}\n')
    for n in notes:
        print("NOTE", n)
    counts = {}
    for p in data["parts"]:
        counts[p["class"]] = counts.get(p["class"], 0) + 1
    print(f"wrote {a.out}: {len(data['parts'])} parts {counts}, board {data['board']['w']} x {data['board']['h']} mm")
    print("next: check the classes, add zones / keepouts / near / apart (SKILL.md section 5), then run placement_check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
