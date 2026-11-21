// 3D Architectural NY Penn Station / Moynihan Train Hall Venue Builder for Pack It Up.
// Renders an authentic spatial station layout (Main Concourse, vaulted skylight roof,
// colonnades, LIRR/Amtrak departure board, Track 17-20 stairs, 31st St Loading Dock +
// docked U-Haul, and 5 surrounding glazed storefronts with real doorway cutouts)
// populated with procedural 3D furniture & QR-labelled moving boxes.

import * as THREE from "three";

const STOP_HEX = {
  1: "#f97316",
  2: "#eab308",
  3: "#10b981",
  4: "#3b82f6",
  5: "#8b5cf6",
  6: "#06b6d4",
};

/**
 * Spatial placement of every Penn Station zone inside the station footprint (1 unit = 1 inch).
 * `rotY`: rotation from local zone (+X depth, +Z width) into world coordinates so each
 * storefront's doorway (`local +X = +L/2` face) opens directly onto the Central Concourse!
 *   - In local zone coords, doorway is on `+X` (`localX = +L/2`).
 *   - North wing (`Z < 0`) wants doorway facing `+Z` (South into concourse) -> `rotY = -Math.PI / 2`!
 *     Wait: in Three.js right-handed Y-up: rotating `(1, 0, 0)` by `-PI/2` around Y gives `(0, 0, +1)` (+Z)!
 *   - South wing (`Z > 0`) wants doorway facing `-Z` (North into concourse) -> `rotY = +Math.PI / 2`!
 *     Rotating `(1, 0, 0)` by `+PI/2` around Y gives `(0, 0, -1)` (-Z)!
 *   - Concourse (`Stop 6`) aligns along hall spine (`rotY = 0`), receiving from `-X` loading dock.
 */
export const VENUE_ZONE_LAYOUT = {
  penn_merch_kiosk: {
    // Local dims [120, 84, 90]: rotated -90deg -> world X span = 84, world Z depth = 120.
    // Front doorway at world Z = -148 -> center Z = -148 - 120/2 = -208.
    cx: -195,
    cz: -208,
    rotY: -Math.PI / 2,
    floorColor: 0x332924,
    accentHex: "#f97316",
    signTitle: "STOP 1 · POP-UP MERCH",
    dockPath: [[-330, -40], [-235, -40], [-195, -148]],
  },
  penn_cafe: {
    // Local dims [168, 120, 96]: rotated -90deg -> world X span = 120, world Z depth = 168.
    // Front doorway at world Z = -148 -> center Z = -148 - 168/2 = -232.
    cx: -55,
    cz: -232,
    rotY: -Math.PI / 2,
    floorColor: 0x362b22,
    accentHex: "#eab308",
    signTitle: "STOP 2 · TRACKSIDE CAFÉ",
    dockPath: [[-330, -24], [-110, -24], [-55, -148]],
  },
  penn_bookshop: {
    // Local dims [180, 132, 96]: rotated -90deg -> world X span = 132, world Z depth = 180.
    // Front doorway at world Z = -148 -> center Z = -148 - 180/2 = -238.
    cx: 115,
    cz: -238,
    rotY: -Math.PI / 2,
    floorColor: 0x1e2f2d,
    accentHex: "#10b981",
    signTitle: "STOP 3 · HUDSON BOOKS",
    dockPath: [[-330, -8], [65, -8], [115, -148]],
  },
  penn_tech_hub: {
    // Local dims [216, 156, 102]: rotated +90deg -> world X span = 156, world Z depth = 216.
    // Front doorway at world Z = +148 -> center Z = +148 + 216/2 = +256.
    cx: -115,
    cz: 256,
    rotY: Math.PI / 2,
    floorColor: 0x1e2838,
    accentHex: "#3b82f6",
    signTitle: "STOP 4 · MOYNIHAN TECH HUB",
    dockPath: [[-330, 18], [-155, 18], [-115, 148]],
  },
  penn_lounge: {
    // Local dims [240, 180, 108]: rotated +90deg -> world X span = 180, world Z depth = 240.
    // Front doorway at world Z = +148 -> center Z = +148 + 240/2 = +268.
    cx: 105,
    cz: 268,
    rotY: Math.PI / 2,
    floorColor: 0x2d2436,
    accentHex: "#8b5cf6",
    signTitle: "STOP 5 · TICKETED LOUNGE",
    dockPath: [[-330, 34], [55, 34], [105, 148]],
  },
  penn_concourse: {
    // Local dims [420, 260, 144]: central grand hall, X = -210..+210, Z = -130..+130.
    cx: 0,
    cz: 0,
    rotY: 0,
    floorColor: 0x2c323d,
    accentHex: "#06b6d4",
    signTitle: "STOP 6 · MAIN LIRR CONCOURSE",
    dockPath: [[-330, 0], [-180, 0]],
  },
};

function makeSignTexture(title, subtitle, accentHex = "#3b82f6", darkBg = "#0f172a") {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 112;
  const ctx = c.getContext("2d");

  ctx.fillStyle = darkBg;
  ctx.fillRect(0, 0, 512, 112);

  ctx.fillStyle = accentHex;
  ctx.fillRect(0, 0, 16, 112);
  ctx.fillRect(0, 104, 512, 8);

  ctx.fillStyle = "#f8fafc";
  ctx.font = "bold 30px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(title, 32, 52);

  ctx.fillStyle = "#94a3b8";
  ctx.font = "600 21px system-ui, -apple-system, sans-serif";
  ctx.fillText(subtitle, 32, 86);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeDepartureBoardTexture() {
  const c = document.createElement("canvas");
  c.width = 768;
  c.height = 240;
  const ctx = c.getContext("2d");

  ctx.fillStyle = "#090d16";
  ctx.fillRect(0, 0, 768, 240);
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 6;
  ctx.strokeRect(3, 3, 762, 234);

  // Top header bar
  ctx.fillStyle = "#1d4ed8";
  ctx.fillRect(6, 6, 756, 48);
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 25px system-ui, -apple-system, sans-serif";
  ctx.fillText("NY PENN STATION · MOYNIHAN & LIRR DEPARTURES", 24, 39);

  const rows = [
    ["12:55", "LIRR · PORT WASHINGTON", "TRK 18", "BOARDING", "#4ade80"],
    ["13:02", "AMTRAK ACELA 2155 · WASH DC", "TRK 12", "ON TIME", "#fbbf24"],
    ["13:08", "LIRR · RONKONKOMA EXPRESS", "TRK 20", "ON TIME", "#fbbf24"],
    ["13:15", "NJT · TRENTON / NEWARK", "TRK 09", "ON TIME", "#fbbf24"],
  ];
  ctx.font = "bold 21px ui-monospace, SFMono-Regular, Menlo, monospace";
  rows.forEach(([time, dest, trk, status, col], i) => {
    const y = 90 + i * 40;
    ctx.fillStyle = i % 2 === 0 ? "rgba(255,255,255,0.03)" : "transparent";
    ctx.fillRect(10, y - 26, 748, 34);
    ctx.fillStyle = "#e2e8f0";
    ctx.fillText(time, 24, y);
    ctx.fillStyle = "#f8fafc";
    ctx.fillText(dest, 112, y);
    ctx.fillStyle = "#60a5fa";
    ctx.fillText(trk, 520, y);
    ctx.fillStyle = col;
    ctx.fillText(status, 628, y);
  });

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeClockTexture() {
  const c = document.createElement("canvas");
  c.width = 128;
  c.height = 128;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#0f172a";
  ctx.beginPath();
  ctx.arc(64, 64, 60, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#eab308";
  ctx.lineWidth = 7;
  ctx.stroke();

  ctx.strokeStyle = "#f8fafc";
  ctx.lineWidth = 3;
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(64 + Math.cos(a) * 44, 64 + Math.sin(a) * 44);
    ctx.lineTo(64 + Math.cos(a) * 52, 64 + Math.sin(a) * 52);
    ctx.stroke();
  }
  // Hands at ~1:00 hackathon join time
  ctx.lineWidth = 5;
  ctx.beginPath(); ctx.moveTo(64, 64); ctx.lineTo(80, 36); ctx.stroke();
  ctx.lineWidth = 3.5;
  ctx.beginPath(); ctx.moveTo(64, 64); ctx.lineTo(64, 22); ctx.stroke();

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * Compute natural architectural staging coordinates `[sx, sy, sz]` and `[sdx, sdy, sdz]`
 * inside a Penn Station zone `[L, W, H]` so rooms look like furnished venues rather than
 * corner-packed storage bins, while guaranteeing every item stays strictly inside `[0..L, 0..W]`.
 */
function stageZoneItemsForVenue(zone) {
  const [L, W, H] = zone.dims_in;
  const [doorW] = zone.door_in || [48, 84];
  const items = (zone.items || []).map((it) => ({ ...it }));
  if (!items.length) return [];

  const boxes = items.filter((i) => i.is_box);
  const furn = items.filter((i) => !i.is_box);

  const staged = [];

  // 1. Stage moving boxes neatly along the back wall (local x near -L/2 -> solver x near 0..26)
  let bxCursorY = 8;
  let stackZ = 0;
  let rowX = 6;
  boxes.forEach((b) => {
    const [dx, dy, dz] = b.size_in;
    if (stackZ + dz > Math.min(H - 6, 54) || stackZ >= 36) {
      stackZ = 0;
      bxCursorY += dy + 4;
    }
    if (bxCursorY + dy > W - 8) {
      bxCursorY = 8;
      rowX += dx + 6;
    }
    const px = Math.min(L - dx - 4, rowX);
    const py = Math.min(W - dy - 4, bxCursorY);
    staged.push({
      item: b,
      pos: [px, py, stackZ],
      size: [dx, dy, dz],
      unfoldedTable: false,
    });
    stackZ += dz;
  });

  // 2. Stage furniture across the main room floor with walking aisles & doorway clearance
  const startX = boxes.length ? Math.min(L * 0.45, rowX + 28) : 14;
  const maxFrontX = L - 16; // leave clearance inside the front doorway (`x = L`)
  const marginY = 10;
  const aisleGapX = zone.zone_type === "concourse" ? 18 : 12;
  const aisleGapY = zone.zone_type === "concourse" ? 14 : 10;

  let curX = startX;
  let curY = marginY;
  let rowMaxDx = 0;

  // Sort furniture so anchor tables/sofas/shelving place cleanly in architectural groups
  const furnOrdered = furn.slice().sort((a, b) =>
    String(a.catalog_id).localeCompare(String(b.catalog_id)) || (b.size_in[0] * b.size_in[1] - a.size_in[0] * a.size_in[1])
  );

  furnOrdered.forEach((f) => {
    let [dx, dy, dz] = f.size_in;
    let unfoldedTable = false;

    // Unfold flat-packed folding/banquet/standing tables on the venue floor so they look set up!
    const lbl = `${f.catalog_id || ""} ${f.label || ""}`.toLowerCase();
    if ((lbl.includes("table") || lbl.includes("desk")) && dz <= 8 && H >= 36) {
      dz = 30;
      unfoldedTable = true;
    }

    // Keep clear of front doorway center `[L - 28 .. L, W/2 - doorW/2 .. W/2 + doorW/2]`
    if (curY + dy > W - marginY) {
      curY = marginY;
      curX += Math.max(20, rowMaxDx) + aisleGapX;
      rowMaxDx = 0;
    }

    if (curX + dx <= maxFrontX && curY + dy <= W - marginY) {
      // Avoid blocking doorway throat right at the front
      const inDoorThroat = curX + dx > L - 30 && curY + dy > W / 2 - doorW / 2 - 8 && curY < W / 2 + doorW / 2 + 8;
      if (!inDoorThroat) {
        staged.push({
          item: f,
          pos: [curX, curY, 0],
          size: [dx, dy, dz],
          unfoldedTable,
        });
        rowMaxDx = Math.max(rowMaxDx, dx);
        curY += dy + aisleGapY;
        return;
      }
    }

    // Fallback: use exact solver 3D coordinates inside the store so nothing ever overflows walls
    staged.push({
      item: f,
      pos: f.pos_in.slice(),
      size: f.size_in.slice(),
      unfoldedTable: false,
    });
  });

  return staged;
}

/**
 * Build a recognizable 3D procedural furniture/box object inside bounding box `(gx, gy, gz)`
 * centered at `(0, 0, 0)` where `gy` is vertical height.
 */
function buildProceduralPiece(it, gx, gy, gz, baseHex, makeBoxFaceTexture, unfoldedTable = false) {
  const root = new THREE.Group();
  const key = `${it.catalog_id || ""} ${it.label || ""}`.toLowerCase();

  const mainMat = new THREE.MeshStandardMaterial({ color: baseHex, roughness: 0.52, metalness: 0.1 });
  const darkMetal = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.45, metalness: 0.55 });
  const woodDark = new THREE.MeshStandardMaterial({ color: 0x5c4033, roughness: 0.65, metalness: 0.05 });
  const screenGlow = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, emissive: 0x1e293b, roughness: 0.25 });

  if (it.is_box) {
    const geo = new THREE.BoxGeometry(gx, gy, gz);
    const qrTex = makeBoxFaceTexture(it, baseHex);
    const sideMat = new THREE.MeshStandardMaterial({ color: baseHex, roughness: 0.68, metalness: 0.04 });
    const qrMat = new THREE.MeshStandardMaterial({ map: qrTex, roughness: 0.55, metalness: 0.04 });
    const m = new THREE.Mesh(geo, [qrMat, qrMat, sideMat, sideMat, sideMat, sideMat]);
    root.add(m);
    return root;
  }

  // 1. Tables & Desks (tabletop + 4 legs)
  if ((key.includes("table") || key.includes("desk")) && (gy >= 15 || unfoldedTable)) {
    const topThick = Math.min(2.4, gy * 0.14);
    if (key.includes("round")) {
      const r = Math.min(gx, gz) * 0.49;
      const top = new THREE.Mesh(new THREE.CylinderGeometry(r, r, topThick, 24), mainMat);
      top.position.y = gy / 2 - topThick / 2;
      root.add(top);
    } else {
      const top = new THREE.Mesh(new THREE.BoxGeometry(gx, topThick, gz), mainMat);
      top.position.y = gy / 2 - topThick / 2;
      root.add(top);
    }
    const legH = gy - topThick;
    const legW = Math.max(1.2, Math.min(2.2, Math.min(gx, gz) * 0.06));
    const legGeo = new THREE.BoxGeometry(legW, legH, legW);
    const ox = gx * 0.43, oz = gz * 0.41;
    [[-ox, -oz], [ox, -oz], [-ox, oz], [ox, oz]].forEach(([lx, lz]) => {
      const leg = new THREE.Mesh(legGeo, darkMetal);
      leg.position.set(lx, -topThick / 2, lz);
      root.add(leg);
    });
    return root;
  }

  // 2. Sofas, Loveseats, Sectionals & Armchairs (seat base + backrest + armrests)
  if (key.includes("sofa") || key.includes("loveseat") || key.includes("sectional") || key.includes("armchair") || key.includes("recliner") || key.includes("single seat") || key.includes("three-seat")) {
    const seatH = gy * 0.42;
    const seat = new THREE.Mesh(new THREE.BoxGeometry(gx, seatH, gz * 0.88), mainMat);
    seat.position.set(0, -gy / 2 + seatH / 2, gz * 0.05);
    root.add(seat);

    const backThick = Math.max(4, gz * 0.24);
    const back = new THREE.Mesh(new THREE.BoxGeometry(gx, gy * 0.92, backThick), mainMat);
    back.position.set(0, -gy * 0.04, -gz / 2 + backThick / 2);
    root.add(back);

    const armW = Math.max(3.5, gx * 0.12);
    const armH = gy * 0.68;
    const armGeo = new THREE.BoxGeometry(armW, armH, gz * 0.92);
    [-gx / 2 + armW / 2, gx / 2 - armW / 2].forEach((ax) => {
      const arm = new THREE.Mesh(armGeo, mainMat);
      arm.position.set(ax, -gy / 2 + armH / 2, 0);
      root.add(arm);
    });
    return root;
  }

  // 3. Chair Stacks & Individual Chairs / Stools
  if (key.includes("chair") || key.includes("stool")) {
    if ((it.stack_count && it.stack_count > 1) || key.includes("stack")) {
      const count = Math.min(8, Math.max(3, it.stack_count || 6));
      const legGeo = new THREE.BoxGeometry(1.4, gy * 0.65, 1.4);
      const ox = gx * 0.4, oz = gz * 0.4;
      [[-ox, -oz], [ox, -oz], [-ox, oz], [ox, oz]].forEach(([lx, lz]) => {
        const l = new THREE.Mesh(legGeo, darkMetal);
        l.position.set(lx, -gy * 0.17, lz);
        root.add(l);
      });
      for (let k = 0; k < count; k++) {
        const yOff = -gy * 0.12 + (k / count) * (gy * 0.52);
        const seat = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.88, 1.8, gz * 0.85), mainMat);
        seat.position.set(0, yOff, 0);
        root.add(seat);
      }
      const topBack = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.86, gy * 0.28, 2.0), mainMat);
      topBack.position.set(0, gy * 0.36, -gz * 0.4);
      root.add(topBack);
      return root;
    }

    const seatY = -gy * 0.05;
    const seat = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.88, 2.2, gz * 0.86), mainMat);
    seat.position.set(0, seatY, 0);
    root.add(seat);
    const legH = gy / 2 + seatY;
    const legGeo = new THREE.BoxGeometry(1.4, legH, 1.4);
    const ox = gx * 0.38, oz = gz * 0.38;
    [[-ox, -oz], [ox, -oz], [-ox, oz], [ox, oz]].forEach(([lx, lz]) => {
      const leg = new THREE.Mesh(legGeo, darkMetal);
      leg.position.set(lx, -gy / 2 + legH / 2, lz);
      root.add(leg);
    });
    if (!key.includes("stool")) {
      const back = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.84, gy * 0.48, 2.0), mainMat);
      back.position.set(0, gy * 0.24, -gz * 0.39);
      root.add(back);
    }
    return root;
  }

  // 4. Bookshelves & Shelving Units (side uprights + horizontal shelves)
  if (key.includes("shelf") || key.includes("shelving") || key.includes("bookcase")) {
    const sideW = Math.max(1.5, gx * 0.05);
    const sideGeo = new THREE.BoxGeometry(sideW, gy, gz);
    [-gx / 2 + sideW / 2, gx / 2 - sideW / 2].forEach((sx) => {
      const s = new THREE.Mesh(sideGeo, mainMat);
      s.position.set(sx, 0, 0);
      root.add(s);
    });
    const tiers = Math.max(3, Math.min(6, Math.round(gy / 16)));
    const shelfGeo = new THREE.BoxGeometry(gx - sideW, 1.5, gz * 0.94);
    for (let t = 0; t <= tiers; t++) {
      const sy = -gy / 2 + 1 + (t / tiers) * (gy - 2);
      const sh = new THREE.Mesh(shelfGeo, mainMat);
      sh.position.set(0, sy, 0);
      root.add(sh);
    }
    return root;
  }

  // 5. Whiteboards, Monitors, TVs & Projector Screens
  if (key.includes("whiteboard") || key.includes("monitor") || key.includes("tv") || key.includes("screen")) {
    const boardH = gy * 0.62;
    const frame = new THREE.Mesh(new THREE.BoxGeometry(gx, boardH, Math.min(4, gz * 0.35)), darkMetal);
    frame.position.set(0, gy * 0.16, 0);
    root.add(frame);
    const panel = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.93, boardH * 0.88, Math.min(4.6, gz * 0.38)), screenGlow);
    panel.position.set(0, gy * 0.16, 0);
    root.add(panel);
    // Stand legs
    const postGeo = new THREE.BoxGeometry(2.0, gy * 0.85, 2.0);
    [-gx * 0.36, gx * 0.36].forEach((px) => {
      const post = new THREE.Mesh(postGeo, darkMetal);
      post.position.set(px, -gy * 0.07, 0);
      root.add(post);
    });
    const footGeo = new THREE.BoxGeometry(3.0, 2.0, gz * 0.92);
    [-gx * 0.36, gx * 0.36].forEach((px) => {
      const ft = new THREE.Mesh(footGeo, darkMetal);
      ft.position.set(px, -gy / 2 + 1, 0);
      root.add(ft);
    });
    return root;
  }

  // 6. Upright Piano
  if (key.includes("piano")) {
    const body = new THREE.Mesh(new THREE.BoxGeometry(gx, gy, gz * 0.68), woodDark);
    body.position.set(0, 0, -gz * 0.14);
    root.add(body);
    const keybed = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.96, 5, gz * 0.42), mainMat);
    keybed.position.set(0, -gy * 0.06, gz * 0.22);
    root.add(keybed);
    const keys = new THREE.Mesh(new THREE.BoxGeometry(gx * 0.88, 1.6, gz * 0.26), screenGlow);
    keys.position.set(0, -gy * 0.06 + 2.8, gz * 0.26);
    root.add(keys);
    return root;
  }

  // Default solid furniture block (sideboards, cabinets, podiums, appliances)
  const fallback = new THREE.Mesh(new THREE.BoxGeometry(gx, gy, gz), mainMat);
  root.add(fallback);
  return root;
}

/**
 * Build the complete 3D NY Penn Station / Moynihan Venue scene into `worldGroup`.
 * Populates `meshEntries` and `binTargets` in the exact shape `index.html` expects!
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
  fmt,
}) {
  const archGroup = new THREE.Group();
  worldGroup.add(archGroup);

  // 1. Grand Station Plinth & Travertine Floor Slab
  const baseSlab = new THREE.Mesh(
    new THREE.BoxGeometry(920, 6, 720),
    new THREE.MeshStandardMaterial({ color: 0x1b2029, roughness: 0.92, metalness: 0.05 })
  );
  baseSlab.position.set(-20, -3.2, 20);
  archGroup.add(baseSlab);

  // Main Concourse polished stone floor + subtle architectural grid
  const concourseFloor = new THREE.Mesh(
    new THREE.PlaneGeometry(540, 292),
    new THREE.MeshStandardMaterial({ color: 0x2b3340, roughness: 0.72, metalness: 0.08 })
  );
  concourseFloor.rotation.x = -Math.PI / 2;
  concourseFloor.position.set(-20, 0.05, 0);
  archGroup.add(concourseFloor);

  const grid = new THREE.GridHelper(540, 18, 0x475569, 0x334155);
  grid.scale.z = 292 / 540;
  grid.position.set(-20, 0.12, 0);
  grid.material.transparent = true;
  grid.material.opacity = 0.28;
  archGroup.add(grid);

  // Brass concourse center medallion
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(22, 26, 36),
    new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.35, metalness: 0.7, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(0, 0.22, 0);
  archGroup.add(ring);

  // 2. North & South Structural Colonnades (stone/steel columns + mezzanine box beams)
  const colMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.5, metalness: 0.35 });
  const plinthMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.65, metalness: 0.2 });
  const colXs = [-250, -145, -40, 65, 170, 250];
  [-142, 142].forEach((cz) => {
    colXs.forEach((cx) => {
      const plinth = new THREE.Mesh(new THREE.BoxGeometry(16, 18, 16), plinthMat);
      plinth.position.set(cx, 9, cz);
      archGroup.add(plinth);

      const shaft = new THREE.Mesh(new THREE.CylinderGeometry(5.5, 6.2, 134, 16), colMat);
      shaft.position.set(cx, 18 + 67, cz);
      archGroup.add(shaft);

      const cap = new THREE.Mesh(new THREE.BoxGeometry(15, 8, 15), plinthMat);
      cap.position.set(cx, 154, cz);
      archGroup.add(cap);
    });

    // Longitudinal mezzanine steel box beam
    const beam = new THREE.Mesh(new THREE.BoxGeometry(540, 10, 10), plinthMat);
    beam.position.set(0, 160, cz);
    archGroup.add(beam);
  });

  // 3. Moynihan Arched Steel-and-Glass Barrel Vault Skylight (optional cutaway via `showRoof`)
  if (showRoof) {
    const vaultGroup = new THREE.Group();
    const trussMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.38, metalness: 0.65 });
    const archSpanHalf = 142;
    const archBaseY = 164;
    const archRise = 74;

    colXs.forEach((cx) => {
      const pts = [];
      const segs = 24;
      for (let s = 0; s <= segs; s++) {
        const t = -1 + (2 * s) / segs; // -1 .. +1 across Z
        const z = t * archSpanHalf;
        const y = archBaseY + archRise * (1 - t * t);
        pts.push(new THREE.Vector3(cx, y, z));
      }
      const curve = new THREE.CatmullRomCurve3(pts);
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 2.2, 8, false), trussMat);
      vaultGroup.add(tube);
    });

    // Longitudinal skylight purlins + subtle translucent glass canopy
    [-0.75, -0.4, 0, 0.4, 0.75].forEach((t) => {
      const z = t * archSpanHalf;
      const y = archBaseY + archRise * (1 - t * t);
      const purlin = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.3, 510, 8), trussMat);
      purlin.rotation.z = Math.PI / 2;
      purlin.position.set(0, y, z);
      vaultGroup.add(purlin);
    });

    // Translucent skylight glass panels (depthWrite: false so picking/visibility from top stays crystal clear)
    const skyShapePts = [];
    for (let s = 0; s <= 24; s++) {
      const t = -1 + (2 * s) / 24;
      skyShapePts.push(new THREE.Vector3(0, archBaseY + archRise * (1 - t * t), t * archSpanHalf));
    }
    const skyCurve = new THREE.CatmullRomCurve3(skyShapePts);
    const skyFrames = skyCurve.getPoints(24);
    const skyGeo = new THREE.BufferGeometry();
    const verts = [];
    for (let i = 0; i < skyFrames.length - 1; i++) {
      const p1 = skyFrames[i], p2 = skyFrames[i + 1];
      verts.push(
        -250, p1.y, p1.z, 250, p1.y, p1.z, 250, p2.y, p2.z,
        -250, p1.y, p1.z, 250, p2.y, p2.z, -250, p2.y, p2.z
      );
    }
    skyGeo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    skyGeo.computeVertexNormals();
    const skyMesh = new THREE.Mesh(
      skyGeo,
      new THREE.MeshPhysicalMaterial({
        color: 0xbae6fd,
        transparent: true,
        opacity: 0.09,
        roughness: 0.15,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    vaultGroup.add(skyMesh);

    // Suspended Moynihan Station Clock at center arch
    const clockTex = makeClockTexture();
    const clockMat = new THREE.MeshBasicMaterial({ map: clockTex });
    const clockBody = new THREE.Mesh(
      new THREE.CylinderGeometry(18, 18, 5, 28),
      [new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.7, roughness: 0.3 }), clockMat, clockMat]
    );
    clockBody.rotation.z = Math.PI / 2;
    clockBody.position.set(0, 198, 0);
    vaultGroup.add(clockBody);

    const hanger = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 36, 8), trussMat);
    hanger.position.set(0, 220, 0);
    vaultGroup.add(hanger);

    archGroup.add(vaultGroup);
  }

  // 4. East End (`X = +265..+365`): LIRR/Amtrak Departure Board + Track 17–20 Platform Stairs
  const boardTex = makeDepartureBoardTexture();
  const boardMesh = new THREE.Mesh(
    new THREE.BoxGeometry(6, 62, 206),
    [
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshBasicMaterial({ map: boardTex }), // -X face looking West into the concourse!
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
      new THREE.MeshStandardMaterial({ color: 0x0f172a }),
    ]
  );
  boardMesh.position.set(264, 126, 0);
  archGroup.add(boardMesh);

  // Two Track Stairwell Portals descending to platforms (`TRACK 17 · 18` & `TRACK 19 · 20`)
  [[-66, "TRACKS 17 · 18"], [66, "TRACKS 19 · 20"]].forEach(([sz, label]) => {
    const well = new THREE.Group();
    well.position.set(296, 0, sz);

    // Safety glass balustrades around stairwell
    const railMat = new THREE.MeshPhysicalMaterial({ color: 0x93c5fd, transparent: true, opacity: 0.28, roughness: 0.2, side: THREE.DoubleSide });
    [-26, 26].forEach((rz) => {
      const glass = new THREE.Mesh(new THREE.BoxGeometry(74, 34, 1.5), railMat);
      glass.position.set(0, 17, rz);
      well.add(glass);
    });

    // Descending stair treads + yellow ADA tactile strip
    const yellowStrip = new THREE.Mesh(
      new THREE.BoxGeometry(6, 0.6, 52),
      new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.6 })
    );
    yellowStrip.position.set(-39, 0.3, 0);
    well.add(yellowStrip);

    const stepMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.8 });
    for (let st = 0; st < 6; st++) {
      const tread = new THREE.Mesh(new THREE.BoxGeometry(11, 2.5, 50), stepMat);
      tread.position.set(-30 + st * 11, -1.5 - st * 3.2, 0);
      well.add(tread);
    }

    const trkTag = makeTextSprite(`↓ ${label}`, "rgba(29, 78, 216, 0.92)", "#ffffff", 0.68);
    trkTag.position.set(-28, 46, 0);
    well.add(trkTag);
    archGroup.add(well);
  });

  // 5. West End (`X = -465..-270`): 31st St Loading Dock + Docked Arrival U-Haul
  const dockGroup = new THREE.Group();
  const dockApron = new THREE.Mesh(
    new THREE.BoxGeometry(110, 4, 240),
    new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.88 })
  );
  dockApron.position.set(-325, -1.5, 0);
  dockGroup.add(dockApron);

  // Yellow safety bollards flanking the freight portal
  const bollardMat = new THREE.MeshStandardMaterial({ color: 0xeab308, roughness: 0.4, metalness: 0.3 });
  [-68, 68].forEach((bz) => {
    const bol = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 3.5, 38, 12), bollardMat);
    bol.position.set(-280, 19, bz);
    dockGroup.add(bol);
  });

  // Scale docked U-Haul truck backed up to the West Loading Dock (`X = -465..-365`)
  const dockBox = new THREE.Mesh(
    new THREE.BoxGeometry(128, 86, 92),
    new THREE.MeshStandardMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.25, roughness: 0.5 })
  );
  dockBox.position.set(-446, 46, 0);
  dockGroup.add(dockBox);
  const dockWire = new THREE.LineSegments(
    new THREE.EdgesGeometry(dockBox.geometry),
    new THREE.LineBasicMaterial({ color: 0xf97316, transparent: true, opacity: 0.75 })
  );
  dockWire.position.copy(dockBox.position);
  dockGroup.add(dockWire);

  // Orange U-Haul stripe
  const stripe = new THREE.Mesh(
    new THREE.BoxGeometry(129, 10, 93),
    new THREE.MeshStandardMaterial({ color: 0xf97316, roughness: 0.5 })
  );
  stripe.position.set(-446, 28, 0);
  dockGroup.add(stripe);

  const dockSign = makeTextSprite("31st ST LOADING DOCK · UNLOAD ENTRY →", "rgba(249, 115, 22, 0.9)", "#ffffff", 0.78);
  dockSign.position.set(-345, 108, 0);
  dockGroup.add(dockSign);
  archGroup.add(dockGroup);

  // 6. Storefront Rooms, Glazed Facades, Doorway Cutouts, Unload Flow Paths & Staged Items
  const zones = plan.zones || [];
  const orderedVenueItems = [];

  zones.forEach((zone) => {
    const spec = VENUE_ZONE_LAYOUT[zone.zone_id];
    if (!spec) return;
    const [L, W, H] = zone.dims_in;
    const [doorW, doorH] = zone.door_in || [48, 84];
    const isConcourse = zone.zone_type === "concourse";

    // Unload path dashed line from Loading Dock into this zone's entrance
    if (spec.dockPath && spec.dockPath.length >= 2) {
      const pathPts = spec.dockPath.map(([px, pz]) => new THREE.Vector3(px, 0.55, pz));
      const pathLine = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(pathPts),
        new THREE.LineDashedMaterial({
          color: new THREE.Color(spec.accentHex),
          dashSize: 10,
          gapSize: 6,
          transparent: true,
          opacity: 0.7,
        })
      );
      pathLine.computeLineDistances();
      archGroup.add(pathLine);
    }

    const roomGroup = new THREE.Group();
    roomGroup.position.set(spec.cx, 0, spec.cz);
    roomGroup.rotation.y = spec.rotY;
    worldGroup.add(roomGroup);

    if (!isConcourse) {
      // Storefront floor carpet / tile
      const rFloor = new THREE.Mesh(
        new THREE.PlaneGeometry(L, W),
        new THREE.MeshStandardMaterial({ color: spec.floorColor, roughness: 0.82, metalness: 0.05 })
      );
      rFloor.rotation.x = -Math.PI / 2;
      rFloor.position.set(0, 0.18, 0);
      roomGroup.add(rFloor);

      // Cutaway architectural perimeter walls (back `-L/2` & side walls `±W/2` at 44" waist-cutaway
      // + full-height corner framing so interior stays 100% visible from any orbit angle!)
      const lowWallH = 42;
      const wallMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.72, metalness: 0.1 });
      const glassMat = new THREE.MeshPhysicalMaterial({
        color: 0x93c5fd,
        transparent: true,
        opacity: 0.18,
        roughness: 0.15,
        side: THREE.DoubleSide,
        depthWrite: false,
      });

      // Back wall (-L/2)
      const backLow = new THREE.Mesh(new THREE.BoxGeometry(3, lowWallH, W), wallMat);
      backLow.position.set(-L / 2 + 1.5, lowWallH / 2, 0);
      roomGroup.add(backLow);

      // Side walls (±W/2)
      [-W / 2 + 1.5, W / 2 - 1.5].forEach((sz) => {
        const sideLow = new THREE.Mesh(new THREE.BoxGeometry(L, lowWallH, 3), wallMat);
        sideLow.position.set(0, lowWallH / 2, sz);
        roomGroup.add(sideLow);
      });

      // Full-height Storefront Facade on `+L/2` (facing into the Main Concourse!) with real `[doorW × doorH]` opening
      const wingSpan = Math.max(0, (W - doorW) / 2);
      if (wingSpan > 2) {
        [-W / 2 + wingSpan / 2, W / 2 - wingSpan / 2].forEach((wz) => {
          // Knee bulkhead + storefront display window glass
          const knee = new THREE.Mesh(new THREE.BoxGeometry(3.5, 22, wingSpan), wallMat);
          knee.position.set(L / 2 - 1.75, 11, wz);
          roomGroup.add(knee);

          const paneH = Math.max(10, doorH - 22);
          const pane = new THREE.Mesh(new THREE.BoxGeometry(1.5, paneH, wingSpan - 2), glassMat);
          pane.position.set(L / 2 - 1.75, 22 + paneH / 2, wz);
          roomGroup.add(pane);
        });
      }

      // Doorway portal frame (jambs + glowing threshold) in store's stop color
      const portalMat = new THREE.MeshStandardMaterial({ color: spec.accentHex, roughness: 0.35, metalness: 0.3 });
      [-doorW / 2, doorW / 2].forEach((dz) => {
        const jamb = new THREE.Mesh(new THREE.BoxGeometry(4.2, Math.min(doorH, H), 3.2), portalMat);
        jamb.position.set(L / 2 - 1.5, Math.min(doorH, H) / 2, dz);
        roomGroup.add(jamb);
      });

      // Storefront Fascia Header & Illuminated Signboard above doorway (`[doorH .. H]`)
      const fasciaH = Math.max(16, H - Math.min(doorH, H - 16));
      const signTex = makeSignTexture(
        spec.signTitle,
        `${zone.item_count} pcs · Door ${Math.round(doorW)}×${Math.round(doorH)}" · ${fmt(zone.floor_pct, 0)}% floor`,
        spec.accentHex
      );
      const fascia = new THREE.Mesh(
        new THREE.BoxGeometry(4.5, fasciaH, Math.min(W, Math.max(doorW + 44, W * 0.88))),
        [
          new THREE.MeshBasicMaterial({ map: signTex }), // +X face facing straight into the Main Concourse!
          wallMat,
          wallMat,
          wallMat,
          wallMat,
          wallMat,
        ]
      );
      fascia.position.set(L / 2 - 1.5, H - fasciaH / 2, 0);
      roomGroup.add(fascia);

      // Subtle room volume outline
      const roomOutline = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(L, H, W)),
        new THREE.LineBasicMaterial({ color: spec.accentHex, transparent: true, opacity: 0.32 })
      );
      roomOutline.position.set(0, H / 2, 0);
      roomGroup.add(roomOutline);
    } else {
      // Concourse floating label banner
      const concBanner = makeTextSprite(
        `STOP 6 · MAIN CONCOURSE HALL (${zone.item_count} pcs)`,
        "rgba(8, 51, 68, 0.88)",
        "#67e8f9",
        0.92
      );
      concBanner.position.set(0, 146, 0);
      roomGroup.add(concBanner);
    }

    // Add camera target for this zone
    binTargets.push({
      label: `Stop ${zone.dock_stop}`,
      center: new THREE.Vector3(spec.cx, Math.min(H * 0.45, 52), spec.cz),
      radius: isConcourse ? 340 : Math.max(L, W, H) * 1.15,
    });

    // Stage and order items inside this zone
    const stagedList = stageZoneItemsForVenue(zone);
    stagedList.sort((a, b) =>
      playDir === "load"
        ? (a.item.load_seq || 0) - (b.item.load_seq || 0)
        : (a.item.unload_seq || 0) - (b.item.unload_seq || 0)
    );
    stagedList.forEach((entry) => orderedVenueItems.push({ ...entry, zone, roomGroup }));
  });

  // Sort globally by dock_stop (Stop 1 -> Stop 6 on Unload; Stop 6 -> Stop 1 on Load) so playback flows naturally!
  orderedVenueItems.sort((a, b) => {
    if (playDir === "unload") {
      return (a.zone.dock_stop - b.zone.dock_stop) || ((a.item.unload_seq || 0) - (b.item.unload_seq || 0));
    }
    return (b.zone.dock_stop - a.zone.dock_stop) || ((a.item.load_seq || 0) - (b.item.load_seq || 0));
  });

  orderedVenueItems.forEach(({ item: it, pos, size, unfoldedTable, zone, roomGroup }, idx) => {
    const [L, W] = zone.dims_in;
    const [x, y, z] = pos;
    const [dx, dy, dz] = size;
    const pad = 0.4;
    const gx = Math.max(dx * 0.86, dx - pad);
    const gy = Math.max(dz * 0.86, dz - pad);
    const gz = Math.max(dy * 0.86, dy - pad);

    const hex = itemColorHex(it);
    const pieceObj = buildProceduralPiece(it, gx, gy, gz, hex, makeBoxFaceTexture, unfoldedTable);

    const localX = x + dx / 2 - L / 2;
    const localY = z + dz / 2;
    const localZ = y + dy / 2 - W / 2;
    pieceObj.position.set(localX, localY, localZ);
    pieceObj.userData = { itemId: it.id };
    pieceObj.traverse((child) => {
      child.userData = { itemId: it.id };
    });

    // Selection / violation bounding box outline
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(gx + 0.6, gy + 0.6, gz + 0.6)),
      new THREE.LineBasicMaterial({
        color: violatingIds.has(it.id) ? 0xff8080 : 0x0f172a,
        transparent: true,
        opacity: violatingIds.has(it.id) ? 0.9 : 0.22,
      })
    );
    pieceObj.add(edges);
    roomGroup.add(pieceObj);

    // Compute world position so fly-to camera works accurately inside rotated rooms
    roomGroup.updateMatrixWorld(true);
    const worldPos = new THREE.Vector3();
    pieceObj.getWorldPosition(worldPos);

    meshEntries.push({
      mesh: pieceObj,
      edges,
      item: it,
      worldPos,
      targetY: localY,
      seqIndex: idx + 1,
      isVenue: true,
    });
  });

  // Prepend special Concourse Walkthrough & Loading Dock camera presets!
  binTargets.unshift(
    {
      label: "Walkthrough Cam",
      center: new THREE.Vector3(60, 56, 0),
      camPos: new THREE.Vector3(-215, 72, 12),
      radius: 220,
    },
    {
      label: "Loading Dock",
      center: new THREE.Vector3(-280, 44, 0),
      camPos: new THREE.Vector3(-540, 165, 195),
      radius: 260,
    }
  );
}

/**
 * Compute human-friendly corner/wall label inside `[L, W]` room for staged `[x, y, z]` item.
 */
export function describeRoomCorner(pos, size, zoneDims, isBox = false) {
  const L = Math.max(1, Number(zoneDims[0] || 180));
  const W = Math.max(1, Number(zoneDims[1] || 120));
  const cx = (pos[0] + 0.5 * size[0]) / L; // 0 = back wall, 1 = front doorway wall
  const cy = (pos[1] + 0.5 * size[1]) / W; // 0 = left wall, 1 = right wall

  if (isBox && cx < 0.35) {
    return cy < 0.45 ? "Back-Left Stock Corner" : cy > 0.55 ? "Back-Right Stock Corner" : "Back Stock Wall";
  }
  const d = cx < 0.35 ? "Back" : cx > 0.66 ? "Front" : "Mid";
  const s = cy < 0.35 ? "Left" : cy > 0.65 ? "Right" : "Center";
  if (d === "Mid" && s === "Center") return "Center Floor";
  if (d === "Mid") return `${s} Wall`;
  if (s === "Center") return d === "Back" ? "Back Wall" : "Front Window Bay";
  return `${d}-${s} Corner`;
}

/**
 * Update `dest_corner` across `plan.zones` and `plan.trucks` using the Venue staging layout
 * so every item's corner badge matches where it actually sits in the 3D venue!
 */
export function annotateStagedCorners(plan) {
  if (!plan || !Array.isArray(plan.zones)) return;
  const cornerByPiece = new Map();

  plan.zones.forEach((zone) => {
    const staged = stageZoneItemsForVenue(zone);
    const tally = {};
    staged.forEach(({ item, pos, size }) => {
      const corner = describeRoomCorner(pos, size, zone.dims_in, item.is_box);
      const pid = item.piece_id || item.id;
      cornerByPiece.set(pid, corner);
      const realIt = (zone.items || []).find((x) => (x.piece_id || x.id) === pid);
      if (realIt) realIt.dest_corner = corner;
      tally[corner] = (tally[corner] || 0) + 1;
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
      else if (!it.dest_corner) it.dest_corner = "Center Floor";

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

/**
 * Render offscreen 16:9 3D interior corner-cam stills (`zone_id -> dataURL`) directly
 * from the Three.js Penn Station Venue model so every destination room/corner card has
 * a crisp architectural visual even when `data/NYPenn/` has no local video files.
 */
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
    tmpScene.add(new THREE.AmbientLight(0xffffff, 0.85));
    const dl = new THREE.DirectionalLight(0xffffff, 0.9);
    dl.position.set(220, 420, 260);
    tmpScene.add(dl);

    const tmpWorld = new THREE.Group();
    tmpScene.add(tmpWorld);
    buildPennVenueScene({
      ...ctxArgs,
      worldGroup: tmpWorld,
      meshEntries: [],
      binTargets: [],
      showRoof: true,
    });

    const cam = new THREE.PerspectiveCamera(48, 16 / 9, 2, 3000);
    const out = {};

    plan.zones.forEach((zone) => {
      const spec = VENUE_ZONE_LAYOUT[zone.zone_id];
      if (!spec) return;
      const [L, W, H] = zone.dims_in;
      if (zone.zone_type === "concourse") {
        cam.position.set(spec.cx - 210, 108, spec.cz + 115);
        cam.lookAt(spec.cx + 55, 34, spec.cz - 10);
      } else {
        // Position camera near doorway looking diagonally into the furnished room & corners
        const dirZ = spec.cz < 0 ? 1 : -1;
        cam.position.set(spec.cx + W * 0.36, Math.min(H * 0.92, 92), spec.cz + dirZ * (L * 0.62));
        cam.lookAt(spec.cx - W * 0.08, Math.min(H * 0.28, 26), spec.cz - dirZ * (L * 0.14));
      }
      snapRenderer.render(tmpScene, cam);
      out[zone.zone_id] = snapRenderer.domElement.toDataURL("image/jpeg", 0.82);
    });
    return out;
  } catch (e) {
    console.warn("Corner snapshot fallback skipped:", e);
    return {};
  }
}

/**
 * Draw a 16:9 wide-angle simulated video keyframe (`320×180` data URL) for mock / sample_venue
 * runs where no raw `.mp4`/`.jpg` file sits on disk, showing room perspective, detection boxes,
 * and source clip + timestamp HUD.
 */
const simStillCache = new Map();
export function makeSimulatedVideoStill({ roomName = "Room", source = "clip.mp4", timestampS = 3.5, accentHex = "#3b82f6", detections = [], highlightBox = null }) {
  const cacheKey = `${roomName}|${source}|${timestampS}|${accentHex}|${JSON.stringify(highlightBox || detections.slice(0, 2))}`;
  if (simStillCache.has(cacheKey)) return simStillCache.get(cacheKey);

  const c = document.createElement("canvas");
  c.width = 320;
  c.height = 180;
  const ctx = c.getContext("2d");

  // Room perspective walls & floor
  const grad = ctx.createLinearGradient(0, 0, 0, 180);
  grad.addColorStop(0, "#1e293b");
  grad.addColorStop(0.62, "#283548");
  grad.addColorStop(0.63, "#334155");
  grad.addColorStop(1, "#1f2937");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 320, 180);

  // Perspective room corner lines
  ctx.strokeStyle = "rgba(148, 163, 184, 0.28)";
  ctx.lineWidth = 1.5;
  ctx.strokeRect(54, 24, 212, 92);
  [[0, 0, 54, 24], [320, 0, 266, 24], [0, 180, 54, 116], [320, 180, 266, 116]].forEach(([x1, y1, x2, y2]) => {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  });

  // Stylized room silhouettes + Gemini perception bounding boxes
  const boxes = highlightBox
    ? [{ label: roomName, box_2d: highlightBox, primary: true }]
    : (detections && detections.length
      ? detections.slice(0, 3)
      : [
          { label: "furniture", box_2d: [410, 120, 820, 540] },
          { label: "stack", box_2d: [360, 590, 840, 860] },
        ]);

  boxes.forEach((b, idx) => {
    const [ymin, xmin, ymax, xmax] = b.box_2d || [380, 180, 820, 740];
    const rx = (xmin / 1000) * 320;
    const ry = (ymin / 1000) * 180;
    const rw = Math.max(28, ((xmax - xmin) / 1000) * 320);
    const rh = Math.max(22, ((ymax - ymin) / 1000) * 180);

    ctx.fillStyle = idx === 0 ? `${accentHex}55` : "rgba(148, 163, 184, 0.25)";
    ctx.fillRect(rx + 3, ry + 3, rw - 6, rh - 6);

    ctx.strokeStyle = b.primary ? "#4ade80" : "#38bdf8";
    ctx.lineWidth = b.primary ? 2.2 : 1.5;
    ctx.strokeRect(rx, ry, rw, rh);

    if (b.label) {
      ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
      const lbl = String(b.label).slice(0, 18);
      ctx.font = "bold 10px system-ui, sans-serif";
      const tw = ctx.measureText(lbl).width + 8;
      ctx.fillRect(rx, Math.max(22, ry - 14), tw, 14);
      ctx.fillStyle = b.primary ? "#86efac" : "#bae6fd";
      ctx.fillText(lbl, rx + 4, Math.max(32, ry - 4));
    }
  });

  // Top camera HUD bar
  ctx.fillStyle = "rgba(9, 13, 22, 0.76)";
  ctx.fillRect(0, 0, 320, 22);
  ctx.fillStyle = "#ef4444";
  ctx.beginPath(); ctx.arc(12, 11, 4, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#f8fafc";
  ctx.font = "600 11px ui-monospace, SFMono-Regular, monospace";
  const mm = Math.floor((timestampS || 0) / 60);
  const ss = String(Math.round((timestampS || 0) % 60)).padStart(2, "0");
  ctx.fillText(`${source} · ${mm}:${ss}`, 22, 15);

  const url = c.toDataURL("image/jpeg", 0.84);
  simStillCache.set(cacheKey, url);
  return url;
}
