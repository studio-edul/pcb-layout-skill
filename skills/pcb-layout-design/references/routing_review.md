# Post-route audit, power-path rating, connector fan-out, rework workflow (pcb-layout-design)

**DRC 0 only proves clearance and connectivity.** The checks below apply to any routed board. What they found comes
from one example board: a 42 x 42 mm 4-layer stepper driver (24 V daisy chain over USB-C, 5 A pass-through, routed
with EasyEDA Pro + Freerouting + a grid router), where every item was wrong on a DRC-clean board. Its numbers - the
"found on the example board" column, the worked example in section 2, the USB-C template in section 4 - are a
pattern, not limits.

Contents: 1 audit of a routed board - 2 power-path rating table - 3 inner power planes - 4 USB-C 16P fan-out -
5 switching regulator as routed - 6 rework workflow (simulate, then apply) - 7 the visual pass

## 1. Audit of a routed board (autorouter output is a draft)
| check | how | found on the example board |
|---|---|---|
| satellite reaches its pin the short way | routed length between the two pads vs straight distance; > 3x is a finding | LDO input cap 0.2 mm under its pin fed through a 40 mm loop; buck FB / RT resistors under their pins fed by 17 mm loops; eFuse dV/dt cap 2 mm from its pin through a via 6 mm away |
| power left at signal width | width and via count of every segment of every power net | 5 A pass-through on 0.2 mm with 2 vias; bulk cap on one 0.15 mm stub and one via; MOSFET source on 0.15 mm |
| ground returns | every power part, bulk / output cap, TVS and ESD array has its own via at the pad | TVS, LDO, bulk cap and buck output cap grounds daisy-chained on one 0.2 mm track; ESD array grounded by the pour only |
| copper under connector shells | component-side tracks and any via inside the shell outline | 31 tracks and 5 vias under three USB-C shells |
| vias in pad rows | via overlapping or between pads of a part | vias between SO-8 pads; via partly in an 0402 pad |
| noisy net beside a sensitive pin | SW / BOOT, motor / class-D / relay outputs vs FB, crystal, ADC, sense lines, antenna feed | BOOT 0.15 mm from the buck FB pin, FB routed between the pads of the boot cap |
| detours | net length vs pad-to-pad distance, via count per net | CAN low 84 mm with 6 vias around the motor connector |
| plane damage (section 3) | signal tracks on the plane layer, pockets, necks, via fences | bulk-cap vias in a pocket behind a signal track (0.5 mm neck) |
| track angles | segments that are not 0 / 45 / 90 deg | 17 skewed pad-entry stubs |
| thermal provisions of the guide | EP via count, GND via ring outside the courtyard, opposite-side copper island free of parts / tracks, mask opening | 3 x 3 EP vias present; via ring and the 8 x 8 mm bottom pad under the motor driver missing. After routing only 4 legal ring sites and a 4.3 x 4.5 mm pad were left (pin-escape vias, bottom-side decoupling and pull-ups all around): reserve both as keep-outs at placement |
| via to foreign pad | distance via edge to pads of other nets (target >= 0.2 mm, rule 0.15) | about 30 vias at 0.15-0.2 mm |

Report what was fixed and what stays, with the reason (e.g. "CAN low still goes round the east edge on the
bottom, 39 mm: centre blocked by the MCU; shielded from the motor outputs by L2 / L3").
FB coupling estimate when in doubt: charge q = C x dV (0.05-0.1 pF to a 24 V switch node = 1-2 pC) onto
5-10 pF of node capacitance = 0.1-0.5 V spikes on a 1 V feedback node. Heuristic, but it decides the fix.

## 2. Power-path rating (mandatory table)
List every series element of each power path, compute its capacity with `scripts/pcbcalc.py`, and state the
smallest value as the rating of the path. Do not size via arrays or planes by feel.
- `via-current --hole-mm 0.3 --plating-um 20`: 0.53 A per via at 10 C rise, 0.73 A at 20 C (default derating 0.7).
- `trace-width --current-a 5`: outer 1 oz 2.8 mm; inner 1 oz 7.2 mm; inner 0.5 oz 14.5 mm (10 C rise).
- Plane resistance: 0.5 oz about 1 mOhm per square, 1 oz about 0.5; count squares along the path. A neck shorter
  than its own width is judged by resistance and heat (squares x sheet R x I^2), not by long-trace ampacity
  (heuristic - say so).
- JLC 4-layer default inner copper is 0.5 oz: either order 1 oz inner or share the current with outer copper.

Worked example (the example board, eFuse limit 5 A). First pass sized by feel, second pass by the table:
| element | first pass | pcbcalc 10 / 20 C | second pass | pcbcalc 10 / 20 C |
|---|---|---|---|---|
| J1 VBUS vias (2.5 A per pad pair) | 3 + 3 | 1.6 / 2.2 A per side | 6 + 5 | 3.2 / 4.4 and 2.7 / 3.6 A |
| L3 strip 5.5 mm x 55 mm | 0.5 oz, 10.9 mOhm | 5 A needs 9.5 mm at 20 C | order 1 oz inner copper | needs 4.75 mm at 20 C |
| eFuse IN vias | 4 | 2.1 / 2.9 A | 9 | 4.8 / 6.5 A |
| eFuse OUT vias | 4 + 1 | 2.7 / 3.6 A | 10 + 1 | 5.9 / 8.0 A |
| J2 VBUS vias, right | 2 | 1.1 / 1.5 A | 6 | 3.2 / 4.4 A |
| J2 VBUS vias, left | 2 | 1.1 / 1.5 A | 3 x 0.4 mm drill | 2.0 / 2.7 A (weakest) |
The first pass was rated 2-3 A although the eFuse limit is 5 A. The rule "eFuse >= 8 vias per side" was right.
Method of the second pass: remove the old cluster, compute the legal via sites for the net (all layers, hole
spacing, no via in pads), walk a 28 mil lattice from the pad over legal 24 mil top-track cells and take the
nearest N sites (`viapack.py` in the project route tools) - same-net vias may sit 0.6 mm apart. Where other
nets leave three sites only, use 0.4 mm drill vias. Decide the pass-through current before placing the
connector-side parts, and reserve the via rows.

## 3. Inner power planes
- Draw the planes as rectangles per net, then **look at the real fill** (EasyEDA:
  `pour.getCopperRegion().getState_PourFills()`), not at the rectangles.
- Narrowest width on the best path between two vias: rasterise the fill, open it with a growing disk until the
  two points disconnect (`fillmap.py` + `necks.py` in the project route tools).
- Via antipad = via pad + 2 x plane clearance (0.61 + 2 x 0.254 = 1.12 mm). Vias closer than that leave no copper
  between them: a row of signal vias across a plane strip is a fence. Line vias up along the current direction.
- A signal track on the plane layer cuts it. Allow short hops only, parallel to the plane current, and check that
  no power via ends up in a pocket behind the track (move the track, not the via, when the via belongs to a
  bulk / decoupling cap).
- Decide the plane partition together with the connector and via-field positions: the data-pin via field of a
  connector sits between its VBUS vias, so the plane needs a corridor under the pad row / shell.

## 4. USB-C 16P receptacle used for power + one data pair (example board: 0.5 mm pad pitch, 0.61 mm vias, 0.15 mm tracks)
No vias and no component-side copper under the shell; everything escapes inboard of the pad row.
Why a template: a track that passes the via of the neighbouring pad has 0.117 mm (4.6 mil) left - below the rule,
so vias are staggered and two tracks jog. u = along the row from the centre, v = inboard from the pad centres, mil.
| net | top layer | via |
|---|---|---|
| VBUS pad pair (u +-88.6 / 100.4) | 20 mil track on the pair | v 38 and v 68; third at (u +-124.5, v 53) |
| GND pins (u +-120.1 / 131.9) | 12 mil track outward into the shell-leg pad | none (the plated slot is the via) |
| pair pad A1 (u -29.5) | inboard to v 31.5, 45 deg outward | (-44, 46) |
| pair pad B1 (u -9.8) | inboard to v 45, 45 deg jog to u -18 | (-18, 62) |
| pair pad A2 (u +9.8) | straight | (9.8, 100) |
| pair pad B2 (u +29.5) | inboard to v 37.5, 45 deg outward | (38, 46) |
| CC next to B2 (u +49.2) | jog 12.8 mil outward (the next pad is NC), then straight | at its resistors |
Bottom layer: B link (38, 46) -> (22, 62) -> (-18, 62); A link (-44, 46) -> (-44, 74) -> (-18, 100) -> (9.8, 100).
A leaves the field at (9.8, 100), B on the outer side of its link; smallest gap 0.16 mm.
- CC / pull-up resistors, ESD array: on the layer and the side where their *other* net arrives; the one signal that
  must cross the field does it on the top layer beyond the last via (v > 115).
- Two stacked 0402 rows need 1.14 mm pitch (courtyard 0.84 + 0.3), not the 0.81 mm that the pads allow.
- An ESD array whose two channels are interchangeable may be turned so that its pads face the way the pair leaves.

## 5. Switching regulator, as routed
- Boot cap on the side of the BOOT / SW pins (other board side right over the pins is fine: one via per pin).
  SW and BOOT never pass the FB pin or the divider.
- FB / RT parts under the IC: via next to the pin (not in the pad, not in the resistor pad), parts either side of it.
- Input cap tied to the VIN and GND pins on the IC's own layer; no ground track between the VIN pins and the cap;
  cap ground vias at the cap pad; a further via from VIN into the plane.

## 6. Rework workflow for scripted EDA (simulate, then apply)
1. Save and copy the project file (one backup per stage).
2. Dump tracks / vias / pads (+ DRC) from the tool.
3. Write the change as a plan applied to the dump in memory: `{move, padpos, rip, segs, vias}`.
4. Check before touching the board: clearance of the new copper and of the moved pads, net islands, placement
   checker with the moved parts, a picture of the area. Route what is left with the grid router.
5. Apply in the order rip -> move -> copper; then compare the real board with the simulation (tools merge and
   split segments, leftovers appear).
6. Rebuild pours, reopen the document, run DRC; then section 1 again.
7. Part pins and interchangeable signals are design variables: re-assign MCU pins so each bus leaves on the side
   that faces its target, swap interchangeable signals (CC1-CC2, ESD-array channels, motor phase polarity) to
   uncross, check each move against `late_changes.md` section 3, and write the result into the spec for firmware.

How to run these checks: most need a dump of the routed board from your EDA tool (tracks, vias, pads with nets,
pour fills) and a short script per check - length per net, width and via count per power segment, vias inside
connector shells or pad rows, distance between noisy and sensitive nets. The checks that work on fabrication files
alone (shorts / opens against the netlist, copper to edge, smallest gap between nets, silk) are in
`scripts/gerber_check.py`.

## 7. The visual pass
The person receiving the board looks at the 2D view, the 3D view and the fab's preview; on the example board they
caught things every script had passed. Before reporting, look the same way:
- **Each copper layer alone, then both sides in 3D.** Found that way: a screw terminal whose wire entries faced into
  the board (footprint turned 180 deg), tracks and vias under USB-C shells, unconnected-pad markers, a part sitting on
  the wrong side.
- **Track shape.** 0 / 45 / 90 deg only (curves only where an RF design asks for them). Freerouting and its importer
  left 17 pad-entry stubs a few degrees off: list the segments whose angle is not a multiple of 45 deg and move their
  free end, never the pad end. Zigzags and loops that a shorter path would remove are measured with the length
  ratio of section 1.
- **What the fab will print.** `scripts/gerber_check.py render`: silk legible, bottom text reads correctly from below,
  pin-1 and polarity marks inside the outline (a footprint's pin-1 dot beside an edge connector fell off the board).
- Write each observation as a finding with layer and coordinates, fix it, and look again.
