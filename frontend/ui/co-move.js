/* Human + Robot Co-Move Biomechanics, Penn Station Occupancy Envelope,
 * and live `gemini-robotics-er-2-preview` (`v1beta`) `[y, x]` Spatial Scanner.
 *
 * Works seamlessly against FastAPI (`/co-move/analyze`, `/co-move/scan`)
 * AND in zero-server `?mock=1` browser mode.
 */
(function () {
  "use strict";

  const params = new URLSearchParams(location.search);
  const MOCK = params.get("mock") === "1";
  const API_BASE = (params.get("api") || "").replace(/\/+$/, "") || location.origin;
  const runId =
    params.get("run_id") ||
    (window.PIU && window.PIU.lastRun && window.PIU.lastRun()) ||
    "sample_venue";

  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);

  const PENN_CTX_JS = {
    penn_merch_kiosk: { gross: 936, fixtures: "Amtrak kiosks, 9th Ave turnstiles & 8-ft entry lane", aisle: 44, elev: false },
    penn_cafe: { gross: 2560, fixtures: "Fixed marble espresso bar, POS island & Food Hall queue rails", aisle: 44, elev: false },
    penn_bookshop: { gross: 1980, fixtures: "Built-in Hudson wall shelving, cash wrap & LIRR flow lane", aisle: 44, elev: false },
    penn_tech_hub: { gross: 2856, fixtures: "1912 steel columns, glass mullions & 31st St Arcade walkway", aisle: 48, elev: false },
    penn_lounge: { gross: 3024, fixtures: "Balcony balustrade, reception desk & +20 ft freight elevator", aisle: 48, elev: true },
    penn_concourse: { gross: 30452, fixtures: "Track 5–16 escalators, departure totems, FDNY 96\" fire lanes & 400k riders", aisle: 96, elev: false },
  };

  const OCC_MODES_JS = {
    permitted_bays: { clutter: 0.0, aisle: 0.28, window: "MTA Off-Peak Freight Window (11:00 PM – 5:00 AM · W 31st St Service Dock)" },
    crowded_stalls_35: { clutter: 0.35, aisle: 0.22, window: "Staged Night Load-In + Pre-Cleared Tenant Corners" },
    rush_hour_55: { clutter: 0.55, aisle: 0.18, window: "Restricted Daytime Window — Hold Overflow on Dock AMR Carts" },
  };

  let latestPlan = null;
  let currentAnalysis = null;
  let activeTab = "ergo";
  let occMode = "permitted_bays";
  let scanState = { loading: false, error: null, result: null, target: "origin" };

  // Local instant analyzer so UI updates in 0ms and works offline in `?mock=1`
  function analyzeLocal(plan, modeKey) {
    if (!plan || !Array.isArray(plan.trucks)) return null;
    const mode = OCC_MODES_JS[modeKey] || OCC_MODES_JS.permitted_bays;
    const zoneDoors = {};
    (plan.zones || []).forEach((z) => {
      zoneDoors[z.zone_id] = z.door_in || [36, 80];
    });

    const buckets = {
      dock_robot: { role: "dock_robot", label: "Dock Unloader Robot", count: 0, weight_lb: 0, examples: [] },
      amr_cart: { role: "amr_cart", label: "Concourse AMR Cart", count: 0, weight_lb: 0, examples: [] },
      stair_dolly: { role: "stair_dolly", label: "Tracked Gyro Dolly", count: 0, weight_lb: 0, examples: [] },
      human_ergo: { role: "human_ergo", label: "Human Biomechanics Crew", count: 0, weight_lb: 0, examples: [] },
    };

    let totalItems = 0;
    let totalWeight = 0;
    const overweightBoxes = [];
    const fatigueStreaks = [];
    const doorwayPlaybook = [];
    const seenDoor = new Set();

    (plan.trucks || []).forEach((t, idx) => {
      const ordered = [...(t.items || [])].sort((a, b) => (a.load_seq || 0) - (b.load_seq || 0));
      let consec = 0;
      let streak = [];

      ordered.forEach((it) => {
        totalItems++;
        const wt = Number(it.weight_lb || 0);
        totalWeight += wt;
        const key = `${it.catalog_id || ""} ${it.label || ""}`.toLowerCase();
        const dims = (it.orig_dims_in || it.size_in || [20, 20, 20]).map(Number);
        const maxD = Math.max(...dims);
        let role = "human_ergo";
        let gear = "2-Person Forearm Straps + Sliders (hip-hinge, zero twist)";

        if (it.is_box && wt <= 50 && !it.fragile) {
          role = "dock_robot";
          gear = "Vacuum-gripper truck unloader -> AMR shuttle";
        } else if (
          (it.is_box && wt <= 50 && it.fragile) ||
          key.includes("pelican_1510") ||
          (!it.is_box && wt <= 42 && maxD <= 36 && !/(lamp|plant|mirror|art|frame|chair|stool|pouf)/.test(key))
        ) {
          role = "amr_cart";
          gear = "Shock-damped autonomous concourse flatbed cart";
        } else if (
          (/(pelican_1650|pelican|safe|refrigerator|fridge|washer|dryer|filing|cabinet|appliance|printer|crate)/.test(key) ||
            (it.is_box && wt > 50)) &&
          !it.load_on_edge
        ) {
          role = "stair_dolly";
          gear = "Motorized rubber-track dolly w/ auto-brake (XSTO class)";
        } else if (/(c_stand|magliner|cart)/.test(key)) {
          gear = "Roll on locked casters + ramp spotter";
        } else if (wt < 65 && !it.two_person) {
          gear = it.fragile || it.load_on_edge ? "Cotton pad + vertical edge handles" : "Close-to-core carry (step feet to turn)";
        }

        const b = buckets[role];
        b.count++;
        b.weight_lb = Math.round((b.weight_lb + wt) * 10) / 10;
        const lbl = it.label || it.id || "item";
        if (b.examples.length < 3 && !b.examples.includes(lbl)) b.examples.push(lbl);

        if (it.is_box && wt > 40) {
          overweightBoxes.push({ label: lbl, weight_lb: wt, fix: `Split into 2 small boxes (~${Math.round(wt / 2)} lb) under 40 lb target.` });
        }
        if (role === "human_ergo" && wt >= 65) {
          consec++;
          streak.push(`${lbl} (${Math.round(wt)} lb)`);
          if (consec === 3) {
            fatigueStreaks.push({ truck: idx + 1, items: [...streak], advice: "Insert a robot box batch or 90s micro-break after 2 heavy lifts." });
          }
        } else {
          consec = 0;
          streak = [];
        }

        if (!it.is_box && (maxD >= 34 || wt >= 55 || it.two_person)) {
          const sig = `${lbl}:${it.dest_zone}`;
          if (!seenDoor.has(sig)) {
            seenDoor.add(sig);
            const dDoor = zoneDoors[it.dest_zone] || [36, 80];
            const dw = Math.min(32, Number(dDoor[0] || 36));
            const dh = Math.min(80, Number(dDoor[1] || 80));
            const [s0, s1] = [...dims].sort((a, b2) => a - b2);
            const minPlan = Math.min(dims[0], dims[1]);
            const dis = Boolean(it.disassemble) || /(dining_table|communal|conference|bed_|desk)/.test(key);
            const diag = Math.hypot(dw, dh) * 0.9;
            let status = "straight_walk_in";
            let badge = "Straight Walk-In";
            let instruction = `Clears ${dw}"×${dh}" door upright (${Math.round(dw - minPlan)}" knuckle margin).`;

            if (dims[2] <= dh - 1 && minPlan <= dw - 2) {
              // keep straight_walk_in
            } else if (dis && s0 <= dw - 2) {
              status = "unbolt_legs_first";
              badge = "Unbolt Legs First";
              instruction = `Unbolt legs before lifting -> carry slab on edge through ${dw}" door; tape Ziploc bolt bag underneath.`;
            } else if (!it.must_stay_upright && s0 <= dw + 1.5 && s1 <= diag) {
              const deg = Math.round((Math.atan2(dw, dh) * 180) / Math.PI);
              status = "diagonal_tilt_pivot";
              badge = `Tilt ${deg}° & Pivot`;
              instruction = `Angle ~${deg}° into frame diagonal (${Math.round(diag)}" diag); Person B leads bottom corner.`;
            } else if (s0 <= dw && s1 <= dh) {
              status = "tight_clearance";
              badge = "Tight (<2\" Margin)";
              instruction = `Wrap corners in cotton pads; pop interior door hinge pins (+1.75") if snug.`;
            } else {
              status = "hinge_pin_or_reroute";
              badge = "Double Freight Door";
              instruction = `Route via W 31st St double freight doors or knock down frame prior to move.`;
            }
            doorwayPlaybook.push({
              label: lbl,
              weight_lb: Math.round(wt),
              dims_in: dims.map((d) => Math.round(d)),
              dest_zone_name: it.dest_zone_name || it.dest_zone || "Penn Station",
              handler_label: b.label,
              gear,
              status,
              badge,
              instruction,
            });
          }
        }
      });
    });

    const rank = { hinge_pin_or_reroute: 0, unbolt_legs_first: 1, diagonal_tilt_pivot: 2, tight_clearance: 3, straight_walk_in: 4 };
    doorwayPlaybook.sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || b.weight_lb - a.weight_lb);

    // Penn occupancy audit
    let totalGross = 41808;
    let totalPermitted = 0;
    let totalNetClear = 0;
    let totalPlaced = 0;
    let overflowCount = 0;
    let loungeWt = 0;

    const zones = (plan.zones || []).map((z) => {
      const ctx = PENN_CTX_JS[z.zone_id] || PENN_CTX_JS.penn_concourse;
      const zDims = z.dims_in || [240, 180, 108];
      const permSqft = Math.round(((zDims[0] * zDims[1]) / 144) * 10) / 10;
      const usableRatio = Math.max(0.2, 1 - mode.clutter - mode.aisle);
      const netClear = Math.round(permSqft * usableRatio * 10) / 10;
      let floorSqin = 0;
      const groundItems = [];
      (z.items || []).forEach((it) => {
        const pos = it.pos_in || [0, 0, 0];
        const sz = it.size_in || [18, 18, 16];
        if (Number(pos[2] || 0) <= 1.0) {
          floorSqin += Number(sz[0]) * Number(sz[1]);
          groundItems.push(it);
        }
      });
      if (z.zone_id === "penn_lounge") loungeWt += Number(z.total_weight_lb || 0);
      const placedSqft = Math.round((floorSqin / 144) * 10) / 10;
      totalPermitted += permSqft;
      totalNetClear += netClear;
      totalPlaced += placedSqft;
      const fits = placedSqft <= netClear + 0.5;
      const overflowItems = [];
      if (!fits) {
        overflowCount++;
        let acc = 0;
        const need = placedSqft - netClear;
        groundItems
          .sort((a, b) => Number(Boolean(b.is_box)) - Number(Boolean(a.is_box)))
          .forEach((gi) => {
            if (acc < need && overflowItems.length < 3) {
              overflowItems.push(gi.label || gi.id);
              acc += ((gi.size_in?.[0] || 18) * (gi.size_in?.[1] || 18)) / 144;
            }
          });
      }
      return {
        zone_id: z.zone_id,
        name: z.name || z.zone_id,
        dock_stop: z.dock_stop || 6,
        gross_wing_sqft: ctx.gross,
        permitted_bay_sqft: permSqft,
        net_clear_sqft: netClear,
        placed_floor_sqft: placedSqft,
        fill_of_clear_pct: Math.round((placedSqft / Math.max(1, netClear)) * 1000) / 10,
        fits_occupied_space: fits,
        existing_fixtures: ctx.fixtures,
        egress_aisle_in: ctx.aisle,
        requires_freight_elevator: ctx.elev,
        overflow_reroute_items: overflowItems,
      };
    }).sort((a, b) => a.dock_stop - b.dock_stop);

    const offloadedLb = Math.round((buckets.dock_robot.weight_lb + buckets.amr_cart.weight_lb + buckets.stair_dolly.weight_lb) * 10) / 10;
    const offloadedPct = Math.round((offloadedLb / Math.max(1, totalWeight)) * 1000) / 10;
    const untouchedSqft = Math.round(totalGross - totalPermitted);
    const untouchedPct = Math.round((untouchedSqft / totalGross) * 1000) / 10;
    const ergoScore = Math.max(62, Math.min(100, 100 - overweightBoxes.length * 4 - fatigueStreaks.length * 7));

    return {
      total_items: totalItems,
      total_weight_lb: Math.round(totalWeight),
      offloaded_weight_lb: offloadedLb,
      offloaded_pct: offloadedPct,
      ergo_score: ergoScore,
      overweight_boxes: overweightBoxes.slice(0, 4),
      fatigue_streaks: fatigueStreaks.slice(0, 3),
      roles: Object.values(buckets),
      doorway_playbook: doorwayPlaybook.slice(0, 5),
      penn_occupancy: {
        occupancy_mode: modeKey,
        load_window: mode.window,
        gross_station_sqft: totalGross,
        untouched_station_sqft: untouchedSqft,
        untouched_station_pct: untouchedPct,
        permitted_bays_sqft: Math.round(totalPermitted),
        net_clear_floor_sqft: Math.round(totalNetClear),
        placed_floor_sqft: Math.round(totalPlaced),
        all_bays_clear: overflowCount === 0,
        overflow_zone_count: overflowCount,
        mezzanine_elevator_trips: loungeWt > 0 ? Math.max(1, Math.ceil(loungeWt / 3375)) : 0,
        mezzanine_elevator_ok: true,
        zones,
      },
    };
  }

  function makeMockScan(target) {
    // Crisp SVG data URL + realistic `[y, x]` coordinates for offline `?mock=1`
    const svg =
      target === "destination"
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
            <rect width="800" height="450" fill="#eef2f7"/>
            <rect x="20" y="18" width="760" height="105" rx="8" fill="#dbe4f0" stroke="#7c8ea6" stroke-width="2"/>
            <text x="42" y="76" font-family="system-ui" font-size="16" font-weight="700" fill="#334155">ACTIVE MOYNIHAN COMMUTER CONCOURSE &amp; 96" FIRE LANE (KEEP CLEAR)</text>
            <rect x="555" y="34" width="205" height="72" rx="6" fill="#c3d0e3" stroke="#5b6d86"/>
            <text x="572" y="75" font-family="system-ui" font-size="13" font-weight="600" fill="#1e293b">TRACK 9–10 ESCALATOR</text>
            <rect x="30" y="152" width="235" height="270" rx="8" fill="#dfd2c3" stroke="#8c6d4f" stroke-width="2"/>
            <text x="56" y="290" font-family="system-ui" font-size="15" font-weight="700" fill="#4a3520">EXISTING ESPRESSO BAR</text>
            <circle cx="315" cy="195" r="30" fill="#f3b67f" stroke="#b45309" stroke-width="2"/>
            <text x="292" y="200" font-family="system-ui" font-size="11" font-weight="700" fill="#7c2d12">A-FRAME</text>
            <rect x="380" y="155" width="390" height="268" rx="10" fill="#d9f2e4" stroke="#15803d" stroke-width="2.5" stroke-dasharray="7 5"/>
            <text x="430" y="292" font-family="system-ui" font-size="15" font-weight="700" fill="#14532d">PERMITTED POP-UP STAGING FLOOR</text>
          </svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
            <rect width="800" height="450" fill="#f5f2eb"/>
            <rect x="20" y="20" width="760" height="410" rx="8" fill="none" stroke="#8b8378" stroke-width="3"/>
            <rect x="665" y="16" width="95" height="16" fill="#16a34a"/>
            <text x="662" y="48" font-family="system-ui" font-size="12" font-weight="700" fill="#15803d">32" EXIT DOOR</text>
            <rect x="52" y="80" width="190" height="255" rx="10" fill="#cbb7a4" stroke="#6b5340" stroke-width="2"/>
            <text x="76" y="212" font-family="system-ui" font-size="14" font-weight="700" fill="#3e2c1e">BOUCLE SOFA (185 lb)</text>
            <rect x="305" y="268" width="305" height="130" rx="8" fill="#ded6c8" stroke="#78716c" stroke-width="2"/>
            <text x="348" y="338" font-family="system-ui" font-size="14" font-weight="700" fill="#44403c">COMMUNAL TABLE (UNBOLT LEGS)</text>
            <circle cx="575" cy="145" r="28" fill="#f5b17b" stroke="#c2410c" stroke-width="2"/>
            <text x="553" y="149" font-family="system-ui" font-size="11" font-weight="700" fill="#7c2d12">POUF 1</text>
            <rect x="320" y="72" width="185" height="62" rx="6" fill="#e2be87" stroke="#92400e" stroke-width="2"/>
            <text x="345" y="108" font-family="system-ui" font-size="13" font-weight="700" fill="#78350f">3 × SEALED BOXES (32 lb)</text>
          </svg>`;

    return {
      target,
      model: "gemini-robotics-er-2-preview (mock)",
      via: "mock_offline",
      preview_data_url: "data:image/svg+xml;base64," + btoa(svg),
      scene_summary:
        target === "destination"
          ? "Keep 96-in commuter concourse & existing espresso counter clear; relocate A-frame sign first, then stage AMR cart inside right-hand permitted bay."
          : "Clear blocking pouf near 32-in exit door first, dispatch robot/AMR for 32 lb box stack, then use 2-person forearm straps on bouclé sofa.",
      waypoints:
        target === "destination"
          ? [
              { step: 1, kind: "keep_out", point: [160, 380], label: "Commuter Concourse & Escalator", instruction: "Active 96-in FDNY egress lane — zero staging or cart parking." },
              { step: 2, kind: "keep_out", point: [640, 185], label: "Existing Espresso Counter", instruction: "Fixed tenant marble counter — maintain 44-in customer clearance." },
              { step: 3, kind: "clear_first", point: [433, 394], label: "Movable A-Frame Sign", instruction: "Fold and tuck aside before rolling AMR concourse cart in." },
              { step: 4, kind: "stage_zone", point: [645, 715], label: "Permitted Pop-Up Floor", instruction: "Stage incoming AMR cart & café stools inside dashed lease boundary." },
            ]
          : [
              { step: 1, kind: "clear_first", point: [322, 718], label: "Floor Pouf Blocking Exit", instruction: "Carry out first so 2-person crew has a clean line to 32-in doorway." },
              { step: 2, kind: "robot_pick", point: [228, 515], label: "32 lb Sealed Box Stack", instruction: "Assign to Dock Unloader Robot + padded AMR shuttle cart." },
              { step: 3, kind: "human_grip", point: [470, 185], label: "Bouclé Sofa Base Grips (A+B)", instruction: "2-person forearm straps under hardwood frame; hip-hinge, tilt 22° at door." },
              { step: 4, kind: "human_grip", point: [740, 570], label: "Communal Table Frame", instruction: "Unbolt legs first, tape hardware bag underneath, carry top on edge." },
            ],
    };
  }

  function ensureUnifiedTabs() {
    const ORDER = ["unload", "stores", "labels", "crew", "journey", "shop"];
    const SHORT_NAMES = {
      unload: ["Unload", "LIFO Truck Unload Order"],
      stores: ["Stores", "Penn Station Storefronts"],
      labels: ["QR", "Printable Offline QR Box Labels"],
    };
    if (!window.PIU_ACTIVATE_TAB) {
      window.PIU_ACTIVATE_TAB = function (tabKey, extra) {
        const tabBar = document.querySelector(".tab-bar[role='tablist']");
        if (!tabBar) return;
        tabBar.querySelectorAll("[role='tab']").forEach((btn) => {
          btn.setAttribute("aria-selected", String(btn.dataset.tab === tabKey));
        });
        ORDER.forEach((k) => {
          const pane = document.getElementById("tab-" + k);
          if (pane) pane.classList.toggle("hidden", k !== tabKey);
        });
        window.dispatchEvent(new CustomEvent("piu:tabchange", { detail: { tab: tabKey, ...(extra || {}) } }));
      };
    }
    if (!window.PIU_REGISTER_TAB) {
      window.PIU_REGISTER_TAB = function (tabKey, label, title) {
        const tabBar = document.querySelector(".tab-bar[role='tablist']");
        const hostCard = tabBar && tabBar.parentNode;
        if (!tabBar || !hostCard) return null;

        Object.entries(SHORT_NAMES).forEach(([k, [txt, ttl]]) => {
          const b = tabBar.querySelector(`[data-tab='${k}']`);
          if (b) {
            b.textContent = txt;
            if (!b.title) b.title = ttl;
          }
        });

        let btn = tabBar.querySelector(`[data-tab='${tabKey}']`);
        if (!btn) {
          btn = document.createElement("button");
          btn.type = "button";
          btn.setAttribute("role", "tab");
          btn.dataset.tab = tabKey;
          btn.setAttribute("aria-selected", "false");
          tabBar.appendChild(btn);
        }
        btn.textContent = label;
        if (title) btn.title = title;

        const buttons = Array.from(tabBar.querySelectorAll("[role='tab']"));
        buttons
          .sort((a, b) => {
            const ia = ORDER.indexOf(a.dataset.tab);
            const ib = ORDER.indexOf(b.dataset.tab);
            return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
          })
          .forEach((b) => tabBar.appendChild(b));

        let pane = document.getElementById("tab-" + tabKey);
        if (!pane) {
          pane = document.createElement("div");
          pane.id = "tab-" + tabKey;
          pane.className = "hidden";
          hostCard.appendChild(pane);
        }

        if (!tabBar.dataset.piuUnified) {
          tabBar.dataset.piuUnified = "1";
          tabBar.addEventListener("click", (e) => {
            const clicked = e.target.closest("[role='tab']");
            if (!clicked || !clicked.dataset.tab) return;
            window.PIU_ACTIVATE_TAB(clicked.dataset.tab);
          });
        }
        return { btn, pane };
      };
    }
  }

  function injectStyles() {
    if (document.getElementById("comove-styles")) return;
    const st = document.createElement("style");
    st.id = "comove-styles";
    st.textContent = `
      .cm-head { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 8px; }
      .cm-head b { font-size: 13.5px; }
      .cm-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 9px; text-align: center; }
      .cm-kpi { background: var(--bg); border: 1px solid var(--line); border-radius: 9px; padding: 6px 4px; font-size: 11px; color: var(--muted); }
      .cm-kpi b { display: block; font-size: 15px; color: var(--ink); font-variant-numeric: tabular-nums; }
      .cm-pills { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 9px; }
      .cm-pills button { flex: 1 1 auto; border: 1px solid var(--line); background: var(--bg); color: var(--muted); font: inherit; font-size: 11.5px; font-weight: 650; padding: 5px 8px; border-radius: 999px; cursor: pointer; text-align: center; }
      .cm-pills button.active { background: var(--accent-soft); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 55%, var(--line)); }
      .cm-role-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); margin-bottom: 5px; font-size: 12px; }
      .cm-badge { font-size: 10.5px; font-weight: 700; padding: 2px 6px; border-radius: 6px; white-space: nowrap; }
      .cm-badge.robot { background: color-mix(in srgb, #0284c7 15%, var(--card)); color: #0284c7; }
      .cm-badge.dolly { background: color-mix(in srgb, #7c3aed 15%, var(--card)); color: #7c3aed; }
      .cm-badge.human { background: color-mix(in srgb, #d97706 16%, var(--card)); color: #b45309; }
      .cm-badge.ok { background: color-mix(in srgb, var(--ok, #16a34a) 15%, var(--card)); color: var(--ok, #16a34a); }
      .cm-badge.warn { background: color-mix(in srgb, var(--bad, #dc2626) 15%, var(--card)); color: var(--bad, #dc2626); }
      .cm-details { margin-top: 8px; border: 1px solid var(--line); border-radius: 9px; background: var(--bg); overflow: hidden; }
      .cm-details summary { list-style: none; cursor: pointer; padding: 7px 9px; font-size: 11.8px; font-weight: 700; display: flex; justify-content: space-between; align-items: center; gap: 6px; }
      .cm-details summary::-webkit-details-marker { display: none; }
      .cm-details summary::after { content: "▾"; font-size: 11px; color: var(--muted); }
      .cm-details[open] summary { border-bottom: 1px solid var(--line); }
      .cm-details[open] summary::after { content: "▴"; }
      .cm-play-item { padding: 6px 8px; border-bottom: 1px solid var(--line); font-size: 11.8px; line-height: 1.35; }
      .cm-play-item:last-child { border-bottom: 0; }
      .cm-banner { padding: 8px 9px; border-radius: 9px; font-size: 11.8px; line-height: 1.4; margin-bottom: 8px; border: 1px solid color-mix(in srgb, var(--ok, #16a34a) 35%, var(--line)); background: color-mix(in srgb, var(--ok, #16a34a) 8%, var(--card)); }
      .cm-banner.warn { border-color: color-mix(in srgb, var(--bad, #dc2626) 40%, var(--line)); background: color-mix(in srgb, var(--bad, #dc2626) 8%, var(--card)); }
      .cm-bar-wrap { height: 6px; border-radius: 4px; background: var(--line); overflow: hidden; margin-top: 4px; }
      .cm-bar-fill { height: 100%; border-radius: 4px; background: var(--ok, #16a34a); }
      .cm-bar-fill.over { background: var(--bad, #dc2626); }
      .cm-scan-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
      .cm-scan-actions .btn { flex: 1; font-size: 11.5px; padding: 7px 8px; justify-content: center; }
      .cm-canvas-wrap { position: relative; border-radius: 9px; overflow: hidden; border: 1px solid var(--line); background: #111; margin-bottom: 7px; }
      .cm-canvas-wrap img { display: block; width: 100%; height: auto; }
      .cm-pin { position: absolute; transform: translate(-50%, -50%); width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.45); border: 2px solid #fff; pointer-events: auto; cursor: help; }
      .cm-pin.clear_first { background: #ea580c; }
      .cm-pin.robot_pick { background: #0284c7; }
      .cm-pin.human_grip { background: #7c3aed; }
      .cm-pin.keep_out { background: #dc2626; }
      .cm-pin.stage_zone { background: #16a34a; }
      @media print { #tab-crew { display: none !important; } }
    `;
    document.head.appendChild(st);
  }

  async function runRoboticsScan(target, fileBase64) {
    scanState = { loading: true, error: null, result: scanState.result, target };
    renderBody();
    try {
      if (MOCK) {
        await new Promise((r) => setTimeout(r, 260));
        scanState = { loading: false, error: null, result: makeMockScan(target), target };
      } else {
        const res = await fetch(`${API_BASE}/co-move/scan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: runId,
            target,
            image_base64: fileBase64 || null,
            context_hint:
              target === "destination"
                ? "NY Penn Station / Moynihan Train Hall permitted pop-up bay with commuter lanes & existing counters."
                : "Venue lounge furniture, boxes, and doorway extraction path.",
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        scanState = { loading: false, error: null, result: data, target };
      }
    } catch (e) {
      // Graceful fallback so live demo never breaks even if venue wifi hiccups
      scanState = { loading: false, error: `Live API note (${e.message}) — showing spatial template`, result: makeMockScan(target), target };
    }
    renderBody();
  }

  function renderBody() {
    const host = document.getElementById("comove-body");
    if (!host) return;
    const data = currentAnalysis;
    if (!data) {
      host.innerHTML = `<div style="font-size:12.5px;color:var(--muted);">Waiting for solved packing plan…</div>`;
      return;
    }

    const occ = data.penn_occupancy;
    let tabHtml = "";

    if (activeTab === "ergo") {
      const roleMeta = {
        dock_robot: { icon: "🤖", cls: "robot" },
        amr_cart: { icon: "🛞", cls: "robot" },
        stair_dolly: { icon: "⚙️", cls: "dolly" },
        human_ergo: { icon: "🦺", cls: "human" },
      };
      const rolesHtml = (data.roles || [])
        .map((r) => {
          const m = roleMeta[r.role] || roleMeta.human_ergo;
          const ex = (r.examples || []).slice(0, 2).join(", ");
          return `<div class="cm-role-row">
            <div>
              <div style="font-weight:650;">${m.icon} ${esc(r.label)}</div>
              <div style="font-size:11px;color:var(--muted);">${esc(ex || "None in current load")}</div>
            </div>
            <span class="cm-badge ${m.cls}">${r.count} pcs · ${Math.round(r.weight_lb).toLocaleString()} lb</span>
          </div>`;
        })
        .join("");

      const alerts = [];
      (data.overweight_boxes || []).forEach((b) => {
        alerts.push(`<div class="cm-play-item">⚠️ <b>${esc(b.label)} (${Math.round(b.weight_lb)} lb)</b> — ${esc(b.fix)}</div>`);
      });
      (data.fatigue_streaks || []).forEach((f) => {
        alerts.push(`<div class="cm-play-item">🫁 <b>Truck ${f.truck} Back-Fatigue Pacing:</b> ${esc(f.advice)}</div>`);
      });

      const doorsHtml = (data.doorway_playbook || [])
        .slice(0, 4)
        .map((d) => {
          const cls = d.status === "straight_walk_in" ? "ok" : d.status === "hinge_pin_or_reroute" ? "warn" : "human";
          return `<div class="cm-play-item">
            <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
              <b>${esc(d.label)} <span style="font-weight:400;color:var(--muted);">(${d.weight_lb} lb)</span></b>
              <span class="cm-badge ${cls}">${esc(d.badge)}</span>
            </div>
            <div style="color:var(--muted);margin-top:2px;">${esc(d.instruction)}</div>
            <div style="font-size:11px;margin-top:2px;"><b>Gear:</b> ${esc(d.gear)}</div>
          </div>`;
        })
        .join("");

      const doorCount = (data.doorway_playbook || []).length;
      const shouldAutoOpen = alerts.length > 0;
      tabHtml = `
        ${rolesHtml}
        <details class="cm-details" ${shouldAutoOpen ? "open" : ""}>
          <summary>
            <span>Doorway Pivots &amp; Spine Guardrails (${doorCount || "all clear"}${alerts.length ? ` · ${alerts.length} alert` : ""})</span>
          </summary>
          <div>
            ${alerts.join("")}
            ${doorsHtml || `<div class="cm-play-item">All items clear 32"×80" doorways upright.</div>`}
          </div>
        </details>
      `;
    } else if (activeTab === "penn") {
      const clearBannerCls = occ.all_bays_clear ? "cm-banner" : "cm-banner warn";
      const zonesHtml = (occ.zones || [])
        .map((z) => {
          const pct = Math.min(100, Math.round(z.fill_of_clear_pct));
          const over = !z.fits_occupied_space;
          return `<div class="cm-play-item">
            <div style="display:flex;justify-content:space-between;gap:6px;align-items:center;">
              <b>Stop ${z.dock_stop} · ${esc(z.name)}</b>
              <span class="cm-badge ${over ? "warn" : "ok"}">${z.placed_floor_sqft} / ${z.net_clear_sqft} sq ft clear</span>
            </div>
            <div style="font-size:11px;color:var(--muted);margin-top:2px;">
              Untouched in ${z.gross_wing_sqft.toLocaleString()} sq ft wing: ${esc(z.existing_fixtures)} · ${z.egress_aisle_in}" egress lane${z.requires_freight_elevator ? ` · +20 ft freight elevator (${occ.mezzanine_elevator_trips} trip)` : ""}
            </div>
            <div class="cm-bar-wrap"><div class="cm-bar-fill ${over ? "over" : ""}" style="width:${pct}%"></div></div>
            ${
              over && z.overflow_reroute_items?.length
                ? `<div style="font-size:11px;color:var(--bad,#dc2626);margin-top:3px;">↪ Hold on AMR cart / reroute to Main Atrium: ${esc(z.overflow_reroute_items.join(", "))}</div>`
                : ""
            }
          </div>`;
        })
        .join("");

      tabHtml = `
        <div class="${clearBannerCls}">
          <b>96% of Penn Station untouched:</b> Of <b>${occ.gross_station_sqft.toLocaleString()} sq ft</b>, <b>${occ.untouched_station_pct}%</b> stays clear for commuters, counters &amp; FDNY fire lanes — using <b>${occ.placed_floor_sqft} sq ft</b> inside pop-up bays (${esc(occ.load_window)}).
        </div>
        <label style="display:block;font-size:11.5px;font-weight:600;margin-bottom:6px;">
          Stress-test existing bay clutter:
          <select id="cm-occ-select" style="margin-top:4px;width:100%;padding:6px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit;font-size:12px;">
            <option value="permitted_bays" ${occMode === "permitted_bays" ? "selected" : ""}>Permitted Pop-Up Bays (Default · 96.0% Untouched)</option>
            <option value="crowded_stalls_35" ${occMode === "crowded_stalls_35" ? "selected" : ""}>35% Occupied Stalls (Existing Counters &amp; Displays)</option>
            <option value="rush_hour_55" ${occMode === "rush_hour_55" ? "selected" : ""}>55% Half-Full Bays + Strict Egress Stress Test</option>
          </select>
        </label>
        <div style="border:1px solid var(--line);border-radius:9px;background:var(--bg);max-height:240px;overflow-y:auto;">
          ${zonesHtml}
        </div>
      `;
    } else {
      const sr = scanState.result;
      const pinsHtml = sr
        ? (sr.waypoints || [])
            .map((w) => {
              const yPct = Math.max(4, Math.min(96, Number(w.point?.[0] || 500) / 10));
              const xPct = Math.max(4, Math.min(96, Number(w.point?.[1] || 500) / 10));
              return `<div class="cm-pin ${esc(w.kind)}" style="top:${yPct}%;left:${xPct}%;" title="${esc(w.label)}: ${esc(w.instruction)}">${w.step}</div>`;
            })
            .join("")
        : "";

      const legendHtml = sr
        ? (sr.waypoints || [])
            .map(
              (w) => `<div class="cm-play-item">
                <b>#${w.step} · ${esc(w.label)}</b> <span style="font-size:10.5px;color:var(--muted);">[${esc(w.kind.replace("_", " "))}]</span>
                <div style="color:var(--muted);">${esc(w.instruction)}</div>
              </div>`
            )
            .join("")
        : "";

      tabHtml = `
        <div style="font-size:11.5px;color:var(--muted);margin-bottom:7px;">
          Live <code>gemini-robotics-er-2-preview</code> spatial callouts (<code>[y, x]</code> 0–1000 waypoints):
        </div>
        <div class="cm-scan-actions">
          <button type="button" class="btn" id="cm-scan-origin" ${scanState.loading ? "disabled" : ""}>🦺 Scan Origin</button>
          <button type="button" class="btn" id="cm-scan-dest" ${scanState.loading ? "disabled" : ""}>🏛️ Scan Penn</button>
          <label class="btn" style="cursor:pointer;flex:0 0 auto;">
            📷 Photo
            <input type="file" id="cm-scan-file" accept="image/*" style="display:none;">
          </label>
        </div>
        ${scanState.loading ? `<div style="font-size:12px;color:var(--accent);padding:6px 0;">Running Gemini Robotics ER 2 spatial pass…</div>` : ""}
        ${scanState.error ? `<div style="font-size:11px;color:var(--muted);margin-bottom:5px;">${esc(scanState.error)}</div>` : ""}
        ${
          sr
            ? `
          <div class="cm-canvas-wrap">
            <img src="${sr.preview_data_url}" alt="Robotics spatial scan">
            ${pinsHtml}
          </div>
          <div style="font-size:11.5px;margin-bottom:6px;"><b>Model (${esc(sr.model)}):</b> ${esc(sr.scene_summary)}</div>
          <div style="border:1px solid var(--line);border-radius:9px;background:var(--bg);max-height:190px;overflow-y:auto;">
            ${legendHtml}
          </div>`
            : `<div style="font-size:11.8px;color:var(--muted);padding:8px;border:1px dashed var(--line);border-radius:8px;">
                Tap <b>Scan Origin</b> for path-clearing + 2-person grip points, or <b>Scan Penn</b> to map existing station counters &amp; commuter keep-out lanes.
              </div>`
        }
      `;
    }

    host.innerHTML = `
      <div class="cm-head">
        <b>🤖 Crew Biomechanics &amp; Space Check</b>
        <span style="font-size:11px;font-weight:600;color:var(--muted);">Robotics ER 2</span>
      </div>
      <div class="cm-kpis">
        <div class="cm-kpi"><b>${data.offloaded_pct}%</b>Robot/Dolly Offload</div>
        <div class="cm-kpi"><b>${data.ergo_score}/100</b>Human Spine Safety</div>
        <div class="cm-kpi"><b>${occ.untouched_station_pct}%</b>Penn Left Clear</div>
      </div>
      <div class="cm-pills">
        <button type="button" data-cmtab="ergo" class="${activeTab === "ergo" ? "active" : ""}">🦺 Crew &amp; Spine</button>
        <button type="button" data-cmtab="penn" class="${activeTab === "penn" ? "active" : ""}">🏛️ Penn 96% Clear</button>
        <button type="button" data-cmtab="scan" class="${activeTab === "scan" ? "active" : ""}">📍 Robotics Scan</button>
      </div>
      ${tabHtml}
    `;

    host.querySelectorAll("[data-cmtab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.getAttribute("data-cmtab");
        renderBody();
      });
    });

    const selOcc = document.getElementById("cm-occ-select");
    if (selOcc) {
      selOcc.addEventListener("change", () => {
        occMode = selOcc.value;
        if (latestPlan) setPlan(latestPlan);
      });
    }

    const btnOrig = document.getElementById("cm-scan-origin");
    if (btnOrig) btnOrig.addEventListener("click", () => runRoboticsScan("origin"));
    const btnDest = document.getElementById("cm-scan-dest");
    if (btnDest) btnDest.addEventListener("click", () => runRoboticsScan("destination"));
    const fileInp = document.getElementById("cm-scan-file");
    if (fileInp) {
      fileInp.addEventListener("change", () => {
        const f = fileInp.files && fileInp.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = () => runRoboticsScan(scanState.target || "origin", String(reader.result || ""));
        reader.readAsDataURL(f);
      });
    }
  }

  function mountCard() {
    if (document.getElementById("comove-body")) return;
    ensureUnifiedTabs();
    injectStyles();

    const reg = window.PIU_REGISTER_TAB && window.PIU_REGISTER_TAB("crew", "Crew", "Human + Robot Co-Move, Spine Safety & Penn Occupancy");
    if (reg && reg.pane) {
      reg.pane.innerHTML = `<div id="comove-body"></div>`;
    } else {
      const verifier = document.getElementById("verifier-panel");
      if (!verifier || !verifier.parentNode) return;
      const sec = document.createElement("section");
      sec.className = "panel-card";
      sec.id = "comove-panel";
      sec.innerHTML = `<div id="comove-body"></div>`;
      verifier.parentNode.insertBefore(sec, verifier.nextSibling);
    }
    renderBody();
  }

  async function setPlan(plan) {
    latestPlan = plan;
    mountCard();
    currentAnalysis = analyzeLocal(plan, occMode);
    renderBody();

    if (!MOCK && plan && Array.isArray(plan.trucks)) {
      try {
        const res = await fetch(`${API_BASE}/co-move/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId, plan, occupancy_mode: occMode }),
        });
        if (res.ok) {
          currentAnalysis = await res.json();
          renderBody();
        }
      } catch (_) {
        // Keep instant local calculation if offline
      }
    }
  }

  window.PIU_COMOVE = {
    setPlan,
    openTab: () => window.PIU_ACTIVATE_TAB && window.PIU_ACTIVATE_TAB("crew"),
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountCard);
  } else {
    mountCard();
  }
})();
