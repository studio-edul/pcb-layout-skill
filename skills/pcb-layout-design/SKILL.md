---
name: pcb-layout-design
description: >-
  PCB layout design partner that checks its own work with deterministic tools. Turns block rules (decoupling,
  buck hot loop, crystal, motor driver, eFuse, connector ESD/TVS, USB-C, CAN) into numeric near/apart limits,
  runs a placement checker before any coordinate reaches the EDA tool, sizes traces, vias and power paths by
  calculation, audits routed boards beyond DRC, and verifies the fabrication files themselves (Gerber copper
  against the IPC-D-356 netlist, silk and mask, release-to-release diff, BOM/CPL). Imports placements from
  KiCad and EasyEDA Pro. Use for PCB placement or floorplanning, layout or design reviews, trace width / via
  current / thermal / impedance estimates, Gerber and JLCPCB release checks, and scripted layout through an
  EDA API. Also for Korean requests such as PCB 배치, 레이아웃 리뷰, 선폭 계산, 거버 검사.
license: MIT
compatibility: >-
  Python 3.9+. scripts/gerber_check.py needs numpy, Pillow and scipy; placement PNGs need matplotlib; the
  impedance field solver in pcbcalc.py uses numpy and scipy when present; everything else is standard library. Works with any EDA tool; KiCad and EasyEDA Pro importers included.
metadata:
  author: studio-edul
  version: "1.1.1"
---

# PCB layout design

Scripts (run from this skill's directory; every Python script prints `--help`):
| script | use |
|---|---|
| `scripts/placement_check.py` | placement JSON -> ERROR / WARN list + PNG. **Mandatory before coordinates go anywhere** |
| `scripts/placement_from_kicad.py` | `.kicad_pcb` -> placement JSON skeleton (courtyards, sides, classes) |
| `scripts/placement_from_easyeda.js` | same for the board open in EasyEDA Pro (run inside the client) |
| `scripts/baseline_diff.py` | baseline vs current placement JSON -> locked parts, board extent or keep-outs that changed |
| `scripts/pcbcalc.py` | trace width, via current, microstrip / differential impedance (2D field solver with copper and solder mask), stripline, LDO heat, buck inductor, RC, divider, power budget |
| `scripts/gerber_check.py` | fabrication files: `layers`, `render` (print preview, silk on pads, copper to edge), `netcheck` (copper + plated holes vs IPC-D-356: shorts, opens), `diff` (two releases) |
| `scripts/audit_release.py` | release folder / zip: required layers, Gerber / Excellon structure, BOM / CPL consistency |

References (read when the task needs them):
- `references/late_changes.md` - changing a laid-out board: what part swaps and syncs broke, `baseline_diff.py`, moving MCU signals (STM32G431)
- `references/review_release.md` - review rubric and finding format, DFM checklist, release checks, bring-up
- `references/routing_review.md` - post-route audit beyond DRC, power-path rating table, inner planes, USB-C 16P fan-out, simulate-then-apply rework, the visual pass
- `references/emc_protection.md` - return paths and layer changes, crosstalk spacing, signal routing, ESD / TVS / surge, filtering, isolation
- `references/power_thermal.md` - power budget, theta_JA tables, formulas, heatsink position, analog supply
- `references/easyeda_pro_api.md` - scripted layout in EasyEDA Pro: units, rotations, pours, DRC, part swaps, traps
- `references/jlcpcb_ordering.md` - order options, PCBA cost model, BOM / CPL upload traps (dated, re-check)
- `references/kicad_notes.md` - KiCad exports for the tools above

## Operating rules
1. **Verify before asserting.** Datasheet, reference design, current fab capability and the user's files beat
   generic numbers. Never invent pinouts, part numbers, distributor IDs, ratings or stackup dimensions.
2. **Facts vs assumptions.** Label assumptions; ask only blocking questions.
3. **Deterministic tools, never mental arithmetic.** Placement -> `placement_check.py`; widths, via counts,
   impedance, regulator heat -> `pcbcalc.py`; release -> `audit_release.py` + `gerber_check.py`. Every power
   path gets a rating table with the weakest element named ("about 1 A per via" by feel is how a 5 A path ends
   up rated 2-3 A).
4. **No coordinates are handed over or pushed to an EDA tool before `placement_check.py` reports ERROR 0** and
   its PNG has been opened and described in one line. No tool access is not an exception.
5. **Don't mutate design files blindly.** A review writes nothing. Read the project first, including its saved rule
   set ("project rule" in section 8), keep a saved copy before bulk edits, read back and verify after every scripted
   stage. Parts the user fixed carry `"locked": true` in a baseline file; after part swaps, syncs and optimiser runs
   `scripts/baseline_diff.py` prints `SUMMARY baseline changes 0` (`references/late_changes.md`). Bulk rework is
   simulated on a board dump first and the real board is diffed against the simulation afterwards
   (`references/routing_review.md` section 6).
6. **DRC 0 is not a review.** Autorouter output is a draft. Before calling a routed board done, run the
   post-route audit and check every numbered rule of the project's own guide against the board - planned
   rules (thermal vias, heat-spreader areas, via counts) silently drop out during routing.
7. **The fab builds from the files, not the database.** Before an order, check the exported Gerbers against
   the netlist and render them (`gerber_check.py`); after any late change, diff the new release against the
   checked one.
8. **Safety boundary.** Mains, high voltage, high current, Li batteries, medical / automotive work need a
   qualified human review. Never claim certification.

## Gates
1. **Requirements** - function, environment (Ta inside the enclosure), rails and peak currents, interfaces and
   connector exposure (ESD), mechanics (envelope, mounting, cable exit), assembly / cost, what "done" means.
2. **Architecture & schematic** - block diagram, power tree + budget, pin allocation, ERC 0. Re-assign MCU pins
   after placement so every bus leaves on the package side facing its target, in the target's pin order; swap
   interchangeable signals (motor phase polarity, CC1/CC2, ESD-array channels, plain GPIOs) to uncross. Do this
   before fighting the router and write the final pin map into the spec for firmware. What a pin move must
   respect: `references/late_changes.md` section 3.
3. **Stackup, placement, routing** - sections 1-7.
4. **Release** - DRC 0 with fab rules, Gerber / drill / BOM / CPL, section 7 steps 8-9.
5. **Bring-up** - current-limited supply, rails before expensive parts, log measurements.

## 0. Definitions
- **Courtyard** = body / pad extent + excess (IPC-7351B level N: 0.25 mm; 0402 / 0603: 0.15 mm; connectors body
  + 0.25 mm, + 2 mm in the plug direction). The checker takes courtyards, never bare body sizes.
- **Anchor** = IC / connector / inductor / bulk cap that fixes a group. **Satellite** = part that belongs to one
  anchor pin (decoupling, bootstrap, FB/RT, IREF, crystal load caps, CC/ESD next to a connector).
- Spacing values are **targets**; fab minimums are lower bounds (in parentheses). Never design to the bound.

## 1. Area budget first
Sum of courtyards / usable area (board minus hole keep-outs and edge band); state the number - `placement_check.py`
prints it per side with the verdict below.
| occupancy | verdict | action |
|---|---|---|
| < 40 % | relaxed | 2-layer may work |
| 40-60 % | normal | 4-layer comfortable |
| 60-75 % | dense | 4-layer + enforced zone floorplan + mostly 0402 |
| > 75 % | too dense | shrink / remove parts, bigger board, or double-sided |

Above 70 %: propose part changes first (smaller bulk cap or crystal, pads instead of headers, 0402 for low-voltage
passives, drop optional LEDs). Double-sided is the last resort: it usually forces the more expensive assembly
service (`references/jlcpcb_ordering.md`) - report it to the user with the cost.

## 2. Zones (floorplan)
- Group by function: power entry / protection, high-current pass-through, switching regulator, LDO, MCU,
  power / motor driver, communication, connectors. Each zone = a box with coordinates.
- Connectors first (mechanics), then noisy / high-current, clocks, sensitive analog; signal flow edge -> centre.
- Routing corridor 3-5 mm between big ICs that exchange many signals; no parts in it.
- Separation (edge-to-edge): crystal vs buck SW / inductor >= 15 mm, crystal vs motor outputs >= 12 mm,
  ADC / analog RC vs SW node >= 10 mm, microphone / analog sensor vs inductor >= 15 mm.
- RF modules: antenna edge flush with / beyond the board edge, keep-out exactly per the module datasheet on all
  layers (copper, parts, holes, battery, screws). In the checker JSON the antenna area is a keep-out with
  `"allow": ["<module ref>"]` (see `assets/placement_example.json`).

## 3. Placement order (strict)
1. Outline, mounting holes, keep-outs (M3: part keep-out radius 3.5-4.0 mm, copper keep-out >= 3 mm), edge band.
2. **List all near / apart pairs** (section 5) in the checker JSON before placing anything.
3. Fixed parts (connectors, holes) at mechanical coordinates; lock.
4. Anchors on a 0.5 mm grid, rotated so their pins face what they talk to.
5. Satellites at their pin: pin + 0.3-0.5 mm from the pad end, long axis parallel to the pin direction, supply pad
   toward the pin, GND pad toward its via. A satellite on the other board side sits right under / beside its pin and
   needs room for one via next to the pin (not in a pad, not under a neighbour pin). Parts hanging on connector pins
   go on the side where their other net arrives. Reserve heat-spreader areas (opposite side of every exposed-pad
   package dissipating > 0.5 W) as keep-outs before putting passives "under their IC".
6. Remaining passives in rows / columns inside the zone box (pitch table, section 4).
7. Checker until ERROR 0 and WARN 0. If a part cannot fit its zone, report "placement failed" with the reason.
   Dense boards: optimise (e.g. annealing on the 0.25 mm grid) with the checker's rules as the cost.
8. Then route.

## 4. Numbers
**Grid:** IC / connector / inductor / bulk centres 0.5 mm; passives / SOT / diodes 0.25 mm; 1.27 mm headers on
0.635 mm; 90 deg rotations only.

**Row pitch (side by side / end to end):** 0402 1.25 / 2.25, 0603 1.75 / 3.00, 0805 2.25 / 3.75, 1206 2.75 / 5.00,
SOT-23 3.50 / 3.75 mm. One row = same size, rotation and centre line. Pin 1 / polarity all left or top; polarised
parts in the same rotation (pick-and-place batches).

**Part-to-part courtyard gap (target, fab min):** passive-passive 0.30 (0.15-0.18); 0603 0.35 (0.25); SOT 0.50 (0.40);
SOIC 0.60 (0.40); IC-IC / QFN 1.0-1.5 (1.0); QFN/QFP-passive 1.0, decoupling 0.3 (never < 0.25 lead-to-pad);
connector-anything 1.0 (THT pins 1.5 for the iron); tall (> 5 mm) parts +1 mm.
Checker classes: passive / power / ic / module / connector / mech.

**Edges:** copper 0.4 mm (pour 0.5; never < 0.3), SMD pad 0.8 mm, body 0.5 mm for assembly without rails; 2.5 mm if
the assembler needs rails. For connectors and modules (edge-hanging USB-C, antenna-edge modules) the checker
asks each side to reach the edge or keep the band; holes (mech) are exempt. Tell the fab about overhangs
(`references/jlcpcb_ordering.md`).

## 5. Block rules -> near / apart entries (edge-to-edge)
In reviews and in the checker's `why` field write the rule ID together with what it requires ("B9: TVS within 5 mm of
the connector pin") - the reader does not have this table.
| ID | block | rule |
|---|---|---|
| B1 | 100 nF decoupling | <= 1.0 mm from the pin pair; 1 uF <= 3 mm; 10 uF <= 5 mm; bulk <= 15 mm; cap -> via <= 0.5 mm |
| B2 | buck | input cap <= 0.5-2 mm (smallest closest) on the IC's layer, tied to VIN / GND pins; bootstrap <= 1 mm on the BOOT/SW side (SW and BOOT never pass FB); inductor <= 3 mm; FB/RT <= 2 mm on the side away from SW, via next to the pin; SW copper <= 15 mm2 |
| B3 | crystal | <= 5 mm from the MCU (target 3), load caps beside it, guard ring, nothing switching under / near it |
| B4 | motor driver QFN | VS 100 nF <= 1 mm, VS 10 uF <= 3 mm, charge pump <= 1-1.5 mm, IREF <= 1.5 mm, EP via array + ring |
| B5 | eFuse / high-current switch | control R/C <= 2 mm, IN/OUT copper >= 25 mm2 each, vias per side = I / via rating (`pcbcalc.py via-current`; 0.3 mm via ~ 0.53 A at 10 C) |
| B6 | power MOSFET, wide power pins | no vias in or between the pads; copper bar beyond the pad row with the via array on the bar |
| B7 | bulk / electrolytic cap | >= 2 vias per pad beside the pad ends, outside the can's base, into an unbroken part of the plane |
| B8 | grounds of power parts | own via(s) at the pad of every regulator, bulk / output cap, TVS and ESD array; no ground daisy chain on signal-width tracks; never pour-only |
| B9 | external connector ESD / TVS | TVS <= 5 mm from the connector pin, protected IC <= 10 mm behind it; short wide GND via |
| B10 | power input | fuse / PTC -> TVS -> bulk; connector rated >= 1.5 x max current; several GND vias at the entry |
| B11 | USB (real USB) | ESD at the connector, D+/D- 90 ohm pair, MCU-to-connector <= 50 mm |
| B12 | USB-C / shelled receptacle | no vias and no component-side copper under the shell; fan-out inboard of the pad row (`references/routing_review.md` section 4); VBUS via columns sized from the pass-through current; GND pins into the shell legs |
| B13 | CAN / RS-485 | ESD at the connector, pair kept together; optional common-mode choke at the connector |
| B14 | connector CC / termination resistors | <= 5 mm from the pin |
| B15 | analog vs switching | apart >= 10-15 mm |

## 6. Routing, stackup, EMC (details: `references/emc_protection.md`)
- 4-layer: L1 parts + signals, **L2 solid GND (no traces, no slots)**, L3 power areas, L4 slow signals + GND.
- Widths from `pcbcalc.py trace-width` (5 A, 1 oz outer, 10 C rise -> 2.8 mm; 3.5 mm with margin); share high
  current between an outer trace and an inner area; via arrays from `pcbcalc.py via-current`.
- Clearance 0.15 mm default, 0.30 mm on 24 V nets. Tracks 0 / 45 / 90 deg only (curves only where an RF design asks
  for them; fix router / importer skew before release), no acute angles.
- Vias: none under connector shells; under ICs only EP thermal vias and that IC's own pin / decoupling vias; never
  in or between fine-pitch pads; >= 0.2 mm (target) from pads of other nets.
- Power is never left at autorouter width: draw the power stage by hand first (bars + via arrays at the pads),
  widen the remaining power tracks to the clearance limit afterwards, then rate every path (operating rule 3).
- Plane layers: a signal track there cuts the plane - short hops only, parallel to the plane current, no power via
  left in a pocket. Via antipads merge below ~1.1 mm pitch (0.6 mm via, 0.25 mm plane clearance): a row of vias
  across a plane strip is a fence. Sheet resistance 0.5 oz ~ 1 mOhm/square, 1 oz ~ 0.5.
- A fast signal's layer change moves its return current too: GND to GND reference -> a GND via beside the signal via
  (about 2 mm, heuristic); GND to a power plane -> a stitching capacitor near the via, or stay on the layer. <= 2 vias
  per fast net. Two signal layers with no plane between them couple broadside: cross them, don't stack them.
- SPI: MOSI/SCLK matched +-2 mm, series R at the source only when the waveform needs it, <= 1 via, edge gap >= 2x
  width to other signals (the 3W rule, centre to centre), never parallel to I2C / UART > 5 mm. I2C >= 10x width from
  SPI SCLK, never parallel to PWM / STEP.
- Kelvin-connect sense / ADC lines; ESD current path short and wide to the plane.
- Copper hygiene: no islands, no necks < 0.2 mm, thermal relief on pour pads (not on EPs), GND stitching along the
  edge every 5-10 mm.
- Thermal: parts > 500 mW get copper + vias; Ta inside an enclosure = outside + 15-30 C; LDO > 1 W -> buck.

## 7. Verification (mandatory)
1. Write the placement JSON (schema at the top of `scripts/placement_check.py`; start from
   `scripts/placement_from_kicad.py` / `scripts/placement_from_easyeda.js` or `assets/placement_example.json`):
   courtyards, classes, zones, keep-outs (holes as circles), near / apart from section 5, sides, board origin.
2. `python scripts/placement_check.py placement.json --png placement.png`
3. Open the PNG, describe it in one line (red = violating parts).
4. Fix until ERROR 0 and WARN 0.
5. Push to the EDA tool, read the real positions back (the importers above), check again.
6. After routing: tool DRC (clearance, unrouted 0, silk over pads 0).
7. Post-route audit (`references/routing_review.md`): satellite connection lengths, power widths and via counts in
   the power-path rating table, own ground vias, copper / vias under shells and ICs, plane necks and pockets on the
   real fill, noisy nets beside sensitive pins, detours, track angles, thermal provisions - then the visual pass of
   section 7 there. Fix, re-run DRC, list what stays with the reason. Parts moved while routing go back through
   steps 1-5, and where a baseline exists `baseline_diff.py` prints `SUMMARY baseline changes 0`.
8. Release files: `python scripts/audit_release.py <dir-or-zip> --layers <n>` (add `--pcb-only` when there is no
   BOM / CPL yet) and the checklist in `references/review_release.md`.
9. Fabrication-level checks with the exported IPC-D-356 netlist:
   `python scripts/gerber_check.py netcheck <release> --ipc board.ipc` (shorts 0, opens 0, pads without copper 0;
   add `--min-gap 0.1` for an independent clearance look), `gerber_check.py render <release> --out preview` (open
   both PNGs: legible silk, bottom text reads correctly from below, pin-1 / polarity marks inside the outline,
   copper-to-edge), and after any late change `gerber_check.py diff <checked> <new>` - only the intended change
   may show. When the user hands over fabrication files alone, steps 8-9 are the whole job.

Self-test: `assets/placement_example.json` -> ERROR 0 / WARN 0 (the repository's `tests/` cover every
Python script).

## 8. Output formats
- **Design:** assumptions, occupancy %, zone table, coordinate table (ref, x, y, rot, side), checker summary,
  risks, next action.
- **Review:** findings first, most severe first:
  `[Critical|Major|Minor|Question] title / Evidence (measured vs required, rule ID with its meaning, source) / Impact / Fix / Confidence`.
  Order: manufacturing blockers -> power & thermal -> return paths & SI -> EMC -> mechanical -> test / service ->
  compliance / lifecycle. Evidence ladder: measurement > datasheet / reference design > fab capability > standard >
  project rule > heuristic (label heuristic-only findings). Rule precedence: user requirement & safety > datasheet
  > fab capability > project rule > generic rule. Then: counts by severity, what was reviewed, what could not be
  verified, ready for the next gate or not. Never "looks good" without the checks performed and the residual
  uncertainty. Don't inflate preferences into Critical.
- **Calculation:** command, inputs, assumptions, result, limitation.
