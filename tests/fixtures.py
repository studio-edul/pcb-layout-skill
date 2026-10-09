"""Synthetic 2-layer test board written as KiCad-style (mm, X2 attributes, RoundRect macro, regions with arcs) or
Protel-style inch files, plus its IPC-D-356 netlist. No real design data is needed to test gerber_check.py.

Board 20 x 20 mm, nets:
  A: R1-1 (4,10) top -> track -> via (10,10) -> bottom track -> U1-1 (16,10) bottom
  B: R1-2 (4,6) top, inside a region with an arc edge -> track -> J1-1 (16,5) through-hole
  X1-1 (10,16) top, not connected (N/C)
"""
from pathlib import Path

KICAD_ROUNDRECT = """%AMRoundRect*
0 Rectangle with rounded corners*
0 $1 Rounding radius*
0 $2 $3 $4 $5 $6 $7 $8 $9 X,Y pos of 4 corners*
0 Add a 4 corners polygon primitive as pad body*
4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0*
0 Add four circle primitives for the rounded corners*
1,1,$1+$1,$2,$3*
1,1,$1+$1,$4,$5*
1,1,$1+$1,$6,$7*
1,1,$1+$1,$8,$9*
0 Add four rect primitives between the rounded corners*
20,1,$1+$1,$2,$3,$4,$5,0*
20,1,$1+$1,$4,$5,$6,$7,0*
20,1,$1+$1,$6,$7,$8,$9,0*
20,1,$1+$1,$8,$9,$2,$3,0*%
"""


class Writer:
    def __init__(self, inch):
        self.inch = inch

    def c(self, v):                                    # coordinate string, leading zeros omitted
        if self.inch:
            return str(round(v / 25.4 * 1e5))            # 2.5 format
        return str(round(v * 1e6))                       # 4.6 format

    def header(self, function):
        if self.inch:
            return "G04 Protel-style test file*\n%FSLAX25Y25*%\n%MOIN*%\n"
        return f"G04 #@! TF.GenerationSoftware,KiCad,Pcbnew,8.0*\n%TF.FileFunction,{function}*%\n%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n"

    def u(self, v):                                    # aperture size in file units
        return f"{v / 25.4:.6f}" if self.inch else f"{v:.6f}"

    def xy(self, x, y, d):
        return f"X{self.c(x)}Y{self.c(y)}D0{d}*\n"


def gerbers(inch=False, short=False, silk_on_pad=True):
    w = Writer(inch)
    rr = lambda r, hw, hh: "RoundRect," + "X".join(w.u(v) for v in (r, -hw + r, -hh + r, hw - r, -hh + r, hw - r, hh - r, -hw + r, hh - r))
    files = {}
    # top copper
    t = w.header("Copper,L1,Top") + KICAD_ROUNDRECT
    t += f"%ADD10{rr(0.1, 0.5, 0.75)}*%\n%ADD11C,{w.u(0.3)}*%\n%ADD12C,{w.u(1.7)}*%\n%ADD13C,{w.u(0.6)}*%\n"
    t += "D10*\n" + w.xy(4, 10, 3) + w.xy(4, 6, 3) + w.xy(10, 16, 3)
    t += "D13*\n" + w.xy(10, 10, 3)                    # via pad
    t += "D12*\n" + w.xy(16, 5, 3)                     # THT pad
    t += "D11*\nG01*\n" + w.xy(4, 10, 2) + w.xy(10, 10, 1)
    t += w.xy(4, 6, 2) + w.xy(16, 6, 1) + w.xy(16, 5, 1)
    if short:
        t += w.xy(4, 10, 2) + w.xy(4, 6, 1)
    # region (copper area around R1-2) with an arc edge: 3..5 x 5..7, right edge bulges (arc centre 5,6)
    t += "G36*\n" + w.xy(3, 5, 2) + "G01*\n" + w.xy(5, 5, 1) + "G75*\nG03*\n"
    t += f"X{w.c(5)}Y{w.c(7)}I{w.c(0)}J{w.c(1)}D01*\nG01*\n" + w.xy(3, 7, 1) + w.xy(3, 5, 1) + "G37*\nM02*\n"
    files["test-F_Cu.gbr" if not inch else "test.GTL"] = t
    # bottom copper
    b = w.header("Copper,L2,Bot") + KICAD_ROUNDRECT
    b += f"%ADD10{rr(0.1, 0.5, 0.75)}*%\n%ADD11C,{w.u(0.3)}*%\n%ADD12C,{w.u(1.7)}*%\n%ADD13C,{w.u(0.6)}*%\n"
    b += "D10*\n" + w.xy(16, 10, 3) + "D13*\n" + w.xy(10, 10, 3) + "D12*\n" + w.xy(16, 5, 3)
    b += "D11*\nG01*\n" + w.xy(10, 10, 2) + w.xy(16, 10, 1) + "M02*\n"
    files["test-B_Cu.gbr" if not inch else "test.GBL"] = b
    # masks: openings on the pads
    for side, pads in (("Top", [(4, 10), (4, 6), (10, 16), (16, 5)]), ("Bot", [(16, 10), (16, 5)])):
        m = w.header(f"Soldermask,{side}") + f"%ADD20R,{w.u(1.1)}X{w.u(1.6)}*%\n%ADD21C,{w.u(1.8)}*%\nD20*\n"
        m += "".join(w.xy(x, y, 3) for x, y in pads if (x, y) != (16, 5)) + "D21*\n" + w.xy(16, 5, 3) + "M02*\n"
        files[(f"test-{'F' if side == 'Top' else 'B'}_Mask.gbr") if not inch else ("test.GTS" if side == "Top" else "test.GBS")] = m
    # silk: a label line and (optionally) a line that crosses R1-1
    s = w.header("Legend,Top") + f"%ADD30C,{w.u(0.15)}*%\nD30*\n" + w.xy(8, 3, 2) + w.xy(12, 3, 1)
    if silk_on_pad:
        s += w.xy(3, 10, 2) + w.xy(5, 10, 1)
    files["test-F_Silkscreen.gbr" if not inch else "test.GTO"] = s + "M02*\n"
    # outline
    o = w.header("Profile,NP") + f"%ADD40C,{w.u(0.1)}*%\nD40*\n" + w.xy(0, 0, 2)
    o += w.xy(20, 0, 1) + w.xy(20, 20, 1) + w.xy(0, 20, 1) + w.xy(0, 0, 1) + "M02*\n"
    files["test-Edge_Cuts.gbr" if not inch else "test.GKO"] = o
    return files


def drills(inch=False, via=True):
    if inch:
        f = lambda v: str(round(v / 25.4 * 1e4))       # 2:4, trailing zeros kept (TZ)
        pth = "M48\n;FILE_FORMAT=2:4\nINCH,TZ\nT1C0.0118\nT2C0.0394\n%\nG90\nG05\n"
        pth += (f"T1\nX{f(10)}Y{f(10)}\n" if via else "") + f"T2\nX{f(16)}Y{f(5)}\nM30\n"
        npth = f"M48\n;FILE_FORMAT=2:4\nINCH,TZ\nT1C0.1181\n%\nG90\nG05\nT1\nX{f(2)}Y{f(18)}\nM30\n"
        return {"test-PTH.TXT": pth, "test-NPTH.TXT": npth}
    pth = "M48\n; #@! TF.FileFunction,Plated,1,2,PTH\nFMAT,2\nMETRIC\nT1C0.300\nT2C1.000\n%\nG90\nG05\n"
    pth += ("T1\nX10.0Y10.0\n" if via else "") + "T2\nX16.0Y5.0\nM30\n"
    npth = "M48\n; #@! TF.FileFunction,NonPlated,1,2,NPTH\nFMAT,2\nMETRIC\nT1C3.000\n%\nG90\nG05\nT1\nX2.0Y18.0\nM30\n"
    return {"test-PTH.drl": pth, "test-NPTH.drl": npth}


def ipc356(inch=False, mirror_y=False):
    unit = 0.00254 if inch else 0.001
    rows = [("327", "A", "R1", "1", 4, 10, "01", ""), ("327", "B", "R1", "2", 4, 6, "01", ""),
            ("317", "A", "VIA", "", 10, 10, "00", "D0300P"), ("327", "A", "U1", "1", 16, 10, "02", ""),
            ("317", "B", "J1", "1", 16, 5, "00", "D1000P"), ("327", "N/C", "X1", "1", 10, 16, "01", "")]
    out = ["C  synthetic test netlist", "P  JOB test", f"P  UNITS CUST {0 if inch else 1}", "P  VER IPC-D-356A"]
    for op, net, ref, pin, x, y, acc, drill in rows:
        y = -y if mirror_y else y
        xs, ys = round(x / unit), round(y / unit)
        coord = f"X{'-' if xs < 0 else '+'}{abs(xs):06d}Y{'-' if ys < 0 else '+'}{abs(ys):06d}"
        line = f"{op}{net:<14s}   {ref:<6s}-{pin:<4s} {drill:>6s}A{acc}{coord}X{round(1.0 / unit):04d}Y{round(1.5 / unit):04d}R000 S0"
        out.append(line)
    return "\n".join(out + ["999"]) + "\n"


def write(dirpath, inch=False, short=False, via=True, mirror_y=False, silk_on_pad=True):
    d = Path(dirpath)
    d.mkdir(parents=True, exist_ok=True)
    for name, text in {**gerbers(inch, short, silk_on_pad), **drills(inch, via)}.items():
        (d / name).write_text(text)
    ipc = d.parent / (d.name + ".ipc")
    ipc.write_text(ipc356(inch, mirror_y))
    return d, ipc
