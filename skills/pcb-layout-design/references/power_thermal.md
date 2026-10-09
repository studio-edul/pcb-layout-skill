# Power and thermal reference (pcb-layout-design)

## Hot-part screening
- Dissipation > 500 mW -> "hot part": give copper area and thermal vias, keep heat-sensitive parts
  (crystal, electrolytics, sensors) away.
- Tj = Ta + P x theta_JA. Use theta_JA from the datasheet; JEDEC 4-layer values are optimistic on small
  boards, add 20-50 %.
- Enclosure: Ta = outside + 15-30 C. Outdoor / vehicle: design for Ta >= 70 C.
- LDO: P = (Vin - Vout) x Iout. Above 1 W use a buck. SOT-23 LDO practical limit ~0.3 W, SOT-223 ~1 W with copper.

## Power budget first
Table per part: designator, rail, Imax, Pmax, duty cycle, Pavg; sum per rail and total; list parts > 500 mW
and clusters of warm parts (heat adds up). Template: designator,part,v_supply,i_max_a,duty,p_avg_w
(`scripts/pcbcalc.py power-budget <csv>` aggregates it).

## Typical theta_JA vs copper (still air, planning only - the datasheet wins)
(claude-pcb-designer thermal-design table, MIT)
| package | min copper | 1 cm2 | 4 cm2 |
|---|---|---|---|
| SOT-23 | 250 | 180 | 130 |
| SOT-23-5 | 200 | 150 | 110 |
| SOT-223 | 60 | 40 | 25 |
| SOIC-8 | 150 | 100 | 70 |
| QFN-20 (EP + vias) | 50 | 30 | 20 |
| QFN-48 (EP + vias) | 35 | 22 | 15 |
| TO-252 (DPAK) | 50 | 30 | 20 |
Check: `python scripts/pcbcalc.py ldo --help` for LDO margin with Ta and theta_JA.

## Copper area vs thermal resistance (1 oz, rough)
| copper area | approx. theta to ambient |
|---|---|
| 1 cm2 | 100 C/W |
| 2 cm2 | 75 C/W |
| 4 cm2 | 55 C/W |
| 8 cm2 | 40 C/W |

## Formulas (compute with a script, never by guess)
- IPC-2221 external trace: I = 0.048 x dT^0.44 x A^0.725 (A in mil^2); internal layers use 0.024.
  1 oz = 1.378 mil thick; width = A / thickness.
- Via current: `pcbcalc.py via-current` (0.3 mm hole, 1.6 mm board, default derating 0.7) gives 0.53 A per via at
  20 um plating and 10 C rise (0.63 A at 25 um, 0.73 A at 20 C rise). "1 A per via" is 20 C rise without derating.
- Plane sheet resistance: 1 oz 0.5 mOhm per square, 0.5 oz 1 mOhm per square (JLC 4-layer inner layers are 0.5 oz
  unless ordered otherwise). Every power path gets a rating table (`routing_review.md` section 2).
- Buck inductor: L = (Vin - Vout) x Vout / (Vin x fsw x dI), dI = 20-40 % of Iout(max).
- Microstrip impedance (IPC-2141): Z0 = 87 / sqrt(er + 1.41) x ln(5.98 h / (0.8 w + t)).
- Stepper driver loss: P ~ 2 x Irms^2 x Rds(on)(HS+LS); TMC2240 0.23 ohm at 1.5 A RMS -> ~1.0 W.

## Where the heat leaves, where a heatsink goes
- Exposed-pad packages (QFN, TQFN, DFN, HTSSOP - motor drivers, bucks, eFuses): the heat leaves through the EP
  into the board; the path through the mould to the package top is far worse (take theta_JC top / bottom from the
  datasheet). The cooling system is: EP solder joint -> via array -> L2 plane + copper on the opposite side.
- Heatsink position, best first:
  1. **Opposite board side, directly under the EP via field**: a copper island on the EP net (usually GND), at
     least the heatsink footprint (8 x 8 mm or more for a 5 x 5 mm QFN), solder mask opened, free of parts and
     tracks; stick-on heatsink, or a 1 mm gap pad (3-6 W/mK) to a bracket or the enclosure. Solder mask left on
     costs about 5 K/W on a 5 x 5 mm contact and 0.6 K/W on 14 x 14 mm (25 um, 0.2 W/mK - rough).
  2. Top of the package: only what gets through the mould. The heatsink must not be larger than the package
     unless every neighbour is lower than the package top (a 0.8 mm TQFN sits lower than 0805 / 1206 MLCCs).
  3. Air across the board: forced air lowers board-to-ambient resistance more than a small heatsink in still air
     (heuristic) - a small fan or the machine's airflow counts as a measure.
- A heatsink only helps toward something cooler. A stepper motor end cap runs 60-80 C: do not couple the driver
  to it before measuring.
- Board measures in order of effect: EP soldered over its full area (paste window 50-60 % when vias are open),
  via array (3 x 3 at 0.3 mm / 1.1 mm pitch or 4 x 4 at 0.25 mm / 0.85 mm), ring of 10-16 GND vias just outside the
  courtyard, unbroken L2 under and around the part, opposite-side copper island, 2 oz outer copper.
- Lower the loss before adding metal: standstill current reduction, lower run current / load-adaptive current
  (CoolStep), supply voltage and chopper frequency no higher than needed (switching loss), derating from the
  driver's temperature readout / warning flag.
- Decide by measurement: worst-case current, 20-30 min soak, driver temperature readout or a thermocouple on the
  opposite-side pad. Keep other heat sources (eFuse, regulators) >= 15 mm away and out of the heatsink area.
- These provisions are placement decisions: reserve the opposite-side area as a keep-out before placing passives
  under the IC, and check after routing that the via ring and the island really exist.

## Analog supply
- Analog rail: ferrite bead + 10 uF bulk + 100 nF at each pin. Vref: 10 uF + 100 nF next to the ADC.
- ADC input RC: R 10-100 ohm, C 1-10 nF.
