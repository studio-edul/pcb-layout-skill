// Build a placement_check.py input from the PCB open in EasyEDA Pro (runs inside EasyEDA).
//
// Run it through the EasyEDA API bridge (github.com/easyeda/easyeda-api-skill) or any script runner that executes
// JavaScript in the EasyEDA Pro client and returns the value of the last `return`. Save the returned text as
// placement.json. Read-only: it changes nothing on the board.
//
// What it fills in: board size and origin (board outline layer), every component with a courtyard estimated from its
// pads + COURTYARD_MM (EasyEDA does not expose the footprint body outline through the API, so tall bodies that overhang
// their pads - electrolytics, connectors, inductors - must be enlarged by hand), rotation, side and a class guessed
// from the designator. Zones, keep-outs and near/apart pairs are left empty for you to add.
// Units: EasyEDA PCB API works in mil; output is mm, y up, rotation CCW (as EasyEDA).

const COURTYARD_MM = 0.25, COURTYARD_SMALL_MM = 0.15;          // IPC-7351B level N; 0402/0603-size parts 0.15
const MM = 0.0254;
const OUTLINE_LAYER = 11;

const comps = await eda.pcb_PrimitiveComponent.getAll();
const pads = await eda.pcb_PrimitivePad.getAll();
const byComp = {};
for (const p of pads) {
  const id = p.getState_PrimitiveId();
  const owner = comps.find(c => id.startsWith(c.getState_PrimitiveId() + 'e'));   // pad ids are "<component id>e<n>"
  if (owner) (byComp[owner.getState_PrimitiveId()] ??= []).push(p);
}

const guess = (ref, area) => {
  const p = (ref.match(/^[A-Za-z]+/) || [''])[0].toUpperCase();
  if (['J', 'P', 'CN', 'USB', 'SW'].includes(p)) return 'connector';
  if (['H', 'MH', 'FID', 'TP'].includes(p)) return 'mech';
  if (p === 'U' || p === 'IC') return area > 150 ? 'module' : 'ic';
  if (['Q', 'K', 'F'].includes(p) || (p === 'L' && area > 9) || (p === 'C' && area > 25)) return 'power';
  return 'passive';
};

const parts = [];
for (const c of comps) {
  const ps = byComp[c.getState_PrimitiveId()] || [];
  if (!ps.length) continue;
  const rot = ((Math.round(c.getState_Rotation()) % 360) + 360) % 360;
  const cx = c.getState_X(), cy = c.getState_Y();
  // pad extents in the component frame (un-rotate around the component origin)
  const a = -rot * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (const p of ps) {
    const s = p.getState_Pad() || [];
    const w = (s[1] || 0) / 2, h = (s[2] ?? s[1] ?? 0) / 2;
    const pr = (p.getState_Rotation() - rot) * Math.PI / 180;
    const dx = p.getState_X() - cx, dy = p.getState_Y() - cy;
    const lx = dx * ca - dy * sa, ly = dx * sa + dy * ca;
    for (const [u, v] of [[-w, -h], [w, -h], [w, h], [-w, h]]) {
      const qx = lx + u * Math.cos(pr) - v * Math.sin(pr), qy = ly + u * Math.sin(pr) + v * Math.cos(pr);
      x0 = Math.min(x0, qx); x1 = Math.max(x1, qx); y0 = Math.min(y0, qy); y1 = Math.max(y1, qy);
    }
  }
  const margin = Math.max(x1 - x0, y1 - y0) * MM <= 1.6 ? COURTYARD_SMALL_MM : COURTYARD_MM;
  const m = margin / MM;
  x0 -= m; x1 += m; y0 -= m; y1 += m;
  const ox = (x0 + x1) / 2, oy = (y0 + y1) / 2, r = rot * Math.PI / 180;        // courtyard centre back to the board frame
  const w = (x1 - x0) * MM, h = (y1 - y0) * MM, ref = c.getState_Designator() || '?';
  const odd = rot % 90 !== 0;
  parts.push({
    ref, x: +((cx + ox * Math.cos(r) - oy * Math.sin(r)) * MM).toFixed(4), y: +((cy + ox * Math.sin(r) + oy * Math.cos(r)) * MM).toFixed(4),
    w: +w.toFixed(4), h: +h.toFixed(4), rot: odd ? 0 : rot, class: guess(ref, w * h),
    side: c.getState_Layer() === 2 ? 'bottom' : 'top', note: odd ? `rotation ${rot} deg: courtyard taken axis-aligned` : 'pads+' + margin,
    ...(odd ? { rot_actual: rot } : {}),
  });
}
const seen = {};
for (const p of parts) {                                    // empty or repeated designators get #2, #3 ...
  seen[p.ref] = (seen[p.ref] || 0) + 1;
  if (seen[p.ref] > 1) p.ref = `${p.ref}#${seen[p.ref]}`;
}

// board outline: lines, arcs and polylines on the outline layer
const pts = [];
for (const l of await eda.pcb_PrimitiveLine.getAll()) if (l.getState_Layer() === OUTLINE_LAYER)
  pts.push([l.getState_StartX(), l.getState_StartY()], [l.getState_EndX(), l.getState_EndY()]);
for (const pl of await eda.pcb_PrimitivePolyline.getAll()) if (pl.getState_Layer() === OUTLINE_LAYER) {
  const src = pl.getState_Polygon().getSource().filter(v => typeof v === 'number');
  for (let i = 0; i + 1 < src.length; i += 2) pts.push([src[i], src[i + 1]]);
}
let board;
if (pts.length) {
  const xs = pts.map(p => p[0] * MM), ys = pts.map(p => p[1] * MM);
  const X0 = Math.min(...xs), Y0 = Math.min(...ys);
  board = { w: +(Math.max(...xs) - X0).toFixed(4), h: +(Math.max(...ys) - Y0).toFixed(4), origin: [+X0.toFixed(4), +Y0.toFixed(4)], edge_clearance: 0.5, grid: 0.25 };
} else {
  board = { w: 0, h: 0, origin: [0, 0], edge_clearance: 0.5, grid: 0.25, note: 'no outline found on layer 11: fill in w, h, origin' };
}

return '{"board": ' + JSON.stringify(board) + ',\n "zones": {}, "keepouts": [],\n "parts": [\n  ' +
  parts.map(p => JSON.stringify(p)).join(',\n  ') + '],\n "near": [], "apart": []}\n';
