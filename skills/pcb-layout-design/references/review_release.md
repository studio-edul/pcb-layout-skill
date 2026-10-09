# Review, DFM, release and bring-up (pcb-layout-design)

Adapted from github.com/SPREsxm/claude-pcb-designer (MIT) design-review-rubric, dfm-checklist,
release and bring-up references; numbers aligned with this skill.

## Review sequence (findings first, most severe first)
1. **Manufacturing blockers** - outline closed on the outline layer only; copper/hole/slot-to-edge; min
   trace/space/drill/annular ring/mask; all nets routed; DRC errors explained; pads/mask/paste/thermal reliefs
   manufacturable; BOM and CPL match the design, no placeholders.
2. **Power & thermal** - path width, copper weight, via count, connector rating (>= 1.5x), fuse margin, one
   rating table per power path (`routing_review.md` section 2); thermal provisions of the guide present on the board;
   regulator dropout/stability/inrush; dissipation, copper area, thermal vias, Ta inside the enclosure; hot
   parts away from temperature-sensitive ones.
3. **Return paths & SI** - continuous reference under fast signals; nothing crosses a plane slot/split;
   return vias at layer changes; pairs symmetric; clocks/SW/RF/analog separated; termination at the right end.
4. **EMC & immunity** - hot loops minimal; cable I/O filtered/protected; ESD current short and wide; stitching
   follows the intended current; board-edge and cable radiation considered.
5. **Mechanical** - connectors accessible with mating and cable-bend clearance; screw heads, ribs, standoffs;
   board flex/vibration; keep-outs include metal and fasteners.
6. **Test, debug, service** - rails/GND measurable without shorting pins; programming/recovery reachable;
   test points match probe/fixture; rework path for expensive parts.
7. **Compliance & lifecycle** - standards identified; creepage/clearance/isolation; derating documented;
   second source / EOL risk.

Severity: Critical (stops fab, damages hardware, unsafe, function impossible) / Major (likely failure, low
yield, reliability or compliance risk) / Minor (cost, robustness, serviceability) / Question (missing fact).

Finding example:
```
[Major] Motor phase OUT1A necks to 0.25 mm for 6 mm
Evidence: U5 pin 23 -> J3.1 on L1, 0.25 mm wide; 1.5 A RMS needs >= 0.8 mm (pcbcalc trace-width, 10 C rise).
Impact: trace heating and voltage drop at full current.
Fix: neck down only within 1 mm of the pad, then 1.0 mm; or add a parallel L4 trace with 3 vias.
Confidence: high (measured in EDA, calculator output attached).
```
A visual review cannot prove impedance, thermal performance, EMC compliance or safety - say what needs
measurement, simulation, the fab stackup or a qualified reviewer.

## DFM checklist (before export)
Schematic
- Every VDD/VSS pin connected; decoupling per datasheet; no floating CMOS inputs; NC pins really NC.
- One pull-up pair per I2C bus; SPI CS per device; reset/boot straps correct; debug header reachable; ERC 0.
- BOM complete (part number, value, package); symbol pins = footprint pads; every "Supplier Part" is a real LCSC number
  (C-number) and matches the part named in the design source.
Layout
- Outline on the outline layer, closed; copper >= 0.4 mm from the edge (pour 0.5); 0 airwires; DRC 0.
- Via annular ring >= 0.15 mm; drill >= 0.3 mm unless needed; via-in-pad filled+capped when used in pads.
- Tracks 0 / 45 / 90 deg only; no vias or component-side copper under connector shells; no vias in or between pads.
- No acute angles; silkscreen text >= 0.8 mm high (1.0 recommended), line >= 0.15 mm, never over pads/vias;
  refdes readable and not under parts.
- Tall (> 5 mm) parts do not shadow small ones; parts > 10 g mechanically fixed.
- Pours: GND fill on all free areas, thermal relief on pour pads, stitching along the edge every 5-10 mm,
  no islands, no necks < 0.2 mm, same-net pour-to-trace spacing >= 0.2 mm.
- Marks: pin-1 and polarity visible after assembly; connector pinouts labelled; board name + revision + date.
- Power: DC-DC SW loop minimal; regulator copper; reverse-polarity and fuse/PTC; Kelvin sense lines;
  high-current via arrays sized by calculation; several GND vias at the power entry.
- SI: controlled-impedance widths from the fab stackup; pairs length-matched; series termination at the
  driver within 5 mm; no stubs; clocks point-to-point; crystal guard ring.
- Mechanical: mounting holes and keep-outs; connector mating clearance; screw-head clearance; thickness specified.
Post-export
- Open Gerbers in an independent viewer (JLC viewer, gerbv); all layers present (copper, mask, silk, outline,
  drill/Excellon); outline on its own layer.
- BOM columns: Designator, Value/Comment, Footprint, LCSC Part #, Quantity. CPL: Designator, Mid X, Mid Y,
  Layer, Rotation. **Check CPL rotations against pin 1 in the JLC preview** (the most common assembly error).
- Netlist vs Gerber: no missing pads, no extra nets.
- `python scripts/audit_release.py <release-dir-or-zip> --json`; resolve every error, review every warning.
  Release zips can hold files with non-ASCII names (EasyEDA adds a Chinese readme); some `unzip` builds stall on
  them - the scripts here read zips directly.
- Render silk over mask (`scripts/gerber_check.py render`): text legible, bottom text reads right from below, silk on pad
  openings ~0, and every pin-1 / polarity mark inside the outline (footprint dots beside an edge connector fall off
  the board and are not printed - add a mark inboard).
- Netlist vs Gerber for real (`scripts/gerber_check.py netcheck --ipc`): rasterises the copper layers, joins islands
  through the plated drill hits and compares them with the IPC-D-356 pad / via nets (shorts 0, opens 0, pads without
  copper 0). Some EDA tools list vias in two drill files (all plated holes + vias only): a hit removed from one file
  is still drilled from the other. Then mask opening on every pad, paste on every SMD pad, no exposed via outside
  thermal pads (a same-net via inside an SMD pad passes DRC - found one in a header pad), copper to edge.
- After a late value change compare the new release with the inspected one (`scripts/gerber_check.py diff`; export
  order and aperture numbers change every time, so a text diff is useless): nothing but the intended difference may
  show. This caught duplicated track segments left by re-creating a part.
- BOM: one line per distributor part number (a swapped part with a different Value splits a line in two, and the
  assembler then flags "same part matched twice").
- Price before promising one: `references/jlcpcb_ordering.md`.

## Bring-up
1. Visual + continuity: no shorts rail-to-GND (measure each rail's resistance to GND before power).
2. Current-limited bench supply (start ~100 mA limit), raise slowly; watch for heat (finger / thermal camera).
3. Check every rail voltage and ripple, then reset, clock, programming, then interfaces one by one.
4. Then load tests (motor current, pass-through current) and thermal soak; log everything
   (rail, value, current, temperature, firmware version).
