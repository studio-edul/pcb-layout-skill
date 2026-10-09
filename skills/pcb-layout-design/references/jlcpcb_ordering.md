# Ordering assembled boards from JLCPCB (pcb-layout-design)

Recorded from the order form and price page in October 2026. Fab forms and fees change: confirm every value on the
live page before quoting a price or an option name. The user places and pays the order.

## Board options worth a decision
| option | note |
|---|---|
| Inner copper weight | 4-layer default is 0.5 oz. Order 1 oz when an inner layer carries power (a 5 A strip needs about half the width at 1 oz) - compute with `pcbcalc.py trace-width --internal --copper-oz` |
| Via covering | 4-layer boards default to plugged; "tented" may not be selectable |
| Mark on PCB | "Remove Mark" (free default) or a 2D barcode. There was no "order number at a specified position" option, so a `JLCJLCJLCJLC` placeholder on the silkscreen would print literally - leave it off |
| Confirm production file | Yes when anything is unusual (edge-hanging connectors, tight edges): you approve the fab's edited files first, about a day later |
| PCB remark | Say what is unusual, e.g. "connectors J1-J4 overhang the board edge by up to 0.5 mm; please add process edges with tabs / stamp holes, not V-cut" |
| Surface finish | HASL is fine for most; ENIG is flatter for fine-pitch QFN / 0.5 mm connectors at a small extra cost |

## Assembly service and cost model
- **Economic PCBA** is single-sided. Parts on both sides force **Standard PCBA**.
- Standard fixed cost (October 2026): setup about $51 for two sides, stencil about $16 for two sides, and a loading
  fee of about $1.5 **per unique part number, basic or extended alike** - so swapping to "basic" parts saves
  nothing on Standard. Economic charges about $3 per extended part number instead and less setup.
- Variable: parts at the distributor's minimum order quantity plus attrition (the parts API reports
  `leastPatchNumber` and `lossNumber`), about $0.0016 per SMT joint, hand-soldering per THT joint plus a fixed
  fee, special-handling fees for some parts (e.g. USB-C receptacles with through-hole legs, a few cents each).
- The fixed part is the same for 1 or 50 boards. Example (5 boards, 43 part types, two-sided, parts $138): fixed
  ~$133, joints ~$8, total ~$280 before PCB and shipping; assembling 3 of 5 boards: ~$226; 2 of 5: ~$199.
- Biggest lever for the next revision: all parts on one side (Economic assembly).
- Imports: duty / VAT thresholds depend on the destination country - check before promising a landed price.

## BOM / CPL upload
- BOM columns: Comment, Designator, Footprint, distributor part number (LCSC "C" number), Quantity. One line per
  part number: two lines with the same number are flagged "matched to the same part" and left unselected.
- CPL columns: Designator, Mid X, Mid Y, Layer (Top / Bottom), Rotation.
- The EDA tool's own "order" button may upload its own BOM: replace it with the checked files ("Upload BOM/CPL").
- Lines with a warning start unselected (special-handling fee notes included): tick them, or that part is not
  placed.
- Re-check stock on the day of the order; low-stock parts can be pre-ordered.
- In the placement preview check pin 1 of every IC, diode bands, electrolytic "+", LED cathodes, polarised connector
  keys - rotations of library footprints usually match, polarity marks are where mistakes show.

## Silkscreen expectations
- Silk is clipped only where the solder mask is open (pads). Text over tracks prints and stays readable.
- Marks outside the board outline are not printed: a footprint's pin-1 dot beside an edge connector disappears -
  add a mark inboard. `scripts/gerber_check.py render` reports silk outside the outline.
