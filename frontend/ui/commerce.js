// Pack It Up · Shopify (shop.dev / mcp.shop.com) Move Supply Kit & Shopping Agent UI.
// Works both against FastAPI (/commerce/kit, /commerce/agent, /commerce/search) AND
// zero-server ?mock=1 mode by calling https://mcp.shop.com directly over CORS (with offline fallback).
(function () {
  "use strict";

  const SHOP_MCP_ENDPOINT = "https://mcp.shop.com";
  const MCP_PROTO = "2026-07-28";

  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);

  function safeUrl(u) {
    const s = String(u || "").trim();
    return /^https?:\/\//i.test(s) ? s : "#";
  }

  function fmtUsd(centsOrUsd, isCents = true) {
    const val = isCents ? Number(centsOrUsd || 0) / 100 : Number(centsOrUsd || 0);
    return "$" + val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // ---------- Browser-direct Shop MCP fallback for ?mock=1 (no Python server needed) ----------
  let mcpReqSeq = 100;
  async function callShopMcpDirect(toolName, args) {
    const res = await fetch(SHOP_MCP_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTO,
        "Mcp-Method": "tools/call",
        "Mcp-Name": toolName,
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: ++mcpReqSeq,
        method: "tools/call",
        params: {
          _meta: {
            "io.modelcontextprotocol/protocolVersion": MCP_PROTO,
            "io.modelcontextprotocol/clientCapabilities": {},
          },
          name: toolName,
          arguments: args,
        },
      }),
    });
    if (!res.ok) throw new Error(`mcp.shop.com HTTP ${res.status}`);
    const body = await res.json();
    if (body.error) throw new Error(body.error.message || "MCP error");
    return (body.result && body.result.structuredContent) || {};
  }

  function parsePackCountJs(title, vTitle) {
    const head = `${vTitle || ""} ${title || ""}`;
    if (/\b(single\s+box|single\s+carton|1-pack|pack\s+of\s+1)\b/i.test(head)) return 1;
    const cleaned = head
      .replace(/\b\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?)?\b/gi, " ")
      .replace(/\b\d+\s*(?:lb|lbs|ect|mil|yd|yds|ft|gauge)\b/gi, " ");
    const m1 = cleaned.match(/\b(?:pack|bundle|case|set)\s+of\s+(\d{1,3})\b/i);
    if (m1 && Number(m1[1]) >= 1 && Number(m1[1]) <= 100) return Number(m1[1]);
    const m2 = cleaned.match(/(?<![x×\d/.])(\d{1,3})\s*(?:-\s*)?(?:pack|pk|pcs|pieces|rolls?|ct|count|blankets?|pads?|bags?)\b/i);
    if (m2 && Number(m2[1]) >= 1 && Number(m2[1]) <= 100) return Number(m2[1]);
    return 1;
  }

  async function buildMockBrowserKit(plan, tier = "standard", postalCode = "10001", customAdds = []) {
    const mult = tier === "essential" ? 1.0 : tier === "pro_heavy_duty" ? 1.2 : 1.1;
    const items = (plan?.trucks || []).flatMap((t) => t.items || []);
    const boxMap = {};
    let furn = 0, fragile = 0, heavy = 0;
    for (const it of items) {
      if (it.is_box || String(it.catalog_id || "").startsWith("box_")) {
        const k = it.catalog_id || "box_medium";
        boxMap[k] = (boxMap[k] || 0) + 1;
      } else {
        furn++;
        if (it.fragile) fragile++;
        if (it.two_person || Number(it.weight_lb || 0) > 50) heavy++;
      }
    }
    if (!Object.keys(boxMap).length) boxMap.box_medium = 4;

    const specs = {
      box_small: ["Small Moving Boxes (16×12×12\")", "16x12x12 small moving boxes"],
      box_medium: ["Medium Moving Boxes (18×18×16\")", "18x18x16 medium moving boxes"],
      box_large: ["Large Moving Boxes (18×18×24\")", "18x18x24 large moving boxes"],
      box_xl: ["XL Moving Boxes (24×18×24\")", "24x18x24 extra large moving boxes"],
      box_wardrobe: ["Wardrobe Boxes w/ Bar", "wardrobe moving box with bar"],
      box_dish_pack: ["Dish Pack Fragile Boxes", "dish pack moving box glassware"],
    };

    const needs = [];
    let totalBoxes = 0;
    for (const [k, raw] of Object.entries(boxMap)) {
      const qty = Math.max(raw, Math.ceil(raw * mult));
      totalBoxes += qty;
      const sp = specs[k] || specs.box_medium;
      needs.push({ need_id: k, title: sp[0], short_title: sp[0], category: "boxes", qty_needed: qty, raw_plan_qty: raw, query: sp[1], reason: `${raw} planned in truck load` });
    }
    needs.push({
      need_id: "supply_tape",
      title: "Heavy-Duty Packing Tape Rolls",
      short_title: "Packing Tape",
      category: "tape_wrap",
      qty_needed: Math.max(2, Math.ceil((totalBoxes + furn * 0.3) / 10)),
      raw_plan_qty: 2,
      query: "heavy duty packing tape rolls moving",
      reason: `Seals ${totalBoxes} moving boxes + wrap`,
    });
    if (fragile > 0) {
      needs.push({
        need_id: "supply_bubble",
        title: "Perforated Bubble Cushioning Roll",
        short_title: "Bubble Wrap",
        category: "fragile_protection",
        qty_needed: Math.max(1, Math.ceil(fragile / 4)),
        raw_plan_qty: 1,
        query: "bubble cushioning wrap roll moving fragile",
        reason: `Protects ${fragile} fragile piece(s)`,
      });
    }
    if (tier !== "essential" && furn > 0) {
      needs.push({
        need_id: "supply_blankets",
        title: "Quilted Moving Blankets (72×80\")",
        short_title: "Moving Blankets",
        category: "furniture_protection",
        qty_needed: Math.max(4, Math.ceil(furn * 0.85)),
        raw_plan_qty: 4,
        query: "moving blankets 72x80 pack",
        reason: `Wraps ${furn} furniture/venue pieces`,
      });
    }
    if (tier !== "essential" && heavy > 0) {
      needs.push({
        need_id: "supply_straps",
        title: "2-Person Forearm Lifting Straps",
        short_title: "Lifting Straps",
        category: "lifting_gear",
        qty_needed: 1,
        raw_plan_qty: 1,
        query: "forearm lifting straps moving heavy furniture",
        reason: `${heavy} two-person heavy lift(s) (>50 lb)`,
      });
    }
    customAdds.forEach((a, i) => {
      needs.push({
        need_id: `custom_${i + 1}`,
        title: a.title,
        short_title: a.title,
        category: "agent_added",
        qty_needed: a.qty_needed || 1,
        raw_plan_qty: a.qty_needed || 1,
        query: a.query,
        reason: a.reason || "Added via Shopping Agent",
      });
    });

    const trace = [];
    const itemsOut = [];
    await Promise.all(
      needs.map(async (n) => {
        try {
          const sc = await callShopMcpDirect("search_catalog", {
            catalog: {
              query: n.query,
              context: { address_country: "US", address_region: "NY", postal_code: postalCode, currency: "USD" },
              filters: { ships_to: { country: "US", region: "NY", postal_code: postalCode } },
              pagination: { limit: 4 },
            },
          });
          const prods = sc.products || [];
          const cands = [];
          for (const p of prods) {
            const v = (p.variants || [])[0];
            if (!v || !v.seller?.domain || !v.price?.amount) continue;
            const ps = parsePackCountJs(p.title, v.title);
            if (ps > Math.max(36, n.qty_needed * 6)) continue;
            const packs = Math.max(1, Math.ceil(n.qty_needed / ps));
            const img = (p.media && p.media[0] && (p.media[0].preview?.url || p.media[0].url)) || "";
            cands.push({
              product_id: p.id,
              variant_id: v.id,
              title: p.title,
              variant_title: ps > 1 ? `${ps}-Pack` : "Single Unit",
              pack_size: ps,
              packs_to_order: packs,
              units_supplied: packs * ps,
              price_cents: v.price.amount,
              line_total_cents: packs * v.price.amount,
              currency: "USD",
              seller_name: v.seller.name || v.seller.domain,
              seller_domain: v.seller.domain,
              seller_url: v.seller.url || `https://${v.seller.domain}`,
              product_url: v.url,
              checkout_url: v.checkout_url || v.url,
              image_url: img,
              source: "shop_mcp_live",
            });
          }
          trace.push({ step: "search_catalog", tool: "mcp.shop.com/search_catalog", need_id: n.need_id, query: n.query, verified_candidates: cands.length });
          if (cands.length) {
            itemsOut.push({
              need_id: n.need_id,
              need_title: n.title,
              short_title: n.short_title,
              category: n.category,
              qty_needed: n.qty_needed,
              raw_plan_qty: n.raw_plan_qty,
              reason: n.reason,
              offer: cands[0],
              alternatives: cands.slice(1, 4),
            });
          }
        } catch (e) {
          trace.push({ step: "search_catalog_error", need_id: n.need_id, error: e.message });
        }
      })
    );

    // Fewer stores: each store is its own cart and shipping fee (same rule as consolidate_stores
    // in backend/commerce.py). Drop a store when moving its lines to stores already in the kit
    // costs less than an estimated shipping fee.
    const EST_SHIP_CENTS = 1500;
    for (;;) {
      const stores = new Set(itemsOut.map((x) => x.offer.seller_domain));
      if (stores.size < 2) break;
      let best = null;
      for (const drop of stores) {
        let extra = 0;
        const moves = [];
        let ok = true;
        for (const it of itemsOut) {
          if (it.offer.seller_domain !== drop) continue;
          const opts = it.alternatives
            .map((a, i) => ({ i, d: a.line_total_cents - it.offer.line_total_cents, dom: a.seller_domain }))
            .filter((o) => o.dom !== drop && stores.has(o.dom))
            .sort((p, q) => p.d - q.d);
          if (!opts.length) { ok = false; break; }
          extra += opts[0].d;
          moves.push([it, opts[0].i]);
        }
        if (ok && moves.length && extra < EST_SHIP_CENTS && (!best || extra < best.extra)) best = { drop, extra, moves };
      }
      if (!best) break;
      for (const [it, i] of best.moves) {
        const alt = it.alternatives[i];
        it.alternatives[i] = it.offer;
        it.offer = alt;
      }
      trace.push({ step: "store_consolidation", dropped_shop: best.drop, extra_item_cents: best.extra });
    }

    // Group by seller_domain and call create_cart live over CORS!
    const byShop = {};
    for (const it of itemsOut) {
      const dom = it.offer.seller_domain;
      (byShop[dom] = byShop[dom] || []).push(it);
    }
    const carts = [];
    await Promise.all(
      Object.entries(byShop).map(async ([dom, grp]) => {
        const sub = grp.reduce((a, x) => a + x.offer.line_total_cents, 0);
        let cartUrl = grp[0].offer.checkout_url || grp[0].offer.product_url;
        try {
          const cr = await callShopMcpDirect("create_cart", {
            shop: dom,
            cart: { line_items: grp.map((x) => ({ item: { id: x.offer.variant_id }, quantity: x.offer.packs_to_order })) },
          });
          if (cr.continue_url) cartUrl = cr.continue_url;
          trace.push({ step: "create_cart", tool: "mcp.shop.com/create_cart", shop: dom, lines: grp.length, has_continue_url: Boolean(cr.continue_url) });
        } catch (e) {
          /* fallback to direct variant checkout_url */
        }
        carts.push({
          shop_domain: dom,
          seller_name: grp[0].offer.seller_name,
          cart_url: cartUrl,
          continue_url: cartUrl,
          shop_pay_supported: true,
          subtotal_cents: sub,
          subtotal_usd: sub / 100,
          line_count: grp.length,
          items: grp.map((x) => ({
            need_id: x.need_id,
            title: x.offer.title,
            quantity: x.offer.packs_to_order,
            units_supplied: x.offer.units_supplied,
            line_total_cents: x.offer.line_total_cents,
            product_url: x.offer.product_url,
          })),
          warnings: [],
        });
      })
    );

    const subtotal = itemsOut.reduce((a, x) => a + x.offer.line_total_cents, 0);
    return {
      run_id: "mock-demo",
      kit: {
        source_mode: itemsOut.length ? "shop_mcp_live" : "offline_fallback",
        tier,
        buffer_pct: Math.round((mult - 1) * 100),
        bom_summary: { buffered_boxes: totalBoxes, furniture_pieces: furn, fragile_pieces: fragile, two_person_lifts: heavy, supply_lines: itemsOut.length },
        items: itemsOut,
        merchant_carts: carts,
        totals: { subtotal_cents: subtotal, subtotal_usd: subtotal / 100, currency: "USD", line_count: itemsOut.length, merchant_count: carts.length, shipments_saved: Math.max(0, itemsOut.length - carts.length) },
        decision_checks: [],
        agent_trace: trace,
        disclosure: "Live prices and carts via Shopify Catalog MCP (mcp.shop.com). Review shipping & taxes on checkout before paying.",
      },
      item_comps: [],
      state: { tier, custom_additions: customAdds },
    };
  }

  // ---------- Inject shared CSS once ----------
  function injectStyles() {
    if (document.getElementById("piu-commerce-css")) return;
    const st = document.createElement("style");
    st.id = "piu-commerce-css";
    st.textContent = `
      .shop-badge-pill {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 3px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 700;
        background: linear-gradient(135deg, #5a31f4 0%, #1f6feb 100%); color: #fff;
        text-decoration: none; border: 0; cursor: pointer;
      }
      .shop-hero-bar {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 8px; padding: 10px 12px; border-radius: 12px;
        background: color-mix(in srgb, #5a31f4 9%, var(--card));
        border: 1px solid color-mix(in srgb, #5a31f4 32%, var(--line));
        margin-bottom: 10px;
      }
      .shop-tier-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 10px; }
      .shop-tier-btn {
        border: 1px solid var(--line); background: var(--bg); color: var(--ink);
        border-radius: 8px; padding: 5px 9px; font-size: 12px; font-weight: 600; cursor: pointer;
      }
      .shop-tier-btn[aria-pressed="true"] { background: #5a31f4; border-color: #5a31f4; color: #fff; }
      .shop-zip-input {
        width: 76px !important; min-height: 30px !important; padding: 4px 8px !important;
        font-size: 12.5px !important; border-radius: 8px !important;
      }
      .shop-carts-box { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
      .shop-cart-card {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 8px; padding: 10px 12px; border-radius: 11px;
        border: 1.5px solid color-mix(in srgb, #5a31f4 38%, var(--line));
        background: var(--card);
      }
      .shop-pay-btn {
        display: inline-flex; align-items: center; gap: 6px;
        background: #5a31f4; color: #fff; border: 0; border-radius: 9px;
        padding: 7px 13px; font-size: 12.5px; font-weight: 700; text-decoration: none;
        cursor: pointer; white-space: nowrap;
      }
      .shop-pay-btn:hover { filter: brightness(1.08); }
      .shop-pay-btn.alt {
        background: var(--bg); color: var(--ink); border: 1px solid var(--line); font-weight: 600;
      }
      .shop-supply-list { display: flex; flex-direction: column; gap: 8px; max-height: 380px; overflow-y: auto; padding-right: 2px; }
      .shop-page-full .shop-supply-list { max-height: none; }
      .shop-line {
        display: grid; grid-template-columns: 52px 1fr auto; gap: 10px; align-items: start;
        padding: 9px 10px; border: 1px solid var(--line); border-radius: 10px; background: var(--bg);
      }
      .shop-line img {
        width: 52px; height: 52px; object-fit: cover; border-radius: 8px; background: var(--card); border: 1px solid var(--line);
      }
      .shop-line-title { font-size: 13px; font-weight: 700; line-height: 1.25; }
      .shop-line-sub { font-size: 11.5px; color: var(--muted); margin-top: 2px; line-height: 1.35; }
      .shop-line-reason {
        display: inline-block; margin-top: 3px; font-size: 11px; padding: 1px 6px;
        border-radius: 6px; background: var(--accent-soft); color: var(--accent); font-weight: 600;
      }
      .shop-price-col { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
      .shop-price-col b { font-size: 13.5px; display: block; }
      .shop-alts { grid-column: 1 / -1; border-top: 1px dashed var(--line); padding-top: 6px; margin-top: 4px; display: flex; flex-direction: column; gap: 5px; }
      .shop-alt-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 11.5px; }
      .shop-agent-box {
        margin-top: 12px; padding: 10px 12px; border-radius: 11px;
        border: 1px solid var(--line); background: var(--bg);
      }
      .shop-chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 6px 0 8px; }
      .shop-chip {
        border: 1px solid var(--line); background: var(--card); color: var(--ink);
        border-radius: 999px; padding: 4px 9px; font-size: 11.5px; cursor: pointer;
      }
      .shop-chip:hover { border-color: #5a31f4; color: #5a31f4; }
      .shop-chat-row { display: flex; gap: 6px; }
      .shop-chat-row input {
        flex: 1; min-height: 36px !important; padding: 6px 10px !important; font-size: 13px !important;
        background: var(--card) !important;
      }
      .shop-agent-reply {
        margin-top: 8px; padding: 8px 10px; border-radius: 9px;
        background: color-mix(in srgb, #5a31f4 10%, var(--card)); font-size: 12.5px; line-height: 1.4;
        white-space: pre-line;
      }
      .shop-comp-card {
        display: grid; grid-template-columns: 48px 1fr auto; gap: 9px; align-items: center;
        padding: 8px 10px; border: 1px solid var(--line); border-radius: 10px; background: var(--bg); margin-top: 6px;
      }
      .shop-comp-card img { width: 48px; height: 48px; border-radius: 7px; object-fit: cover; background: var(--card); }
      .shop-trace { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: var(--muted); max-height: 150px; overflow-y: auto; margin-top: 6px; }
      .shop-drawer {
        margin-top: 9px; border: 1px solid var(--line); border-radius: 10px; background: var(--bg); overflow: hidden;
      }
      .shop-drawer > summary {
        list-style: none; cursor: pointer; padding: 8px 11px; font-size: 12.5px; font-weight: 700;
        display: flex; justify-content: space-between; align-items: center; gap: 6px;
      }
      .shop-drawer > summary::-webkit-details-marker { display: none; }
      .shop-drawer > .shop-drawer-body {
        padding: 8px 10px 10px; border-top: 1px solid var(--line);
      }
      @media print { #tab-shop, #btn-jump-shop { display: none !important; } }
    `;
    document.head.appendChild(st);
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

  // ---------- Controller Factory ----------
  function mountCommerceWidget(container, opts = {}) {
    injectStyles();
    const { API_BASE, MOCK, link, placeholder } = window.PIU || {
      API_BASE: location.origin,
      MOCK: false,
      link: (p) => p,
      placeholder: () => "",
    };

    let state = {
      runId: opts.runId || "sample_venue",
      plan: opts.plan || null,
      extraItems: opts.extraItems || [],
      postalCode: "10001",
      tier: "standard",
      agentState: {},
      data: null,
      loading: false,
      lastReply: "",
      lastModel: "",
      expandedAlts: new Set(),
      supplyOpen: false,
    };

    async function fetchKit(tierOverride) {
      if (tierOverride) {
        state.tier = tierOverride;
        state.agentState = { ...state.agentState, tier: tierOverride };
      }
      state.loading = true;
      render();

      try {
        let payload = null;
        if (!MOCK) {
          const res = await fetch(`${API_BASE}/commerce/kit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              run_id: state.runId,
              plan: state.plan,
              extra_items: state.extraItems,
              tier: state.tier,
              postal_code: state.postalCode,
              state: state.agentState,
              include_comps: true,
            }),
          });
          if (res.ok) payload = await res.json();
        }
        if (!payload) {
          payload = await buildMockBrowserKit(
            state.plan,
            state.tier,
            state.postalCode,
            state.agentState.custom_additions || []
          );
        }
        state.data = payload;
        state.agentState = payload.state || state.agentState;
        if (opts.onTotalsUpdate && payload.kit?.totals) {
          opts.onTotalsUpdate(payload.kit.totals, payload.kit.bom_summary);
        }
      } catch (err) {
        state.lastReply = `Couldn't reach Shop.dev catalog: ${err.message}`;
      } finally {
        state.loading = false;
        render();
      }
    }

    async function sendAgentPrompt(msg) {
      const text = String(msg || "").trim();
      if (!text) return;
      state.loading = true;
      state.lastReply = "Shopping Agent is searching Shopify Catalog & updating your carts…";
      render();

      try {
        if (!MOCK) {
          const res = await fetch(`${API_BASE}/commerce/agent`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              run_id: state.runId,
              plan: state.plan,
              extra_items: state.extraItems,
              postal_code: state.postalCode,
              message: text,
              state: state.agentState,
            }),
          });
          if (res.ok) {
            const out = await res.json();
            state.lastReply = out.reply || "Updated your Move Supply Kit.";
            state.lastModel = out.model || "";
            state.agentState = out.state || state.agentState;
            state.tier = state.agentState.tier || state.tier;
            state.data = { ...state.data, kit: out.kit, state: out.state };
            if (opts.onTotalsUpdate && out.kit?.totals) {
              opts.onTotalsUpdate(out.kit.totals, out.kit.bom_summary);
            }
            state.loading = false;
            render();
            return;
          }
        }
        // Browser fallback in ?mock=1 mode
        const low = text.toLowerCase();
        const adds = [...(state.agentState.custom_additions || [])];
        if (low.includes("heavy") || low.includes("double")) state.tier = "pro_heavy_duty";
        else if (low.includes("essential") || low.includes("cheap")) state.tier = "essential";
        if (low.includes("dolly") || low.includes("hand truck")) {
          adds.push({ title: "Heavy-Duty Folding Hand Truck Dolly", query: "heavy duty hand truck dolly moving", qty_needed: 1, reason: "Requested via Shopping Agent" });
        }
        if (low.includes("eco") || low.includes("paper")) {
          adds.push({ title: "Recyclable Honeycomb Kraft Packing Paper", query: "honeycomb kraft packing paper roll moving", qty_needed: 1, reason: "Eco-friendly wrap requested" });
        }
        state.agentState.custom_additions = adds;
        await fetchKit(state.tier);
        state.lastReply = `Updated your live Shopify Move Supply Kit (${fmtUsd(state.data?.kit?.totals?.subtotal_cents || 0)} total).`;
      } catch (err) {
        state.lastReply = `Agent error: ${err.message}`;
      } finally {
        state.loading = false;
        render();
      }
    }

    function swapOffer(needId, altIdx) {
      if (!state.data?.kit?.items) return;
      const item = state.data.kit.items.find((x) => x.need_id === needId);
      if (!item || !item.alternatives?.[altIdx]) return;
      const chosen = item.alternatives[altIdx];
      const prev = item.offer;
      item.alternatives[altIdx] = prev;
      item.offer = chosen;
      // Recompute subtotal & direct checkout URL for swapped merchant
      const sub = state.data.kit.items.reduce((a, x) => a + x.offer.line_total_cents, 0);
      state.data.kit.totals.subtotal_cents = sub;
      state.data.kit.totals.subtotal_usd = sub / 100;
      const existingCart = state.data.kit.merchant_carts.find((c) => c.shop_domain === chosen.seller_domain);
      if (!existingCart) {
        state.data.kit.merchant_carts.push({
          shop_domain: chosen.seller_domain,
          seller_name: chosen.seller_name,
          cart_url: chosen.checkout_url || chosen.product_url,
          continue_url: chosen.checkout_url || chosen.product_url,
          shop_pay_supported: true,
          subtotal_cents: chosen.line_total_cents,
          subtotal_usd: chosen.line_total_cents / 100,
          line_count: 1,
          items: [{ need_id: needId, title: chosen.title, quantity: chosen.packs_to_order }],
          warnings: [],
        });
      }
      state.expandedAlts.delete(needId);
      if (opts.onTotalsUpdate) opts.onTotalsUpdate(state.data.kit.totals, state.data.kit.bom_summary);
      render();
    }

    function render() {
      const kit = state.data?.kit;
      const comps = state.data?.item_comps || [];
      const totals = kit?.totals || { subtotal_cents: 0, line_count: 0, merchant_count: 0, shipments_saved: 0 };
      const isLive = kit?.source_mode === "shop_mcp_live";
      const decCount = (kit?.decision_checks || []).length;

      const fullPageLink = opts.fullPage
        ? ""
        : `<a class="btn sm" style="min-height:28px;padding:3px 8px;font-size:11.5px" href="${esc(link("shop.html", { run_id: state.runId }))}">Full Shop ↗</a>`;

      const supplyLinesHtml = `
        <div class="shop-supply-list">
          ${(kit?.items || []).map((it) => {
            const o = it.offer;
            const img = o.image_url ? safeUrl(o.image_url) : placeholder(it.short_title);
            const showAlts = state.expandedAlts.has(it.need_id);
            return `
              <div class="shop-line">
                <img src="${esc(img)}" alt="${esc(it.short_title)}" loading="lazy">
                <div>
                  <div class="shop-line-title">
                    <a href="${esc(safeUrl(o.product_url))}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none">${esc(o.title)}</a>
                  </div>
                  <div class="shop-line-sub">
                    <b>Need ${it.qty_needed}</b> → buying <b>${o.packs_to_order}× ${esc(o.variant_title)}</b> (${o.units_supplied} units) · ${esc(o.seller_name)}
                  </div>
                  <span class="shop-line-reason">${esc(it.reason)}</span>
                  ${(it.alternatives || []).length ? `
                    <button type="button" class="btn link" data-toggle-alt="${esc(it.need_id)}" style="font-size:11.5px;margin-left:6px">
                      ${showAlts ? "Hide options ▲" : `Compare ${it.alternatives.length} more ▾`}
                    </button>
                  ` : ""}
                </div>
                <div class="shop-price-col">
                  <b>${fmtUsd(o.line_total_cents)}</b>
                  <span class="small muted">${fmtUsd(o.price_cents)} ea</span>
                </div>
                ${showAlts ? `
                  <div class="shop-alts">
                    ${it.alternatives.map((alt, aIdx) => `
                      <div class="shop-alt-row">
                        <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                          <b>${esc(alt.seller_name)}</b> · ${esc(alt.title.slice(0, 48))} (${alt.packs_to_order}× ${fmtUsd(alt.price_cents)})
                        </span>
                        <button type="button" class="shop-tier-btn" data-swap-need="${esc(it.need_id)}" data-swap-idx="${aIdx}">
                          Use (${fmtUsd(alt.line_total_cents)})
                        </button>
                      </div>
                    `).join("")}
                  </div>
                ` : ""}
              </div>
            `;
          }).join("")}
        </div>
      `;

      const agentHtml = `
        <div class="shop-agent-box" style="${opts.fullPage ? "" : "margin-top:0;margin-bottom:9px"}">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px">
            <b style="font-size:12.5px">🤖 Shopping Agent</b>
            <span class="small muted">${esc(state.lastModel || "Gemini 4 + mcp.shop.com")}</span>
          </div>
          <div class="shop-chips">
            <button type="button" class="shop-chip" data-prompt="Upgrade to heavy-duty double-wall boxes and pro pads">📦 Heavy-duty</button>
            <button type="button" class="shop-chip" data-prompt="Add breathable cotton covers and stone corner guards for Orior bespoke furniture">🇮🇪 Orior care kit</button>
            <button type="button" class="shop-chip" data-prompt="Add E-track ratchet straps and Pelican pick-and-pluck case foam for cinema camera gear">🎬 ARRI/Adorama kit</button>
            ${opts.fullPage ? `
              <button type="button" class="shop-chip" data-prompt="Swap plastic bubble wrap for eco-friendly honeycomb kraft paper">🌿 Eco kraft paper</button>
              <button type="button" class="shop-chip" data-prompt="Ask the store what their return policy is on unused moving boxes">💬 Return policy</button>
            ` : ""}
          </div>
          <form class="shop-chat-row" id="shop-agent-form">
            <input type="text" id="shop-agent-input" placeholder="Ask agent: 'Keep under $120', 'Add 2 mattress bags'…" aria-label="Ask Shopping Agent">
            <button type="submit" class="btn sm primary" ${state.loading ? "disabled" : ""}>Ask</button>
          </form>
          ${state.lastReply ? `<div class="shop-agent-reply">${esc(state.lastReply)}</div>` : ""}
        </div>
      `;

      const compsCardsHtml = comps.map((c) => `
        <div class="shop-comp-card">
          <img src="${esc(c.comp.image_url ? safeUrl(c.comp.image_url) : placeholder(c.item_label))}" alt="${esc(c.item_label)}" loading="lazy">
          <div>
            <div style="font-size:12.5px;font-weight:700">${esc(c.quantity)}× ${esc(c.item_label)} <span class="small muted">(${esc(c.room_name)})</span></div>
            <div class="small" style="color:var(--accent);font-weight:600">${esc(c.verdict)}</div>
            <div class="small muted">Comp: ${esc((c.comp.title || "").slice(0, 52))} · ${esc(c.comp.seller_name)}</div>
          </div>
          <a class="shop-tier-btn" style="text-decoration:none;white-space:nowrap" href="${esc(safeUrl(c.comp.product_url))}" target="_blank" rel="noopener noreferrer">
            ${fmtUsd(c.comp.price_usd, false)} ↗
          </a>
        </div>
      `).join("");

      const lineCount = (kit?.items || []).length;

      container.innerHTML = `
        <div class="${opts.fullPage ? "shop-page-full" : ""}">
          <div class="shop-hero-bar">
            <div>
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span class="shop-badge-pill">🛍️ Shop.dev</span>
                <b style="font-size:14px">${state.loading ? "Building Kit…" : `${fmtUsd(totals.subtotal_cents)} Supply Kit`}</b>
                ${isLive ? `<span class="badge" style="color:var(--ok);border-color:var(--ok)">● Live</span>` : ""}
                ${decCount ? `<span class="badge" title="Verified by Gemini Decision 1">✓ Decisions (${decCount})</span>` : ""}
              </div>
              <div class="small muted" style="margin-top:2px">
                ${kit ? `${kit.bom_summary.buffered_boxes} boxes + ${Math.max(0, totals.line_count - kit.items.filter((i) => i.category === "boxes").length)} supplies · ${totals.merchant_count} cart(s)` : "Exact boxes, tape, wrap & blankets from your 3D load"}
              </div>
            </div>
            ${fullPageLink}
          </div>

          <div class="shop-tier-row">
            <button type="button" class="shop-tier-btn" data-tier="essential" aria-pressed="${state.tier === "essential"}">Essential</button>
            <button type="button" class="shop-tier-btn" data-tier="standard" aria-pressed="${state.tier === "standard"}">Standard</button>
            <button type="button" class="shop-tier-btn" data-tier="pro_heavy_duty" aria-pressed="${state.tier === "pro_heavy_duty"}">Pro</button>
            <span style="margin-left:auto;display:inline-flex;align-items:center;gap:4px" class="small muted">
              ZIP <input type="text" class="shop-zip-input" id="shop-zip" value="${esc(state.postalCode)}" maxlength="10" aria-label="Delivery ZIP code">
              <button type="button" class="shop-tier-btn" id="shop-zip-go">Go</button>
            </span>
          </div>

          ${kit && kit.merchant_carts.length ? `
            <div class="shop-carts-box">
              ${kit.merchant_carts.map((c) => `
                <div class="shop-cart-card">
                  <div>
                    <div style="font-weight:700;font-size:13px">
                      ${esc(c.seller_name)}
                      <span class="small muted" style="font-weight:500">· ${c.line_count} item${c.line_count === 1 ? "" : "s"} · ${fmtUsd(c.subtotal_cents)}</span>
                    </div>
                    <div class="small muted">${esc(c.items.map((i) => `${i.quantity}× ${i.title.slice(0, 28)}`).join(" + ").slice(0, 82))}</div>
                    ${(c.warnings || []).map((w) => `<div class="warn" style="font-size:11px">${esc(w)}</div>`).join("")}
                  </div>
                  <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
                    ${c.shop_pay_url ? `<a class="shop-pay-btn" href="${esc(safeUrl(c.shop_pay_url))}" target="_blank" rel="noopener noreferrer">Shop Pay ↗</a>` : ""}
                    <a class="${c.shop_pay_url ? "shop-pay-btn alt" : "shop-pay-btn"}" href="${esc(safeUrl(c.cart_url || c.continue_url))}" target="_blank" rel="noopener noreferrer">
                      Open Cart (${fmtUsd(c.subtotal_cents)}) ↗
                    </a>
                  </div>
                </div>
              `).join("")}
            </div>
          ` : ""}

          ${opts.fullPage ? `
            ${supplyLinesHtml}
            ${agentHtml}
            ${comps.length ? `
              <div style="margin-top:12px">
                <b style="font-size:13px">⚖️ Haul vs. Replace &amp; Resale Comps (Shop.dev Discovery)</b>
                ${compsCardsHtml}
              </div>
            ` : ""}
          ` : `
            ${agentHtml}
            ${lineCount ? `
              <details class="shop-drawer" id="shop-supply-drawer" ${state.supplyOpen ? "open" : ""}>
                <summary>
                  <span>📦 Supply Breakdown &amp; Swaps (${lineCount} lines)</span>
                  <span class="small muted">${state.supplyOpen ? "Hide ▴" : "View ▾"}</span>
                </summary>
                <div class="shop-drawer-body">
                  ${supplyLinesHtml}
                </div>
              </details>
            ` : ""}
            ${comps.length ? `
              <details class="shop-drawer">
                <summary>
                  <span>⚖️ Haul vs. Replace Comps (${comps.length})</span>
                  <span class="small muted">View ▾</span>
                </summary>
                <div class="shop-drawer-body">
                  ${compsCardsHtml}
                </div>
              </details>
            ` : ""}
          `}

          ${kit ? `
            <p class="small muted" style="margin-top:8px;font-size:11px;line-height:1.35">${esc(kit.disclosure)}</p>
            <details style="margin-top:4px">
              <summary class="small muted" style="cursor:pointer;font-size:11px">MCP &amp; Decisions trace (${(kit.agent_trace || []).length} calls)</summary>
              <div class="shop-trace">
                ${(kit.agent_trace || []).map((t) => `<div>• <b>${esc(t.step)}</b> ${esc(t.need_id || t.shop || "")} ${t.chosen ? `→ ${esc(t.chosen.slice(0, 38))} (p=${t.confidence})` : ""} ${t.latency_ms ? `${t.latency_ms}ms` : ""}</div>`).join("")}
              </div>
            </details>
          ` : ""}
        </div>
      `;

      // Wire events
      const supplyDrawer = container.querySelector("#shop-supply-drawer");
      if (supplyDrawer) {
        supplyDrawer.addEventListener("toggle", () => {
          state.supplyOpen = supplyDrawer.open;
        });
      }
      container.querySelectorAll("[data-tier]").forEach((btn) => {
        btn.addEventListener("click", () => fetchKit(btn.dataset.tier));
      });
      const zipBtn = container.querySelector("#shop-zip-go");
      const zipInp = container.querySelector("#shop-zip");
      if (zipBtn && zipInp) {
        zipBtn.addEventListener("click", () => {
          state.postalCode = zipInp.value.trim() || "10001";
          fetchKit();
        });
      }
      container.querySelectorAll("[data-toggle-alt]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.dataset.toggleAlt;
          if (state.expandedAlts.has(id)) state.expandedAlts.delete(id);
          else state.expandedAlts.add(id);
          state.supplyOpen = true;
          render();
        });
      });
      container.querySelectorAll("[data-swap-need]").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.supplyOpen = true;
          swapOffer(btn.dataset.swapNeed, Number(btn.dataset.swapIdx));
        });
      });
      container.querySelectorAll("[data-prompt]").forEach((chip) => {
        chip.addEventListener("click", () => sendAgentPrompt(chip.dataset.prompt));
      });
      const form = container.querySelector("#shop-agent-form");
      const inp = container.querySelector("#shop-agent-input");
      if (form && inp) {
        form.addEventListener("submit", (e) => {
          e.preventDefault();
          sendAgentPrompt(inp.value);
        });
      }
    }

    render();
    if (opts.autoFetch !== false) fetchKit();

    return {
      refreshFromPlan({ runId, plan, extraItems }) {
        state.runId = runId || state.runId;
        state.plan = plan || state.plan;
        state.extraItems = extraItems || [];
        return fetchKit();
      },
      getState: () => state,
    };
  }

  // ---------- Auto-mount on index.html (3D Pack & Unload output page) ----------
  function autoMountOnPackPage() {
    if (!document.body || !document.body.classList.contains("pack-page")) return;
    if (document.getElementById("tab-shop")) return;
    ensureUnifiedTabs();
    injectStyles();

    const piu = window.PIU || {
      params: new URLSearchParams(location.search),
      lastRun: () => null,
      link: (p) => p,
      MOCK: false,
    };
    const rawRunId = piu.params.get("run_id") || piu.lastRun() || "sample_venue";

    // 1. Add step 4 link in top breadcrumb
    const stepsEl = document.querySelector(".topbar .steps");
    if (stepsEl && !document.getElementById("nav-shop")) {
      stepsEl.insertAdjacentHTML(
        "beforeend",
        ` · <a id="nav-shop" href="${esc(piu.link("shop.html", { run_id: rawRunId }))}">4 Buy Boxes</a>`
      );
    }

    // 2. Add compact "🛍️ Kit" pill in topbar nav-actions
    const navActions = document.querySelector(".nav-actions");
    let jumpBtn = null;
    if (navActions) {
      jumpBtn = document.createElement("button");
      jumpBtn.type = "button";
      jumpBtn.id = "btn-jump-shop";
      jumpBtn.className = "shop-badge-pill";
      jumpBtn.title = "Open Shopify Move Supply Kit & Shopping Agent";
      jumpBtn.innerHTML = "🛍️ Supply Kit";
      navActions.prepend(jumpBtn);
    }

    // 3. Register clean "Shop" tab in unified right-side `.tab-bar`
    const reg = window.PIU_REGISTER_TAB && window.PIU_REGISTER_TAB("shop", "Shop", "Shopify Move Supply Kit & Shopping Agent");
    if (!reg) return;
    const shopTabBtn = reg.btn;
    const shopPane = reg.pane;

    function activateShopTab() {
      window.PIU_ACTIVATE_TAB("shop");
    }

    if (jumpBtn) {
      jumpBtn.addEventListener("click", () => {
        activateShopTab();
        shopPane.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }

    // 4. Inject real-world Orior White-Glove Tribute & Production What-If toggles
    let oriorWhiteGlove = true;
    let addCinemaRig = false;
    let policyBanner = null;
    const whatIfToggles = document.querySelector("#whatif-panel .whatif-toggles");
    if (whatIfToggles && !document.getElementById("tog-orior-wg")) {
      const oriorBtn = document.createElement("button");
      oriorBtn.type = "button";
      oriorBtn.id = "tog-orior-wg";
      oriorBtn.className = "chip-toggle";
      oriorBtn.setAttribute("aria-pressed", "true");
      oriorBtn.title = "Proof-of-concept tribute to Orior (Newry, Ireland) & The Malin: packs every bespoke stone & upholstery piece with zero top-stacking, +2\" pad clearance, upright team lifts & breathable cotton covers.";
      oriorBtn.textContent = "✨ Orior Care";

      const cinemaBtn = document.createElement("button");
      cinemaBtn.type = "button";
      cinemaBtn.id = "tog-cinema-rig";
      cinemaBtn.className = "chip-toggle";
      cinemaBtn.setAttribute("aria-pressed", "false");
      cinemaBtn.title = "PVO Media / Adorama & ARRI Rental camera-truck loadout: Pelican 1650 floor bases, unstacked 1510 lens cases & upright C-stand cart.";
      cinemaBtn.textContent = "🎬 + Cinema Rig";

      whatIfToggles.appendChild(oriorBtn);
      whatIfToggles.appendChild(cinemaBtn);

      policyBanner = document.createElement("div");
      policyBanner.id = "venue-policy-note";
      policyBanner.className = "small hidden";
      policyBanner.style.cssText = "margin-top:6px;padding:4px 8px;border-radius:7px;background:var(--accent-soft);color:var(--ink);font-size:11.5px;line-height:1.3;";
      whatIfToggles.insertAdjacentElement("afterend", policyBanner);

      const triggerResolve = () => {
        const btn = document.getElementById("btn-resolve");
        if (btn) btn.click();
      };
      oriorBtn.addEventListener("click", () => {
        oriorWhiteGlove = !oriorWhiteGlove;
        oriorBtn.setAttribute("aria-pressed", String(oriorWhiteGlove));
        triggerResolve();
      });
      cinemaBtn.addEventListener("click", () => {
        addCinemaRig = !addCinemaRig;
        cinemaBtn.setAttribute("aria-pressed", String(addCinemaRig));
        triggerResolve();
      });
    }

    const CINEMA_EXTRA_ITEMS = [
      { id: "judge_pelican_1650", label: "Pelican 1650 ARRI Build Case (floor tier)", catalog_id: "pelican_1650", quantity: 2, dims_in: [32, 21, 13], weight_lb: 62, fragile: true, must_stay_upright: true, two_person: true, stackable: "light_only" },
      { id: "judge_pelican_1510", label: "Pelican 1510 Master Prime Lens Case", catalog_id: "pelican_1510", quantity: 2, dims_in: [22, 14, 9], weight_lb: 26, fragile: true, must_stay_upright: true, two_person: false, stackable: "no" },
      { id: "judge_cstand_cart", label: "PVO / Adorama C-Stand & Grip Cart (locked)", catalog_id: "c_stand_cart", quantity: 1, dims_in: [48, 26, 68], weight_lb: 135, fragile: false, must_stay_upright: true, two_person: true, stackable: "no" },
    ];

    // 5. Mount widget & sync automatically whenever /solve completes (including judge What-If re-solves!)
    const widget = mountCommerceWidget(shopPane, {
      runId: rawRunId,
      autoFetch: piu.MOCK,
      onTotalsUpdate(totals) {
        if (jumpBtn && totals?.subtotal_cents) {
          jumpBtn.innerHTML = `🛍️ Kit ${fmtUsd(totals.subtotal_cents)}`;
        }
        shopTabBtn.textContent = "Shop";
        if (totals?.subtotal_cents) {
          shopTabBtn.title = `Shopify Move Supply Kit (${fmtUsd(totals.subtotal_cents)})`;
        }
      },
    });

    const origFetch = window.fetch.bind(window);
    window.fetch = async function (...args) {
      let url = String(typeof args[0] === "string" ? args[0] : (args[0] && args[0].url) || "");
      let effectiveExtras = [];
      if (/\/solve(\b|\/|\?)/.test(url) && args[1] && typeof args[1].body === "string") {
        try {
          const parsed = JSON.parse(args[1].body);
          parsed.strategy = parsed.strategy || {};
          if (oriorWhiteGlove) parsed.strategy.orior_white_glove = true;
          parsed.extra_items = [...(parsed.extra_items || []), ...(addCinemaRig ? CINEMA_EXTRA_ITEMS : [])];
          effectiveExtras = parsed.extra_items;
          args = [args[0], { ...args[1], body: JSON.stringify(parsed) }];
        } catch (e) { /* ignore */ }
      }
      const res = await origFetch(...args);
      try {
        if (res.ok && /\/solve(\b|\/|\?)/.test(url)) {
          res.clone().json().then((planJson) => {
            if (policyBanner) {
              const notes = [];
              if (planJson.venue_policy?.white_glove_units) {
                notes.push(`<span title="Proof-of-concept simulation — in real life The Malin's bespoke Irish Orior furniture stays curated per club."><b>✨ Orior Care (${planJson.venue_policy.white_glove_units} pcs):</b> Zero top-stacking, +2" pad clearance &amp; cotton covers</span>`);
              }
              if (addCinemaRig) {
                notes.push(`<span><b>🎬 Cinema Rig:</b> 2× Pelican 1650 base, 2× unstacked 1510 glass &amp; locked C-stand cart</span>`);
              }
              policyBanner.innerHTML = notes.join(" · ");
              policyBanner.classList.toggle("hidden", notes.length === 0);
            }
            widget.refreshFromPlan({
              runId: planJson.run_id || rawRunId,
              plan: planJson,
              extraItems: effectiveExtras,
            });
          }).catch(() => {});
        }
      } catch (e) { /* never interfere with caller */ }
      return res;
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoMountOnPackPage);
  } else {
    setTimeout(autoMountOnPackPage, 0);
  }

  window.PIU_COMMERCE = { mountCommerceWidget, callShopMcpDirect, fmtUsd, esc, safeUrl };
})();
