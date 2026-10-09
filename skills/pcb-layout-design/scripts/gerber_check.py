#!/usr/bin/env python3
"""Check fabrication outputs at the Gerber level, independent of the EDA tool that wrote them.

    gerber_check.py layers  <release>                       what each file is (copper / mask / silk / drill ...)
    gerber_check.py render  <release> --out preview         print preview per side + silk-on-pad, copper-to-edge
    gerber_check.py netcheck <release> --ipc board.ipc      copper + plated holes vs the IPC-D-356 netlist:
                                                            shorts, opens, pads without copper, through holes
                                                            with no drill hit [--min-gap 0.1 adds a clearance look]
    gerber_check.py diff    <release-a> <release-b>         per-layer geometry difference (export noise ignored)

<release> is a directory or a .zip with RS-274X Gerbers and Excellon drill files (EasyEDA / Protel names,
KiCad names or X2 file attributes). Coordinates are mm. Needs numpy, Pillow and scipy.

Why: DRC checks the design database, the fab builds from these files. A pad that lost its via, a bridge
added by an export bug, a silk mark that falls off the board or a stray change between two exports only
show up here. The checks are raster based (default 50 px/mm = 0.02 mm), so gaps below ~0.04 mm are not
resolved, and the check proves connectivity, not clearance against the fab's rules.

Limits: through holes join all copper layers (blind/buried vias are treated as through), negative-image
layers (%IPNEG%) and step-and-repeat (%SR%) are not supported (reported), aperture holes are ignored.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
    from scipy import ndimage
except ImportError as e:  # pragma: no cover
    sys.exit(f"gerber_check.py needs numpy, Pillow and scipy ({e}). pip install numpy pillow scipy")

PX = 50  # pixels per mm


# ---------------------------------------------------------------- release files and layer roles

def read_release(path):
    """{name: text} for every readable file in a directory or zip (non-ASCII names are fine here)."""
    p = Path(path)
    out = {}
    if p.is_file() and p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            for i in z.infolist():
                if not i.is_dir():
                    out[Path(i.filename).name] = z.read(i).decode("utf-8", "replace")
    else:
        for f in sorted(p.iterdir()):
            if f.is_file():
                out[f.name] = f.read_text("utf-8", "replace")
    return out


ROLE_BY_EXT = {".gtl": "copper_top", ".gbl": "copper_bottom", ".gts": "mask_top", ".gbs": "mask_bottom",
               ".gto": "silk_top", ".gbo": "silk_bottom", ".gtp": "paste_top", ".gbp": "paste_bottom",
               ".gko": "outline", ".gm1": "outline", ".gml": "outline", ".gm": "outline"}
KICAD = [("f_cu", "copper_top"), ("b_cu", "copper_bottom"), ("f_mask", "mask_top"), ("b_mask", "mask_bottom"),
         ("f_silks", "silk_top"), ("b_silks", "silk_bottom"), ("f_paste", "paste_top"), ("b_paste", "paste_bottom"),
         ("edge_cuts", "outline")]


def role_of(name, text):
    """('copper', n) / ('mask_top', None) / ('drill', plated?) / (None, None). n: 1 = top, 99 = bottom."""
    low = name.lower()
    head = text[:4000]
    if re.search(r"^\s*M48", text, re.M) or low.endswith((".drl", ".xln", ".exc")):
        plated = not ("npth" in low or "non_plated" in head.lower() or "nonplated" in head.lower()
                      or "non-plated" in head.lower())
        return "drill", plated
    if "%FS" not in text and "FSLA" not in text:
        return None, None
    m = re.search(r"%TF\.FileFunction,([^*]*)\*%", head)
    if m:
        f = m.group(1).split(",")
        kind = f[0].lower()
        if kind == "copper":
            side = (f[2] if len(f) > 2 else "").lower()
            n = int(re.sub(r"\D", "", f[1]) or 0)
            return "copper", (1 if side == "top" else 99 if side == "bot" else n)
        side = "top" if "top" in [x.lower() for x in f[1:]] else "bottom"
        for k, r in (("soldermask", "mask"), ("legend", "silk"), ("paste", "paste")):
            if kind == k:
                return f"{r}_{side}", None
        if kind == "profile":
            return "outline", None
    ext = Path(low).suffix
    if ext in ROLE_BY_EXT:
        r = ROLE_BY_EXT[ext]
        return ("copper", 1 if r.endswith("top") else 99) if r.startswith("copper") else (r, None)
    m = re.match(r"\.g(?:p)?(\d+)$", ext)                        # .G1 .G2 (EasyEDA/Protel inner), .GP1
    if m:
        return "copper", 1 + int(m.group(1))
    m = re.search(r"in(\d+)_cu", low)
    if m:
        return "copper", 1 + int(m.group(1))
    for k, r in KICAD:
        if k in low:
            return ("copper", 1 if r.endswith("top") else 99) if r.startswith("copper") else (r, None)
    return None, None


def classify(files):
    """roles: {'copper': [(order, name)], 'drill': [(name, plated)], 'mask_top': name, ...}"""
    roles = {"copper": [], "drill": []}
    for name, text in files.items():
        r, extra = role_of(name, text)
        if r == "copper":
            roles["copper"].append((extra, name))
        elif r == "drill":
            roles["drill"].append((name, extra))
        elif r:
            roles.setdefault(r, name)
    roles["copper"].sort()
    return roles


# ---------------------------------------------------------------- RS-274X parser

class Gerber:
    """Objects in mm: ('line', width, [(x, y)...], dark) / ('flash', aperture, x, y, dark) / ('region', pts, dark).
    aperture = ('C', [d]) | ('R', [w, h]) | ('O', [w, h]) | ('P', [d, n, rot]) | ('M', shapes) where shapes is a
    list of (dark, polygon-or-circle) evaluated from an aperture macro."""

    def __init__(self, text, name=""):
        self.name, self.objects, self.warnings = name, [], []
        self._parse(text)

    def _num(self, s, axis):
        if "." in s:                                            # not standard, but some writers do it
            v = float(s)
        else:
            i, d = self.fmt[axis]
            neg = s.startswith("-")
            s = s.lstrip("+-")
            if self.zero_mode == "T":                           # trailing zeros kept: pad on the left
                s = s.rjust(i + d, "0")
            v = int(s or "0") / 10 ** d
            v = -v if neg else v
        return v * self.scale

    def _parse(self, text):
        self.fmt = {"X": (2, 6), "Y": (2, 6), "I": (2, 6), "J": (2, 6)}
        self.zero_mode, self.scale = "L", 1.0
        macros, aps = {}, {}
        x = y = 0.0
        ap, mode, quadrant, dark = None, "G01", "multi", True
        region = None                                           # list of contours while in G36
        for m in re.finditer(r"%([^%]*)%|([^%*]*)\*", text):
            if m.group(1) is not None:
                for blk in [b for b in m.group(1).split("*") if b.strip()] if not m.group(1).startswith("AM") else [m.group(1)]:
                    blk = blk.strip()
                    if blk.startswith("FS"):
                        f = re.match(r"FS([LT])?[AI]?X(\d)(\d)Y(\d)(\d)", blk)
                        if f:
                            self.zero_mode = f.group(1) or "L"
                            for k in "XIJ":
                                self.fmt[k] = (int(f.group(2)), int(f.group(3)))
                            self.fmt["Y"] = (int(f.group(4)), int(f.group(5)))
                            self.fmt["J"] = self.fmt["Y"]
                    elif blk.startswith("MO"):
                        self.scale = 25.4 if "IN" in blk else 1.0
                    elif blk.startswith("AM"):
                        nm, _, body = blk[2:].partition("*")
                        macros[nm] = body
                    elif blk.startswith("AD"):
                        a = re.match(r"ADD(\d+)([^,]+),?(.*)", blk)
                        if a:
                            params = [float(v) for v in a.group(3).split("X") if v.strip()] if a.group(3) else []
                            aps[int(a.group(1))] = self._aperture(a.group(2), params, macros)
                    elif blk.startswith("LP"):
                        dark = blk[2:3] != "C"
                    elif blk.startswith("IP") and "NEG" in blk:
                        self.warnings.append("negative image polarity (%IPNEG%) not supported")
                    elif blk.startswith("SR") and re.search(r"X[2-9]|Y[2-9]", blk):
                        self.warnings.append("step-and-repeat (%SR%) not supported: only the first copy is drawn")
                    elif blk.startswith(("LM", "LR", "LS")) and not re.match(r"L[MRS](N|0|1(\.0*)?)?$", blk):
                        self.warnings.append(f"aperture transformation {blk} ignored")
                continue
            cmd = m.group(2).strip()
            if not cmd or cmd.startswith("G04"):
                continue
            for g in re.findall(r"G0?(\d+)", cmd):
                g = int(g)
                if g in (1, 2, 3):
                    mode = f"G0{g}"
                elif g == 36:
                    region = [[]]
                elif g == 37:
                    for c in region or []:
                        if len(c) > 2:
                            self.objects.append(("region", c, dark))
                    region = None
                elif g == 74:
                    quadrant = "single"
                elif g == 75:
                    quadrant = "multi"
                elif g == 70:
                    self.scale = 25.4
                elif g == 71:
                    self.scale = 1.0
            d = re.search(r"D0*(\d+)$", cmd)
            if d and int(d.group(1)) >= 10:
                ap = int(d.group(1))
                continue
            c = {k: self._num(v, k) for k, v in re.findall(r"([XYIJ])([+-]?[\d.]+)", cmd)}
            op = int(d.group(1)) if d else (1 if c and region is None and ("X" in c or "Y" in c) else None)
            if op is None and region is not None and c:
                op = 1
            if op is None:
                continue
            nx, ny = c.get("X", x), c.get("Y", y)
            if op == 1:
                pts = [(x, y), (nx, ny)]
                if mode in ("G02", "G03"):
                    pts = self._arc(x, y, nx, ny, c.get("I", 0.0), c.get("J", 0.0), mode == "G02", quadrant)
                if region is not None:
                    if not region[-1]:
                        region[-1].append((x, y))
                    region[-1].extend(pts[1:])
                elif ap in aps:
                    a = aps[ap]
                    w = a[1][0] if a[0] in ("C", "P") else min(a[1][:2]) if a[0] in ("R", "O") else 0.1
                    self.objects.append(("line", w, pts, dark))
            elif op == 2:
                if region is not None and region[-1]:
                    region.append([])
            elif op == 3 and ap in aps:
                self.objects.append(("flash", aps[ap], nx, ny, dark))
            x, y = nx, ny

    def _arc(self, x0, y0, x1, y1, i, j, cw, quadrant):
        cands = [(x0 + i, y0 + j)] if quadrant == "multi" else \
            [(x0 + si * abs(i), y0 + sj * abs(j)) for si in (1, -1) for sj in (1, -1)]
        best = None
        for cx, cy in cands:
            r0, r1 = math.hypot(x0 - cx, y0 - cy), math.hypot(x1 - cx, y1 - cy)
            a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
            if cw:
                while a1 >= a0: a1 -= 2 * math.pi
            else:
                while a1 <= a0: a1 += 2 * math.pi
            if quadrant == "multi" and abs(a1 - a0) < 1e-9 or (quadrant == "multi" and (x0, y0) == (x1, y1)):
                a1 = a0 + (-2 * math.pi if cw else 2 * math.pi)  # full circle
            sweep = abs(a1 - a0)
            score = abs(r0 - r1) + (0 if quadrant == "multi" or sweep <= math.pi / 2 + 1e-6 else 1e3)
            if best is None or score < best[0]:
                best = (score, cx, cy, r0, a0, a1)
        _, cx, cy, r, a0, a1 = best
        n = max(4, int(abs(a1 - a0) * max(r, 0.05) * 10))
        return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]

    def _aperture(self, kind, p, macros):
        if kind in ("C", "R", "O", "P"):
            return (kind, p + [0, 0, 0])
        if kind in macros:
            return ("M", macro_shapes(macros[kind], p))
        self.warnings.append(f"unknown aperture {kind}: drawn as 0.1 mm circle")
        return ("C", [0.1, 0, 0])


def _eval(expr, var):
    e = re.sub(r"\$(\d+)", lambda m: f"({var.get(int(m.group(1)), 0.0)!r})", expr.replace("x", "*").replace("X", "*"))
    if not re.fullmatch(r"[\d.+\-*/() eE]*", e):
        raise ValueError(f"bad macro expression {expr!r}")
    return float(eval(e, {"__builtins__": {}}, {})) if e.strip() else 0.0


def _rot(pts, deg):
    if not deg:
        return pts
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(px * c - py * s, px * s + py * c) for px, py in pts]


def macro_shapes(body, params):
    """Evaluate an aperture macro: list of (dark, ('poly', pts) | ('circle', cx, cy, d))."""
    var = {k + 1: v for k, v in enumerate(params)}
    out = []
    for prim in [s.strip() for s in body.split("*") if s.strip()]:
        if prim.startswith("$"):
            k, _, e = prim.partition("=")
            var[int(k[1:])] = _eval(e, var)
            continue
        if re.match(r"0(\s|$)", prim):
            continue                                            # comment primitive
        f = prim.split(",")
        code = int(float(f[0]))
        a = [_eval(v, var) for v in f[1:]]
        dark = a[0] >= 0.5
        if code == 1:
            rot = a[4] if len(a) > 4 else 0
            (cx, cy), = _rot([(a[2], a[3])], rot)
            out.append((dark, ("circle", cx, cy, a[1])))
        elif code in (20, 2):
            w, x1, y1, x2, y2, rot = a[1], a[2], a[3], a[4], a[5], a[6] if len(a) > 6 else 0
            L = math.hypot(x2 - x1, y2 - y1) or 1e-9
            nx, ny = -(y2 - y1) / L * w / 2, (x2 - x1) / L * w / 2
            out.append((dark, ("poly", _rot([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)], rot))))
        elif code == 21:
            w, h, cx, cy, rot = a[1], a[2], a[3], a[4], a[5] if len(a) > 5 else 0
            out.append((dark, ("poly", _rot([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)], rot))))
        elif code == 4:
            n = int(a[1])
            pts = [(a[2 + 2 * k], a[3 + 2 * k]) for k in range(n + 1)]
            out.append((dark, ("poly", _rot(pts, a[4 + 2 * n] if len(a) > 4 + 2 * n else 0))))
        elif code == 5:
            n, cx, cy, d, rot = int(a[1]), a[2], a[3], a[4], a[5] if len(a) > 5 else 0
            pts = [(cx + d / 2 * math.cos(2 * math.pi * k / n), cy + d / 2 * math.sin(2 * math.pi * k / n)) for k in range(n)]
            out.append((dark, ("poly", _rot(pts, rot))))
        elif code == 7:                                         # thermal: drawn as a full ring (gaps ignored)
            (cx, cy), = _rot([(a[0], a[1])], a[5] if len(a) > 5 else 0)
            out.append((True, ("circle", cx, cy, a[2])))
            out.append((False, ("circle", cx, cy, a[3])))
    return out


# ---------------------------------------------------------------- Excellon parser

def parse_drill(text):
    """Hits in mm: list of (x, y, diameter, (x2, y2) or None for a slot end)."""
    metric, zeros, fmt = True, "L", None
    tools, hits = {}, []
    t = None
    x = y = 0.0
    down = None
    m = re.search(r"FILE_FORMAT\s*=\s*(\d):(\d)", text)
    if m:
        fmt = (int(m.group(1)), int(m.group(2)))

    def num(s):
        if "." in s:
            v = float(s)
        else:
            i, d = fmt or ((3, 3) if metric else (2, 4))
            neg = s.startswith("-")
            s = s.lstrip("+-")
            v = int(s.ljust(i + d, "0") if zeros == "L" else s or "0") / 10 ** d
            v = -v if neg else v
        return v if metric else v * 25.4

    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith(";"):
            continue
        u = ln.upper()
        if u.startswith(("METRIC", "M71", "INCH", "M72")):
            metric = u.startswith(("METRIC", "M71"))
            zeros = "T" if "TZ" in u else "L"
            f = re.search(r"(0+)\.(0+)", u)                       # e.g. METRIC,LZ,000.000 -> 3:3
            if f and fmt is None:
                fmt = (len(f.group(1)), len(f.group(2)))
            continue
        tm = re.match(r"T(\d+)(?:F\d+S\d+)?C([\d.]+)", u)
        if tm:
            d = float(tm.group(2))
            tools[int(tm.group(1))] = d if metric else d * 25.4
            continue
        ts = re.match(r"T(\d+)$", u)
        if ts:
            t = int(ts.group(1))
            continue
        if u.startswith("M15"):
            down = (x, y)
            continue
        if u.startswith(("M16", "M17")):
            down = None
            continue
        parts = re.split(r"G85", u)
        c0 = dict((k, num(v)) for k, v in re.findall(r"([XY])([+-]?[\d.]+)", parts[0]))
        if not c0 and len(parts) == 1:
            continue
        nx, ny = c0.get("X", x), c0.get("Y", y)
        dia = tools.get(t, 0.0)
        if len(parts) > 1:                                      # G85 slot
            c1 = dict((k, num(v)) for k, v in re.findall(r"([XY])([+-]?[\d.]+)", parts[1]))
            hits.append((nx, ny, dia, (c1.get("X", nx), c1.get("Y", ny))))
            x, y = c1.get("X", nx), c1.get("Y", ny)
            continue
        if u.startswith("G00"):
            x, y = nx, ny
            continue
        if u.startswith("G01") and down is not None:            # routed slot segment
            hits.append((x, y, dia, (nx, ny)))
            x, y = nx, ny
            continue
        hits.append((nx, ny, dia, None))
        x, y = nx, ny
    return hits


# ---------------------------------------------------------------- IPC-D-356 netlist

def parse_ipc356(text):
    """Pads and vias with nets: list of dict(net, ref, pin, x, y, layer ('top'|'bottom'|'through'), size)."""
    unit = 0.00254                                              # CUST 0 / 2: 0.0001 inch
    out = []
    for ln in text.splitlines():
        if ln.startswith("P") and "UNITS" in ln:
            if re.search(r"CUST\s+1|\bSI\b", ln):
                unit = 0.001
            continue
        if not ln.startswith(("317", "327")):
            continue
        net = ln[3:17].strip()
        ref, pin = ln[20:26].strip(), ln[27:31].strip()
        m = re.search(r"A(\d\d)X([ +-]?\d+)Y([ +-]?\d+)(?:X(\d+))?(?:Y(\d*))?", ln[31:])
        if not m:
            continue
        acc = int(m.group(1))
        layer = "through" if ln.startswith("317") else ("top" if acc <= 1 else "bottom")
        size = int(m.group(4)) * unit if m.group(4) else 0.0
        if net in ("N/C", ""):
            net = f"N/C:{ref}-{pin}"                             # every unconnected pad is its own net
        out.append(dict(net=net, ref=ref, pin=pin, x=int(m.group(2).replace(" ", "")) * unit,
                        y=int(m.group(3).replace(" ", "")) * unit, layer=layer, size=size))
    return out


# ---------------------------------------------------------------- rasteriser

def bounds(gerbers):
    xs, ys = [], []
    for g in gerbers:
        for o in g.objects:
            pts = o[2] if o[0] == "line" else o[1] if o[0] == "region" else [(o[2], o[3])]
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
    if not xs:
        raise SystemExit("no geometry found")
    return (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)


class Canvas:
    def __init__(self, box, px=PX):
        self.box, self.px = box, px
        self.w, self.h = int(math.ceil((box[2] - box[0]) * px)), int(math.ceil((box[3] - box[1]) * px))

    def P(self, x, y):
        return ((x - self.box[0]) * self.px, (self.box[3] - y) * self.px)

    def rc(self, x, y):
        return int((self.box[3] - y) * self.px), int((x - self.box[0]) * self.px)

    def render(self, g):
        img = Image.new("L", (self.w, self.h), 0)
        dr = ImageDraw.Draw(img)
        for o in g.objects:
            v = 255 if o[-1] else 0
            if o[0] == "line":
                self._line(dr, o[2], o[1], v)
            elif o[0] == "region":
                dr.polygon([self.P(*p) for p in o[1]], fill=v)
            else:
                self._flash(img, dr, o[1], o[2], o[3], v)
        return np.array(img) > 127

    def _dot(self, dr, x, y, d, v):
        r = max(d * self.px / 2, 0.5)
        cx, cy = self.P(x, y)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=v)

    def _line(self, dr, pts, w, v):
        dr.line([self.P(*p) for p in pts], fill=v, width=max(1, round(w * self.px)))
        for p in pts:
            self._dot(dr, p[0], p[1], w, v)

    def _flash(self, img, dr, ap, x, y, v):
        kind, p = ap
        if kind == "C":
            self._dot(dr, x, y, p[0], v)
        elif kind in ("R", "O"):
            w, h = p[0], p[1]
            a, b = self.P(x - w / 2, y + h / 2), self.P(x + w / 2, y - h / 2)
            if kind == "R":
                dr.rectangle([a, b], fill=v)
            else:
                dr.rounded_rectangle([a, b], radius=min(w, h) * self.px / 2, fill=v)
        elif kind == "P":
            d, n, rot = p[0], int(p[1] or 3), p[2]
            dr.polygon([self.P(x + d / 2 * math.cos(math.radians(rot) + 2 * math.pi * k / n),
                               y + d / 2 * math.sin(math.radians(rot) + 2 * math.pi * k / n)) for k in range(n)], fill=v)
        elif kind == "M":                                        # compose the macro, then paste it with the layer polarity
            ext = [abs(c) + (s[3] / 2 if s[0] == "circle" else 0)
                   for _, s in p for c in ((s[1], s[2]) if s[0] == "circle" else [q for pt in s[1] for q in pt])]
            R = (max(ext) if ext else 0.1) + 0.05
            n = max(2, int(2 * R * self.px) + 2)
            sub = Image.new("L", (n, n), 0)
            sd = ImageDraw.Draw(sub)
            Q = lambda px_, py_: ((px_ + R) * self.px, (R - py_) * self.px)
            for dark, s in p:
                fv = 255 if dark else 0
                if s[0] == "circle":
                    cx, cy = Q(s[1], s[2]); r = max(s[3] * self.px / 2, 0.5)
                    sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fv)
                else:
                    sd.polygon([Q(*q) for q in s[1]], fill=fv)
            ox, oy = self.P(x - R, y + R)
            img.paste(v, (int(round(ox)), int(round(oy))), sub)


# ---------------------------------------------------------------- commands

def load(path):
    files = read_release(path)
    roles = classify(files)
    gb = {}
    for k, v in list(roles.items()):
        if k == "copper":
            continue
        if k != "drill" and isinstance(v, str):
            gb[k] = Gerber(files[v], v)
    copper = [(o, Gerber(files[n], n)) for o, n in roles["copper"]]
    drills = [(n, plated, parse_drill(files[n])) for n, plated in roles["drill"]]
    return files, roles, gb, copper, drills


def warn_all(gb, copper):
    for g in list(gb.values()) + [g for _, g in copper]:
        for w in sorted(set(g.warnings)):
            print(f"WARN  {g.name}: {w}")


def cmd_layers(a):
    files, roles, gb, copper, drills = load(a.release)
    for o, n in roles["copper"]:
        print(f"copper L{o if o != 99 else 'bottom'}  {n}")
    for k in sorted(k for k in roles if k not in ("copper", "drill")):
        print(f"{k:13s} {roles[k]}")
    for n, plated, hits in drills:
        print(f"drill {'PTH ' if plated else 'NPTH'}    {n}  ({len(hits)} hits)")
    known = {n for _, n in roles["copper"]} | {n for n, _ in roles["drill"]} | {v for k, v in roles.items() if isinstance(v, str)}
    for n in files:
        if n not in known:
            print(f"unused        {n}")
    return 0


def outline_mask(cv, gb):
    if "outline" not in gb:
        return None, None
    stroke = cv.render(gb["outline"])
    inside = ndimage.binary_fill_holes(stroke) & ~stroke
    return stroke, (inside if inside.sum() > 0 else None)


def cmd_render(a):
    files, roles, gb, copper, drills = load(a.release)
    warn_all(gb, copper)
    cv = Canvas(bounds([g for _, g in copper] + list(gb.values())), a.px)
    stroke, inside = outline_mask(cv, gb)
    if inside is None:
        print("WARN  no closed board outline found: edge checks skipped")
    cu = {o: cv.render(g) for o, g in copper}
    for side, cuk in (("top", min(cu) if cu else None), ("bottom", max(cu) if cu else None)):
        silk = cv.render(gb[f"silk_{side}"]) if f"silk_{side}" in gb else np.zeros((cv.h, cv.w), bool)
        mask = cv.render(gb[f"mask_{side}"]) if f"mask_{side}" in gb else np.zeros((cv.h, cv.w), bool)
        c = cu.get(cuk, np.zeros((cv.h, cv.w), bool))
        img = np.zeros((cv.h, cv.w, 3), np.uint8); img[:] = (40, 40, 40)
        board = inside if inside is not None else np.ones((cv.h, cv.w), bool)
        img[board] = (28, 92, 52); img[board & c] = (52, 130, 70)
        img[mask & c] = (200, 170, 90)
        img[silk & ~mask] = (245, 245, 245)
        if stroke is not None:
            img[stroke] = (20, 20, 20)
        im = Image.fromarray(img)
        if side == "bottom":
            im = im.transpose(Image.FLIP_LEFT_RIGHT)              # as seen from below
        out = f"{a.out}_{side}.png"
        im.save(out)
        ov = silk & mask
        print(f"{side}: wrote {out}; silk on mask openings {ov.sum() / a.px ** 2:.3f} mm2 (the fab clips it)")
        if inside is not None:
            off = silk & ~inside & ~stroke
            if off.any():
                print(f"WARN  {side}: {off.sum() / a.px ** 2:.3f} mm2 of silk lies outside the board outline (not printed)")
    if inside is not None:
        widths = [o[1] for o in gb["outline"].objects if o[0] == "line"]
        half = sorted(widths)[len(widths) // 2] / 2 if widths else 0.0      # measure to the outline's centre line
        dist = ndimage.distance_transform_edt(inside) / a.px + half
        for o, m in sorted(cu.items()):
            name = dict(copper)[o].name
            outside = m & ~inside & ~ndimage.binary_dilation(stroke, iterations=2)
            inner = m & inside
            dmin = dist[inner].min() if inner.any() else float("nan")
            r, c = np.unravel_index(np.argmin(np.where(inner, dist, 1e9)), dist.shape)
            x, y = cv.box[0] + c / a.px, cv.box[3] - r / a.px
            flag = "WARN " if dmin < a.edge else "     "
            print(f"{flag} {name}: copper to board edge min {dmin:.3f} mm at ({x:.2f}, {y:.2f})"
                  + (f"; {outside.sum() / a.px ** 2:.3f} mm2 outside the outline" if outside.any() else ""))
    return 0


def connectivity(cv, copper, drills):
    imgs = {o: cv.render(g) for o, g in copper}
    lab, base, n = {}, {}, 0
    for o, m in imgs.items():
        lab[o], cnt = ndimage.label(m)
        base[o] = n
        n += cnt + 1
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def node(o, x, y):
        r, c = cv.rc(x, y)
        if not (0 <= r < cv.h and 0 <= c < cv.w):
            return None
        v = lab[o][r, c]
        return base[o] + v if v else None

    bare = 0
    for name, plated, hits in drills:
        if not plated:
            continue
        for x, y, d, end in hits:
            pts = [(x, y)] if end is None else [(x + (end[0] - x) * t, y + (end[1] - y) * t) for t in (0, 0.5, 1)]
            for px_, py_ in pts:
                ns = [v for v in (node(o, px_, py_) for o in imgs) if v is not None]
                bare += len(ns) < 2
                for v in ns[1:]:
                    parent[find(v)] = find(ns[0])
    return imgs, lab, base, find, node, bare


def cmd_netcheck(a):
    files, roles, gb, copper, drills = load(a.release)
    warn_all(gb, copper)
    if not copper:
        raise SystemExit("no copper layers found")
    pads = parse_ipc356(Path(a.ipc).read_text("utf-8", "replace"))
    if not pads:
        raise SystemExit("no 317/327 records in the IPC-D-356 file")
    cv = Canvas(bounds([g for _, g in copper]), a.px)
    imgs, lab, base, find, node, bare = connectivity(cv, copper, drills)
    top, bot = min(imgs), max(imgs)

    def locate(p, sx, sy, dx, dy):
        x, y = p["x"] * sx + dx, p["y"] * sy + dy
        o = bot if p["layer"] == "bottom" else top
        v = node(o, x, y)
        if v is None and p["size"]:                              # pad centre in a hole or a thermal gap: look around
            r = p["size"] / 4
            for k in range(8):
                v = node(o, x + r * math.cos(k * math.pi / 4), y + r * math.sin(k * math.pi / 4))
                if v is not None:
                    break
        return v

    dx, dy = a.offset
    trans = [(1, 1)] if a.no_auto else [(1, 1), (1, -1)]
    best = max(trans, key=lambda t: sum(locate(p, t[0], t[1], dx, dy) is not None for p in pads))
    if best != (1, 1):
        print("INFO  netlist Y axis is mirrored against the Gerbers: flipped it")
    nodes = [(p, locate(p, best[0], best[1], dx, dy)) for p in pads]
    miss = [p for p, v in nodes if v is None]
    print(f"pads and vias in the netlist {len(pads)}, on copper {len(pads) - len(miss)}; "
          f"plated hits touching < 2 layers {bare}")
    by_isl, by_net = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    for p, v in nodes:
        if v is None:
            continue
        r = find(v)
        tag = f"{p['ref']}-{p['pin']}" if p["ref"] != "VIA" else f"via({p['x'] * best[0] + dx:.2f},{p['y'] * best[1] + dy:.2f})"
        by_isl[r][p["net"]].append(tag)
        by_net[p["net"]][r].append(tag)
    shorts = {r: v for r, v in by_isl.items() if len(v) > 1}
    opens = {k: v for k, v in by_net.items() if len(v) > 1 and not k.startswith("N/C:")}
    plated = [(x, y) for _, pl, hits in drills if pl for x, y, _, _ in hits] + \
             [e for _, pl, hits in drills if pl for _, _, _, e in hits if e]
    undrilled = []
    for p in pads:                                               # through-hole pads / vias with no plated drill hit
        if p["layer"] != "through":
            continue
        x, y = p["x"] * best[0] + dx, p["y"] * best[1] + dy
        tol = max(p["size"] / 2, 0.15) + 0.05
        if not any(abs(hx - x) <= tol and abs(hy - y) <= tol for hx, hy in plated):
            undrilled.append(p)
    for p in miss[:20]:
        print(f"ERROR NO_COPPER {p['ref']}-{p['pin']} ({p['net']}) at ({p['x']:.3f}, {p['y']:.3f}) on {p['layer']}")
    if len(miss) > len(pads) // 2:
        print("HINT  most pads miss the copper: check units, origin (--offset dx,dy) and that the netlist belongs to these Gerbers")
    for v in shorts.values():
        print("ERROR SHORT " + " / ".join(f"{n}: {', '.join(t[:3])}" for n, t in sorted(v.items())))
    for net, v in sorted(opens.items()):
        print(f"ERROR OPEN  {net}: " + " | ".join(", ".join(t[:4]) for t in v.values()))
    for p in undrilled[:20]:
        what = "via" if p["ref"] == "VIA" else f"{p['ref']}-{p['pin']}"
        print(f"ERROR NO_DRILL {what} ({p['net']}) at ({p['x'] * best[0] + dx:.2f}, {p['y'] * best[1] + dy:.2f}): no plated hole in the drill files - layers are not joined there")
    if a.min_gap:
        gap_check(cv, imgs, lab, base, find, by_isl, a.min_gap, dict(copper))
    print(f"SUMMARY shorts {len(shorts)}, opens {len(opens)}, pads without copper {len(miss)}, undrilled {len(undrilled)}")
    return 1 if shorts or opens or miss or undrilled else 0


def gap_check(cv, imgs, lab, base, find, by_isl, gap, names):
    """Places where copper of different nets comes closer than `gap` mm (raster estimate +-1 px)."""
    netof = {r: sorted(v)[0] for r, v in by_isl.items()}
    for o, m in imgs.items():
        roots = np.array([find(base[o] + i) for i in range(lab[o].max() + 1)])
        near = ndimage.distance_transform_edt(~m) <= gap / 2 * cv.px
        l2, _ = ndimage.label(near)
        pairs = np.unique(np.stack([l2[m], roots[lab[o][m]]]), axis=1)
        grp = defaultdict(set)
        for g_, r in pairs.T:
            grp[g_].add(netof.get(r, f"island{r}"))
        hits = [sorted(s) for s in grp.values() if len(s) > 1]
        print(f"{'WARN ' if hits else '     '} {names[o].name}: {len(hits)} place(s) with different nets closer than {gap} mm"
              + (": " + "; ".join("/".join(h) for h in hits[:6]) if hits else ""))


def _key(o):
    if o[0] == "line":
        return ("line", round(o[1], 4), tuple((round(x, 4), round(y, 4)) for x, y in o[2]), o[3])
    if o[0] == "region":
        return ("region", tuple((round(x, 4), round(y, 4)) for x, y in o[1]), o[2])
    ap = o[1]
    shape = (ap[0], tuple(round(v, 4) for v in ap[1])) if ap[0] != "M" else ("M", repr(ap[1])[:2000])
    return ("flash", shape, round(o[2], 4), round(o[3], 4), o[4])


def _bbox(objs):
    pts = [p for o in objs for p in (o[2] if o[0] == "line" else o[1] if o[0] == "region" else [(o[2], o[3])])]
    return f"x {min(p[0] for p in pts):.2f}..{max(p[0] for p in pts):.2f}, y {min(p[1] for p in pts):.2f}..{max(p[1] for p in pts):.2f}"


def cmd_diff(a):
    A, B = read_release(a.a), read_release(a.b)
    ra, rb = classify(A), classify(B)
    pairs = [(f"copper L{o}", ra_n, dict((x, y) for x, y in rb["copper"]).get(o)) for o, ra_n in ra["copper"]]
    pairs += [(k, ra[k], rb.get(k)) for k in ra if k not in ("copper", "drill")]
    diffs = 0
    for label, na, nb in pairs:
        if nb is None:
            print(f"DIFF  {label}: only in A ({na})"); diffs += 1; continue
        ga, gb_ = Gerber(A[na], na), Gerber(B[nb], nb)
        ca, cb = Counter(map(_key, ga.objects)), Counter(map(_key, gb_.objects))
        if ca == cb:
            print(f"same  {label} ({len(ga.objects)} objects)")
            continue
        diffs += 1
        oa = [o for o in ga.objects if (ca - cb)[_key(o)]]
        ob = [o for o in gb_.objects if (cb - ca)[_key(o)]]
        print(f"DIFF  {label}: {sum((ca - cb).values())} only in A" + (f" ({_bbox(oa)})" if oa else "")
              + f", {sum((cb - ca).values())} only in B" + (f" ({_bbox(ob)})" if ob else ""))
    da = {n: (p, sorted((round(x, 3), round(y, 3), round(d, 3), e and (round(e[0], 3), round(e[1], 3))) for x, y, d, e in parse_drill(A[n]))) for n, p in ra["drill"]}
    db = sorted((p, h) for n, p in rb["drill"] for h in [sorted((round(x, 3), round(y, 3), round(d, 3), e and (round(e[0], 3), round(e[1], 3))) for x, y, d, e in parse_drill(B[n]))])
    if sorted(da.values()) == db:
        print(f"same  drill ({sum(len(h) for _, h in da.values())} hits)")
    else:
        diffs += 1
        print("DIFF  drill files differ")
    print(f"SUMMARY {diffs} layer(s) differ")
    return 1 if diffs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("layers"); s.add_argument("release")
    s = sub.add_parser("render"); s.add_argument("release"); s.add_argument("--out", default="preview")
    s.add_argument("--edge", type=float, default=0.2, help="warn when copper is closer to the edge (mm)")
    s = sub.add_parser("netcheck"); s.add_argument("release"); s.add_argument("--ipc", required=True)
    s.add_argument("--min-gap", type=float, default=0, help="also report different nets closer than this (mm)")
    s.add_argument("--offset", type=lambda v: tuple(float(t) for t in v.split(",")), default=(0.0, 0.0),
                   help="dx,dy (mm) added to netlist coordinates")
    s.add_argument("--no-auto", action="store_true", help="do not try a mirrored Y axis")
    s = sub.add_parser("diff"); s.add_argument("a"); s.add_argument("b")
    for s in sub.choices.values():
        s.add_argument("--px", type=int, default=PX, help="raster resolution, pixels per mm (default 50)")
    a = ap.parse_args(argv)
    return {"layers": cmd_layers, "render": cmd_render, "netcheck": cmd_netcheck, "diff": cmd_diff}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
