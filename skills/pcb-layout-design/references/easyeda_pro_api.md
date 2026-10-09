# Scripted layout in EasyEDA Pro (pcb-layout-design)

Observed on EasyEDA Pro 3.2 desktop (2026) through the official API bridge (github.com/easyeda/easyeda-api-skill).
Re-check on newer versions - API details move between releases.

Contents: units and transforms - documents and saving - pours - DRC - part swaps without importChanges - tracks
and vias - placement export - routing - manufacturing exports

## Units and transforms
- PCB API coordinates are **mil** (convert mm -> mil once, at the call). The schematic uses 10-mil grid units, y up.
- PCB component rotation is **counter-clockwise**; schematic component rotation is **clockwise**.
- Bottom-layer parts (`layer: 2`) are flipped about their **local x axis** (local y -> -y), then rotated CCW. Compare
  predicted and real pad positions after the first bottom-side push (expect < 0.01 mm).
- Moving a part to the other side: `pcb_PrimitiveComponent.modify(id, {x, y, rotation, layer})`, then try the four
  rotations until the pads read back at the planned positions.
- Pad positions right after `pcb_PrimitiveComponent.modify` can be stale: compute them from footprint offsets
  captured at import, or wait ~3 s before reading pads.
- Pad ids are `<component id>e<n>`: that is how pads are matched to their component without a per-part call.

## Documents and saving
- Every request: `dmt_EditorControl.openDocument(<uuid>)` first (the user may have switched tabs).
- Save after each stage (`pcb_Document.save()`): a reload drops unsaved moves.
- The bridge times out on long requests: batch work into small requests (<= 20 per-id edits).
- Stale DRC / connectivity after scripted edits: close and reopen the document through the API
  (`dmt_EditorControl.closeDocument(tabId)` + `openDocument`) - no application restart. DRC right after opening returns
  nothing; wait a few seconds.
- After a client restart the bridge reconnects from the client menu (API Gateway -> Reconnect). Reconnect instead of
  restarting the application.

## Pours
- `pcb_PrimitivePour.create(net, layer, polygon, 'solid', false, name, priority, 10, false)` with
  `pcb_MathPolygon.createPolygon(['R', x, yTop, w, h, 0, 0])`. Path (`'L'`) polygons and line width 0.2 are rejected.
- Names are renumbered on create: find pours by net / polygon, not by name.
- A pour region that contains no pad or via of its own net loses its fill at rebuild (island removal): every
  rectangle needs one; overlap same-net rectangles by >= 0.5 mm.
- Rebuild all pours after any copper edit; the real fill is `pour.getCopperRegion().getState_PourFills()` (check
  necks and pockets on that, not on the rectangles you drew). A rebuild right after a part swap can leave a
  pour-to-pad clearance error that a second rebuild clears.

## DRC
- `pcb_Drc.overwriteCurrentRuleConfiguration(cur.config)` works when it gets the `.config` of
  `getCurrentRuleConfiguration()` (the wrapper object is silently ignored).
- Waive a vendor-footprint violation by changing only that table entry, and record the waiver.
- "Netlist Error" (schematic vs PCB) also fires on harmless differences: display-only component properties and a
  net class that exists only on the PCB. Compare the exported netlists yourself (components, pins, nets) before
  acting on it.

## Part swaps without importChanges
- `pcb_Document.importChanges()` opens an "Apply Changes" dialog. On a board whose parts were placed by script it
  proposes to remove and re-add **every** part (schematic and PCB link ids differ): do not apply it - placement and
  routing are lost.
- Net changes on such a board: edit the schematic, then `pcb_PrimitivePad.modify(padId, {net})`.
- Replacing a part: create the new device in the schematic and on the PCB at the old position, give both the old
  unique id (`modify(id, {uniqueId})`), copy pad nets by pad number, delete the old part.
- Library symbols of "the same" R / C can have pins 1 and 2 swapped or a shorter body: turn the new symbol until its
  pins sit on the old pin positions; never draw a wire between two pins of one part; compare the netlist after
  every schematic edit. EasyEDA merges collinear wires on create, so deleting "your" wire can delete the original net
  wire with it.
- Re-creating a PCB part can leave a second copy of the tracks that ended on its pads (same layer, net, end points,
  width): remove exact duplicates afterwards.
- "Supplier Part" of schematic-imported parts can read `<MPN>.1`: set `supplierId` to the distributor number on the
  schematic and PCB components before exporting the BOM.
- Changing a schematic component's rotation can reset its supplier fields: set them again afterwards.

## Tracks and vias
- Deleting a segment at a T-junction merges the two collinear neighbours into a new primitive (old ids vanish); so does
  making neighbours the same width. Wrap per-id calls in try/catch and diff the board afterwards.
- `pcb_PrimitiveVia.modify` does not update the canvas: delete + create.
- Avoid segments shorter than their width (connectivity breaks).
- A same-net via inside an SMD pad passes DRC: check vias against pads yourself.

## Placement export
`scripts/placement_from_easyeda.js` (run inside the client) writes the placement JSON for `placement_check.py`. The API
does not expose footprint body outlines, so courtyards are pads + margin: enlarge parts whose body overhangs the pads.

## Routing
- Schematic `autoLayout` / `autoRouting` and PCB `autoRouting` were unavailable offline in the tested build.
- Freerouting (DSN export / SES import) is good for one fresh full route only - it ignores copper that is already
  there. Route leftovers with a grid router on a board dump. The importer can skew pad-entry segments off 0/45/90 deg
  and duplicate vias: check both after import.

## Manufacturing exports
- `pcb_ManufactureData.getGerberFile(...)`, `getBomFile(name, 'csv')`, `getPickAndPlaceFile(name, 'csv', 'mm')` return
  File objects; BOM and CPL CSVs are UTF-16 tab-separated - convert to the assembler's columns.
- `pcb_ManufactureData.getIpcD356AFile(name)` (beta) gives the netlist for `scripts/gerber_check.py netcheck`. It fails
  unless the PCB document is open.
- `sch_ManufactureData.getNetlistFile` returns null unless a schematic tab is active.
- 3D: `get3DFile(name, 'obj', [...], 'Outfit', true)` returns a zip (OBJ + MTL) that renders headless in Blender.
- Exported drill files: plated through holes and vias are listed in a general PTH file and again in a via file.
