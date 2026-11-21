// Pack It Up · Real-Time Point A -> Point B Truck Route Guide & Calm Unpack-to-Last-Item Companion.
// Works seamlessly against FastAPI (`/route/brief`) AND zero-server `?mock=1` mode (calling CORS-enabled
// OpenStreetMap Nominatim, OSRM, Open-Meteo, and NYC DOT feeds directly with instant offline fallbacks).
(function () {
  "use strict";

  const DEFAULT_ORIGIN = "The Malin SoHo, 387 Broadway, New York, NY 10013";
  const DEFAULT_DEST = "NY Penn Station, 234 W 31st St, New York, NY 10001";

  const TRUCK_SPECS_JS = {
    uhaul_van: { name: "U-Haul 9 ft Cargo Van", extHIn: 81, extLenFt: 18.5, gvwr: 9000, dualRear: false },
    uhaul_10: { name: "U-Haul 10 ft", extHIn: 103, extLenFt: 19.5, gvwr: 8600, dualRear: false },
    uhaul_15: { name: "U-Haul 15 ft", extHIn: 122, extLenFt: 22.5, gvwr: 14500, dualRear: true },
    uhaul_20: { name: "U-Haul 20 ft", extHIn: 121, extLenFt: 26.4, gvwr: 14500, dualRear: true },
    uhaul_26: { name: "U-Haul 26 ft", extHIn: 144, extLenFt: 33.7, gvwr: 25999, dualRear: true },
  };

  const NAV_APPS_JS = {
    google_maps: {
      id: "google_maps",
      name: "Google Maps",
      hasTruckMode: false,
      badge: "Passenger Car Only — No Truck Mode",
      tip: "Google Maps has NO commercial truck or bridge-height mode on phones—its blue line treats you like a sedan and WILL route box trucks onto banned parkways (FDR Drive, Brooklyn Bridge, Belt Pkwy, Storrow Dr). Switch to Hammer or Trucker Path for highway routing, or verify every highway against the No-Truck list below.",
    },
    apple_maps: {
      id: "apple_maps",
      name: "Apple Maps",
      hasTruckMode: false,
      badge: "Passenger Car Only — No Truck Mode",
      tip: "Apple Maps does NOT filter low bridges or truck-prohibited parkways. Switch to a free truck GPS app (Hammer or Trucker Path) with your roof height entered before driving, and only use Apple Maps for walking/building entrance checks.",
    },
    waze: {
      id: "waze",
      name: "Waze",
      hasTruckMode: false,
      badge: "Car / Taxi Only — No Truck Mode",
      tip: "Waze has Car, Taxi, and Motorcycle modes—no Commercial Truck or height setting—and detours aggressively onto narrow side streets and parkways. Pair with Hammer or stick strictly to Local Truck Routes.",
    },
    hammer: {
      id: "hammer",
      name: "Hammer (Truck GPS)",
      hasTruckMode: true,
      badge: "True Commercial Truck Mode (Free)",
      tip: "Tap the Truck icon → Vehicle Dimensions → enter the buffered height & length below and toggle Commercial Vehicle ON before starting navigation.",
    },
    trucker_path: {
      id: "trucker_path",
      name: "Trucker Path",
      hasTruckMode: true,
      badge: "True Commercial Truck Mode",
      tip: "Open Settings → Truck Profile → set 2-Axle Box Truck with the buffered roof height & weight below to automatically avoid parkways and low railroad bridges.",
    },
    copilot: {
      id: "copilot",
      name: "CoPilot / Sygic Truck",
      hasTruckMode: true,
      badge: "True Commercial Truck Mode",
      tip: "Choose Medium Commercial Truck profile and enter your roof clearance + GVWR; cached maps keep working inside river tunnels.",
    },
  };

  const QUICK_PRESETS = [
    {
      label: "Malin SoHo → Penn Station",
      origin: "The Malin SoHo, 387 Broadway, New York, NY 10013",
      destination: "NY Penn Station, 234 W 31st St, New York, NY 10001",
    },
    {
      label: "Brooklyn → Penn Station",
      origin: "Williamsburg, Bedford Ave, Brooklyn, NY 11211",
      destination: "NY Penn Station, 234 W 31st St, New York, NY 10001",
    },
    {
      label: "Hoboken NJ → Penn Station",
      origin: "Hoboken, Washington St, NJ 07030",
      destination: "NY Penn Station, 234 W 31st St, New York, NY 10001",
    },
    {
      label: "Upper West Side → Brooklyn",
      origin: "Upper West Side, W 79th St, New York, NY 10024",
      destination: "Williamsburg, Bedford Ave, Brooklyn, NY 11211",
    },
  ];

  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);

  function fmtFtIn(inches) {
    const n = Math.round(Number(inches || 144));
    return `${Math.floor(n / 12)}' ${n % 12}"`;
  }

  function safeHref(u) {
    const s = String(u || "").trim();
    return /^https?:\/\//i.test(s) ? s : "#";
  }

  function injectStyles() {
    if (document.getElementById("piu-journey-styles")) return;
    const st = document.createElement("style");
    st.id = "piu-journey-styles";
    st.textContent = `
      /* Keep right-hand tab bar flexible when 4-5 tabs are present */
      .tab-bar[role="tablist"] {
        display: flex !important;
        flex-wrap: wrap;
        gap: 4px;
      }
      .tab-bar[role="tablist"] > button {
        flex: 1 1 auto;
        min-width: fit-content;
        padding: 7px 8px;
      }

      .route-pill-btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 6px 12px; border-radius: 999px; font: inherit; font-size: 12.5px; font-weight: 700;
        border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--line));
        background: var(--card); color: var(--ink); cursor: pointer; min-height: 36px;
      }
      .route-pill-btn:hover { border-color: var(--accent); background: var(--accent-soft); }

      /* Calm, collapsible Move Co-Pilot strip (never pushy or overbearing) */
      .companion-strip {
        margin: 0 0 12px;
        padding: 10px 14px;
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        transition: padding 0.15s ease;
      }
      .companion-strip.quiet {
        padding: 6px 12px;
        background: color-mix(in srgb, var(--card) 75%, var(--bg));
      }
      .comp-top {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;
      }
      .comp-stages {
        display: flex; flex-wrap: wrap; align-items: center; gap: 5px;
      }
      .comp-stage-btn {
        border: 1px solid var(--line); background: var(--bg); color: var(--muted);
        font: inherit; font-size: 12px; font-weight: 650; padding: 4px 10px;
        border-radius: 999px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
      }
      .comp-stage-btn:hover { border-color: var(--accent); color: var(--ink); }
      .comp-stage-btn[aria-pressed="true"] {
        background: var(--accent-soft); color: var(--accent);
        border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
      }
      .comp-stage-btn.done {
        color: var(--ok); border-color: color-mix(in srgb, var(--ok) 40%, var(--line));
      }
      .comp-quiet-btn {
        border: 0; background: transparent; color: var(--muted); font: inherit;
        font-size: 11.5px; font-weight: 600; cursor: pointer; padding: 3px 7px; border-radius: 6px;
      }
      .comp-quiet-btn:hover { background: var(--bg); color: var(--ink); }
      .comp-nudge-row {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 10px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line);
        font-size: 13px; color: var(--ink); line-height: 1.4;
      }
      .companion-strip.quiet .comp-nudge-row { display: none; }
      .comp-nudge-text { flex: 1 1 280px; color: var(--muted); }
      .comp-nudge-text b { color: var(--ink); }
      .comp-cta {
        border: 1px solid var(--line); background: var(--bg); color: var(--accent);
        font: inherit; font-size: 12px; font-weight: 700; padding: 5px 10px;
        border-radius: 8px; cursor: pointer; white-space: nowrap;
      }
      .comp-cta:hover { border-color: var(--accent); background: var(--accent-soft); }

      /* Sub-mode toggle inside Route & Unpack tab */
      .j-subbar {
        display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 10px;
      }
      .j-subbtn {
        border: 1px solid var(--line); background: var(--bg); color: var(--muted);
        font: inherit; font-size: 12.5px; font-weight: 700; padding: 7px 8px;
        border-radius: 9px; cursor: pointer; text-align: center;
      }
      .j-subbtn[aria-pressed="true"] {
        background: var(--accent-soft); color: var(--accent);
        border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
      }

      /* Address inputs & route cards */
      .addr-box {
        background: var(--bg); border: 1px solid var(--line); border-radius: 11px;
        padding: 10px; margin-bottom: 10px;
      }
      .addr-row {
        display: grid; grid-template-columns: 22px 1fr; gap: 7px; align-items: center; margin-bottom: 7px;
      }
      .addr-dot {
        width: 20px; height: 20px; border-radius: 999px; font-size: 11px; font-weight: 800;
        display: inline-flex; align-items: center; justify-content: center;
      }
      .addr-dot.a { background: var(--accent-soft); color: var(--accent); }
      .addr-dot.b { background: color-mix(in srgb, var(--ok) 18%, var(--card)); color: var(--ok); }
      .addr-input {
        width: 100%; min-height: 36px; padding: 6px 9px; border-radius: 8px;
        border: 1px solid var(--line); background: var(--card); color: var(--ink);
        font: inherit; font-size: 12.5px;
      }
      .addr-actions {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px;
      }
      .preset-chips {
        display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px;
      }
      .preset-chip {
        border: 1px solid var(--line); background: var(--card); color: var(--muted);
        font: inherit; font-size: 11px; font-weight: 600; padding: 2px 7px;
        border-radius: 999px; cursor: pointer;
      }
      .preset-chip:hover { border-color: var(--accent); color: var(--ink); }

      .live-banner {
        padding: 9px 11px; border-radius: 10px; border: 1px solid var(--line);
        background: color-mix(in srgb, var(--accent-soft) 45%, var(--card));
        margin-bottom: 9px; font-size: 12.5px; line-height: 1.4;
      }
      .live-banner-head {
        display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px;
        font-weight: 750; font-size: 13.5px; color: var(--ink); margin-bottom: 3px;
      }
      .live-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
      .live-chip {
        font-size: 10.5px; font-weight: 650; padding: 2px 6px; border-radius: 6px;
        background: var(--card); border: 1px solid var(--line); color: var(--muted);
      }
      .live-chip.ok { color: var(--ok); border-color: color-mix(in srgb, var(--ok) 40%, var(--line)); }
      .live-chip.warn { color: #b45309; border-color: #f59e0b; background: #fffbeb; }
      @media (prefers-color-scheme: dark) {
        :root:not([data-theme="light"]) .live-chip.warn { color: #fcd34d; border-color: #78350f; background: #2e2111; }
      }

      .rt-card {
        border: 1px solid var(--line); border-radius: 10px; padding: 9px 11px;
        background: var(--bg); margin-bottom: 8px; font-size: 12.5px; line-height: 1.42;
      }
      .rt-card h3 {
        margin: 0 0 6px; font-size: 13px; font-weight: 750;
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px;
      }
      .rt-list { margin: 5px 0 0; padding-left: 16px; }
      .rt-list li { margin-bottom: 5px; }
      .nav-app-grid { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0; }
      .nav-app-pill {
        border: 1px solid var(--line); background: var(--card); color: var(--ink);
        font: inherit; font-size: 11.5px; font-weight: 650; padding: 4px 8px;
        border-radius: 8px; cursor: pointer;
      }
      .nav-app-pill[aria-pressed="true"] {
        background: var(--accent); color: var(--accent-ink); border-color: var(--accent);
      }
      .truck-spec-strip {
        font-size: 11.5px; font-weight: 650; padding: 6px 8px; border-radius: 8px;
        background: var(--card); border: 1px dashed var(--accent); color: var(--ink);
        margin: 6px 0; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 6px;
      }
      .warn-callout {
        padding: 7px 9px; border-radius: 8px; font-size: 12px; margin-top: 5px;
        border: 1px solid #f59e0b; background: color-mix(in srgb, #f59e0b 11%, var(--card));
      }
      .ok-callout {
        padding: 7px 9px; border-radius: 8px; font-size: 12px; margin-top: 5px;
        border: 1px solid color-mix(in srgb, var(--ok) 45%, var(--line));
        background: color-mix(in srgb, var(--ok) 10%, var(--card));
      }
      .no-truck-item {
        padding: 6px 8px; border-radius: 8px; background: var(--card);
        border-left: 3px solid #ef4444; margin-bottom: 6px;
      }
      .no-truck-item.watch { border-left-color: #f59e0b; }

      /* Unpack-to-Last-Item calm tracker */
      .unpack-prog-card {
        padding: 10px 11px; border-radius: 10px; border: 1px solid var(--line);
        background: var(--bg); margin-bottom: 9px;
      }
      .unpack-bar {
        height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; margin-top: 6px;
      }
      .unpack-bar > i {
        display: block; height: 100%; background: var(--ok); transition: width 0.25s ease;
      }
      .unpack-room {
        border: 1px solid var(--line); border-radius: 10px; background: var(--bg);
        margin-bottom: 7px; overflow: hidden;
      }
      .unpack-room summary {
        list-style: none; cursor: pointer; padding: 8px 10px;
        display: flex; align-items: center; justify-content: space-between; gap: 8px;
        font-size: 13px; font-weight: 700;
      }
      .unpack-room summary::-webkit-details-marker { display: none; }
      .unpack-items {
        border-top: 1px solid var(--line); padding: 4px 10px 8px; max-height: 220px; overflow-y: auto;
      }
      .unpack-row {
        display: flex; align-items: flex-start; gap: 8px; padding: 5px 0;
        border-bottom: 1px dashed var(--line); font-size: 12.5px; cursor: pointer;
      }
      .unpack-row:last-child { border-bottom: 0; }
      .unpack-row.checked { opacity: 0.6; text-decoration: line-through; }
      .unpack-done-card {
        padding: 12px; border-radius: 11px; text-align: center;
        border: 1.5px solid color-mix(in srgb, var(--ok) 55%, var(--line));
        background: color-mix(in srgb, var(--ok) 10%, var(--card));
        margin-bottom: 10px; font-size: 13px;
      }

      @media print {
        .companion-strip, .route-pill-btn { display: none !important; }
      }
    `;
    document.head.appendChild(st);
  }

  // ---------- Browser-direct Real-Time Fallback (for ?mock=1 with no Python backend) ----------
  async function fetchJsonTimeout(url, ms = 4500) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
      const r = await fetch(url, { signal: ctrl.signal });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function buildBrowserLiveBrief({ origin, destination, plan, truckId, navApp }) {
    const origStr = (origin || "").trim() || DEFAULT_ORIGIN;
    const destStr = (destination || "").trim() || DEFAULT_DEST;
    const chosenTid = truckId || plan?.trucks?.[0]?.truck_id || "uhaul_26";
    const tSpec = TRUCK_SPECS_JS[chosenTid] || TRUCK_SPECS_JS.uhaul_26;
    const truckCount = Math.max(1, (plan?.trucks || []).length);
    const allItems = (plan?.trucks || []).flatMap((t) => t.items || []);
    const boxCount = allItems.filter((i) => i.is_box).length;
    const fragileCount = allItems.filter((i) => i.fragile).length;
    const heavyCount = allItems.filter((i) => i.two_person || Number(i.weight_lb || 0) > 50).length;
    const navHLabel = fmtFtIn(tSpec.extHIn + 6);
    const extHLabel = fmtFtIn(tSpec.extHIn);
    const curbFt = Math.ceil(tSpec.extLenFt + 12);

    const liveSources = [];
    let origGeo = { label: origStr, short_label: "Point A", lat: 40.7186, lon: -74.0018, state: "NY", urban_tier: "dense_city" };
    let destGeo = { label: destStr, short_label: "Point B", lat: 40.7506, lon: -73.9935, state: "NY", urban_tier: "dense_city" };

    // 1. Live Nominatim Geocoding
    try {
      const [gA, gB] = await Promise.all([
        fetchJsonTimeout(`https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=1&q=${encodeURIComponent(origStr)}`),
        fetchJsonTimeout(`https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=1&q=${encodeURIComponent(destStr)}`),
      ]);
      if (gA?.[0]) {
        const a = gA[0].address || {};
        origGeo = {
          label: gA[0].display_name || origStr,
          short_label: [a.borough || a.city || a.town, a.state].filter(Boolean).join(", ") || origStr.slice(0, 32),
          lat: Number(gA[0].lat),
          lon: Number(gA[0].lon),
          state: a.state || "",
          urban_tier: /new york|brooklyn|queens|bronx|manhattan|hoboken|jersey city|boston|chicago|philadelphia|san francisco/i.test(gA[0].display_name) ? "dense_city" : "suburban",
        };
      }
      if (gB?.[0]) {
        const b = gB[0].address || {};
        destGeo = {
          label: gB[0].display_name || destStr,
          short_label: [b.borough || b.city || b.town, b.state].filter(Boolean).join(", ") || destStr.slice(0, 32),
          lat: Number(gB[0].lat),
          lon: Number(gB[0].lon),
          state: b.state || "",
          urban_tier: /new york|brooklyn|queens|bronx|manhattan|hoboken|jersey city|boston|chicago|philadelphia|san francisco/i.test(gB[0].display_name) ? "dense_city" : "suburban",
        };
      }
      liveSources.push("OpenStreetMap Nominatim");
    } catch (e) { /* offline preset fallback */ }

    // 2. Live OSRM Routing + Open-Meteo Weather + NYC DOT Traffic Speeds in parallel
    let distMi = 2.8, carMin = 16, primaryRoads = [];
    let wxDest = { temp_f: null, gusts_mph: null, precip_in: 0, precip_prob_4h_pct: 0, condition: "Fair" };
    let avgMph = null;

    await Promise.all([
      fetchJsonTimeout(
        `https://router.project-osrm.org/route/v1/driving/${origGeo.lon.toFixed(5)},${origGeo.lat.toFixed(5)};${destGeo.lon.toFixed(5)},${destGeo.lat.toFixed(5)}?overview=false&steps=true&alternatives=true`
      ).then((osrm) => {
        const r0 = osrm?.routes?.[0];
        if (r0) {
          distMi = Math.max(0.2, Number((r0.distance / 1609.344).toFixed(1)));
          carMin = Math.max(4, Math.round(r0.duration / 60));
          const seen = new Set();
          for (const leg of r0.legs || []) {
            for (const st of leg.steps || []) {
              const nm = [st.name, st.ref].filter(Boolean).join(" ").trim();
              if (nm && !seen.has(nm.toLowerCase())) {
                seen.add(nm.toLowerCase());
                primaryRoads.push(nm);
              }
            }
          }
          liveSources.push("OSRM Live Street Router");
        }
      }).catch(() => {}),

      fetchJsonTimeout(
        `https://api.open-meteo.com/v1/forecast?latitude=${destGeo.lat.toFixed(4)}&longitude=${destGeo.lon.toFixed(4)}&current=temperature_2m,precipitation,wind_gusts_10m&hourly=precipitation_probability&forecast_hours=4&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch`
      ).then((wx) => {
        if (wx?.current) {
          wxDest = {
            temp_f: Math.round(wx.current.temperature_2m),
            precip_in: Number(wx.current.precipitation || 0),
            gusts_mph: Math.round(wx.current.wind_gusts_10m || 10),
            precip_prob_4h_pct: Math.max(0, ...(wx.hourly?.precipitation_probability || [0])),
            condition: Number(wx.current.precipitation || 0) > 0 ? "Rain" : "Clear / Dry",
          };
          liveSources.push("Open-Meteo Live Weather");
        }
      }).catch(() => {}),

      fetchJsonTimeout("https://data.cityofnewyork.us/resource/i4gi-tjb9.json?$order=:id%20DESC&$limit=25")
        .then((rows) => {
          if (Array.isArray(rows) && rows.length) {
            const spds = rows.map((r) => Number(r.speed)).filter((n) => n > 0 && n < 75);
            if (spds.length) {
              avgMph = Number((spds.reduce((a, b) => a + b, 0) / spds.length).toFixed(1));
              liveSources.push("NYC DOT Live Traffic Sensors");
            }
          }
        }).catch(() => {}),
    ]);

    const truckEtaMin = Math.max(7, Math.round(carMin * (destGeo.urban_tier === "dense_city" ? 1.3 : 1.15)));
    const navObj = NAV_APPS_JS[navApp] || NAV_APPS_JS.google_maps;
    const roadBlob = primaryRoads.join(" | ").toLowerCase();

    const warnings = [];
    if (/fdr|east river/i.test(roadBlob)) {
      warnings.push({
        road: "FDR Drive (Detected on Car Route!)",
        severity: "critical",
        detected_on: "Consumer GPS fastest route",
        reason: `Zero box trucks allowed (${extHLabel} truck vs 9'–11' overpasses).`,
        safe_alternative: "Use 1st, 2nd, or 3rd Ave Local Truck Routes instead.",
      });
    }
    if (/brooklyn bridge/i.test(roadBlob)) {
      warnings.push({
        road: "Brooklyn Bridge (Detected on Car Route!)",
        severity: "critical",
        detected_on: "Consumer GPS fastest route",
        reason: "All commercial & rental box trucks are prohibited on Brooklyn Bridge.",
        safe_alternative: "Use Manhattan Bridge (lower roadway) or Williamsburg Bridge (outer roadways).",
      });
    }
    if (/holland tunnel/i.test(roadBlob) || /nj|hoboken|jersey/i.test(origStr)) {
      warnings.push({
        road: "Holland Tunnel Commercial Box-Truck Limits",
        severity: "watch",
        detected_on: "Hudson River Crossing Rule",
        reason: "Strict Port Authority commercial axle & 12'0\" height gauge restrictions.",
        safe_alternative: "Use the Lincoln Tunnel (13'0\" clearance, exits right near W 31st St / Penn Station).",
      });
    }
    warnings.push({
      road: "All NY Parkways (FDR, Henry Hudson N of 59th, Belt Pkwy) & Non-Truck Cross Streets",
      severity: "watch",
      detected_on: "Commercial Box-Truck Rule",
      reason: `Every rental box truck (${tSpec.name}, ${extHLabel} tall) counts as a commercial vehicle—banned on all Parkways.`,
      safe_alternative: "Stay on NYC DOT Local Truck Routes (Canal, Houston, 14th, 23rd, 34th St & 8th/9th/10th/11th Aves) until your final block.",
    });

    const tollItems = [];
    if (/nj|hoboken|jersey|lincoln|holland|george washington/i.test(origStr + " " + roadBlob)) {
      tollItems.push({
        name: "Hudson River Crossing (Eastbound into NY)",
        estimate: tSpec.dualRear ? "$32–$46 E-ZPass (2-axle, 6-tire commercial)" : "$16–$22 E-ZPass",
        note: "Dual-rear-wheel U-Hauls (15/20/26 ft) bill at commercial single-unit truck rates.",
      });
    } else {
      tollItems.push({
        name: "Surface Avenue Corridor",
        estimate: "$0 bridge/tunnel tolls on local Manhattan avenues",
        note: "Note: Entering Manhattan south of 60th St from outside triggers Congestion Relief Zone (~$21.60 peak single-unit truck).",
      });
    }

    const oEnc = encodeURIComponent(origStr);
    const dEnc = encodeURIComponent(destStr);

    return {
      fetched_at: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
      live_sources: liveSources.length ? liveSources : ["Built-in NYC & Truck Corridor Profile"],
      origin: origGeo,
      destination: destGeo,
      fleet: {
        truck_id: chosenTid,
        truck_name: tSpec.name,
        truck_count: truckCount,
        fleet_label: truckCount > 1 ? `${truckCount} × ${tSpec.name}` : tSpec.name,
        ext_height_label: extHLabel,
        recommended_nav_height_label: navHLabel,
        ext_length_ft: tSpec.extLenFt,
        curb_space_needed_ft: curbFt,
        gvwr_lb: tSpec.gvwr,
        toll_class: tSpec.dualRear ? "2-Axle, 6-Tire Commercial Truck" : "2-Axle, 4-Tire Light Box Truck",
        total_boxes: boxCount,
        fragile_pieces: fragileCount,
        two_person_pieces: heavyCount,
      },
      drive: {
        distance_miles: distMi,
        truck_eta_min: truckEtaMin,
        roads_on_car_route: primaryRoads.slice(0, 10),
        calm_headline: `${distMi} mi · ~${truckEtaMin} min truck drive · set ${navHLabel} height clearance`,
        route_summary: `From ${origGeo.short_label} to ${destGeo.short_label} (${distMi} mi, ~${truckEtaMin} min in ${tSpec.name}).` +
          (wxDest.temp_f != null ? ` Live weather: ${wxDest.temp_f}°F, ${wxDest.condition.toLowerCase()} (gusts ${wxDest.gusts_mph} mph).` : "") +
          (avgMph != null ? ` NYC DOT live traffic sensors: ${avgMph} mph avg.` : ""),
        weather_alert: wxDest.gusts_mph >= 25 ? `Live wind gusts (${wxDest.gusts_mph} mph): take bridges steady in your ${extHLabel} high-wall truck.` : null,
      },
      weather: { destination: wxDest },
      traffic: { active: avgMph != null, avg_mph: avgMph, corridors: [] },
      decision: { choice: "commercial_truck_avenues_and_city_curb_plan", confidence: null, via: "browser_live" },
      nav_reminder: {
        selected_app: {
          id: navObj.id,
          name: navObj.name,
          has_native_truck_mode: navObj.hasTruckMode,
          badge: navObj.badge,
        },
        available_apps: Object.values(NAV_APPS_JS).map((a) => ({
          id: a.id,
          name: a.name,
          has_native_truck_mode: a.hasTruckMode,
          badge: a.badge,
        })),
        truck_profile_card: `Height: ${navHLabel} (${extHLabel} roof + 6" buffer) · Length: ${tSpec.extLenFt} ft · GVWR: ${tSpec.gvwr.toLocaleString()} lb`,
        tip: navObj.tip,
        links: {
          google_maps: `https://www.google.com/maps/dir/?api=1&origin=${oEnc}&destination=${dEnc}&travelmode=driving`,
          google_maps_no_tolls: `https://www.google.com/maps/dir/?api=1&origin=${oEnc}&destination=${dEnc}&travelmode=driving&avoid=tolls`,
          apple_maps: `https://maps.apple.com/?saddr=${oEnc}&daddr=${dEnc}&dirflg=d`,
          waze: `https://waze.com/ul?ll=${destGeo.lat.toFixed(5)},${destGeo.lon.toFixed(5)}&navigate=yes`,
        },
      },
      no_truck_roads: { warnings, ai_bullets: [] },
      tolls: {
        toll_class: tSpec.dualRear ? "2-Axle, 6-Tire Commercial Truck" : "2-Axle, 4-Tire Light Box Truck",
        items: tollItems,
        rental_plate_tip: "Rental plate-tolling adds a $15–$25/day processor fee on top of tolls—bring your own E-ZPass transponder if possible.",
        ai_bullets: [],
      },
      parking: {
        is_city: destGeo.urban_tier === "dense_city",
        context_badge: destGeo.urban_tier === "dense_city" ? "Dense City Curb & Dock Mode" : "Driveway & Local Street Mode",
        curb_space_needed_ft: curbFt,
        tips: [
          `Reserve ~${curbFt} ft of straight curb (${tSpec.extLenFt} ft truck + 12 ft pull-out ramp). Around Penn Station (W 31st–33rd St), use signed Commercial Loading zones (3-hr limit) and stay clear of 8th Ave bus/bike lanes.`,
          `Keep 15 ft clear of fire hydrants, spot your ${extHLabel} roof corner against sidewalk scaffolding sheds & tree branches at the curb tilt, and keep a contact number on the dash while shuttling items.`,
        ],
        ai_bullets: [],
      },
      stage_nudges: {
        pack: `Keep one small 'Open-First' bag (chargers, box cutter, hardware bolts, water) separate from your ${Math.max(1, boxCount)} packed boxes.`,
        load: `Follow the 3D Load scrubber cab-to-tail: ${heavyCount} heavy pieces anchor the floor, ${fragileCount} fragile pieces stay on top.`,
        drive: `Switch to Commercial Truck Mode (${navHLabel} height) on your phone before pulling out, and skip all Parkways.`,
        park_unload: `Claim ~${curbFt} ft at the curb/dock, watch low awnings (${extHLabel} roof), and flip the 3D scrubber to Unload (LIFO).`,
        unpack: "Unpack at your own pace—start with your Open-First essentials and check off items below until the very last piece is home.",
      },
    };
  }

  // ---------- Main Auto-Mount on index.html ----------
  function mountMoveJourney() {
    if (!document.body || !document.body.classList.contains("pack-page")) return;
    if (document.getElementById("piu-companion-strip")) return;
    injectStyles();

    const piu = window.PIU || {
      params: new URLSearchParams(location.search),
      lastRun: () => null,
      API_BASE: "",
      MOCK: false,
    };
    const runId = piu.params.get("run_id") || piu.lastRun() || "sample_venue";
    const storageKey = `piu_journey_v1_${runId}`;

    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(storageKey) || "{}") || {};
    } catch (e) { saved = {}; }

    const state = {
      origin: saved.origin || DEFAULT_ORIGIN,
      destination: saved.destination || DEFAULT_DEST,
      navApp: saved.navApp || "google_maps",
      stage: saved.stage || "drive", // pack | load | drive | park_unload | unpack
      quiet: Boolean(saved.quiet),
      subTab: saved.subTab || "route", // route | unpack
      unpackedIds: new Set(Array.isArray(saved.unpackedIds) ? saved.unpackedIds : []),
      essentialsDone: Boolean(saved.essentialsDone),
      searchQuery: "",
      plan: null,
      brief: null,
      loadingBrief: false,
    };

    function persist() {
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            origin: state.origin,
            destination: state.destination,
            navApp: state.navApp,
            stage: state.stage,
            quiet: state.quiet,
            subTab: state.subTab,
            unpackedIds: Array.from(state.unpackedIds),
            essentialsDone: state.essentialsDone,
          })
        );
      } catch (e) { /* storage full or private mode */ }
    }

    function allPlanItems() {
      return (state.plan?.trucks || []).flatMap((t, tIdx) =>
        (t.items || []).map((it) => ({ ...it, _truckIdx: it.truck_index ?? tIdx }))
      );
    }

    function unpackCounts() {
      const items = allPlanItems();
      const total = items.length;
      let done = 0;
      for (const it of items) {
        if (state.unpackedIds.has(it.id)) done++;
      }
      return { done, total, pct: total ? Math.round((done / total) * 100) : 0 };
    }

    // 1. Insert Calm Companion Strip right below #verdict-banner
    const verdictEl = document.getElementById("verdict-banner");
    const companionEl = document.createElement("section");
    companionEl.id = "piu-companion-strip";
    companionEl.className = "companion-strip" + (state.quiet ? " quiet" : "");
    companionEl.setAttribute("aria-label", "Calm Move-Day Companion");
    if (verdictEl) {
      verdictEl.insertAdjacentElement("afterend", companionEl);
    }

    // 2. Add quick topbar button "🛣️ Route & Unpack"
    const navActions = document.querySelector(".nav-actions");
    let topJumpBtn = null;
    if (navActions) {
      topJumpBtn = document.createElement("button");
      topJumpBtn.type = "button";
      topJumpBtn.id = "btn-jump-journey";
      topJumpBtn.className = "route-pill-btn";
      topJumpBtn.innerHTML = "🛣️ Route &amp; Unpack";
      navActions.prepend(topJumpBtn);
    }

    // 3. Add `🛣️ Route & Unpack` tab to right-hand `.tab-bar`
    const tabBar = document.querySelector(".tab-bar[role='tablist']");
    const labelsPane = document.getElementById("tab-labels");
    if (!tabBar || !labelsPane) return;

    const journeyTabBtn = document.createElement("button");
    journeyTabBtn.type = "button";
    journeyTabBtn.setAttribute("role", "tab");
    journeyTabBtn.dataset.tab = "journey";
    journeyTabBtn.setAttribute("aria-selected", "false");
    journeyTabBtn.textContent = "🛣️ Route & Unpack";

    // Place right before Buy Boxes if present, else at end
    const shopTab = tabBar.querySelector("[data-tab='shop']");
    if (shopTab) {
      tabBar.insertBefore(journeyTabBtn, shopTab);
    } else {
      tabBar.appendChild(journeyTabBtn);
    }

    const journeyPane = document.createElement("div");
    journeyPane.id = "tab-journey";
    journeyPane.className = "hidden";
    labelsPane.insertAdjacentElement("afterend", journeyPane);

    function activateJourneyTab(subMode) {
      if (subMode) {
        state.subTab = subMode;
        persist();
      }
      tabBar.querySelectorAll("[role='tab']").forEach((btn) => {
        btn.setAttribute("aria-selected", String(btn === journeyTabBtn));
      });
      ["tab-unload", "tab-stores", "tab-labels", "tab-shop"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
      });
      journeyPane.classList.remove("hidden");
      renderJourneyPane();
    }

    // Event delegation + MutationObserver on tabBar so ALL tabs (including #btn-jump-shop) cooperate cleanly
    tabBar.addEventListener("click", (e) => {
      const clicked = e.target.closest("[role='tab']");
      if (!clicked) return;
      if (clicked === journeyTabBtn) {
        e.stopPropagation();
        activateJourneyTab();
      } else {
        journeyPane.classList.add("hidden");
        journeyTabBtn.setAttribute("aria-selected", "false");
      }
    }, true);

    const tabObserver = new MutationObserver(() => {
      const otherSelected = Array.from(tabBar.querySelectorAll("[role='tab']")).some(
        (t) => t !== journeyTabBtn && t.getAttribute("aria-selected") === "true"
      );
      if (otherSelected && !journeyPane.classList.contains("hidden")) {
        journeyPane.classList.add("hidden");
        journeyTabBtn.setAttribute("aria-selected", "false");
      }
    });
    tabObserver.observe(tabBar, { attributes: true, subtree: true, attributeFilter: ["aria-selected"] });

    if (topJumpBtn) {
      topJumpBtn.addEventListener("click", () => {
        activateJourneyTab();
        journeyPane.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }

    // Enhance the small static `.nav-tip` inside `#tab-unload` with a live summary + 1-click open
    function updateUnloadFooterTip() {
      const navTip = document.querySelector("#tab-unload .nav-tip");
      if (!navTip || !state.brief) return;
      const fl = state.brief.fleet || {};
      const dr = state.brief.drive || {};
      navTip.innerHTML = `
        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px">
          <span>🚛 <b>Live Route (${esc(dr.distance_miles)} mi · ~${esc(dr.truck_eta_min)} min):</b> Set phone GPS to <b>Commercial Truck Mode (${esc(fl.recommended_nav_height_label)})</b> · avoid parkways · reserve ~${esc(fl.curb_space_needed_ft)} ft at curb.</span>
          <button type="button" class="comp-cta" id="btn-from-unload-route"> Tolls, Roads &amp; Unpack →</button>
        </div>`;
      const btn = document.getElementById("btn-from-unload-route");
      if (btn) btn.addEventListener("click", () => activateJourneyTab("route"));
    }

    // ---------- Render Calm Move Companion Strip ----------
    function renderCompanionStrip() {
      const { done, total } = unpackCounts();
      companionEl.classList.toggle("quiet", state.quiet);

      const nudges = state.brief?.stage_nudges || {
        pack: "Pack one small 'Open-First' essentials bag so tonight stays effortless.",
        load: "Follow the 3D Load scrubber from cab wall to rear door—heavy items on the floor, fragile on top.",
        drive: "Switch your phone nav app to Commercial Truck Mode, check tolls, and stay off no-truck parkways.",
        park_unload: "Reserve curb space for truck + ramp, watch awning clearance, and unload rear-to-cab (LIFO).",
        unpack: "Check off boxes room by room at your own pace until your very last item is unpacked.",
      };

      const stageDefs = [
        { id: "pack", label: "1 · Pack", cta: "QR Labels", act: () => document.querySelector("[data-tab='labels']")?.click() },
        { id: "load", label: "2 · Load", cta: "3D Load Order", act: () => document.getElementById("dir-load")?.click() },
        { id: "drive", label: "3 · Drive A→B", cta: "Live Route & Tolls", act: () => activateJourneyTab("route") },
        { id: "park_unload", label: "4 · Curb & Unload", cta: "Parking & LIFO", act: () => { document.getElementById("dir-unload")?.click(); activateJourneyTab("route"); } },
        { id: "unpack", label: total ? `5 · Unpack (${done}/${total})` : "5 · Unpack", done: total > 0 && done === total, cta: "Unpack Checklist", act: () => activateJourneyTab("unpack") },
      ];

      const activeDef = stageDefs.find((s) => s.id === state.stage) || stageDefs[2];
      const nudgeText =
        total > 0 && done === total && state.stage === "unpack"
          ? "🎉 Every single item is unpacked! Do a quick final sweep of the truck bed & fuel gauge before returning keys."
          : nudges[activeDef.id] || "";

      if (topJumpBtn) {
        topJumpBtn.innerHTML =
          total > 0 && done > 0
            ? `🛣️ Route · Unpack (${done}/${total})`
            : "🛣️ Route &amp; Unpack";
      }

      companionEl.innerHTML = `
        <div class="comp-top">
          <div class="comp-stages" role="group" aria-label="Move-day progress chapters">
            <span style="font-size:12px;font-weight:750;margin-right:4px">🧭 Move Co-Pilot:</span>
            ${stageDefs
              .map(
                (s) => `
              <button type="button" class="comp-stage-btn ${s.done ? "done" : ""}" data-stage-pick="${esc(s.id)}" aria-pressed="${String(s.id === state.stage)}">
                ${s.done ? "✓ " : ""}${esc(s.label)}
              </button>`
              )
              .join("")}
          </div>
          <button type="button" class="comp-quiet-btn" id="btn-comp-quiet" title="Hide or show guidance tips">
            ${state.quiet ? "Show tips ▾" : "Quiet mode ▴"}
          </button>
        </div>
        <div class="comp-nudge-row">
          <div class="comp-nudge-text"><b>Supportive tip:</b> ${esc(nudgeText)}</div>
          <button type="button" class="comp-cta" id="btn-comp-cta">${esc(activeDef.cta)} →</button>
        </div>
      `;

      companionEl.querySelectorAll("[data-stage-pick]").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.stage = btn.dataset.stagePick;
          state.quiet = false;
          persist();
          renderCompanionStrip();
          if (state.stage === "drive") activateJourneyTab("route");
          if (state.stage === "unpack") activateJourneyTab("unpack");
        });
      });

      document.getElementById("btn-comp-quiet")?.addEventListener("click", () => {
        state.quiet = !state.quiet;
        persist();
        renderCompanionStrip();
      });

      document.getElementById("btn-comp-cta")?.addEventListener("click", () => activeDef.act());
    }

    // ---------- Render Route & Unpack Tab Pane ----------
    function renderJourneyPane() {
      const { done, total, pct } = unpackCounts();
      const b = state.brief;

      const subBarHtml = `
        <div class="j-subbar" role="group" aria-label="Route Guide vs Unpack Tracker">
          <button type="button" class="j-subbtn" data-j-sub="route" aria-pressed="${String(state.subTab === "route")}">
            🛣️ Live A→B Route &amp; Parking
          </button>
          <button type="button" class="j-subbtn" data-j-sub="unpack" aria-pressed="${String(state.subTab === "unpack")}">
            📦 Unpack to Last Item (${done}/${total})
          </button>
        </div>
      `;

      let bodyHtml = "";
      if (state.subTab === "route") {
        const fl = b?.fleet || {};
        const dr = b?.drive || {};
        const nav = b?.nav_reminder || {};
        const selApp = nav.selected_app || {};
        const links = nav.links || {};
        const noTruck = b?.no_truck_roads?.warnings || [];
        const noTruckAi = b?.no_truck_roads?.ai_bullets || [];
        const tolls = b?.tolls || {};
        const parking = b?.parking || {};
        const wxD = b?.weather?.destination || {};
        const tfc = b?.traffic || {};

        bodyHtml = `
          <form class="addr-box" id="piu-route-form">
            <div class="addr-row">
              <span class="addr-dot a" title="Point A (Origin)">A</span>
              <input type="text" class="addr-input" id="inp-route-a" value="${esc(state.origin)}" placeholder="Point A origin street address, city, ZIP" aria-label="Origin address Point A">
            </div>
            <div class="addr-row">
              <span class="addr-dot b" title="Point B (Destination)">B</span>
              <input type="text" class="addr-input" id="inp-route-b" value="${esc(state.destination)}" placeholder="Point B destination street address, city, ZIP" aria-label="Destination address Point B">
            </div>
            <div class="addr-actions">
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <button type="button" class="btn sm" id="btn-route-swap" title="Swap Point A and Point B">⇅ Swap</button>
                <button type="button" class="btn sm" id="btn-route-refresh" title="Pull fresh real-time weather, traffic & routing">${state.loadingBrief ? "Updating…" : "↻ Live Refresh"}</button>
              </div>
              <button type="submit" class="btn sm primary" ${state.loadingBrief ? "disabled" : ""}>${state.loadingBrief ? "Pulling Live Data…" : "Check Truck Route"}</button>
            </div>
            <div class="preset-chips">
              ${QUICK_PRESETS.map(
                (p, idx) => `<button type="button" class="preset-chip" data-preset-idx="${idx}">${esc(p.label)}</button>`
              ).join("")}
            </div>
          </form>

          ${
            !b
              ? `<div class="live-banner">Pulling real-time routing, bridge clearances, tolls, weather &amp; traffic for your truck…</div>`
              : `
            <div class="live-banner">
              <div class="live-banner-head">
                <span>${esc(dr.calm_headline || "")}</span>
                <span class="small muted">${esc(fl.fleet_label || "")}</span>
              </div>
              <div style="color:var(--muted)">${esc(dr.route_summary || "")}</div>
              ${dr.weather_alert ? `<div class="warn-callout">🌬️ ${esc(dr.weather_alert)}</div>` : ""}
              <div class="live-chips">
                <span class="live-chip ok">● Live ${esc((b.fetched_at || "").split("T").pop())}</span>
                ${wxD.temp_f != null ? `<span class="live-chip">🌡️ Dest ${esc(wxD.temp_f)}°F · ${esc(wxD.condition)} · Gusts ${esc(wxD.gusts_mph)} mph</span>` : ""}
                ${tfc.avg_mph != null ? `<span class="live-chip">🚦 NYC DOT Sensors: ${esc(tfc.avg_mph)} mph</span>` : ""}
                ${b.decision?.choice ? `<span class="live-chip ${b.decision.choice.includes("reroute") ? "warn" : "ok"}">🎯 ${esc(b.decision.choice.replace(/_/g, " "))}${b.decision.confidence ? ` (${Math.round(b.decision.confidence * 100)}%)` : ""}</span>` : ""}
              </div>
              <div class="small muted" style="margin-top:5px;font-size:10.5px">
                Sources: ${esc((b.live_sources || []).join(" · "))}
              </div>
            </div>

            <!-- 1. Commercial Truck Mode Phone Reminder -->
            <div class="rt-card">
              <h3>
                <span>📱 1. Switch Phone Maps to Commercial Truck Mode</span>
                <span class="live-chip ${selApp.has_native_truck_mode ? "ok" : "warn"}">${esc(selApp.badge || "")}</span>
              </h3>
              <div class="small muted">Tap the maps app on your phone:</div>
              <div class="nav-app-grid">
                ${(nav.available_apps || [])
                  .map(
                    (a) => `
                  <button type="button" class="nav-app-pill" data-nav-app="${esc(a.id)}" aria-pressed="${String(a.id === state.navApp)}">
                    ${a.has_native_truck_mode ? "🚛 " : "🚗 "}${esc(a.name)}
                  </button>`
                  )
                  .join("")}
              </div>
              <div class="truck-spec-strip">
                <span>📐 ${esc(nav.truck_profile_card || "")}</span>
                <button type="button" class="preset-chip" id="btn-copy-specs">Copy specs</button>
              </div>
              <div class="${selApp.has_native_truck_mode ? "ok-callout" : "warn-callout"}">
                ${selApp.has_native_truck_mode ? "✅ " : "⚠️ "}<b>${esc(selApp.name)}:</b> ${esc(nav.tip || "")}
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:7px">
                <a class="btn sm" target="_blank" rel="noopener" href="${safeHref(links.google_maps)}">Open Google Maps</a>
                <a class="btn sm" target="_blank" rel="noopener" href="${safeHref(links.google_maps_no_tolls)}">Avoid Tolls Link</a>
                <a class="btn sm" target="_blank" rel="noopener" href="${safeHref(links.apple_maps)}">Apple Maps</a>
                <a class="btn sm" target="_blank" rel="noopener" href="${safeHref(links.waze)}">Waze</a>
              </div>
            </div>

            <!-- 2. Roads That Can't Have Trucks & Low Clearances -->
            <div class="rt-card">
              <h3>
                <span>🚫 2. No-Truck Roads &amp; Roof Clearances</span>
                <span class="live-chip">${esc(fl.ext_height_label || "12' 0\"")} Roof</span>
              </h3>
              ${noTruck
                .map(
                  (w) => `
                <div class="no-truck-item ${w.severity === "critical" ? "critical" : "watch"}">
                  <div style="display:flex;justify-content:space-between;gap:6px;font-weight:700">
                    <span>${w.severity === "critical" ? "🛑 " : "⚠️ "}${esc(w.road)}</span>
                    <span class="small muted">${esc(w.detected_on)}</span>
                  </div>
                  <div style="margin-top:2px;color:var(--muted)">${esc(w.reason)}</div>
                  <div style="margin-top:3px"><b>Safe Truck Route:</b> ${esc(w.safe_alternative)}</div>
                </div>`
                )
                .join("")}
              ${
                noTruckAi.length
                  ? `<ul class="rt-list">${noTruckAi.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
                  : ""
              }
            </div>

            <!-- 3. Tolls & Congestion Zone -->
            <div class="rt-card">
              <h3>
                <span>💳 3. Tolls &amp; Axle Class</span>
                <span class="live-chip">${esc(tolls.toll_class || "")}</span>
              </h3>
              ${(tolls.items || [])
                .map(
                  (t) => `
                <div style="margin-bottom:6px;padding-bottom:6px;border-bottom:1px dashed var(--line)">
                  <div style="display:flex;justify-content:space-between;gap:6px;font-weight:700">
                    <span>${esc(t.name)}</span>
                    <span style="color:var(--accent)">${esc(t.estimate)}</span>
                  </div>
                  <div class="small muted">${esc(t.note)}</div>
                </div>`
                )
                .join("")}
              ${
                (tolls.ai_bullets || []).length
                  ? `<ul class="rt-list">${tolls.ai_bullets.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
                  : ""
              }
              <div class="small muted" style="margin-top:4px">💡 ${esc(tolls.rental_plate_tip || "")}</div>
            </div>

            <!-- 4. City Parking & Curb Survival Tips -->
            <div class="rt-card">
              <h3>
                <span>🅿️ 4. Parking &amp; Unloading at Point B</span>
                <span class="live-chip">${esc(parking.context_badge || "")}</span>
              </h3>
              <ul class="rt-list">
                ${((parking.ai_bullets && parking.ai_bullets.length ? parking.ai_bullets : parking.tips) || [])
                  .map((tip) => `<li>${esc(tip)}</li>`)
                  .join("")}
              </ul>
            </div>
          `
          }
        `;
      } else {
        // ---------- Sub-Tab 2: Calm Unpack-to-Last-Item Companion ----------
        const items = allPlanItems();
        const q = state.searchQuery.trim().toLowerCase();
        const filtered = q
          ? items.filter((it) =>
              `${it.label || ""} ${it.contents || ""} ${it.box_short_name || ""} ${it.dest_zone_name || ""} ${it.dest_corner || ""} ${it.room_name || ""}`
                .toLowerCase()
                .includes(q)
            )
          : items;

        // Group by Destination Zone / Room
        const byZone = new Map();
        for (const it of filtered) {
          const zKey = it.dest_zone_name || it.room_name || "Destination Room";
          if (!byZone.has(zKey)) byZone.set(zKey, []);
          byZone.get(zKey).push(it);
        }

        bodyHtml = `
          ${
            total > 0 && done === total
              ? `
            <div class="unpack-done-card">
              <div style="font-size:22px;margin-bottom:4px">🏡</div>
              <div style="font-weight:800;font-size:15px">You unpacked your very last item!</div>
              <div class="small muted" style="margin-top:4px">
                Final easy wrap-up: walk the empty truck bed once for hardware/pads, snap a photo of the fuel gauge &amp; swept floor at drop-off, and flatten boxes to pass along.
              </div>
            </div>`
              : ""
          }

          <div class="unpack-prog-card">
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">
              <span style="font-weight:750;font-size:13.5px">Unpack Progress · ${done} of ${total} items settled</span>
              <span class="small muted">${total - done === 0 ? "All done!" : `${total - done} left`} (${pct}%)</span>
            </div>
            <div class="unpack-bar"><i style="width:${pct}%"></i></div>
            <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:6px;margin-top:8px">
              <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="chk-essentials" ${state.essentialsDone ? "checked" : ""}>
                <span>🌙 Night-One Essentials tote opened (chargers, bedding, kettle, bolts)</span>
              </label>
              ${
                done > 0
                  ? `<button type="button" class="comp-quiet-btn" id="btn-reset-unpack">Reset checks</button>`
                  : ""
              }
            </div>
          </div>

          <div style="margin-bottom:9px">
            <input type="search" class="addr-input" id="inp-unpack-search" value="${esc(state.searchQuery)}" placeholder="🔍 Find any item or box ('chairs', 'monitor', 'kitchen', 'Lounge A')…">
          </div>

          <div id="unpack-rooms-host">
            ${
              Array.from(byZone.entries())
                .map(([zoneName, zItems], zIdx) => {
                  const zDone = zItems.filter((i) => state.unpackedIds.has(i.id)).length;
                  const allZDone = zItems.length > 0 && zDone === zItems.length;
                  return `
                  <details class="unpack-room" ${zIdx < 2 || q ? "open" : ""}>
                    <summary>
                      <span>${allZDone ? "✅ " : "📦 "}${esc(zoneName)} <span class="small muted" style="font-weight:500">(${zDone}/${zItems.length})</span></span>
                      <button type="button" class="preset-chip" data-toggle-room="${esc(zoneName)}">
                        ${allZDone ? "Undo room" : "Mark room unpacked"}
                      </button>
                    </summary>
                    <div class="unpack-items">
                      ${zItems
                        .map((it) => {
                          const isChecked = state.unpackedIds.has(it.id);
                          return `
                          <label class="unpack-row ${isChecked ? "checked" : ""}">
                            <input type="checkbox" data-unpack-id="${esc(it.id)}" ${isChecked ? "checked" : ""}>
                            <div style="flex:1;min-width:0">
                              <div style="font-weight:650">
                                ${esc(it.box_short_name ? `[${it.box_short_name}] ` : "")}${esc(it.label)}
                                ${it.fragile ? `<span class="lift-tag fragile">Fragile</span>` : ""}
                              </div>
                              <div class="small muted">
                                Place: <b>${esc(it.dest_corner || "Center Floor")}</b> · Truck ${it._truckIdx + 1} Unload #${esc(it.unload_seq || "–")}
                                ${it.contents ? ` · In box: ${esc(String(it.contents).slice(0, 60))}` : ""}
                              </div>
                            </div>
                          </label>`;
                        })
                        .join("")}
                    </div>
                  </details>`;
                })
                .join("") || `<p class="small muted">No matching items in this move plan.</p>`
            }
          </div>
        `;
      }

      journeyPane.innerHTML = subBarHtml + bodyHtml;

      // Wire sub-bar buttons
      journeyPane.querySelectorAll("[data-j-sub]").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.subTab = btn.dataset.jSub;
          if (state.subTab === "unpack") state.stage = "unpack";
          persist();
          renderCompanionStrip();
          renderJourneyPane();
        });
      });

      if (state.subTab === "route") {
        const form = document.getElementById("piu-route-form");
        form?.addEventListener("submit", (e) => {
          e.preventDefault();
          state.origin = document.getElementById("inp-route-a")?.value || DEFAULT_ORIGIN;
          state.destination = document.getElementById("inp-route-b")?.value || DEFAULT_DEST;
          persist();
          fetchLiveRouteBrief(false);
        });

        document.getElementById("btn-route-swap")?.addEventListener("click", () => {
          const a = document.getElementById("inp-route-a")?.value || state.origin;
          const bVal = document.getElementById("inp-route-b")?.value || state.destination;
          state.origin = bVal;
          state.destination = a;
          persist();
          fetchLiveRouteBrief(false);
        });

        document.getElementById("btn-route-refresh")?.addEventListener("click", () => {
          state.origin = document.getElementById("inp-route-a")?.value || state.origin;
          state.destination = document.getElementById("inp-route-b")?.value || state.destination;
          persist();
          fetchLiveRouteBrief(true);
        });

        journeyPane.querySelectorAll("[data-preset-idx]").forEach((chip) => {
          chip.addEventListener("click", () => {
            const p = QUICK_PRESETS[Number(chip.dataset.presetIdx)];
            if (!p) return;
            state.origin = p.origin;
            state.destination = p.destination;
            persist();
            fetchLiveRouteBrief(false);
          });
        });

        journeyPane.querySelectorAll("[data-nav-app]").forEach((pill) => {
          pill.addEventListener("click", () => {
            state.navApp = pill.dataset.navApp;
            persist();
            fetchLiveRouteBrief(false);
          });
        });

        document.getElementById("btn-copy-specs")?.addEventListener("click", (e) => {
          const txt = b?.nav_reminder?.truck_profile_card || "";
          if (navigator.clipboard && txt) {
            navigator.clipboard.writeText(txt).catch(() => {});
            e.currentTarget.textContent = "Copied ✓";
            setTimeout(() => {
              const el = document.getElementById("btn-copy-specs");
              if (el) el.textContent = "Copy specs";
            }, 1500);
          }
        });
      } else {
        document.getElementById("chk-essentials")?.addEventListener("change", (e) => {
          state.essentialsDone = e.target.checked;
          persist();
        });

        document.getElementById("btn-reset-unpack")?.addEventListener("click", () => {
          state.unpackedIds.clear();
          state.essentialsDone = false;
          persist();
          renderCompanionStrip();
          renderJourneyPane();
          syncJourneyTabLabel();
        });

        const searchEl = document.getElementById("inp-unpack-search");
        searchEl?.addEventListener("input", (e) => {
          const pos = e.target.selectionStart;
          state.searchQuery = e.target.value;
          renderJourneyPane();
          const nextEl = document.getElementById("inp-unpack-search");
          if (nextEl) {
            nextEl.focus();
            try { nextEl.setSelectionRange(pos, pos); } catch (err) { /* ignore */ }
          }
        });

        journeyPane.querySelectorAll("[data-unpack-id]").forEach((chk) => {
          chk.addEventListener("change", () => {
            const id = chk.dataset.unpackId;
            if (chk.checked) state.unpackedIds.add(id);
            else state.unpackedIds.delete(id);
            state.stage = "unpack";
            persist();
            renderCompanionStrip();
            renderJourneyPane();
            syncJourneyTabLabel();
          });
        });

        journeyPane.querySelectorAll("[data-toggle-room]").forEach((btn) => {
          btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const roomName = btn.dataset.toggleRoom;
            const roomItems = allPlanItems().filter(
              (it) => (it.dest_zone_name || it.room_name || "Destination Room") === roomName
            );
            const allDone = roomItems.every((it) => state.unpackedIds.has(it.id));
            for (const it of roomItems) {
              if (allDone) state.unpackedIds.delete(it.id);
              else state.unpackedIds.add(it.id);
            }
            state.stage = "unpack";
            persist();
            renderCompanionStrip();
            renderJourneyPane();
            syncJourneyTabLabel();
          });
        });
      }
    }

    function syncJourneyTabLabel() {
      const { done, total } = unpackCounts();
      journeyTabBtn.textContent =
        total > 0 && done > 0 ? `🛣️ Route · Unpack (${done}/${total})` : "🛣️ Route & Unpack";
    }

    // ---------- Fetch Live Route Brief (FastAPI -> Browser Live Fallback) ----------
    let reqCounter = 0;
    async function fetchLiveRouteBrief(forceRefresh = false) {
      const myReq = ++reqCounter;
      state.loadingBrief = true;
      if (!journeyPane.classList.contains("hidden") && state.subTab === "route") {
        renderJourneyPane();
      }

      const selTruckEl = document.getElementById("sel-truck");
      const truckId = selTruckEl?.value || state.plan?.trucks?.[0]?.truck_id || "uhaul_26";

      try {
        let data = null;
        if (!piu.MOCK) {
          try {
            const res = await origFetch(`${piu.API_BASE || ""}/route/brief`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                run_id: runId,
                plan: state.plan,
                origin: state.origin,
                destination: state.destination,
                truck_id: truckId,
                nav_app: state.navApp,
                refresh: forceRefresh,
              }),
            });
            if (res.ok) data = await res.json();
          } catch (e) { /* fall through to browser live fetch */ }
        }
        if (!data) {
          data = await buildBrowserLiveBrief({
            origin: state.origin,
            destination: state.destination,
            plan: state.plan,
            truckId,
            navApp: state.navApp,
          });
        }
        if (myReq !== reqCounter) return;
        state.brief = data;
      } finally {
        if (myReq === reqCounter) {
          state.loadingBrief = false;
          renderCompanionStrip();
          updateUnloadFooterTip();
          syncJourneyTabLabel();
          if (!journeyPane.classList.contains("hidden")) {
            renderJourneyPane();
          }
        }
      }
    }

    // One plan reaches setPlan twice: from the /solve hook below and from index.html's own call.
    // Ask for the route brief once per distinct plan, not once per caller (FAILURES.md 15:18).
    function planSignature(p) {
      const s = p.summary || {};
      return JSON.stringify([
        p.run_id, p.strategy || null, (p.trucks || []).map((t) => [t.truck_id, (t.items || []).length]),
        s.total_items, s.total_weight_lb, p.score && p.score.total,
      ]);
    }
    let briefPlanSig = null;
    let firstBriefTimer = null;

    function setPlan(newPlan) {
      if (!newPlan || !Array.isArray(newPlan.trucks)) return;
      state.plan = newPlan;
      renderCompanionStrip();
      syncJourneyTabLabel();
      const sig = planSignature(newPlan);
      if (sig === briefPlanSig) return;
      briefPlanSig = sig;
      clearTimeout(firstBriefTimer);
      fetchLiveRouteBrief(false);
    }

    // Hook into `/solve` fetch responses (and sync with Load/Unload scrubber clicks gently!)
    const origFetch = window.fetch.bind(window);
    window.fetch = async function (...args) {
      const res = await origFetch(...args);
      try {
        const url = String(typeof args[0] === "string" ? args[0] : (args[0] && args[0].url) || "");
        if (res.ok && /\/solve(\b|\/|\?)/.test(url)) {
          res.clone().json().then((planJson) => setPlan(planJson)).catch(() => {});
        }
      } catch (e) { /* never interfere with caller */ }
      return res;
    };

    // Gently sync companion stage when user switches Load vs Unload scrubber (without stealing focus!)
    document.getElementById("dir-load")?.addEventListener("click", () => {
      if (state.stage !== "load") {
        state.stage = "load";
        persist();
        renderCompanionStrip();
      }
    });
    document.getElementById("dir-unload")?.addEventListener("click", () => {
      if (state.stage !== "park_unload") {
        state.stage = "park_unload";
        persist();
        renderCompanionStrip();
      }
    });

    // Initial render. The first plan normally arrives within a second or two and asks for the brief
    // itself (setPlan); asking here as well sent a second, plan-less request on every page load.
    // If no plan has come after 4 s (inventory still processing), ask without one.
    renderCompanionStrip();
    firstBriefTimer = setTimeout(() => { if (!briefPlanSig) fetchLiveRouteBrief(false); }, 4000);

    window.PIU_JOURNEY = { setPlan, refreshRoute: () => fetchLiveRouteBrief(true), openTab: activateJourneyTab };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountMoveJourney);
  } else {
    setTimeout(mountMoveJourney, 0);
  }
})();
