// 1:1 True Architectural Scale 3D Model of Moynihan Train Hall & SOM LIRR Concourse.
// Scale: 1 Three.js unit = 1 inch (exact same 1:1 scale as our 72" tables & 314" U-Haul 26' trucks).
//
// Grounded in published SOM (Skidmore, Owings & Merrill) & Schlaich Bergermann Partner specs:
//   - Main Moynihan Boarding Atrium: 200 ft × 150 ft (2,400" × 1,800" = 30,000–31,000 sq ft)
//   - Skylight Vaults: 4 double-curved catenary glass-and-steel vaults peaking at 92 ft (1,104")
//   - Historic Steel Trusses: 3 restored 1912 riveted Pratt trusses, 150 ft (1,800") span, 50 ft (600") o.c.
//   - Upper Mezzanine Balcony: +20 ft (240") perimeter balcony overlooking the hall (Metropolitan Lounge)
//   - Track 5–16 Boarding Portals: glass-balustrade escalator islands + LED gate totems on concourse floor
//   - East LIRR 33rd St Concourse: widened to 57 ft (684") × 18 ft (216") ceiling with luminous LED coffers

import * as THREE from "three";

/**
 * 1:1 Architectural Zone Placements (`1 unit = 1 inch`).
 * Notice `floorY`: Stop 5 (Members Lounge) sits at `floorY = 240` (+20 ft) right on the
 * South Mezzanine Balcony overlooking the 92-ft skylit Train Hall, just like the real
 * Amtrak Metropolitan Lounge in Moynihan Train Hall!
 */
export const VENUE_ZONE_LAYOUT = {
  penn_merch_kiosk: {
    // 36 ft × 26 ft open welcome pavilion inside West Entrance near 9th Ave / 31st St
    cx: -860,
    cz: -520,
    floorY: 0,
    rotY: -Math.PI / 2,
    vDims: [312, 432, 168],
    doorSpan: 340,
    floorColor: 0x2d2926,
    rugColor: 0x3730a3,
    accentHex: "#f97316",
    signTitle: "STOP 1 · WEST ENTRANCE CHECK-IN & SWAG",
    dockPath: [[-1360, -140], [-980, -140], [-860, -364]],
  },
  penn_cafe: {
    // 64 ft × 40 ft Food Hall & Espresso Bay along North 33rd St Colonnade (Moynihan Food Hall)
    cx: -180,
    cz: -1140,
    floorY: 0,
    rotY: -Math.PI / 2,
    vDims: [480, 768, 216],
    doorSpan: 560,
    floorColor: 0x332920,
    rugColor: 0x7c2d12,
    accentHex: "#eab308",
    signTitle: "STOP 2 · MOYNIHAN FOOD HALL & ESPRESSO BAR",
    dockPath: [[-1360, -60], [-360, -60], [-180, -900]],
  },
  penn_bookshop: {
    // 55 ft × 36 ft retail bay opening onto the 57-ft-wide SOM LIRR 33rd St Concourse (East Wing)
    cx: 1720,
    cz: -558,
    floorY: 0,
    rotY: -Math.PI / 2,
    vDims: [432, 660, 204],
    doorSpan: 480,
    floorColor: 0x1f2e2b,
    rugColor: 0x1e3a3a,
    accentHex: "#10b981",
    signTitle: "STOP 3 · LIRR CONCOURSE LIBRARY & FOCUS BAR",
    dockPath: [[-1360, -15], [1460, -15], [1720, -342]],
  },
  penn_tech_hub: {
    // 68 ft × 42 ft ground-level Deep-Work Studio along South 31st St Arcade beneath Mezzanine
    cx: -320,
    cz: 1152,
    floorY: 0,
    rotY: Math.PI / 2,
    vDims: [504, 816, 216],
    doorSpan: 600,
    floorColor: 0x1f2937,
    rugColor: 0x1e3a5f,
    accentHex: "#3b82f6",
    signTitle: "STOP 4 · 31st ST ARCADE DEEP-WORK STUDIO",
    dockPath: [[-1360, 55], [-520, 55], [-320, 900]],
  },
  penn_lounge: {
    // 72 ft × 42 ft Upper Mezzanine Balcony Suite (+20 ft = 240" elevation!) overlooking the Main Atrium
    cx: 460,
    cz: 1110,
    floorY: 240,
    rotY: Math.PI / 2,
    vDims: [420, 864, 180],
    doorSpan: 760,
    isMezzanine: true,
    floorColor: 0x2b2333,
    rugColor: 0x4c3549,
    accentHex: "#8b5cf6",
    signTitle: "STOP 5 · MEZZANINE METROPOLITAN / MALIN LOUNGE (+20 FT)",
    dockPath: [[-1360, 120], [150, 120], [150, 860]],
  },
  penn_concourse: {
    // Central Hackathon & Coworking Village centered inside the 200×150 ft (2,400×1,800") Skylit Atrium
    cx: 0,
    cz: 0,
    floorY: 0,
    rotY: 0,
    vDims: [1160, 760, 1104],
    doorSpan: 760,
    floorColor: 0x2b323e,
    rugColor: 0x1e293b,
    accentHex: "#06b6d4",
    signTitle: "STOP 6 · MAIN ATRIUM HACKATHON VILLAGE (200×150 FT HALL)",
    dockPath: [[-1360, 0], [-580, 0]],
  },
};

function classifyItem(it) {
  const k = `${it.catalog_id || ""} ${it.label || ""}`.toLowerCase();
  if (it.is_box) return "box";
  if (k.includes("round") && k.includes("table")) return "round_table";
  if (k.includes("coffee") && k.includes("table")) return "coffee_table";
  if (k.includes("table") || k.includes("desk")) return "desk_table";
  if ((it.stack_count && it.stack_count > 1) || k.includes("chair_stack") || k.includes("stack of")) return "chair_stack";
  if (k.includes("bar_stool") || k.includes("stool")) return "stool";
  if (k.includes("office_chair") || k.includes("chair")) return "chair";
  if (k.includes("sofa") || k.includes("loveseat") || k.includes("sectional")) return "sofa";
  if (k.includes("armchair") || k.includes("recliner") || k.includes("single seat")) return "armchair";
  if (k.includes("ottoman") || k.includes("pouf")) return "ottoman";
  if (k.includes("rug")) return "rug";
  if (k.includes("monitor") || k.includes("tv")) return "monitor";
  if (k.includes("whiteboard")) return "whiteboard";
  if (k.includes("projector_screen") || (k.includes("screen") && !k.includes("pos"))) return "screen";
  if (k.includes("projector")) return "projector";
  if (k.includes("podium") || k.includes("lectern")) return "podium";
  if (k.includes("piano")) return "piano";
  if (k.includes("espresso") || k.includes("pastry") || k.includes("microwave")) return "counter_appliance";
  if (k.includes("framed_art") || k.includes("mirror") || k.includes("art")) return "wall_art";
  if (k.includes("shelf") || k.includes("shelving") || k.includes("bookcase")) return "bookshelf";
  if (k.includes("merch_rack") || k.includes("rack")) return "merch_rack";
  if (k.includes("pos_kiosk") || k.includes("kiosk")) return "pos_kiosk";
  if (k.includes("sideboard") || k.includes("credenza") || k.includes("filing") || k.includes("cabinet") || k.includes("dresser")) return "credenza";
  if (k.includes("power_strip")) return "power_strip";
  return "generic";
}

function makeSignTexture(title, subtitle, accentHex = "#3b82f6", darkBg = "#0f172a") {
  const c = document.createElement("canvas");
  c.width = 640;
  c.height = 120;
  const ctx = c.getContext("2d");

  ctx.fillStyle = darkBg;
  ctx.fillRect(0, 0, 640, 120);
  ctx.fillStyle = accentHex;
  ctx.fillRect(0, 0, 18, 120);
  ctx.fillRect(0, 112, 640, 8);

  ctx.fillStyle = "#f8fafc";
  ctx.font = "bold 28px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(title, 34, 54);

  ctx.fillStyle = "#94a3b8";
  ctx.font = "600 21px system-ui, -apple-system, sans-serif";
  ctx.fillText(subtitle, 34, 90);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeDepartureBoardTexture() {
  const c = document.createElement("canvas");
  c.width = 896;
  c.height = 256;
  const ctx = c.getContext("2d");

  ctx.fillStyle = "#090d16";
  ctx.fillRect(0, 0, 896, 256);
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 6;
  ctx.strokeRect(3, 3, 890, 250);

  ctx.fillStyle = "#1d4ed8";
  ctx.fillRect(6, 6, 884, 52);
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 26px system-ui, -apple-system, sans-serif";
  ctx.fillText("NY PENN & MOYNIHAN TRAIN HALL · DEPARTURES & HACKATHON", 24, 41);

  const rows = [
    ["ATRIUM", "MAIN CONCOURSE · GEMINI 4 HACKATHON ARENA", "STOP 6", "LIVE NOW", "#4ade80"],
    ["MEZZ", "METROPOLITAN × MALIN LOUNGE (+20 FT BALCONY)", "STOP 5", "OPEN", "#c084fc"],
    ["14:08", "AMTRAK ACELA 2155 · WASHINGTON DC", "TRK 11", "BOARDING", "#4ade80"],
    ["14:15", "LIRR · PORT WASHINGTON / RONKONKOMA", "TRK 18", "ON TIME", "#fbbf24"],
  ];
  ctx.font = "bold 21px ui-monospace, SFMono-Regular, Menlo, monospace";
  rows.forEach(([col1, dest, trk, status, col], i) => {
    const y = 96 + i * 42;
    ctx.fillStyle = i % 2 === 0 ? "rgba(255,255,255,0.035)" : "transparent";
    ctx.fillRect(10, y - 28, 876, 36);
    ctx.fillStyle = "#93c5fd";
    ctx.fillText(col1, 22, y);
    ctx.fillStyle = "#f8fafc";
    ctx.fillText(dest, 132, y);
    ctx.fillStyle = "#cbd5e1";
    ctx.fillText(trk, 648, y);
    ctx.fillStyle = col;
    ctx.fillText(status, 756, y);
  });

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeClockTexture() {
  const c = document.createElement("canvas");
  c.width = 160;
  c.height = 160;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#0f172a";
  ctx.beginPath(); ctx.arc(80, 80, 74, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "#eab308"; ctx.lineWidth = 9; ctx.stroke();
  ctx.strokeStyle = "#f8fafc"; ctx.lineWidth = 4;
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(80 + Math.cos(a) * 54, 80 + Math.sin(a) * 54);
    ctx.lineTo(80 + Math.cos(a) * 65, 80 + Math.sin(a) * 65);
    ctx.stroke();
  }
  ctx.lineWidth = 6;
  ctx.beginPath(); ctx.moveTo(80, 80); ctx.lineTo(104, 52); ctx.stroke();
  ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo(80, 80); ctx.lineTo(80, 24); ctx.stroke();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * Minimalist SOM-style 1:1 human scale figure (`68"` = 5 ft 8 in tall) so the viewer's eye
 * immediately reads the 92-foot skylight, 20-foot mezzanine, and 6-foot coworking tables!
 */
function buildHumanScaleFigure(x, y, z, colorHex = 0xcbd5e1) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  const mat = new THREE.MeshStandardMaterial({
    color: colorHex,
    roughness: 0.65,
    transparent: true,
    opacity: 0.82,
  });
  // Legs + Torso (`0..57"`)
  const body = new THREE.Mesh(new THREE.CylinderGeometry(4.8, 3.4, 56, 12), mat);
  body.position.y = 28;
  g.add(body);
  // Shoulders
  const shoulders = new THREE.Mesh(new THREE.SphereGeometry(5.6, 12, 10), mat);
  shoulders.scale.set(1.2, 0.7, 0.75);
  shoulders.position.y = 53;
  g.add(shoulders);
  // Head (`58..68"` = 5'8" total height)
  const head = new THREE.Mesh(new THREE.SphereGeometry(4.4, 12, 12), mat);
  head.position.y = 63.5;
  g.add(head);
  return g;
}

/**
 * Coworking Interior Designer at 1:1 Human Scale (`1 unit = 1 inch`)!
 * Furniture keeps its true 1:1 physical dimensions (`72×30"` banquet tables, `84×36"` sofas,
 * `60"` round tables, `30"` desk height), arranged with realistic generous architectural spacing!
 */
function designCoworkingZone(zone, spec) {
  const [L, W] = spec.vDims;
  const items = (zone.items || []).slice();
  const placements = [];
  const fixtures = [];

  const byKind = {};
  items.forEach((it) => {
    const k = classifyItem(it);
    (byKind[k] = byKind[k] || []).push(it);
  });
  const take = (k) => byKind[k] || [];

  const place = (it, lx, localFloorY, lz, gx, gy, gz, rotY = 0, cornerOverride = null, extra = {}) => {
    const cxNorm = (lx + L / 2) / L;
    const czNorm = (lz + W / 2) / W;
    let corner = cornerOverride;
    if (!corner) {
      const d = cxNorm < 0.34 ? "Back" : cxNorm > 0.68 ? "Concourse Front" : "Center";
      const s = czNorm < 0.34 ? "Left" : czNorm > 0.66 ? "Right" : "Mid";
      if (d === "Center" && s === "Mid") corner = "Center Coworking Floor";
      else if (d === "Center") corner = `${s} Collaboration Wing`;
      else if (s === "Mid") corner = d === "Back" ? "Back Feature Wall" : "Front Promenade";
      else corner = `${d}-${s} Nook`;
    }
    placements.push({
      item: it,
      localPos: [lx, localFloorY + gy / 2, lz],
      dims: [gx, gy, gz],
      rotY,
      kind: classifyItem(it),
      cornerLabel: corner,
      ...extra,
    });
  };

  // 1. Moving boxes tucked into a Back-of-House Supply Room / Alcove along `-L/2 + 16`
  const boxes = take("box");
  if (boxes.length) {
    const zStart = -W * 0.38;
    let bz = zStart;
    let tier = 0;
    boxes.forEach((b) => {
      const [dx, dy, dz] = b.size_in;
      const yFloor = tier * (dz + 1.0);
      place(b, -L / 2 + dx / 2 + 10, yFloor, bz, dx, dz, dy, 0, "Backstage Supply Alcove", { isTuckedBox: true });
      tier++;
      if (tier >= 3) {
        tier = 0;
        bz += dy + 6;
        if (bz > W * 0.38) bz = zStart;
      }
    });
  }

  /* ==================== 1:1 ZONE COWORKING LAYOUTS ==================== */

  if (zone.zone_id === "penn_concourse") {
    // --- MAIN ATRIUM HACKATHON VILLAGE (`1,160" × 760"` event carpet centered inside the `2,400" × 1,800"` Train Hall!) ---
    // Event village carpet pad + brass stanchion perimeter
    fixtures.push({ type: "area_rug", lx: -10, lz: 0, w: 1120, d: 700, color: 0x1e2636 });
    fixtures.push({ type: "stage_deck", lx: 430, lz: 0, w: 168, d: 380, h: 16 });
    fixtures.push({ type: "human", lx: 385, ly: 16, lz: -42 }); // Speaker at podium!
    fixtures.push({ type: "human", lx: -180, ly: 0, lz: -110 });
    fixtures.push({ type: "human", lx: -40, ly: 0, lz: 115 });
    fixtures.push({ type: "human", lx: 165, ly: 0, lz: -25 });

    const screens = take("screen");
    screens.forEach((sc, i) => {
      const sz = screens.length === 1 ? 0 : (i === 0 ? -105 : 105);
      place(sc, 492, 16, sz, 12, 96, 128, 0, "East Keynote Stage");
    });

    const podiums = take("podium");
    podiums.forEach((pd, i) => {
      const pz = podiums.length === 1 ? 0 : (i === 0 ? -48 : 48);
      place(pd, 376, 16, pz, 26, 47, 26, Math.PI, "East Keynote Stage");
    });

    const projectors = take("projector");
    projectors.forEach((pr, i) => {
      const pz = projectors.length === 1 ? 0 : (i === 0 ? -105 : 105);
      fixtures.push({ type: "pedestal", lx: 318, lz: pz, h: 38 });
      place(pr, 318, 38, pz, 18, 8, 18, 0, "Stage AV Pedestal");
    });

    take("piano").forEach((pi, i) => {
      place(pi, 435, 16, -152 + i * 64, 25, 48, 58, -0.35, "East Keynote Stage");
    });

    // 7 Double-Wide 6-ft Hacker Coworking Islands (`144" = 12 ft` on center — true spacious hackathon aisles!)
    const tables = take("desk_table");
    const deskSpots = [];
    const pairs = [];
    for (let i = 0; i < tables.length; i += 2) pairs.push(tables.slice(i, i + 2));

    pairs.forEach((pair, pIdx) => {
      const col = Math.floor(pIdx / 2);
      const row = pIdx % 2;
      const podX = -410 + col * 168; // 14-foot spacing between island centers!
      const podZ = row === 0 ? -175 : 175;
      pair.forEach((tb, sideIdx) => {
        const tz = pair.length === 2 ? podZ + (sideIdx === 0 ? -15.5 : 15.5) : podZ;
        place(tb, podX, 0.8, tz, 72, 30, 30, 0, row === 0 ? "North Hacker Pods" : "South Hacker Pods", {
          hasLaptops: true,
        });
      });
      deskSpots.push({ x: podX, z: podZ });
    });

    // 60-inch Round Collaboration Tables down the spacious Center Promenade (`lz = -58 / +58`)
    const rounds = take("round_table");
    const roundSpots = [];
    rounds.forEach((rt, rIdx) => {
      const col = Math.floor(rIdx / 2);
      const row = rIdx % 2;
      const rx = -110 + col * 168;
      const rz = row === 0 ? -56 : 56;
      place(rt, rx, 0.8, rz, 60, 30, 60, 0, "Center Collaboration Lounge", { hasCenterpiece: true });
      roundSpots.push({ x: rx, z: rz });
    });

    // Unstack `stacking_chair_stack` into 6-chair seated rings around each pod & round table!
    take("chair_stack").forEach((st, sIdx) => {
      if (sIdx < deskSpots.length) {
        const pod = deskSpots[sIdx];
        place(st, pod.x, 0.8, pod.z, 70, 33, 86, 0, "Hacker Island Seating", { chairLayout: "island_6" });
      } else if (roundSpots.length) {
        const rt = roundSpots[(sIdx - deskSpots.length) % roundSpots.length];
        place(st, rt.x, 0.8, rt.z, 82, 33, 82, 0, "Round Table Seating", { chairLayout: "round_6" });
      }
    });

    [[-520, -310], [0, -310], [500, -310], [-520, 310], [0, 310], [500, 310]].forEach(([px, pz]) => {
      fixtures.push({ type: "planter_tree", lx: px, lz: pz });
    });
  } else if (zone.zone_id === "penn_lounge") {
    // --- STOP 5: MEZZANINE METROPOLITAN × MALIN LOUNGE (`420" × 864"` at +20 ft elevation overlooking Atrium!) ---
    fixtures.push({ type: "area_rug", lx: 25, lz: -210, w: 260, d: 310, color: spec.rugColor });
    fixtures.push({ type: "area_rug", lx: 25, lz: 210, w: 260, d: 310, color: 0x3b2d4a });
    fixtures.push({ type: "lounge_table", lx: 25, lz: -210, r: 28 });
    fixtures.push({ type: "lounge_table", lx: 25, lz: 210, r: 28 });
    fixtures.push({ type: "pendant_cluster", lx: 25, lz: -210, h: 124 });
    fixtures.push({ type: "pendant_cluster", lx: 25, lz: 210, h: 124 });
    fixtures.push({ type: "planter_tree", lx: 145, lz: -370 });
    fixtures.push({ type: "planter_tree", lx: 145, lz: 0 });
    fixtures.push({ type: "planter_tree", lx: 145, lz: 370 });
    fixtures.push({ type: "human", lx: 155, ly: 0, lz: -60 }); // Overlooking the balcony glass!

    take("rug").forEach((rg, idx) => {
      place(rg, 25, 0.4, idx === 0 ? -210 : 210, 140, 0.9, 180, 0, "Mezzanine Lounge Rug");
    });

    take("credenza").forEach((cr, idx) => {
      const cz = -160 + idx * 320;
      place(cr, -L / 2 + 26, 0, cz, 20, 33, 84, Math.PI / 2, "Mezzanine Credenza Wall");
    });

    const sofaSlots = [
      { lx: -55, lz: -210, rot: Math.PI / 2, c: "West Mezzanine Salon" },
      { lx: -55, lz: 210, rot: Math.PI / 2, c: "East Mezzanine Salon" },
      { lx: 25, lz: -315, rot: 0, c: "West Mezzanine Salon" },
      { lx: 25, lz: 315, rot: Math.PI, c: "East Mezzanine Salon" },
      { lx: 105, lz: 0, rot: Math.PI / 2, c: "Atrium Overlook Divan" },
    ];
    take("sofa").forEach((sf, idx) => {
      const sl = sofaSlots[idx % sofaSlots.length];
      const [l, w, h] = sf.orig_dims_in || sf.size_in;
      place(sf, sl.lx, 0.9, sl.lz, l, Math.max(33, h), w, sl.rot, sl.c);
    });

    const armSlots = [
      { lx: 95, lz: -265, rot: -Math.PI * 0.75, c: "West Mezzanine Salon" },
      { lx: 95, lz: -155, rot: -Math.PI * 0.25, c: "West Mezzanine Salon" },
      { lx: 25, lz: -105, rot: Math.PI, c: "Center Mezzanine Overlook" },
      { lx: 95, lz: 155, rot: -Math.PI * 0.75, c: "East Mezzanine Salon" },
      { lx: 95, lz: 265, rot: -Math.PI * 0.25, c: "East Mezzanine Salon" },
      { lx: 25, lz: 105, rot: 0, c: "Center Mezzanine Overlook" },
    ];
    take("armchair").forEach((ac, idx) => {
      const sl = armSlots[idx % armSlots.length];
      place(ac, sl.lx, 0.9, sl.lz, 36, 32, 36, sl.rot, sl.c);
    });
  } else if (zone.zone_id === "penn_cafe") {
    // --- STOP 2: MOYNIHAN FOOD HALL & ESPRESSO BAR (`480" × 768"` = 40 ft × 64 ft!) ---
    const barX = -85;
    fixtures.push({ type: "espresso_bar", lx: barX, lz: 0, w: 36, d: 340, h: 40 });
    fixtures.push({ type: "pendant_cluster", lx: barX, lz: -90, h: 120 });
    fixtures.push({ type: "pendant_cluster", lx: barX, lz: 90, h: 120 });
    fixtures.push({ type: "human", lx: barX - 24, ly: 0, lz: -20 }); // Barista behind counter!
    fixtures.push({ type: "human", lx: barX + 42, ly: 0, lz: 35 });

    take("counter_appliance").forEach((ap, idx) => {
      const az = -96 + idx * 96;
      const [dx, dy, dz] = ap.size_in;
      place(ap, barX, 40, az, Math.min(28, dy), Math.max(18, dz), Math.min(32, dx), 0, "Marble Espresso Bar");
    });

    take("stool").forEach((st, idx) => {
      const sz = -125 + idx * 50;
      place(st, barX + 34, 0, sz, 17, 30, 17, -Math.PI / 2, "Espresso Bar Stools");
    });

    take("rug").forEach((rg, idx) => {
      const rz = idx === 0 ? -150 : 150;
      place(rg, 95, 0, rz, 130, 0.8, 170, 0, idx === 0 ? "West Bistro Patio" : "East Bistro Patio");
    });

    take("coffee_table").forEach((ct, idx) => {
      const cz = idx === 0 ? -150 : 150;
      place(ct, 95, 0.8, cz, 28, 18, 48, 0, idx === 0 ? "West Bistro Table" : "East Bistro Table", { hasCenterpiece: true });
    });

    const ottoSlots = [
      { lx: 56, lz: -150, c: "West Bistro Table" },
      { lx: 134, lz: -150, c: "West Bistro Table" },
      { lx: 56, lz: 150, c: "East Bistro Table" },
      { lx: 134, lz: 150, c: "East Bistro Table" },
    ];
    take("ottoman").forEach((ot, idx) => {
      const sl = ottoSlots[idx % ottoSlots.length];
      place(ot, sl.lx, 0.8, sl.lz, 22, 18, 22, 0, sl.c);
    });
  } else if (zone.zone_id === "penn_bookshop") {
    // --- STOP 3: LIRR CONCOURSE LIBRARY & DEVELOPER FOCUS BAR (`432" × 660"` = 36 ft × 55 ft!) ---
    fixtures.push({ type: "area_rug", lx: 20, lz: 0, w: 240, d: 380, color: spec.rugColor });
    const focusZ = W / 2 - 32;
    fixtures.push({ type: "focus_bar", lx: 10, lz: focusZ, w: 290, d: 30, h: 30 });
    fixtures.push({ type: "human", lx: -20, ly: 0, lz: focusZ - 28 });

    take("bookshelf").forEach((sh, idx) => {
      const sx = -100 + idx * 100;
      place(sh, sx, 0, -W / 2 + 14, 48, 78, 15, 0, "West Oak Library Wall", { withBooks: true });
    });

    const desks = take("desk_table");
    desks.forEach((dk, idx) => {
      place(dk, 20 + idx * 80, 0.8, -20, 32, 30, 64, 0, "Center Reading Table", { hasLaptops: true });
    });

    take("monitor").forEach((mn, idx) => {
      if (idx === 0 && desks.length) {
        place(mn, 20, 30.8, -20, 8, 18, 26, Math.PI / 2, "Center Reading Table");
      } else {
        const barIdx = desks.length ? idx - 1 : idx;
        const mx = -105 + barIdx * 44;
        place(mn, mx, 30, focusZ - 2, 26, 18, 7, Math.PI, "Developer 4K Focus Bar");
      }
    });

    take("wall_art").forEach((ar, idx) => {
      if (idx < 2) {
        place(ar, -55 + idx * 120, 66, W / 2 - 5, 38, 28, 3, Math.PI, "East Gallery Wall");
      } else {
        place(ar, -L / 2 + 6, 66, -95 + (idx - 2) * 190, 3, 28, 38, 0, "Back Gallery Wall");
      }
    });

    take("power_strip").forEach((ps, idx) => {
      place(ps, -80 + idx * 54, 0, focusZ + 2, 16, 10, 14, 0, "Under-Bar Power Channel");
    });
  } else if (zone.zone_id === "penn_tech_hub") {
    // --- STOP 4: 31st ST ARCADE DEEP-WORK STUDIO (`504" × 816"` = 42 ft × 68 ft!) ---
    fixtures.push({ type: "area_rug", lx: 15, lz: -145, w: 260, d: 240, color: spec.rugColor });
    fixtures.push({ type: "area_rug", lx: 15, lz: 145, w: 260, d: 240, color: spec.rugColor });
    fixtures.push({ type: "planter_tree", lx: 175, lz: -320 });
    fixtures.push({ type: "planter_tree", lx: 175, lz: 320 });
    fixtures.push({ type: "human", lx: -35, ly: 0, lz: -145 });

    const desks = take("desk_table");
    const deskCoords = [];
    desks.forEach((dk, idx) => {
      const pod = Math.floor(idx / 2);
      const side = idx % 2;
      const dx = 15 + (side === 0 ? -17 : 17);
      const dz = pod === 0 ? -145 : 145;
      place(dk, dx, 0.8, dz, 32, 30, 64, 0, pod === 0 ? "West Deep-Work Pod" : "East Deep-Work Pod", { hasLaptops: true });
      deskCoords.push({ x: dx, z: dz, side });
    });

    const chairs = take("chair");
    chairs.forEach((ch, idx) => {
      if (deskCoords.length) {
        const dc = deskCoords[idx % deskCoords.length];
        const zShift = idx >= deskCoords.length ? 16 : -16;
        const chairX = dc.x + (dc.side === 0 ? -28 : 28);
        const rot = dc.side === 0 ? Math.PI / 2 : -Math.PI / 2;
        place(ch, chairX, 0.8, dc.z + zShift, 25, 39, 25, rot, dc.z < 0 ? "West Deep-Work Pod" : "East Deep-Work Pod");
      }
    });

    take("monitor").forEach((mn, idx) => {
      const dc = deskCoords[idx % Math.max(1, deskCoords.length)] || { x: 15, z: 0, side: 0 };
      place(mn, dc.x, 30.8, dc.z, 7, 18, 26, dc.side === 0 ? -Math.PI / 2 : Math.PI / 2, "Standing Desk Monitor");
    });

    take("whiteboard").forEach((wb, idx) => {
      const wz = idx % 2 === 0 ? -W / 2 + 34 : W / 2 - 34;
      const wx = -60 + Math.floor(idx / 2) * 140;
      place(wb, wx, 0, wz, 72, 75, 22, idx % 2 === 0 ? 0.12 : -0.12, "Glass Whiteboard Wall");
    });

    take("credenza").forEach((fc, idx) => {
      place(fc, -L / 2 + 44, 0, -120 + idx * 240, 25, 29, 16, Math.PI / 2, "Back Studio Cabinets");
    });
    take("power_strip").forEach((ps, idx) => {
      place(ps, 15, 0.8, idx === 0 ? -145 : 145, 16, 10, 14, 0, "Under-Desk Power Channel");
    });
  } else if (zone.zone_id === "penn_merch_kiosk") {
    // --- STOP 1: WEST ENTRANCE WELCOME & SWAG PAVILION (`312" × 432"` = 26 ft × 36 ft!) ---
    fixtures.push({ type: "area_rug", lx: 15, lz: 0, w: 220, d: 310, color: spec.rugColor });
    fixtures.push({ type: "human", lx: 28, ly: 0, lz: 0 }); // Welcome host behind check-in desk!

    take("desk_table").forEach((dk, idx) => {
      place(dk, 58 - idx * 54, 0.8, 0, 32, 30, 68, Math.PI / 2, "Welcome Check-In Desk", { hasLaptops: true });
    });

    take("pos_kiosk").forEach((pk, idx) => {
      const pz = idx === 0 ? -96 : 96;
      place(pk, 72, 0.8, pz, 20, 56, 20, Math.PI / 2, "Badge Check-In Kiosks");
    });

    take("merch_rack").forEach((mr, idx) => {
      const mz = -110 + idx * 110;
      place(mr, -52, 0.8, mz, 24, 66, 52, Math.PI / 2, "Swag & Hoodie Boutique");
    });
  }

  const placedIds = new Set(placements.map((p) => p.item.id));
  items.filter((it) => !placedIds.has(it.id)).forEach((it, rIdx) => {
    const [dx, dy, dz] = it.size_in;
    const col = rIdx % 4;
    const row = Math.floor(rIdx / 4);
    place(it, -60 + row * 72, 0, -W * 0.25 + col * (W * 0.17), dx, dz, dy, 0, "Coworking Floor");
  });

  return { placements, fixtures };
}

function buildCoworkingPieceMesh(p, baseHex, makeBoxFaceTexture) {
  const { item: it, dims: [gx, gy, gz], kind, hasLaptops, hasCenterpiece, withBooks, chairLayout } = p;
  const root = new THREE.Group();

  const mainMat = new THREE.MeshStandardMaterial({ color: baseHex, roughness: 0.48, metalness: 0.08 });
  const warmOak = new THREE.MeshStandardMaterial({ color: 0xb88655, roughness: 0.58, metalness: 0.05 });
  const walnutMat = new THREE.MeshStandardMaterial({ color: 0x5c3d28, roughness: 0.55, metalness: 0.06 });
  const darkMetal = new THREE.MeshStandardMaterial({ color: 0x27303f, roughness: 0.42, metalness: 0.6 });
  const chromeMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.28, metalness: 0.78 });
  const screenGlow = new THREE.MeshStandardMaterial({ color: 0xe0f2fe, emissive: 0x1d4ed8, emissiveIntensity: 0.35, roughness: 0.2 });

  const addLaptop = (lx, ly, lz, rot = 0) => {
    const g = new THREE.Group();
    g.position.set(lx, ly, lz);
    g.rotation.y = rot;
    g.add(new THREE.Mesh(new THREE.BoxGeometry(9.5, 0.5, 13.5), chromeMat));
    const lid = new THREE.Mesh(new THREE.BoxGeometry(0.5, 9, 13.5), screenGlow);
    lid.position.set(-4.4, 4.3, 0);
    lid.rotation.z = 0.22;
    g.add(lid);
    root.add(g);
  };

  const buildSingleChair = (cx, cz, rotY, seatW = 18, seatH = 18, totalH = 33) => {
    const cg = new THREE.Group();
    cg.position.set(cx, 0, cz);
    cg.rotation.y = rotY;
    const sY = -totalH / 2 + seatH;
    const seat = new THREE.Mesh(new THREE.BoxGeometry(seatW, 2.0, seatW), mainMat);
    seat.position.set(0, sY, 0);
    cg.add(seat);
    const back = new THREE.Mesh(new THREE.BoxGeometry(seatW * 0.92, totalH - seatH, 1.8), mainMat);
    back.position.set(0, sY + (totalH - seatH) / 2, -seatW * 0.44);
    cg.add(back);
    const legGeo = new THREE.BoxGeometry(1.3, seatH, 1.3);
    const o = seatW * 0.4;
    [[-o, -o], [o, -o], [-o, o], [o, o]].forEach(([lx, lz]) => {
      const leg = new THREE.Mesh(legGeo, darkMetal);
      leg.position.set(lx, -totalH / 2 + seatH / 2, lz);
      cg.add(leg);
    });
    return cg;
  };

  if (kind === "box") {
    const geo = new THREE.BoxGeometry(gx, gy, gz);
    const qrTex = makeBoxFaceTexture(it, baseHex);
    const sideMat = new THREE.MeshStandardMaterial({ color: 0xc29b6c, roughness: 0.75, metalness: 0.02 });
    const qrMat = new THREE.MeshStandardMaterial({ map: qrTex, roughness: 0.6, metalness: 0.04 });
    // BoxGeometry faces: 0:+X, 1:-X, 2:+Y (TOP flaps), 3:-Y, 4:+Z, 5:-Z
    root.add(new THREE.Mesh(geo, [sideMat, sideMat, qrMat, sideMat, sideMat, sideMat]));
    return root;
  }

  if (kind === "chair_stack" && chairLayout) {
    if (chairLayout === "island_6") {
      [-22, 0, 22].forEach((cx) => {
        root.add(buildSingleChair(cx, -39, 0));
        root.add(buildSingleChair(cx, 39, Math.PI));
      });
      return root;
    }
    if (chairLayout === "round_6") {
      for (let k = 0; k < 6; k++) {
        const ang = (k / 6) * Math.PI * 2;
        const r = 39;
        root.add(buildSingleChair(Math.cos(ang) * r, Math.sin(ang) * r, -ang - Math.PI / 2));
      }
      return root;
    }
  }

  if (kind === "rug") {
    root.add(new THREE.Mesh(new THREE.BoxGeometry(gx, Math.max(0.8, gy), gz), new THREE.MeshStandardMaterial({ color: 0x6d4c41, roughness: 0.92 })));
    root.add(new THREE.Mesh(new THREE.BoxGeometry(gx * 0.88, Math.max(0.95, gy + 0.15), gz * 0.88), new THREE.MeshStandardMaterial({ color: baseHex, roughness: 0.9 })));
    return root;
  }

  if (kind === "desk_table" || kind === "round_table" || kind === "coffee_table") {
    const topThick = 2.0;
    const topMat = kind === "coffee_table" ? walnutMat : warmOak;
    if (kind === "round_table") {
      const r = Math.min(gx, gz) * 0.49;
      const top = new THREE.Mesh(new THREE.CylinderGeometry(r, r, topThick, 28), topMat);
      top.position.y = gy / 2 - topThick / 2;
      root.add(top);
      const ped = new THREE.Mesh(new THREE.CylinderGeometry(2.6, 3.4, gy - topThick, 12), darkMetal);
      ped.position.y = -topThick / 2;
      root.add(ped);
      const baseDisc = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.42, r * 0.45, 1.5, 20), darkMetal);
      baseDisc.position.y = -gy / 2 + 0.8;
      root.add(baseDisc);
    } else {
      const top = new THREE.Mesh(new THREE.BoxGeometry(gx, topThick, gz), topMat);
      top.position.y = gy / 2 - topThick / 2;
      root.add(top);
      const trim = new THREE.Mesh(new THREE.BoxGeometry(gx + 0.4, 0.9, gz + 0.4), mainMat);
      trim.position.y = gy / 2 - topThick + 0.3;
      root.add(trim);
      const legH = gy - topThick;
      const legGeo = new THREE.BoxGeometry(1.9, legH, 1.9);
      const ox = gx * 0.44, oz = gz * 0.42;
      [[-ox, -oz], [ox, -oz], [-ox, oz], [ox, oz]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(legGeo, darkMetal);
        leg.position.set(lx, -topThick / 2, lz);
        root.add(leg);
      });
    }
    if (hasLaptops) {
      if (gx >= 55) {
        addLaptop(-18, gy / 2 + 0.3, 0, Math.PI / 2);
        addLaptop(18, gy / 2 + 0.3, 0, -Math.PI / 2);
      } else {
        addLaptop(0, gy / 2 + 0.3, -12, 0);
        addLaptop(0, gy / 2 + 0.3, 12, Math.PI);
      }
    }
    if (hasCenterpiece) {
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 2.6, 4.8, 12), walnutMat);
      pot.position.y = gy / 2 + 2.4;
      root.add(pot);
      const foliage = new THREE.Mesh(new THREE.SphereGeometry(5.5, 12, 10), new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.8 }));
      foliage.position.y = gy / 2 + 6.8;
      root.add(foliage);
    }
    return root;
  }

  if (kind === "chair") {
    root.add(buildSingleChair(0, 0, 0, gx * 0.85, gy * 0.46, gy));
    return root;
  }

  if (kind === "stool") {
    const r = Math.min(gx, gz) * 0.44;
    const cushion = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 3.2, 18), mainMat);
    cushion.position.y = gy / 2 - 1.6;
    root.add(cushion);
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(1.4, 1.8, gy - 3.2, 12), darkMetal);
    stem.position.y = -1.6;
    root.add(stem);
    return root;
  }

  if (kind === "sofa" || kind === "armchair") {
    const seatH = gy * 0.42;
    const seat = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.92, seatH, gz * 0.86), mainMat);
    seat.position.set(0, -gy / 2 + seatH / 2 + 2, gz * 0.05);
    root.add(seat);
    const backThick = Math.max(5, gz * 0.24);
    const back = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.96, gy * 0.88, backThick), mainMat);
    back.position.set(0, 0, -gz / 2 + backThick / 2);
    root.add(back);
    const armW = Math.max(4.5, gx * 0.12);
    const armH = gy * 0.66;
    const armGeo = new THREE.BoxGeometry(armW, armH, gz * 0.9);
    [-gx / 2 + armW / 2, gx / 2 - armW / 2].forEach((ax) => {
      const arm = new THREE.Mesh(armGeo, mainMat);
      arm.position.set(ax, -gy / 2 + armH / 2 + 2, 0);
      root.add(arm);
    });
    return root;
  }

  if (kind === "ottoman") {
    const r = Math.min(gx, gz) * 0.48;
    root.add(new THREE.Mesh(new THREE.CylinderGeometry(r * 0.92, r, gy, 20), mainMat));
    return root;
  }

  if (kind === "monitor") {
    const bezelW = Math.max(gx, gz);
    const bezelD = Math.min(gx, gz);
    const panelH = gy * 0.74;
    const bezel = new THREE.Mesh(new THREE.BoxGeometry(bezelW, panelH, Math.min(2.2, bezelD)), darkMetal);
    bezel.position.y = gy * 0.13;
    root.add(bezel);
    const disp = new THREE.Mesh(new THREE.BoxGeometry(bezelW * 0.92, panelH * 0.88, Math.min(2.5, bezelD + 0.3)), screenGlow);
    disp.position.y = gy * 0.13;
    root.add(disp);
    const neck = new THREE.Mesh(new THREE.BoxGeometry(2.4, gy * 0.35, 1.8), chromeMat);
    neck.position.y = -gy * 0.32;
    root.add(neck);
    return root;
  }

  if (kind === "whiteboard" || kind === "screen") {
    const boardH = gy * 0.64;
    const boardW = Math.max(gx, gz);
    const frame = new THREE.Mesh(new THREE.BoxGeometry(boardW, boardH, 2.6), darkMetal);
    frame.position.y = gy * 0.16;
    root.add(frame);
    const glass = new THREE.Mesh(
      new THREE.BoxGeometry(boardW * 0.94, boardH * 0.9, 3.0),
      kind === "screen" ? screenGlow : new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.2 })
    );
    glass.position.y = gy * 0.16;
    root.add(glass);
    [-boardW * 0.42, boardW * 0.42].forEach((px) => {
      const post = new THREE.Mesh(new THREE.BoxGeometry(2.2, gy * 0.92, 2.2), darkMetal);
      post.position.set(px, -gy * 0.04, 0);
      root.add(post);
    });
    return root;
  }

  if (kind === "bookshelf") {
    const sideW = 1.8;
    [-gx / 2 + sideW / 2, gx / 2 - sideW / 2].forEach((sx) => {
      const s = new THREE.Mesh(new THREE.BoxGeometry(sideW, gy, gz), warmOak);
      s.position.x = sx;
      root.add(s);
    });
    const back = new THREE.Mesh(new THREE.BoxGeometry(gx, gy, 1.0), walnutMat);
    back.position.z = -gz / 2 + 0.5;
    root.add(back);
    const tiers = 5;
    const bookColors = [0x3b82f6, 0xf97316, 0x10b981, 0xeab308, 0xec4899, 0xf8fafc];
    for (let t = 0; t <= tiers; t++) {
      const sy = -gy / 2 + 1.5 + (t / tiers) * (gy - 3);
      const sh = new THREE.Mesh(new THREE.BoxGeometry(gx - sideW, 1.4, gz * 0.94), warmOak);
      sh.position.y = sy;
      root.add(sh);
      if (withBooks && t < tiers) {
        for (let b = 0; b < 5; b++) {
          const bw = (gx - 10) / 6;
          const bh = (gy / tiers) * 0.68;
          const bk = new THREE.Mesh(new THREE.BoxGeometry(bw * 0.82, bh, gz * 0.68), new THREE.MeshStandardMaterial({ color: bookColors[(b + t * 2) % bookColors.length] }));
          bk.position.set(-gx * 0.34 + b * (bw + 1.2), sy + 0.7 + bh / 2, 0.5);
          root.add(bk);
        }
      }
    }
    return root;
  }

  if (kind === "wall_art") {
    root.add(new THREE.Mesh(new THREE.BoxGeometry(gx, gy, gz), walnutMat));
    root.add(new THREE.Mesh(new THREE.BoxGeometry(gx * 0.84 + 0.4, gy * 0.82, gz * 0.84 + 0.4), mainMat));
    return root;
  }

  if (kind === "merch_rack") {
    const barW = Math.max(gx, gz);
    const topBar = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.1, barW, 10), chromeMat);
    topBar.rotation.z = Math.PI / 2;
    topBar.position.y = gy / 2 - 2;
    root.add(topBar);
    [-barW * 0.45, barW * 0.45].forEach((rx) => {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.2, gy, 10), darkMetal);
      post.position.x = rx;
      root.add(post);
    });
    const hoodieCols = [0x1f6feb, 0xf97316, 0x10b981, 0x8b5cf6, 0xf8fafc];
    for (let h = 0; h < 5; h++) {
      const garment = new THREE.Mesh(new THREE.BoxGeometry(barW * 0.14, gy * 0.52, 15), new THREE.MeshStandardMaterial({ color: hoodieCols[h % hoodieCols.length] }));
      garment.position.set(-barW * 0.32 + h * (barW * 0.16), gy * 0.08, 0);
      root.add(garment);
    }
    return root;
  }

  if (kind === "pos_kiosk" || kind === "podium") {
    const colW = kind === "podium" ? gx * 0.72 : gx * 0.45;
    const stand = new THREE.Mesh(new THREE.BoxGeometry(colW, gy * 0.82, gz * 0.65), kind === "podium" ? walnutMat : darkMetal);
    stand.position.y = -gy * 0.09;
    root.add(stand);
    const head = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.95, gy * 0.24, gz * 0.92), kind === "podium" ? warmOak : screenGlow);
    head.position.y = gy * 0.35;
    head.rotation.x = 0.32;
    root.add(head);
    return root;
  }

  if (kind === "counter_appliance") {
    root.add(new THREE.Mesh(new THREE.BoxGeometry(gx, gy, gz), chromeMat));
    const accent = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.9, gy * 0.35, gz + 0.6), mainMat);
    accent.position.y = gy * 0.22;
    root.add(accent);
    return root;
  }

  if (kind === "piano") {
    const body = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.7, gy, gz), walnutMat);
    body.position.x = -gx * 0.12;
    root.add(body);
    const keys = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.45, 3.5, gz * 0.92), screenGlow);
    keys.position.set(gx * 0.22, -gy * 0.05, 0);
    root.add(keys);
    return root;
  }

  const cabinet = new THREE.Mesh(new THREE.BoxGeometry(gx, gy - 3, gz), warmOak);
  cabinet.position.y = 1.5;
  root.add(cabinet);
  const stoneTop = new THREE.Mesh(new THREE.BoxGeometry(gx + 0.8, 2.0, gz + 0.8), mainMat);
  stoneTop.position.y = gy / 2 - 1.0;
  root.add(stoneTop);
  return root;
}

function renderZoneBuiltInFixtures(roomGroup, fixtures) {
  const walnut = new THREE.MeshStandardMaterial({ color: 0x4a3222, roughness: 0.62 });
  const marble = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.28, metalness: 0.1 });
  const brass = new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.32, metalness: 0.72 });
  const globeGlow = new THREE.MeshStandardMaterial({ color: 0xfef3c7, emissive: 0xfbbf24, emissiveIntensity: 0.8 });
  const foliageMat = new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.78 });

  fixtures.forEach((fx) => {
    if (fx.type === "stage_deck") {
      const deck = new THREE.Mesh(new THREE.BoxGeometry(fx.w, fx.h, fx.d), walnut);
      deck.position.set(fx.lx, fx.h / 2, fx.lz);
      roomGroup.add(deck);
      const trim = new THREE.Mesh(new THREE.BoxGeometry(fx.w + 2, 2.0, fx.d + 2), brass);
      trim.position.set(fx.lx, fx.h - 0.8, fx.lz);
      roomGroup.add(trim);
    } else if (fx.type === "espresso_bar") {
      const base = new THREE.Mesh(new THREE.BoxGeometry(fx.w, fx.h - 3, fx.d), walnut);
      base.position.set(fx.lx, (fx.h - 3) / 2, fx.lz);
      roomGroup.add(base);
      const counter = new THREE.Mesh(new THREE.BoxGeometry(fx.w + 6, 3, fx.d + 6), marble);
      counter.position.set(fx.lx + 2, fx.h - 1.5, fx.lz);
      roomGroup.add(counter);
    } else if (fx.type === "focus_bar") {
      const top = new THREE.Mesh(new THREE.BoxGeometry(fx.w, 2.5, fx.d), walnut);
      top.position.set(fx.lx, fx.h - 1.25, fx.lz);
      roomGroup.add(top);
      [-fx.w * 0.45, 0, fx.w * 0.45].forEach((ox) => {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(3, fx.h - 2.5, fx.d * 0.85), brass);
        leg.position.set(fx.lx + ox, (fx.h - 2.5) / 2, fx.lz);
        roomGroup.add(leg);
      });
    } else if (fx.type === "area_rug") {
      const rug = new THREE.Mesh(new THREE.BoxGeometry(fx.w, 0.8, fx.d), new THREE.MeshStandardMaterial({ color: fx.color || 0x312e81, roughness: 0.92 }));
      rug.position.set(fx.lx, 0.4, fx.lz);
      roomGroup.add(rug);
    } else if (fx.type === "lounge_table") {
      const top = new THREE.Mesh(new THREE.CylinderGeometry(fx.r, fx.r, 2.0, 24), marble);
      top.position.set(fx.lx, 17, fx.lz);
      roomGroup.add(top);
      const base = new THREE.Mesh(new THREE.CylinderGeometry(fx.r * 0.45, fx.r * 0.55, 16, 16), walnut);
      base.position.set(fx.lx, 8.5, fx.lz);
      roomGroup.add(base);
    } else if (fx.type === "pendant_cluster") {
      [-28, 28].forEach((oz, i) => {
        const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 36, 6), brass);
        cord.position.set(fx.lx, fx.h + 16, fx.lz + oz);
        roomGroup.add(cord);
        const bulb = new THREE.Mesh(new THREE.SphereGeometry(7.5, 14, 12), globeGlow);
        bulb.position.set(fx.lx, fx.h - 2 - i * 4, fx.lz + oz);
        roomGroup.add(bulb);
      });
    } else if (fx.type === "planter_tree") {
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(14, 11, 26, 14), walnut);
      pot.position.set(fx.lx, 13, fx.lz);
      roomGroup.add(pot);
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(2.4, 3.4, 58, 8), walnut);
      trunk.position.set(fx.lx, 48, fx.lz);
      roomGroup.add(trunk);
      const crown = new THREE.Mesh(new THREE.SphereGeometry(28, 16, 12), foliageMat);
      crown.position.set(fx.lx, 88, fx.lz);
      roomGroup.add(crown);
    } else if (fx.type === "pedestal") {
      const ped = new THREE.Mesh(new THREE.CylinderGeometry(4.5, 6, fx.h, 12), walnut);
      ped.position.set(fx.lx, fx.h / 2, fx.lz);
      roomGroup.add(ped);
    } else if (fx.type === "human") {
      roomGroup.add(buildHumanScaleFigure(fx.lx, fx.ly || 0, fx.lz));
    }
  });
}

/**
 * Build a 1912 Historic Riveted Steel Pratt Truss spanning `1,800"` (`150 ft`) across Z!
 */
function buildHistoricSteelTruss(trussX, spanZ = 1800, baseY = 648, depthY = 126, mat) {
  const g = new THREE.Group();
  g.position.x = trussX;

  // Bottom & Top heavy riveted box chords (`150 ft = 1,800"` long)
  const botChord = new THREE.Mesh(new THREE.BoxGeometry(16, 14, spanZ), mat);
  botChord.position.set(0, baseY, 0);
  g.add(botChord);

  const topChord = new THREE.Mesh(new THREE.BoxGeometry(16, 14, spanZ), mat);
  topChord.position.set(0, baseY + depthY, 0);
  g.add(topChord);

  // Vertical & diagonal Pratt truss web members every 100" (`8.3 ft`)
  const panels = 18;
  const dz = spanZ / panels;
  for (let i = 0; i <= panels; i++) {
    const z = -spanZ / 2 + i * dz;
    const vert = new THREE.Mesh(new THREE.BoxGeometry(11, depthY, 10), mat);
    vert.position.set(0, baseY + depthY / 2, z);
    g.add(vert);

    if (i < panels) {
      const diagLen = Math.hypot(dz, depthY);
      const diag = new THREE.Mesh(new THREE.BoxGeometry(8, diagLen, 7), mat);
      const zMid = z + dz / 2;
      diag.position.set(0, baseY + depthY / 2, zMid);
      const sign = zMid < 0 ? 1 : -1;
      diag.rotation.x = sign * Math.atan2(dz, depthY);
      g.add(diag);
    }
  }
  return g;
}

/**
 * Build one of Moynihan's 4 Double-Curved Catenary Skylight Gridshell Vaults (`600" × 1,800"`, apex `1,104"` = `92 ft`!).
 */
function buildCatenarySkylightVaultBay(xMin, xMax, zSpan = 1800, springY = 664, apexY = 1104, ribMat, glassMat) {
  const g = new THREE.Group();
  const nx = 10, nz = 20;
  const maxRise = apexY - springY; // 440" rise -> peaks at 1,104" = 92 ft!

  const ptAt = (ix, iz) => {
    const u = -1 + (2 * ix) / nx; // -1 .. +1 across 50-ft bay X
    const v = -1 + (2 * iz) / nz; // -1 .. +1 across 150-ft span Z
    const x = 0.5 * (xMin + xMax) + 0.5 * (xMax - xMin) * u;
    const z = 0.5 * zSpan * v;
    // Double-curved catenary pillow (rises across the 150-ft span AND billows between the 50-ft steel trusses!)
    const archZ = Math.max(0, 1 - v * v);
    const pillowX = 0.34 + 0.66 * Math.cos(u * Math.PI * 0.5);
    const y = springY + maxRise * archZ * pillowX;
    return new THREE.Vector3(x, y, z);
  };

  const verts = [];
  const lineVerts = [];
  for (let ix = 0; ix < nx; ix++) {
    for (let iz = 0; iz < nz; iz++) {
      const p00 = ptAt(ix, iz);
      const p10 = ptAt(ix + 1, iz);
      const p11 = ptAt(ix + 1, iz + 1);
      const p01 = ptAt(ix, iz + 1);

      verts.push(
        p00.x, p00.y, p00.z, p10.x, p10.y, p10.z, p11.x, p11.y, p11.z,
        p00.x, p00.y, p00.z, p11.x, p11.y, p11.z, p01.x, p01.y, p01.z
      );
      // Diagrid + orthogonal spider steel glazing bars
      lineVerts.push(
        p00.x, p00.y, p00.z, p10.x, p10.y, p10.z,
        p00.x, p00.y, p00.z, p01.x, p01.y, p01.z,
        p00.x, p00.y, p00.z, p11.x, p11.y, p11.z
      );
    }
  }

  const glassGeo = new THREE.BufferGeometry();
  glassGeo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
  glassGeo.computeVertexNormals();
  g.add(new THREE.Mesh(glassGeo, glassMat));

  const ribGeo = new THREE.BufferGeometry();
  ribGeo.setAttribute("position", new THREE.Float32BufferAttribute(lineVerts, 3));
  g.add(new THREE.LineSegments(ribGeo, ribMat));

  return g;
}

/**
 * Build a Track Boarding Escalator Island (`Tracks 5–16`) on the Moynihan Concourse floor.
 */
function buildTrackEscalatorIsland(cx, cz, gateLabel, makeTextSprite) {
  const g = new THREE.Group();
  g.position.set(cx, 0, cz);

  const wellW = 220, wellD = 84;
  // Dark stairwell void on floor
  const voidPad = new THREE.Mesh(
    new THREE.PlaneGeometry(wellW, wellD),
    new THREE.MeshStandardMaterial({ color: 0x0b0f17, roughness: 0.9 })
  );
  voidPad.rotation.x = -Math.PI / 2;
  voidPad.position.y = 0.3;
  g.add(voidPad);

  // Glass balustrades (`42"` tall) around escalator opening
  const glass = new THREE.MeshPhysicalMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthWrite: false });
  [-wellD / 2, wellD / 2].forEach((rz) => {
    const side = new THREE.Mesh(new THREE.BoxGeometry(wellW, 42, 2), glass);
    side.position.set(0, 21, rz);
    g.add(side);
  });
  const back = new THREE.Mesh(new THREE.BoxGeometry(2, 42, wellD), glass);
  back.position.set(wellW / 2, 21, 0);
  g.add(back);

  // Sloping escalator stainless deck descending eastward
  const ramp = new THREE.Mesh(
    new THREE.BoxGeometry(170, 6, 56),
    new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.6, roughness: 0.4 })
  );
  ramp.position.set(10, -14, 0);
  ramp.rotation.z = -0.18;
  g.add(ramp);

  // Iconic Moynihan vertical LED Boarding Gate Totem (`16 ft = 192"` tall)
  const totem = new THREE.Mesh(
    new THREE.BoxGeometry(14, 192, 28),
    new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.35, metalness: 0.4 })
  );
  totem.position.set(-wellW / 2 - 14, 96, 0);
  g.add(totem);

  const tag = makeTextSprite(gateLabel, "rgba(29, 78, 216, 0.92)", "#ffffff", 1.35);
  tag.position.set(-wellW / 2 - 14, 212, 0);
  g.add(tag);

  return g;
}

/**
 * Canvas sign & brand medallion generator for permanent Moynihan / Penn Station tenants
 * (Starbucks, Shake Shack, Duane Reade, Dunkin', The Irish Exit, Blue Bottle, Magnolia, Amtrak, etc.).
 */
function makeTenantBrandTexture({ brand, sub, bgHex = "#0f172a", accentHex = "#00704A", badgeText = "★", badgeBg = "#00704A" }) {
  const c = document.createElement("canvas");
  c.width = 640;
  c.height = 128;
  const ctx = c.getContext("2d");

  ctx.fillStyle = bgHex;
  ctx.fillRect(0, 0, 640, 128);
  ctx.fillStyle = accentHex;
  ctx.fillRect(0, 118, 640, 10);

  // Illuminated circular brand medallion on left
  ctx.fillStyle = badgeBg;
  ctx.beginPath();
  ctx.arc(62, 62, 38, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 3;
  ctx.stroke();

  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 26px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(badgeText, 62, 63);

  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#f8fafc";
  ctx.font = "800 30px system-ui, -apple-system, sans-serif";
  ctx.fillText(brand, 118, 58);

  ctx.fillStyle = "#cbd5e1";
  ctx.font = "600 20px system-ui, -apple-system, sans-serif";
  ctx.fillText(sub, 118, 92);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * Build a 1:1 architectural station retail storefront bay (local +Z opens into the concourse).
 */
function addStationStorefrontBay(parent, opts) {
  const {
    cx, cz, floorY = 0, rotY = 0,
    width = 260, depth = 120, height = 192,
    brand, sub, bgHex = "#111827", accentHex = "#00704A", badgeText = "☕", badgeBg = "#00704A",
    style = "coffee",
  } = opts;

  const g = new THREE.Group();
  g.position.set(cx, floorY, cz);
  g.rotation.y = rotY;

  const shellMat = new THREE.MeshStandardMaterial({ color: 0x1e2633, roughness: 0.72, metalness: 0.12 });
  const warmWood = new THREE.MeshStandardMaterial({ color: 0x7c5333, roughness: 0.56 });
  const quartzMat = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.25, metalness: 0.08 });
  const chromeMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.25, metalness: 0.8 });
  const accentMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(accentHex), roughness: 0.42, metalness: 0.15 });
  const menuGlow = new THREE.MeshBasicMaterial({ color: style === "starbucks" ? 0x064e3b : 0x0f172a });

  // Recessed floor pad
  const pad = new THREE.Mesh(
    new THREE.PlaneGeometry(width, depth),
    new THREE.MeshStandardMaterial({ color: 0x262f3d, roughness: 0.7 })
  );
  pad.rotation.x = -Math.PI / 2;
  pad.position.set(0, 0.35, 0);
  g.add(pad);

  // Back wall & flanking piers
  const back = new THREE.Mesh(new THREE.BoxGeometry(width, height, 5), shellMat);
  back.position.set(0, height / 2, -depth / 2 + 2.5);
  g.add(back);

  [-width / 2 + 4, width / 2 - 4].forEach((px) => {
    const pier = new THREE.Mesh(new THREE.BoxGeometry(8, height, depth), shellMat);
    pier.position.set(px, height / 2, 0);
    g.add(pier);
  });

  // Illuminated ceiling light strip inside storefront
  const soffitGlow = new THREE.Mesh(
    new THREE.PlaneGeometry(width - 24, depth * 0.55),
    new THREE.MeshBasicMaterial({ color: 0xfef3c7, transparent: true, opacity: 0.35, side: THREE.DoubleSide })
  );
  soffitGlow.rotation.x = Math.PI / 2;
  soffitGlow.position.set(0, height - 4, 0);
  g.add(soffitGlow);

  // Front illuminated brand fascia at +depth/2
  const brandTex = makeTenantBrandTexture({ brand, sub, bgHex, accentHex, badgeText, badgeBg });
  const fascia = new THREE.Mesh(
    new THREE.BoxGeometry(width, 40, 8),
    [shellMat, shellMat, shellMat, shellMat, new THREE.MeshBasicMaterial({ map: brandTex }), shellMat]
  );
  fascia.position.set(0, height - 20, depth / 2 - 2);
  g.add(fascia);

  // Back-wall menu board / signage band
  const menuBoard = new THREE.Mesh(new THREE.BoxGeometry(width * 0.76, 32, 3), menuGlow);
  menuBoard.position.set(0, 98, -depth / 2 + 7);
  g.add(menuBoard);
  const menuTrim = new THREE.Mesh(new THREE.BoxGeometry(width * 0.78, 3, 4), accentMat);
  menuTrim.position.set(0, 115, -depth / 2 + 7);
  g.add(menuTrim);

  if (style === "starbucks" || style === "coffee" || style === "shakeshack") {
    // Service & espresso / pickup counter
    const cW = width * 0.74;
    const base = new THREE.Mesh(new THREE.BoxGeometry(cW, 38, 32), style === "shakeshack" ? shellMat : warmWood);
    base.position.set(0, 19, 10);
    g.add(base);
    const top = new THREE.Mesh(new THREE.BoxGeometry(cW + 4, 3, 36), quartzMat);
    top.position.set(0, 39.5, 10);
    g.add(top);

    // Accent front apron stripe
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(cW + 1, 8, 1.5), accentMat);
    stripe.position.set(0, 31, 26.5);
    g.add(stripe);

    // Espresso machines + glass pastry display case
    [-cW * 0.26, 0].forEach((mx) => {
      const esp = new THREE.Mesh(new THREE.BoxGeometry(28, 18, 20), chromeMat);
      esp.position.set(mx, 50, 8);
      g.add(esp);
    });
    const pastry = new THREE.Mesh(
      new THREE.BoxGeometry(44, 20, 22),
      new THREE.MeshPhysicalMaterial({ color: 0xfef3c7, transparent: true, opacity: 0.45, roughness: 0.15 })
    );
    pastry.position.set(cW * 0.28, 51, 10);
    g.add(pastry);

    // Barista figure behind counter
    g.add(buildHumanScaleFigure(-24, 0, -16, style === "starbucks" ? 0x15803d : 0x94a3b8));

    // For Starbucks LIRR Concourse: add café tables & commuters out front on the concourse apron!
    if (style === "starbucks") {
      [-95, 0, 95].forEach((tx) => {
        const tbl = new THREE.Mesh(new THREE.CylinderGeometry(16, 16, 2, 18), warmWood);
        tbl.position.set(tx, 30, depth / 2 + 34);
        g.add(tbl);
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(2, 2.5, 29, 10), shellMat);
        leg.position.set(tx, 14.5, depth / 2 + 34);
        g.add(leg);
      });
      g.add(buildHumanScaleFigure(48, 0, depth / 2 + 24, 0xe2e8f0));
    }
  } else if (style === "tickets") {
    // MTA / LIRR Touchscreen Fare & OMNY Machines row
    for (let k = 0; k < 4; k++) {
      const kx = -width * 0.33 + k * (width * 0.22);
      const body = new THREE.Mesh(new THREE.BoxGeometry(26, 74, 22), chromeMat);
      body.position.set(kx, 37, 8);
      g.add(body);
      const scr = new THREE.Mesh(
        new THREE.BoxGeometry(20, 24, 2),
        new THREE.MeshBasicMaterial({ color: 0x38bdf8 })
      );
      scr.position.set(kx, 50, 19.5);
      g.add(scr);
      const hdr = new THREE.Mesh(new THREE.BoxGeometry(26, 8, 23), accentMat);
      hdr.position.set(kx, 70, 8);
      g.add(hdr);
    }
  } else if (style === "amtrak") {
    // Amtrak curved Heritage-Blue Customer Service / Lounge desk
    const deskW = width * 0.72;
    const desk = new THREE.Mesh(new THREE.BoxGeometry(deskW, 40, 34), accentMat);
    desk.position.set(0, 20, 12);
    g.add(desk);
    const counter = new THREE.Mesh(new THREE.BoxGeometry(deskW + 6, 3, 38), quartzMat);
    counter.position.set(0, 41.5, 12);
    g.add(counter);
    g.add(buildHumanScaleFigure(-40, 0, -14, 0x60a5fa));
    g.add(buildHumanScaleFigure(45, 0, -14, 0x60a5fa));
  } else if (style === "waiting") {
    // Ticketed Passenger Waiting Room walnut benches
    [-32, 18].forEach((bz) => {
      [-width * 0.24, width * 0.24].forEach((bx) => {
        const seat = new THREE.Mesh(new THREE.BoxGeometry(width * 0.38, 18, 22), warmWood);
        seat.position.set(bx, 9, bz);
        g.add(seat);
        const backRest = new THREE.Mesh(new THREE.BoxGeometry(width * 0.38, 18, 4), warmWood);
        backRest.position.set(bx, 24, bz - 9);
        g.add(backRest);
      });
    });
  } else {
    // Pharmacy / Boutique illuminated shelving Gondolas
    [-width * 0.25, width * 0.25].forEach((sx) => {
      const rack = new THREE.Mesh(new THREE.BoxGeometry(width * 0.32, 68, 18), quartzMat);
      rack.position.set(sx, 34, -8);
      g.add(rack);
    });
    const cash = new THREE.Mesh(new THREE.BoxGeometry(64, 38, 26), warmWood);
    cash.position.set(0, 19, 26);
    g.add(cash);
  }

  parent.add(g);
}

/**
 * Build Moynihan Food Hall's signature 360° oval walnut-and-brass island bar ("The Irish Exit").
 */
function buildIrishExitIslandBar(parent, cx, cz, makeTextSprite) {
  const g = new THREE.Group();
  g.position.set(cx, 0, cz);

  const walnut = new THREE.MeshStandardMaterial({ color: 0x5c3a21, roughness: 0.5 });
  const brass = new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.28, metalness: 0.78 });
  const amberGlow = new THREE.MeshStandardMaterial({ color: 0xfde68a, emissive: 0xd97706, emissiveIntensity: 0.65, roughness: 0.25 });
  const leather = new THREE.MeshStandardMaterial({ color: 0x7c2d12, roughness: 0.6 });

  // Oval bar counter (`220" × 112"` achieved by scaling a cylinder `scale.x = 1.95`)
  const barBase = new THREE.Mesh(new THREE.CylinderGeometry(54, 52, 40, 32), walnut);
  barBase.scale.set(1.95, 1, 1);
  barBase.position.y = 20;
  g.add(barBase);

  const barTop = new THREE.Mesh(new THREE.CylinderGeometry(59, 59, 3.2, 32), brass);
  barTop.scale.set(1.95, 1, 1);
  barTop.position.y = 41.5;
  g.add(barTop);

  // Center illuminated bottle tower
  [18, 34, 48].forEach((ty, idx) => {
    const tier = new THREE.Mesh(new THREE.CylinderGeometry(22 - idx * 4, 24 - idx * 4, 12, 24), amberGlow);
    tier.scale.set(1.75, 1, 1);
    tier.position.y = 42 + ty;
    g.add(tier);
  });

  // Suspended brass halo canopy above island bar
  const halo = new THREE.Mesh(new THREE.TorusGeometry(54, 3.2, 12, 36), brass);
  halo.rotation.x = Math.PI / 2;
  halo.scale.set(1.9, 1, 1);
  halo.position.y = 138;
  g.add(halo);

  // 10 leather barstools around the oval perimeter
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    const sx = Math.cos(a) * 124;
    const sz = Math.sin(a) * 68;
    const cushion = new THREE.Mesh(new THREE.CylinderGeometry(8.5, 8.5, 3.2, 16), leather);
    cushion.position.set(sx, 29, sz);
    g.add(cushion);
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(1.4, 1.8, 28, 8), brass);
    stem.position.set(sx, 14, sz);
    g.add(stem);
  }

  const sign = makeTextSprite("🍸 THE IRISH EXIT · MOYNIHAN FOOD HALL BAR", "rgba(69, 26, 3, 0.92)", "#fde68a", 1.28);
  sign.position.set(0, 168, 0);
  g.add(sign);

  parent.add(g);
}

/**
 * Render the actual real-life existing tenants & public concourse fixtures of
 * Moynihan Train Hall and the renovated 57-ft LIRR 33rd St Concourse!
 */
function buildRealStationTenants(archGroup, makeTextSprite) {
  const tenants = new THREE.Group();

  // --- A. EAST 57-FT SOM LIRR 33rd ST CONCOURSE REAL TENANTS (Starbucks, Shake Shack, Duane Reade, Dunkin', LIRR Tickets) ---
  addStationStorefrontBay(tenants, {
    cx: 1730, cz: 414, rotY: Math.PI, width: 340, depth: 144, height: 198,
    brand: "STARBUCKS COFFEE",
    sub: "LIRR 33rd St Concourse · Espresso & Mobile Pickup",
    bgHex: "#072b1f", accentHex: "#00704A", badgeText: "☕", badgeBg: "#00704A",
    style: "starbucks",
  });
  addStationStorefrontBay(tenants, {
    cx: 2110, cz: 408, rotY: Math.PI, width: 310, depth: 132, height: 192,
    brand: "SHAKE SHACK",
    sub: "Penn Station LIRR Concourse · Burgers & Shakes",
    bgHex: "#18181b", accentHex: "#64A70B", badgeText: "🍔", badgeBg: "#4d7c0f",
    style: "shakeshack",
  });
  addStationStorefrontBay(tenants, {
    cx: 1380, cz: 402, rotY: Math.PI, width: 260, depth: 120, height: 192,
    brand: "DUANE READE",
    sub: "by Walgreens · LIRR Concourse Pharmacy",
    bgHex: "#172554", accentHex: "#ef4444", badgeText: "Rx", badgeBg: "#dc2626",
    style: "pharmacy",
  });
  addStationStorefrontBay(tenants, {
    cx: 1295, cz: -390, rotY: 0, width: 170, depth: 96, height: 186,
    brand: "MTA LIRR TICKETS",
    sub: "Tracks 17–21 Fare & OMNY Kiosks",
    bgHex: "#0f172a", accentHex: "#eab308", badgeText: "🎫", badgeBg: "#1d4ed8",
    style: "tickets",
  });
  addStationStorefrontBay(tenants, {
    cx: 2210, cz: -400, rotY: 0, width: 260, depth: 116, height: 186,
    brand: "DUNKIN' · GOTHAM NEWS",
    sub: "LIRR Concourse East · Coffee & Newsstand",
    bgHex: "#271522", accentHex: "#f97316", badgeText: "DD", badgeBg: "#db2777",
    style: "coffee",
  });

  // Floating landmark pin above LIRR Starbucks so George spots it immediately from aerial too!
  const sbuxPin = makeTextSprite("☕ STARBUCKS (LIRR CONCOURSE)", "rgba(0, 112, 74, 0.94)", "#ffffff", 1.38);
  sbuxPin.position.set(1730, 232, 330);
  tenants.add(sbuxPin);

  // --- B. MOYNIHAN TRAIN HALL FOOD HALL & NORTH COLONNADE REAL TENANTS ---
  buildIrishExitIslandBar(tenants, -820, -1035, makeTextSprite);

  addStationStorefrontBay(tenants, {
    cx: 410, cz: -960, rotY: 0, width: 250, depth: 120, height: 196,
    brand: "BLUE BOTTLE COFFEE",
    sub: "Moynihan North Concourse · Pour-Over & Espresso",
    bgHex: "#0f172a", accentHex: "#0ea5e9", badgeText: "💧", badgeBg: "#0284c7",
    style: "coffee",
  });
  addStationStorefrontBay(tenants, {
    cx: 710, cz: -960, rotY: 0, width: 280, depth: 120, height: 196,
    brand: "MAGNOLIA BAKERY · H&H",
    sub: "Moynihan Food Hall · Bakery & NYC Bagels",
    bgHex: "#132a24", accentHex: "#34d399", badgeText: "🧁", badgeBg: "#059669",
    style: "coffee",
  });
  addStationStorefrontBay(tenants, {
    cx: 1010, cz: -960, rotY: 0, width: 250, depth: 120, height: 196,
    brand: "STARBUCKS · MOYNIHAN",
    sub: "Moynihan East Gateway Pickup",
    bgHex: "#072b1f", accentHex: "#00704A", badgeText: "☕", badgeBg: "#00704A",
    style: "starbucks",
  });

  // --- C. SOUTH 31st ST AMTRAK CONCOURSE & TICKETED WAITING ROOM ---
  addStationStorefrontBay(tenants, {
    cx: 440, cz: 966, rotY: Math.PI, width: 340, depth: 132, height: 196,
    brand: "AMTRAK TICKETING & RED CAP",
    sub: "31st St Concourse · Customer Service & Baggage",
    bgHex: "#0c243c", accentHex: "#0284c7", badgeText: "🚆", badgeBg: "#0369a1",
    style: "amtrak",
  });
  addStationStorefrontBay(tenants, {
    cx: 870, cz: 972, rotY: Math.PI, width: 380, depth: 144, height: 196,
    brand: "TICKETED WAITING ROOM",
    sub: "Amtrak & LIRR Seated Concourse Sanctuary",
    bgHex: "#172554", accentHex: "#60a5fa", badgeText: "💺", badgeBg: "#1d4ed8",
    style: "waiting",
  });

  // --- D. WEST 9th AVE RETAIL ARCADE (Malin+Goetz & Moleskine) ---
  addStationStorefrontBay(tenants, {
    cx: -1254, cz: -340, rotY: Math.PI / 2, width: 210, depth: 108, height: 186,
    brand: "MALIN+GOETZ",
    sub: "9th Ave Apothecary",
    bgHex: "#1e293b", accentHex: "#38bdf8", badgeText: "M+", badgeBg: "#0284c7",
    style: "boutique",
  });
  addStationStorefrontBay(tenants, {
    cx: -1254, cz: 360, rotY: Math.PI / 2, width: 220, depth: 108, height: 186,
    brand: "MOLESKINE · RAINS",
    sub: "9th Ave Retail Corridor",
    bgHex: "#18181b", accentHex: "#eab308", badgeText: "📓", badgeBg: "#ca8a04",
    style: "boutique",
  });

  // --- E. +20 FT SOUTH MEZZANINE AMTRAK METROPOLITAN LOUNGE ---
  addStationStorefrontBay(tenants, {
    cx: -580, cz: 1140, floorY: 240, rotY: Math.PI, width: 420, depth: 160, height: 168,
    brand: "AMTRAK METROPOLITAN LOUNGE",
    sub: "+20 ft Balcony Terrace · First Class & Acela",
    bgHex: "#0f172a", accentHex: "#38bdf8", badgeText: "🥂", badgeBg: "#1d4ed8",
    style: "amtrak",
  });

  archGroup.add(tenants);
}

/**
 * Build the complete 1:1 Scale Moynihan Train Hall + SOM LIRR Concourse into `worldGroup`.
 */
export function buildPennVenueScene({
  plan,
  worldGroup,
  meshEntries,
  binTargets,
  playDir,
  itemColorHex,
  violatingIds,
  makeBoxFaceTexture,
  makeTextSprite,
  showRoof = true,
  hideUnpackedBoxes = false,
  showExistingTenants = true,
  fmt,
}) {
  const archGroup = new THREE.Group();
  worldGroup.add(archGroup);

  // ==================== 1. FULL CITY-BLOCK BASE & TRAVERTINE ATRIUM FLOOR (`200 × 150 FT = 2,400 × 1,800"`) ====================
  const cityBlockSlab = new THREE.Mesh(
    new THREE.BoxGeometry(4700, 12, 3100),
    new THREE.MeshStandardMaterial({ color: 0x151922, roughness: 0.95 })
  );
  cityBlockSlab.position.set(220, -6.2, 0);
  archGroup.add(cityBlockSlab);

  // 31,000 sq ft Main Moynihan Boarding Concourse Travertine Floor (`2,400" × 1,800"`)
  const atriumFloor = new THREE.Mesh(
    new THREE.PlaneGeometry(2400, 1800),
    new THREE.MeshStandardMaterial({ color: 0x353d4b, roughness: 0.65, metalness: 0.08 })
  );
  atriumFloor.rotation.x = -Math.PI / 2;
  atriumFloor.position.set(0, 0.1, 0);
  archGroup.add(atriumFloor);

  // 10-foot (`120"`) architectural stone expansion grid across the 200×150 ft hall
  const grid = new THREE.GridHelper(2400, 20, 0x64748b, 0x475569);
  grid.scale.z = 1800 / 2400;
  grid.position.set(0, 0.25, 0);
  grid.material.transparent = true;
  grid.material.opacity = 0.28;
  archGroup.add(grid);

  // Scale reference callout on floor border
  const scaleTag = makeTextSprite(
    "MOYNIHAN ATRIUM · 200 FT × 150 FT (31,000 SQ FT) · 92 FT SKYLIGHT · 1:1 SCALE",
    "rgba(15, 23, 42, 0.88)",
    "#93c5fd",
    2.2
  );
  scaleTag.position.set(0, 24, -865);
  archGroup.add(scaleTag);

  // Commuter human-scale figures (`5'8" = 68"`) walking the grand concourse for instant scale perception
  [[-680, -320], [-540, 280], [640, -240], [720, 310], [1350, 60], [1580, -90]].forEach(([hx, hz]) => {
    archGroup.add(buildHumanScaleFigure(hx, 0, hz, 0x94a3b8));
  });

  // ==================== 2. HISTORIC BEAUX-ARTS GRANITE PIERS & +20 FT (`240"`) MEZZANINE BALCONY ====================
  const limestoneMat = new THREE.MeshStandardMaterial({ color: 0x647082, roughness: 0.68, metalness: 0.12 });
  const steelMat = new THREE.MeshStandardMaterial({ color: 0x3b4454, roughness: 0.45, metalness: 0.65 });
  const mezzDeckMat = new THREE.MeshStandardMaterial({ color: 0x28303d, roughness: 0.75 });
  const railGlassMat = new THREE.MeshPhysicalMaterial({
    color: 0xbae6fd,
    transparent: true,
    opacity: 0.26,
    roughness: 0.15,
    side: THREE.DoubleSide,
    depthWrite: false,
  });

  // Monumental perimeter columns at the 50-ft (`600"`) structural bays (`X = -1200, -600, 0, +600, +1200`, `Z = ±900`)
  const bayXs = [-1200, -600, 0, 600, 1200];
  [-900, 900].forEach((pz) => {
    bayXs.forEach((px) => {
      const pier = new THREE.Mesh(new THREE.BoxGeometry(54, 660, 54), limestoneMat);
      pier.position.set(px, 330, pz);
      archGroup.add(pier);
      const base = new THREE.Mesh(new THREE.BoxGeometry(68, 36, 68), steelMat);
      base.position.set(px, 18, pz);
      archGroup.add(base);
    });
    // Perimeter ring girder at `Y = 654"` (`54.5 ft`)
    const ringBeam = new THREE.Mesh(new THREE.BoxGeometry(2460, 28, 36), steelMat);
    ringBeam.position.set(0, 654, pz);
    archGroup.add(ringBeam);
  });

  // Second-Story Mezzanine Balcony (`Y = 240"` = +20 ft high) along North, South, and West perimeter!
  // South Mezzanine Promenade (`Z = +840 .. +1380`, hosting the Metropolitan / Malin Lounge!)
  const southMezz = new THREE.Mesh(new THREE.BoxGeometry(2400, 14, 540), mezzDeckMat);
  southMezz.position.set(0, 233, 1110);
  archGroup.add(southMezz);
  const southRail = new THREE.Mesh(new THREE.BoxGeometry(2360, 44, 2.5), railGlassMat);
  southRail.position.set(0, 262, 842);
  archGroup.add(southRail);

  // North Mezzanine Balcony (`Z = -840 .. -1020` gallery walkway above Food Hall)
  const northMezz = new THREE.Mesh(new THREE.BoxGeometry(2400, 14, 180), mezzDeckMat);
  northMezz.position.set(0, 233, -930);
  archGroup.add(northMezz);
  const northRail = new THREE.Mesh(new THREE.BoxGeometry(2360, 44, 2.5), railGlassMat);
  northRail.position.set(0, 262, -842);
  archGroup.add(northRail);

  // Dedicated Mezzanine Lounge Escalator & Feature Staircase rising from `Y = 0` to `Y = 240"` on South Concourse (`X = -40, Z = +780`)
  const mezzEsc = new THREE.Group();
  const escLen = Math.hypot(380, 240);
  const escRamp = new THREE.Mesh(
    new THREE.BoxGeometry(escLen, 14, 68),
    new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.55, roughness: 0.4 })
  );
  escRamp.position.set(-140, 120, 800);
  escRamp.rotation.z = Math.atan2(240, 380);
  mezzEsc.add(escRamp);
  const mezzEscTag = makeTextSprite("↑ MEZZANINE LOUNGE (+20 FT)", "rgba(139, 92, 246, 0.9)", "#ffffff", 1.3);
  mezzEscTag.position.set(-310, 96, 800);
  mezzEsc.add(mezzEscTag);
  archGroup.add(mezzEsc);

  // ==================== 3. FOUR TRACK BOARDING ESCALATOR ISLANDS (`Tracks 5–16`) ====================
  [
    [-760, -520, "TRACKS 5 · 6"],
    [-760, 520, "TRACKS 7 · 8"],
    [760, -520, "TRACKS 11 · 12"],
    [760, 520, "TRACKS 15 · 16"],
  ].forEach(([ix, iz, lbl]) => {
    archGroup.add(buildTrackEscalatorIsland(ix, iz, lbl, makeTextSprite));
  });

  // ==================== 4. THREE 150-FT HISTORIC STEEL TRUSSES + FOUR 92-FT CATENARY VAULTS ====================
  if (showRoof) {
    const roofGroup = new THREE.Group();

    // 3 Historic 1912 Steel Trusses at X = -600", 0", +600" (`50 ft` on center, `150 ft` span!)
    [-600, 0, 600].forEach((tx) => {
      roofGroup.add(buildHistoricSteelTruss(tx, 1800, 648, 126, steelMat));
    });
    // End arch gable trusses at X = -1200" and +1200"
    [-1200, 1200].forEach((tx) => {
      roofGroup.add(buildHistoricSteelTruss(tx, 1800, 648, 84, steelMat));
    });

    const ribMat = new THREE.LineBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.42 });
    const skyGlassMat = new THREE.MeshPhysicalMaterial({
      color: 0xdbeafe,
      transparent: true,
      opacity: 0.085,
      roughness: 0.12,
      side: THREE.DoubleSide,
      depthWrite: false,
    });

    // 4 Grand Catenary Skylight Vaults peaking at `Y = 1,104"` (`92 feet`!)
    [
      [-1200, -600],
      [-600, 0],
      [0, 600],
      [600, 1200],
    ].forEach(([x0, x1]) => {
      roofGroup.add(buildCatenarySkylightVaultBay(x0, x1, 1800, 668, 1104, ribMat, skyGlassMat));
    });

    // Iconic Suspended Moynihan Central Clock hanging from Center Truss (`X = 0, Z = 0`, `Y = 480"`)
    const clockTex = makeClockTexture();
    const clockFace = new THREE.MeshBasicMaterial({ map: clockTex });
    const clockDrum = new THREE.Mesh(
      new THREE.CylinderGeometry(48, 48, 16, 32),
      [new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.75, roughness: 0.28 }), clockFace, clockFace]
    );
    clockDrum.rotation.z = Math.PI / 2;
    clockDrum.position.set(0, 485, 0);
    roofGroup.add(clockDrum);

    const hanger = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 2.5, 165, 10), steelMat);
    hanger.position.set(0, 570, 0);
    roofGroup.add(hanger);

    const apexTag = makeTextSprite("SKYLIGHT APEX · 92 FT (1,104 IN)", "rgba(15, 23, 42, 0.85)", "#fde68a", 1.8);
    apexTag.position.set(0, 1138, 0);
    roofGroup.add(apexTag);

    archGroup.add(roofGroup);
  }

  // ==================== 5. EAST WING: SOM RENOVATED LIRR CONCOURSE (`57 FT = 684"` WIDE × `18 FT = 216"` HIGH!) ====================
  const lirrGroup = new THREE.Group();
  // Spans `X = +1,200" .. +2,520"` (`110 ft` connector segment), `Z = -342" .. +342"` (`57 ft = 684"` exact width!)
  const lirrFloor = new THREE.Mesh(
    new THREE.PlaneGeometry(1320, 684),
    new THREE.MeshStandardMaterial({ color: 0x303846, roughness: 0.66 })
  );
  lirrFloor.rotation.x = -Math.PI / 2;
  lirrFloor.position.set(1860, 0.14, 0);
  lirrGroup.add(lirrFloor);

  // SOM's signature 18-ft-high (`Y = 216"`) Luminous Color-Accented LED Coffered Ceiling!
  if (showRoof) {
    const ledMat = new THREE.MeshBasicMaterial({ color: 0xe0f2fe, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false });
    for (let bx = 1320; bx <= 2400; bx += 180) {
      const panel = new THREE.Mesh(new THREE.PlaneGeometry(148, 580), ledMat);
      panel.rotation.x = Math.PI / 2;
      panel.position.set(bx, 216, 0);
      lirrGroup.add(panel);
    }
  }

  // Wide Digital Departure Board at East Gateway (`X = +1,210, Y = 330"`, facing West into Moynihan Atrium!)
  const boardTex = makeDepartureBoardTexture();
  const boardMesh = new THREE.Mesh(
    new THREE.BoxGeometry(12, 138, 520),
    [
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshBasicMaterial({ map: boardTex }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
    ]
  );
  boardMesh.position.set(1196, 336, 0);
  lirrGroup.add(boardMesh);

  const lirrTag = makeTextSprite(
    "EAST WING · SOM LIRR 33rd ST CONCOURSE (57 FT WIDE × 18 FT HIGH) → TRACKS 17–21",
    "rgba(29, 78, 216, 0.88)",
    "#ffffff",
    1.7
  );
  lirrTag.position.set(1860, 250, 0);
  lirrGroup.add(lirrTag);

  // Track 17–21 Platform Stairs at East end of LIRR Concourse (`X = +2,360`)
  [[-165, "TRACKS 17 · 18"], [165, "TRACKS 19 · 21"]].forEach(([sz, lbl]) => {
    archGroup.add(buildTrackEscalatorIsland(2280, sz, lbl, makeTextSprite));
  });
  archGroup.add(lirrGroup);

  // ==================== 6. WEST END: 31st ST LOADING DOCK + TRUE 1:1 `314"` (26-FT) U-HAUL FLEET ====================
  const dockGroup = new THREE.Group();
  const dockApron = new THREE.Mesh(
    new THREE.BoxGeometry(520, 8, 920),
    new THREE.MeshStandardMaterial({ color: 0x2c3340, roughness: 0.9 })
  );
  dockApron.position.set(-1460, -3.5, 0);
  dockGroup.add(dockApron);

  // Render the ACTUAL `314" × 98" × 99"` (26-ft) U-Haul Fleet backed up to the loading bays at 1:1 scale!
  const truckCount = Math.max(1, Math.min(4, (plan.trucks || []).length || 3));
  for (let ti = 0; ti < truckCount; ti++) {
    const tz = (ti - (truckCount - 1) / 2) * 180;
    // Exact 26-ft U-Haul cargo box: 314" × 98" × 99" on 35" deck height!
    const cargo = new THREE.Mesh(
      new THREE.BoxGeometry(314, 99, 98),
      new THREE.MeshStandardMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.34, roughness: 0.45 })
    );
    cargo.position.set(-1540, 35 + 49.5, tz);
    dockGroup.add(cargo);

    const wire = new THREE.LineSegments(
      new THREE.EdgesGeometry(cargo.geometry),
      new THREE.LineBasicMaterial({ color: 0xf97316, transparent: true, opacity: 0.85 })
    );
    wire.position.copy(cargo.position);
    dockGroup.add(wire);

    const orangeStripe = new THREE.Mesh(
      new THREE.BoxGeometry(315, 14, 99),
      new THREE.MeshStandardMaterial({ color: 0xf97316 })
    );
    orangeStripe.position.set(-1540, 56, tz);
    dockGroup.add(orangeStripe);

    const cab = new THREE.Mesh(
      new THREE.BoxGeometry(78, 82, 92),
      new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.5 })
    );
    cab.position.set(-1540 - 157 - 40, 44, tz);
    dockGroup.add(cab);
  }

  const dockSign = makeTextSprite(
    `31st ST LOADING DOCK · ${truckCount} × 26-FT U-HAUL (1:1 SCALE) →`,
    "rgba(249, 115, 22, 0.92)",
    "#ffffff",
    1.65
  );
  dockSign.position.set(-1520, 195, 0);
  dockGroup.add(dockSign);
  archGroup.add(dockGroup);

  // ==================== 6B. REAL-LIFE EXISTING TENANTS & CONCOURSE SHOPS ====================
  if (showExistingTenants) {
    buildRealStationTenants(archGroup, makeTextSprite);
  }

  // ==================== 7. COWORKING SUITES, MEZZANINE LOUNGE & 1:1 STAGED FURNITURE ====================
  const zones = plan.zones || [];
  const orderedVenueItems = [];

  zones.forEach((zone) => {
    const spec = VENUE_ZONE_LAYOUT[zone.zone_id];
    if (!spec) return;
    const [L, W, H] = spec.vDims;
    const openW = spec.doorSpan || 360;
    const baseElev = spec.floorY || 0;
    const isConcourse = zone.zone_type === "concourse";

    // Ground-level dock-to-zone guide line
    if (spec.dockPath && spec.dockPath.length >= 2) {
      const pathPts = spec.dockPath.map(([px, pz]) => new THREE.Vector3(px, 1.2, pz));
      const pathLine = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(pathPts),
        new THREE.LineDashedMaterial({
          color: new THREE.Color(spec.accentHex),
          dashSize: 28,
          gapSize: 16,
          transparent: true,
          opacity: 0.62,
        })
      );
      pathLine.computeLineDistances();
      archGroup.add(pathLine);
    }

    const roomGroup = new THREE.Group();
    roomGroup.position.set(spec.cx, baseElev, spec.cz);
    roomGroup.rotation.y = spec.rotY;
    worldGroup.add(roomGroup);

    if (!isConcourse) {
      const rFloor = new THREE.Mesh(
        new THREE.PlaneGeometry(L, W),
        new THREE.MeshStandardMaterial({ color: spec.floorColor, roughness: 0.76, metalness: 0.05 })
      );
      rFloor.rotation.x = -Math.PI / 2;
      rFloor.position.set(0, 0.3, 0);
      roomGroup.add(rFloor);

      const wallMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.7, metalness: 0.12 });
      const glassMat = new THREE.MeshPhysicalMaterial({
        color: 0x93c5fd,
        transparent: true,
        opacity: 0.16,
        roughness: 0.12,
        side: THREE.DoubleSide,
        depthWrite: false,
      });

      const backWall = new THREE.Mesh(new THREE.BoxGeometry(6, 72, W), wallMat);
      backWall.position.set(-L / 2 + 3, 36, 0);
      roomGroup.add(backWall);

      [-W / 2 + 3, W / 2 - 3].forEach((sz) => {
        const sideWall = new THREE.Mesh(new THREE.BoxGeometry(L, 60, 6), wallMat);
        sideWall.position.set(0, 30, sz);
        roomGroup.add(sideWall);
      });

      if (!spec.isMezzanine) {
        const wingSpan = Math.max(0, (W - openW) / 2);
        if (wingSpan > 12) {
          [-W / 2 + wingSpan / 2, W / 2 - wingSpan / 2].forEach((wz) => {
            const pane = new THREE.Mesh(new THREE.BoxGeometry(3, H - 36, wingSpan - 4), glassMat);
            pane.position.set(L / 2 - 2, (H - 36) / 2, wz);
            roomGroup.add(pane);
          });
        }
      }

      const signTex = makeSignTexture(
        spec.signTitle,
        `${Math.round(W / 12)}×${Math.round(L / 12)} FT SUITE · ${zone.item_count} PCS STAGED`,
        spec.accentHex
      );
      const fascia = new THREE.Mesh(
        new THREE.BoxGeometry(8, 36, Math.min(W * 0.85, 420)),
        [new THREE.MeshBasicMaterial({ map: signTex }), wallMat, wallMat, wallMat, wallMat, wallMat]
      );
      fascia.position.set(L / 2 - 4, spec.isMezzanine ? 156 : H - 18, 0);
      roomGroup.add(fascia);
    } else {
      const concBanner = makeTextSprite(
        "STOP 6 · MAIN ATRIUM HACKATHON & COWORKING VILLAGE",
        "rgba(8, 51, 68, 0.9)",
        "#67e8f9",
        1.85
      );
      concBanner.position.set(0, 196, 0);
      roomGroup.add(concBanner);
    }

    binTargets.push({
      label: `Stop ${zone.dock_stop}`,
      center: new THREE.Vector3(spec.cx, baseElev + 48, spec.cz),
      radius: isConcourse ? 780 : Math.max(L, W) * 0.72,
      photoZone: zone.zone_id,
    });

    const { placements, fixtures } = designCoworkingZone(zone, spec);
    renderZoneBuiltInFixtures(roomGroup, fixtures);

    placements.sort((a, b) =>
      playDir === "load"
        ? (a.item.load_seq || 0) - (b.item.load_seq || 0)
        : (a.item.unload_seq || 0) - (b.item.unload_seq || 0)
    );
    placements.forEach((p) => orderedVenueItems.push({ ...p, zone, roomGroup }));
  });

  orderedVenueItems.sort((a, b) => {
    if (playDir === "unload") {
      return (a.zone.dock_stop - b.zone.dock_stop) || ((a.item.unload_seq || 0) - (b.item.unload_seq || 0));
    }
    return (b.zone.dock_stop - a.zone.dock_stop) || ((a.item.load_seq || 0) - (b.item.load_seq || 0));
  });

  orderedVenueItems.forEach((p, idx) => {
    const { item: it, localPos: [lx, ly, lz], dims: [gx, gy, gz], rotY, roomGroup, isTuckedBox } = p;
    const hex = itemColorHex(it);
    const pieceObj = buildCoworkingPieceMesh(p, hex, makeBoxFaceTexture);

    pieceObj.position.set(lx, ly, lz);
    pieceObj.rotation.y = rotY || 0;
    pieceObj.userData = { itemId: it.id, isTuckedBox: Boolean(isTuckedBox) };
    pieceObj.traverse((child) => {
      child.userData = { itemId: it.id };
    });

    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(gx + 1.0, gy + 1.0, gz + 1.0)),
      new THREE.LineBasicMaterial({
        color: violatingIds.has(it.id) ? 0xff8080 : 0x0f172a,
        transparent: true,
        opacity: violatingIds.has(it.id) ? 0.95 : 0.0,
      })
    );
    pieceObj.add(edges);
    if (hideUnpackedBoxes && isTuckedBox) {
      pieceObj.visible = false;
    }
    roomGroup.add(pieceObj);

    roomGroup.updateMatrixWorld(true);
    const worldPos = new THREE.Vector3();
    pieceObj.getWorldPosition(worldPos);

    meshEntries.push({
      mesh: pieceObj,
      edges,
      item: it,
      worldPos,
      targetY: ly,
      seqIndex: idx + 1,
      isVenue: true,
      hiddenByBoxToggle: Boolean(hideUnpackedBoxes && isTuckedBox),
    });
  });

  // Eye-level & architectural camera presets calibrated to 1:1 human scale (`Y = 68"` = 5'8" eye height!)
  binTargets.unshift(
    {
      // Standing at human eye height (`68"`) on West Concourse looking East across the 200-ft hall & up at the 92-ft vaults!
      label: "Human Eye-Level (5'8\")",
      center: new THREE.Vector3(240, 210, 0),
      camPos: new THREE.Vector3(-560, 68, 85),
      radius: 420,
      photoZone: "penn_concourse",
    },
    {
      // Standing on the +20 ft Mezzanine Metropolitan Lounge balcony looking out over the entire 31,000 sq ft Train Hall!
      label: "Mezzanine Overlook (+20')",
      center: new THREE.Vector3(-60, 140, -120),
      camPos: new THREE.Vector3(480, 318, 920),
      radius: 520,
      photoZone: "penn_lounge",
    },
    {
      // SOM 57-ft LIRR 33rd St Concourse framing Starbucks, Shake Shack, Duane Reade & Stop 3!
      label: "☕ LIRR Concourse & Starbucks",
      center: new THREE.Vector3(1760, 74, 140),
      camPos: new THREE.Vector3(1280, 92, -165),
      radius: 420,
      photoZone: "penn_bookshop",
    },
    {
      // Moynihan Food Hall, The Irish Exit Bar, Blue Bottle & Magnolia Bakery
      label: "🍸 Food Hall & Irish Exit",
      center: new THREE.Vector3(-420, 64, -960),
      camPos: new THREE.Vector3(-880, 128, -580),
      radius: 420,
      photoZone: "penn_cafe",
    },
    {
      // Close-up of the Keynote Stage & Hacker Pods
      label: "Hackathon Arena",
      center: new THREE.Vector3(40, 42, 0),
      camPos: new THREE.Vector3(-520, 265, 490),
      radius: 440,
      photoZone: "penn_concourse",
    }
  );
}

export function describeRoomCorner(pos, size, zoneDims, isBox = false) {
  if (isBox) return "Backstage Supply Alcove";
  const L = Math.max(1, Number(zoneDims[0] || 180));
  const W = Math.max(1, Number(zoneDims[1] || 120));
  const cx = (pos[0] + 0.5 * size[0]) / L;
  const cy = (pos[1] + 0.5 * size[1]) / W;
  const d = cx < 0.35 ? "Back" : cx > 0.66 ? "Front" : "Center";
  const s = cy < 0.35 ? "Left" : cy > 0.65 ? "Right" : "Mid";
  if (d === "Center" && s === "Mid") return "Center Coworking Floor";
  if (d === "Center") return `${s} Wing`;
  if (s === "Mid") return d === "Back" ? "Back Feature Wall" : "Front Promenade";
  return `${d}-${s} Nook`;
}

export function annotateStagedCorners(plan) {
  if (!plan || !Array.isArray(plan.zones)) return;
  const cornerByPiece = new Map();

  plan.zones.forEach((zone) => {
    const spec = VENUE_ZONE_LAYOUT[zone.zone_id];
    if (!spec) return;
    const { placements } = designCoworkingZone(zone, spec);
    const tally = {};
    placements.forEach(({ item, cornerLabel }) => {
      const pid = item.piece_id || item.id;
      cornerByPiece.set(pid, cornerLabel);
      const realIt = (zone.items || []).find((x) => (x.piece_id || x.id) === pid);
      if (realIt) realIt.dest_corner = cornerLabel;
      tally[cornerLabel] = (tally[cornerLabel] || 0) + 1;
    });
    zone.corners_summary = Object.entries(tally)
      .sort((a, b) => b[1] - a[1])
      .map(([corner, count]) => ({ corner, count }));
  });

  (plan.trucks || []).forEach((t) => {
    const dstMap = new Map();
    (t.items || []).forEach((it) => {
      const pid = it.piece_id || it.id;
      if (cornerByPiece.has(pid)) it.dest_corner = cornerByPiece.get(pid);
      else if (!it.dest_corner) it.dest_corner = "Coworking Floor";

      const zid = it.dest_zone || "penn_concourse";
      if (!dstMap.has(zid)) {
        const zObj = (plan.zones || []).find((z) => z.zone_id === zid) || {};
        dstMap.set(zid, {
          zone_id: zid,
          name: it.dest_zone_name || zObj.name || zid,
          dock_stop: it.dock_stop || zObj.dock_stop || 6,
          item_count: 0,
          corners: {},
          dest_still: zObj.dest_still || null,
        });
      }
      const rec = dstMap.get(zid);
      rec.item_count++;
      rec.corners[it.dest_corner] = (rec.corners[it.dest_corner] || 0) + 1;
    });
    t.dest_zones = Array.from(dstMap.values()).sort((a, b) => a.dock_stop - b.dock_stop);
  });
}

let snapRenderer = null;
export function captureVenueCornerStills(ctxArgs) {
  const { plan } = ctxArgs;
  if (!plan || !Array.isArray(plan.zones)) return {};
  try {
    if (!snapRenderer) {
      const cv = document.createElement("canvas");
      cv.width = 320;
      cv.height = 180;
      snapRenderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, preserveDrawingBuffer: true });
      snapRenderer.outputColorSpace = THREE.SRGBColorSpace;
    }
    const tmpScene = new THREE.Scene();
    tmpScene.background = new THREE.Color(0x131822);
    tmpScene.add(new THREE.AmbientLight(0xffffff, 0.88));
    const dl = new THREE.DirectionalLight(0xffffff, 0.95);
    dl.position.set(600, 1400, 800);
    tmpScene.add(dl);

    const tmpWorld = new THREE.Group();
    tmpScene.add(tmpWorld);
    buildPennVenueScene({
      ...ctxArgs,
      worldGroup: tmpWorld,
      meshEntries: [],
      binTargets: [],
      showRoof: true,
      hideUnpackedBoxes: true,
    });

    const cam = new THREE.PerspectiveCamera(50, 16 / 9, 4, 9000);
    const out = {};

    plan.zones.forEach((zone) => {
      const spec = VENUE_ZONE_LAYOUT[zone.zone_id];
      if (!spec) return;
      const [L, W] = spec.vDims;
      const baseY = spec.floorY || 0;
      if (zone.zone_type === "concourse") {
        cam.position.set(-480, 145, 220);
        cam.lookAt(180, 95, -10);
      } else {
        const dirZ = spec.cz < 0 ? 1 : -1;
        cam.position.set(spec.cx + W * 0.22, baseY + 108, spec.cz + dirZ * (L * 0.56));
        cam.lookAt(spec.cx - W * 0.04, baseY + 30, spec.cz - dirZ * (L * 0.05));
      }
      snapRenderer.render(tmpScene, cam);
      out[zone.zone_id] = snapRenderer.domElement.toDataURL("image/jpeg", 0.84);
    });
    return out;
  } catch (e) {
    console.warn("Corner snapshot fallback skipped:", e);
    return {};
  }
}

/**
 * Verified Real Photographs of Moynihan Train Hall & Penn Station LIRR Concourse
 * (Wikimedia Commons CC-licensed architectural photography — zero mockups!).
 */
export const REAL_HALL_PHOTOS = [
  {
    id: "moynihan_atrium",
    zone_id: "penn_concourse",
    stop: 6,
    title: "Moynihan Boarding Concourse (200×150 ft · 92-ft Skylight)",
    tenants: "Tracks 5–16 escalators, suspended central clock, 31,000 sq ft travertine floor",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Moynihan_Train_Hall_interior,_Dec_27_2022.jpg?width=1024",
    credit: "Wikimedia Commons · Moynihan Train Hall Interior",
  },
  {
    id: "lirr_concourse",
    zone_id: "penn_bookshop",
    stop: 3,
    title: "Renovated 57-ft LIRR 33rd St Concourse (Starbucks, Shake Shack, Duane Reade)",
    tenants: "Starbucks, Shake Shack, Dunkin', Duane Reade, Gotham News & LIRR Tracks 17–21",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Penn_Station_LIRR_concourse,_renovated_high_ceiling.jpg?width=1024",
    credit: "Wikimedia Commons · SOM 57-ft LIRR Concourse",
  },
  {
    id: "lirr_led_ceiling",
    zone_id: "penn_bookshop",
    stop: 3,
    title: "LIRR Concourse 18-ft Luminous Coffered Ceiling",
    tenants: "Widened from 30 ft to 57 ft in 2023 with full-height retail storefronts",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/LIRR_concourse_2023_renovation.png?width=1024",
    credit: "Wikimedia Commons · MTA LIRR Concourse Renovation",
  },
  {
    id: "moynihan_blue_bottle",
    zone_id: "penn_cafe",
    stop: 2,
    title: "Blue Bottle Coffee — Moynihan North Concourse",
    tenants: "Alongside Starbucks, Magnolia Bakery, H&H Bagels & The Irish Exit bar",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Blue_Bottle_Coffee_Moynihan_Station_NY.jpg?width=960",
    credit: "Wikimedia Commons · Blue Bottle Coffee Moynihan",
  },
  {
    id: "moynihan_magnolia",
    zone_id: "penn_cafe",
    stop: 2,
    title: "Magnolia Bakery & Moynihan Food Hall Colonnade",
    tenants: "North 33rd St Food Hall wing (The Irish Exit, Chopt, Jacob's Pickles, Alidoro)",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Magnolia_Bakery_at_Moynihan_Train_Hall_during_COVID_pandemic_2021.jpg?width=960",
    credit: "Wikimedia Commons · Magnolia Bakery Moynihan",
  },
  {
    id: "mezzanine_lounge",
    zone_id: "penn_lounge",
    stop: 5,
    title: "Amtrak Metropolitan Lounge (+20 ft Mezzanine Balcony)",
    tenants: "Upper-level terrace lounge overlooking the 92-ft skylit Moynihan Concourse",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Amtrak_Metropolitan_Lounge_New_York_2026b.jpg?width=1024",
    credit: "Wikimedia Commons · Amtrak Metropolitan Lounge NYC",
  },
  {
    id: "amtrak_31st",
    zone_id: "penn_tech_hub",
    stop: 4,
    title: "South 31st St Concourse — Amtrak Ticketing & Red Cap",
    tenants: "Amtrak Customer Service, Red Cap Baggage & Ticketed Waiting Room",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Amtrak_Customer_Service_Moynihan_Train_Hall_NYC.jpg?width=960",
    credit: "Wikimedia Commons · Amtrak Customer Service Moynihan",
  },
  {
    id: "moynihan_trusses",
    zone_id: "penn_concourse",
    stop: 6,
    title: "Restored 1912 Riveted Steel Trusses & Four Catenary Vaults",
    tenants: "Three 150-ft steel trusses spaced 50 ft o.c. supporting 500+ tons of glass",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/Moynihan_Train_Hall_interior_and_roof,_Apr_18_2022.jpg?width=1024",
    credit: "Wikimedia Commons · Moynihan Roof & Trusses",
  },
  {
    id: "west_end_concourse",
    zone_id: "penn_merch_kiosk",
    stop: 1,
    title: "West End Concourse & 9th Ave Retail Entrance",
    tenants: "Malin+Goetz, Moleskine, Rains & LIRR West End track access",
    url: "https://commons.wikimedia.org/wiki/Special:FilePath/West_End_Concourse.jpg?width=960",
    credit: "Wikimedia Commons · West End Concourse",
  },
];

/**
 * Keyless Embedded Google 360° Street View & Interactive Indoor Station Map URLs.
 */
export const REAL_HALL_MAP_VIEWS = [
  {
    id: "indoor_map",
    label: "🗺️ Indoor Floor Map",
    caption: "Google Maps Indoor Directory (Starbucks, Shake Shack, Food Hall, Lounge & Tracks)",
    iframeUrl: "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d1511.107!2d-73.99575!3d40.75135!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x89c259ae15c2ec85%3A0x6b8f3a3885d97f26!2sMoynihan%20Train%20Hall!5e0!3m2!1sen!2sus!4v1710000000000!5m2!1sen!2sus",
    externalUrl: "https://www.google.com/maps/place/Moynihan+Train+Hall/@40.75148,-73.99605,19z",
  },
  {
    id: "sv_farley_8th",
    label: "🌐 360° Farley / 8th Ave",
    caption: "Interactive 360° Google Street View — Historic James A. Farley Steps & Colonnade",
    iframeUrl: "https://maps.google.com/maps?layer=c&cbll=40.75112,-73.99492&cbp=12,248,0,0,0&output=svembed",
    externalUrl: "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=40.75148,-73.99605",
  },
  {
    id: "sv_31st_dock",
    label: "🌐 360° 31st St Entrance",
    caption: "Interactive 360° Google Street View — 31st St Midblock Glass Canopy & Loading Corridor",
    iframeUrl: "https://maps.google.com/maps?layer=c&cbll=40.75086,-73.99638&cbp=12,25,0,0,0&output=svembed",
    externalUrl: "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=40.75086,-73.99638",
  },
  {
    id: "sv_lirr_7th",
    label: "🌐 360° LIRR Gateway",
    caption: "Interactive 360° Google Street View — LIRR 33rd St & 7th Ave East End Glass Canopy",
    iframeUrl: "https://maps.google.com/maps?layer=c&cbll=40.75038,-73.99138&cbp=12,292,0,0,0&output=svembed",
    externalUrl: "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=40.75058,-73.99265",
  },
];

export function getRealPhotoForZone(zoneId) {
  return REAL_HALL_PHOTOS.find((p) => p.zone_id === zoneId) || REAL_HALL_PHOTOS[0];
}
