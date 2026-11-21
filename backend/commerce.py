"""Bonus Track: Build with Commerce (Shopify / shop.dev) — Move Supply Kit & Shopping Agent.

Connects Pack It Up's 3D packing plan and resolved inventory directly to Shopify's
live Shop MCP / Universal Commerce Protocol server (`https://mcp.shop.com`, documented
at `https://shop.dev` and `https://mcp.shop.com/skill.md`):

1. **Move Supply Bill of Materials (`compute_supply_needs`)**:
   Reads exact moving box counts (`box_small`, `box_medium`, `box_large`, `box_xl`,
   `box_wardrobe`, `box_dish_pack`) and item physics flags (`fragile`, `two_person`,
   `disassemble`, mattresses, furniture pads) from the packing plan.
2. **Product Discovery & Spec Verification (`discover_move_kit`)**:
   Queries `search_catalog` on `mcp.shop.com` with NYC `ships_to` filtering, parses
   bundle/pack counts vs dimensions so lookalike small mailers are rejected, consolidates
   multi-item orders onto shared Shopify merchants where cost-effective, and uses the
   Gemini Decisions API (`for_job("decide")`, `gemini-decision-1`) to verify ambiguous
   product matches.
3. **Self-Healing Multi-Merchant Carts & Shop Pay Checkouts (`build_merchant_carts`)**:
   Calls `create_cart` and `create_checkout` on `mcp.shop.com` to produce live pre-filled
   Shopify cart links and Shop Pay (`shop.app/checkouts/...`) one-click continuation URLs,
   automatically swapping to a backup merchant if an item is unavailable.
4. **Haul vs. Replace & Sell Valuation Comps (`discover_item_comps`)**:
   Uses `search_catalog` (including multimodal `like.image` room crops when available) to
   price items marked `sell` and compare hauling bulky items vs replacing at destination.
5. **Interactive Shopping Agent (`run_shopping_agent`)**:
   Uses Gemini 4 (`for_job("shop")`) to handle natural-language buyer requests, adjust
   bundles/tiers, query merchant policies via `ask_business`, and rebuild live carts.

Note: Per `AGENTS.md`, no model SDK is imported here; all model calls go through `backend.llm`.
Per `mcp.shop.com/skill.md`, `complete_checkout` is never called without explicit user
confirmation—every cart returns its complete `continue_url` and merchant disclosures.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import io
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from backend import catalog, expand
from backend.llm import LLMError, _load_env, for_job, load_config

ROOT = Path(__file__).resolve().parents[1]
SHOP_CACHE_DIR = ROOT / ".cache" / "shop_mcp"

SHOP_MCP_URL = os.environ.get("SHOP_MCP_URL", "https://mcp.shop.com")
MCP_PROTOCOL_VERSION = "2026-07-28"

DEFAULT_DESTINATION = {
    "country": "US",
    "region": "NY",
    "postal_code": "10001",
    "currency": "USD",
}

# Search specs for each box catalog_id and protective supply type.
BOX_SUPPLY_SPECS: dict[str, dict[str, Any]] = {
    "box_small": {
        "title": "Small Moving Boxes (16×12×12\", 1.5 cu ft)",
        "short_title": "Small Book Boxes",
        "category": "boxes",
        "target_dims_in": [16, 12, 12],
        "min_max_dim_in": 12.0,
        "query_standard": "16x12x12 small moving boxes corrugated",
        "query_pro": "16x12x12 heavy duty small book moving boxes",
        "default_unit_est_cents": 215,
    },
    "box_medium": {
        "title": "Medium Moving Boxes (18×18×16\", 3.0 cu ft)",
        "short_title": "Medium Moving Boxes",
        "category": "boxes",
        "target_dims_in": [18, 18, 16],
        "min_max_dim_in": 15.0,
        "query_standard": "18x18x16 medium moving boxes",
        "query_pro": "18x18x16 heavy duty double wall medium moving boxes",
        "default_unit_est_cents": 325,
    },
    "box_large": {
        "title": "Large Moving Boxes (18×18×24\", 4.5 cu ft)",
        "short_title": "Large Moving Boxes",
        "category": "boxes",
        "target_dims_in": [24, 18, 18],
        "min_max_dim_in": 18.0,
        "query_standard": "18x18x24 large moving boxes",
        "query_pro": "18x18x24 heavy duty double wall large moving boxes",
        "default_unit_est_cents": 425,
    },
    "box_xl": {
        "title": "Extra-Large Moving Boxes (24×18×24\", 6.0 cu ft)",
        "short_title": "XL Moving Boxes",
        "category": "boxes",
        "target_dims_in": [24, 24, 18],
        "min_max_dim_in": 20.0,
        "query_standard": "24x18x24 extra large moving boxes",
        "query_pro": "24x18x24 heavy duty extra large moving boxes",
        "default_unit_est_cents": 550,
    },
    "box_wardrobe": {
        "title": "Wardrobe Moving Boxes w/ Hanging Bar (24×21×46\")",
        "short_title": "Wardrobe Boxes",
        "category": "boxes",
        "target_dims_in": [24, 21, 46],
        "min_max_dim_in": 30.0,
        "query_standard": "wardrobe moving box with metal bar",
        "query_pro": "heavy duty wardrobe moving box with hanging bar",
        "default_unit_est_cents": 1695,
    },
    "box_dish_pack": {
        "title": "Dish Pack / Glassware Barrel Boxes (18×18×28\")",
        "short_title": "Dish Pack Boxes",
        "category": "boxes",
        "target_dims_in": [18, 18, 28],
        "min_max_dim_in": 16.0,
        "query_standard": "dish pack moving box fragile glassware",
        "query_pro": "double wall dish pack moving box cell dividers",
        "default_unit_est_cents": 950,
    },
}

PROTECTION_SPECS: dict[str, dict[str, Any]] = {
    "supply_tape": {
        "title": "Heavy-Duty Acrylic Packing Tape Rolls",
        "short_title": "Packing Tape Rolls",
        "category": "tape_wrap",
        "query_standard": "heavy duty packing tape rolls moving",
        "query_pro": "Scotch heavy duty shipping packaging tape dispenser rolls",
        "unit_word": "roll",
        "default_unit_est_cents": 350,
    },
    "supply_bubble": {
        "title": "Perforated Bubble Cushioning Wrap Roll",
        "short_title": "Bubble Wrap Rolls",
        "category": "fragile_protection",
        "query_standard": "bubble cushioning wrap roll moving fragile",
        "query_pro": "heavy duty large bubble cushioning wrap roll perforated",
        "unit_word": "roll",
        "default_unit_est_cents": 1899,
    },
    "supply_blankets": {
        "title": "Quilted Moving Blankets / Furniture Pads (72×80\")",
        "short_title": "Moving Blankets",
        "category": "furniture_protection",
        "query_standard": "moving blankets 72x80 pack",
        "query_pro": "heavy duty quilted moving blankets 72x80 12 pack",
        "unit_word": "blanket",
        "default_unit_est_cents": 750,
    },
    "supply_stretch": {
        "title": "Heavy-Duty Stretch Wrap Film Roll (80 Gauge)",
        "short_title": "Stretch Wrap Rolls",
        "category": "tape_wrap",
        "query_standard": "stretch wrap film roll moving furniture",
        "query_pro": "80 gauge heavy duty stretch wrap roll with handles moving",
        "unit_word": "roll",
        "default_unit_est_cents": 1499,
    },
    "supply_mattress_bag": {
        "title": "Heavy-Duty Mattress Moving & Storage Bag",
        "short_title": "Mattress Bags",
        "category": "furniture_protection",
        "query_standard": "queen king mattress moving bag heavy duty",
        "query_pro": "extra thick tarp mattress moving bag with handles",
        "unit_word": "bag",
        "default_unit_est_cents": 1299,
    },
    "supply_straps": {
        "title": "2-Person Forearm Lifting & Moving Straps",
        "short_title": "2-Person Lifting Straps",
        "category": "lifting_gear",
        "query_standard": "forearm lifting straps moving heavy furniture",
        "query_pro": "shoulder dolly heavy duty moving straps 2 movers",
        "unit_word": "set",
        "default_unit_est_cents": 1999,
    },
}

# Verified snapshot fallback ONLY used when venue Wi-Fi has no internet access (`offline_fallback`).
OFFLINE_FALLBACK_OFFERS: dict[str, dict[str, Any]] = {
    "box_small": {
        "product_id": "gid://shopify/p/offline_box_small",
        "variant_id": "gid://shopify/ProductVariant/44750305394884",
        "title": "Small Moving Box 16 x 12 x 12 (1.5 cu ft)",
        "variant_title": "Single Box",
        "pack_size": 1,
        "price_cents": 175,
        "currency": "USD",
        "seller_name": "Gpack Supplies",
        "seller_domain": "gpack-usa.myshopify.com",
        "seller_url": "https://gpack-usa.myshopify.com",
        "product_url": "https://gpack-usa.myshopify.com",
        "checkout_url": "https://gpack-usa.myshopify.com",
        "image_url": "",
        "source": "offline_fallback",
    },
    "box_medium": {
        "product_id": "gid://shopify/p/offline_box_medium",
        "variant_id": "gid://shopify/ProductVariant/44750305427652",
        "title": "Moving Boxes 18 x 18 x 16 (Medium 3.0 cu ft)",
        "variant_title": "Single Box",
        "pack_size": 1,
        "price_cents": 225,
        "currency": "USD",
        "seller_name": "Gpack Supplies",
        "seller_domain": "gpack-usa.myshopify.com",
        "seller_url": "https://gpack-usa.myshopify.com",
        "product_url": "https://gpack-usa.myshopify.com",
        "checkout_url": "https://gpack-usa.myshopify.com",
        "image_url": "",
        "source": "offline_fallback",
    },
    "box_large": {
        "product_id": "gid://shopify/p/offline_box_large",
        "variant_id": "gid://shopify/ProductVariant/34310508970120",
        "title": "4.5 cu ft Large Moving Carton (18 x 18 x 24)",
        "variant_title": "Single Box",
        "pack_size": 1,
        "price_cents": 450,
        "currency": "USD",
        "seller_name": "New Haven Moving Equipment",
        "seller_domain": "newhavenadmin.myshopify.com",
        "seller_url": "https://newhaven.com",
        "product_url": "https://newhaven.com",
        "checkout_url": "https://newhaven.com",
        "image_url": "",
        "source": "offline_fallback",
    },
    "supply_blankets": {
        "product_id": "gid://shopify/p/offline_blankets",
        "variant_id": "gid://shopify/ProductVariant/50890760388914",
        "title": "Moving Blankets 12 pcs (72x80)",
        "variant_title": "12 Pack",
        "pack_size": 12,
        "price_cents": 6000,
        "currency": "USD",
        "seller_name": "Karim Moving Supplies",
        "seller_domain": "a19217.myshopify.com",
        "seller_url": "https://a19217.myshopify.com",
        "product_url": "https://a19217.myshopify.com",
        "checkout_url": "https://a19217.myshopify.com",
        "image_url": "",
        "source": "offline_fallback",
    },
    "supply_tape": {
        "product_id": "gid://shopify/p/offline_tape",
        "variant_id": "gid://shopify/ProductVariant/44126382293224",
        "title": "Scotch Heavy Duty Shipping Packaging Tape with Dispenser, 4 Rolls",
        "variant_title": "4 Rolls",
        "pack_size": 4,
        "price_cents": 2198,
        "currency": "USD",
        "seller_name": "ShelHealth",
        "seller_domain": "shelhealth.myshopify.com",
        "seller_url": "https://shelhealth.myshopify.com",
        "product_url": "https://shelhealth.myshopify.com",
        "checkout_url": "https://shelhealth.myshopify.com",
        "image_url": "",
        "source": "offline_fallback",
    },
}

_req_counter = 0
_req_lock = threading.Lock()


def _next_req_id() -> int:
    global _req_counter
    with _req_lock:
        _req_counter += 1
        return _req_counter


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    txt = re.sub(r"<[^>]+>", " ", str(raw))
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _sha_key(prefix: str, payload: Any) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _shop_job_name() -> str:
    jobs = load_config().get("jobs", {})
    for candidate in ("shop", "plan", "perceive"):
        if candidate in jobs:
            return candidate
    return "hello"


class ShopMCPError(RuntimeError):
    """Raised when `mcp.shop.com` returns an HTTP or JSON-RPC error."""


class ShopMCPClient:
    """Zero-API-key client for Shopify's hosted `https://mcp.shop.com` MCP server."""

    def __init__(self, endpoint: str = SHOP_MCP_URL, timeout_s: float = 14.0, use_cache: bool = True):
        self.endpoint = endpoint.rstrip("/") or "https://mcp.shop.com"
        self.timeout_s = timeout_s
        self.use_cache = use_cache

    def _cache_read(self, key: str, max_age_s: float = 3600.0) -> dict[str, Any] | None:
        if not self.use_cache:
            return None
        p = SHOP_CACHE_DIR / f"{key}.json"
        if not p.exists():
            return None
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if time.time() - float(obj.get("ts", 0)) <= max_age_s:
                return obj.get("data")
        except Exception:
            return None
        return None

    def _cache_write(self, key: str, data: dict[str, Any]) -> None:
        if not self.use_cache:
            return
        try:
            SHOP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = SHOP_CACHE_DIR / f"{key}.{threading.get_ident()}.tmp"
            tmp.write_text(json.dumps({"ts": time.time(), "data": data}), encoding="utf-8")
            os.replace(tmp, SHOP_CACHE_DIR / f"{key}.json")
        except Exception:
            pass

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        cacheable: bool = False,
        cache_ttl_s: float = 3600.0,
    ) -> dict[str, Any]:
        """Invoke an MCP tool on `https://mcp.shop.com` and return its `structuredContent` dict."""
        cache_key = _sha_key(name, arguments) if cacheable else ""
        if cacheable:
            hit = self._cache_read(cache_key, max_age_s=cache_ttl_s)
            if hit is not None:
                return {**hit, "_cached": True}

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            "Mcp-Method": "tools/call",
            "Mcp-Name": name,
            "User-Agent": "PackItUp-ShoppingAgent/1.0",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": _next_req_id(),
            "method": "tools/call",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
                "name": name,
                "arguments": arguments,
            },
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")[:400]
            except Exception:
                pass
            raise ShopMCPError(f"HTTP {exc.code} calling {name}: {err_body}") from exc
        except Exception as exc:
            raise ShopMCPError(f"Network error calling {name}: {exc}") from exc

        parsed = _parse_mcp_response_body(raw)
        if "error" in parsed and parsed["error"]:
            err = parsed["error"]
            raise ShopMCPError(f"MCP error in {name} ({err.get('code')}): {err.get('message')}")

        result = parsed.get("result") or {}
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            # Fall back to parsing JSON text content block if structuredContent is absent.
            structured = {}
            for block in result.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    txt = str(block["text"]).strip()
                    if txt.startswith("{"):
                        try:
                            structured = json.loads(txt)
                            break
                        except Exception:
                            structured = {"text": txt}
                    else:
                        structured = {"text": txt}

        out = {
            **structured,
            "_is_error": bool(result.get("isError")),
            "_latency_ms": round((time.time() - t0) * 1000),
            "_cached": False,
        }
        if cacheable and not out["_is_error"]:
            self._cache_write(cache_key, out)
        return out

    def search_catalog(
        self,
        query: str | None = None,
        *,
        destination: dict[str, str] | None = None,
        max_price_cents: int | None = None,
        min_price_cents: int | None = None,
        shops: list[str] | None = None,
        like_id: str | None = None,
        like_image_b64: str | None = None,
        like_image_mime: str = "image/jpeg",
        limit: int = 6,
    ) -> dict[str, Any]:
        dest = {**DEFAULT_DESTINATION, **(destination or {})}
        cat: dict[str, Any] = {
            "context": {
                "address_country": dest["country"],
                "address_region": dest["region"],
                "postal_code": dest["postal_code"],
                "currency": dest["currency"],
            },
            "filters": {
                "ships_to": {
                    "country": dest["country"],
                    "region": dest["region"],
                    "postal_code": dest["postal_code"],
                }
            },
            "pagination": {"limit": max(1, min(20, int(limit)))},
        }
        if query:
            cat["query"] = query
        if max_price_cents is not None or min_price_cents is not None:
            price_f: dict[str, int] = {}
            if min_price_cents is not None:
                price_f["min"] = int(min_price_cents)
            if max_price_cents is not None:
                price_f["max"] = int(max_price_cents)
            cat["filters"]["price"] = price_f
        if shops:
            cat["filters"]["shops"] = list(shops)
        if like_image_b64:
            cat["like"] = {"image": {"content_type": like_image_mime, "data": like_image_b64}}
        elif like_id:
            cat["like"] = {"id": like_id}

        # Do not disk-cache large base64 image payloads if huge, otherwise cache 1 hour.
        return self.call_tool("search_catalog", {"catalog": cat}, cacheable=not bool(like_image_b64))

    def get_product(self, product_id: str, selected: list[dict[str, str]] | None = None) -> dict[str, Any]:
        arg: dict[str, Any] = {"id": product_id, "context": {"address_country": "US", "currency": "USD"}}
        if selected:
            arg["selected"] = selected
        return self.call_tool("get_product", {"catalog": arg}, cacheable=True)

    def ask_business(self, shop_domain: str, query: str, ids: list[str] | None = None) -> dict[str, Any]:
        ask_obj: dict[str, Any] = {"query": query}
        if ids:
            ask_obj["ids"] = list(ids)
        return self.call_tool("ask_business", {"shop": shop_domain, "ask": ask_obj}, cacheable=True, cache_ttl_s=900.0)

    def create_cart(self, shop_domain: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.call_tool(
            "create_cart",
            {"shop": shop_domain, "cart": {"line_items": line_items}},
            cacheable=True,
            cache_ttl_s=600.0,
        )

    def create_checkout(self, shop_domain: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.call_tool(
            "create_checkout",
            {"shop": shop_domain, "checkout": {"line_items": line_items}},
            cacheable=True,
            cache_ttl_s=600.0,
        )


def _parse_mcp_response_body(raw: str) -> dict[str, Any]:
    txt = raw.strip()
    if txt.startswith("{"):
        return json.loads(txt)
    # Handle text/event-stream SSE framing (`data: {...}`).
    last_json: dict[str, Any] = {}
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk.startswith("{"):
                try:
                    last_json = json.loads(chunk)
                except Exception:
                    continue
    if last_json:
        return last_json
    raise ShopMCPError(f"Unparseable MCP response: {txt[:200]!r}")


# ---------------------------------------------------------------------------
# Pack-count & physical-dimension parsing for Shopify Catalog offers
# ---------------------------------------------------------------------------

_SINGLE_RE = re.compile(r"\b(?:single\s+box|single\s+carton|1\s*-\s*pack|pack\s+of\s+1|qty\s*:?\s*1)\b", re.I)
_PACK_OF_RE = re.compile(r"\b(?:pack|bundle|case|set|box|lot)\s+of\s+(\d{1,3})\b", re.I)
_COUNT_UNIT_RE = re.compile(
    r"(?<![x×\d/.])(\d{1,3})\s*(?:-\s*)?(?:pack|pk|pcs|pieces|rolls?|bundle|ct|count|blankets?|pads?|bags?|cartons?)\b",
    re.I,
)
_DIMS_3D_RE = re.compile(
    r"(\d{1,2}(?:\.\d+)?)\s*(?:\"|\bin\b|inch(?:es)?)?\s*[x×]\s*"
    r"(\d{1,2}(?:\.\d+)?)\s*(?:\"|\bin\b|inch(?:es)?)?\s*[x×]\s*"
    r"(\d{1,2}(?:\.\d+)?)",
    re.I,
)


def parse_pack_size(title: str, variant_title: str = "", description: str = "") -> int:
    """Infer how many physical units (boxes, rolls, blankets) one variant quantity contains."""
    head = f"{variant_title} | {title}".strip()
    if _SINGLE_RE.search(head):
        return 1

    # Remove 3D/2D dimension substrings (`18 x 18 x 16`, `72x80`) and strength ratings (`200 lb`, `32 ect`)
    # so dimension numbers are never mistaken for pack counts.
    cleaned = _DIMS_3D_RE.sub(" ", head)
    cleaned = re.sub(r"\b\d+\s*[x×]\s*\d+\b", " ", cleaned)
    cleaned = re.sub(r"\b\d+\s*(?:lb|lbs|pound|ect|mil|yd|yds|yards?|ft|feet|cu\.?\s*ft|gauge)\b", " ", cleaned, flags=re.I)

    m = _PACK_OF_RE.search(cleaned)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 120:
            return n

    m2 = _COUNT_UNIT_RE.search(cleaned)
    if m2:
        n = int(m2.group(1))
        if 1 <= n <= 120:
            return n

    # Check short plain description only for explicit `Package Includes: N x ...` or `Pack of N`.
    if description:
        desc_short = description[:500]
        m3 = _PACK_OF_RE.search(desc_short)
        if m3:
            n = int(m3.group(1))
            if 1 <= n <= 120:
                return n
    return 1


def parse_box_dims_in(text: str) -> tuple[float, float, float] | None:
    """Extract `(d1, d2, d3)` inches sorted descending from product title/description if present."""
    for m in _DIMS_3D_RE.finditer(text):
        vals = sorted((float(m.group(1)), float(m.group(2)), float(m.group(3))), reverse=True)
        # Ignore cm conversions that follow a slash when inches already matched first, or huge/tiny numbers.
        if 2.0 <= vals[0] <= 90.0 and 1.0 <= vals[2] <= 60.0:
            return (vals[0], vals[1], vals[2])
    return None


def _normalize_catalog_offers(products: list[dict[str, Any]], need: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Shop MCP `products[]` into scored, spec-checked offer dicts."""
    candidates: list[dict[str, Any]] = []
    min_max_dim = float(need.get("min_max_dim_in") or 0.0)
    target_dims = need.get("target_dims_in")
    qty_needed = max(1, int(need["qty_needed"]))

    for rank_idx, prod in enumerate(products):
        p_title = str(prod.get("title") or "").strip()
        p_desc = _strip_html(((prod.get("description") or {}).get("plain")) if isinstance(prod.get("description"), dict) else "")
        p_media = prod.get("media") or []
        p_img = ""
        if p_media and isinstance(p_media[0], dict):
            p_img = str(((p_media[0].get("preview") or {}).get("url")) or p_media[0].get("url") or "")

        for var in (prod.get("variants") or [])[:3]:
            avail = (var.get("availability") or {}).get("available", True)
            if not avail:
                continue
            price_obj = var.get("price") or {}
            price_cents = int(price_obj.get("amount") or 0)
            currency = str(price_obj.get("currency") or "USD")
            if price_cents < 50 or currency != "USD":
                continue

            seller = var.get("seller") or {}
            shop_domain = str(seller.get("domain") or "").strip()
            vid = str(var.get("id") or "").strip()
            if not shop_domain or not vid:
                continue

            v_title = str(var.get("title") or p_title).strip()
            v_desc = _strip_html(((var.get("description") or {}).get("plain")) if isinstance(var.get("description"), dict) else p_desc)
            v_media = var.get("media") or []
            img_url = p_img
            if v_media and isinstance(v_media[0], dict):
                img_url = str(((v_media[0].get("preview") or {}).get("url")) or v_media[0].get("url") or p_img)

            combined_title = f"{p_title} {v_title}"
            low_text = combined_title.lower()
            # Filter out obvious non-supply noise (dollhouse miniatures, graphic tees, stickers, gift cards).
            if any(bad in low_text for bad in ("dollhouse", "miniature", "t-shirt", "hoodie", "gift card", "earring", "necklace")):
                continue

            parsed_dims = parse_box_dims_in(combined_title) or parse_box_dims_in(v_desc[:300])
            if min_max_dim > 0 and parsed_dims is not None:
                # Reject tiny e-commerce jewelry/shipping mailers (e.g. 8x6x4) when buying real moving boxes!
                if parsed_dims[0] < min_max_dim - 1.5:
                    continue

            pack_size = parse_pack_size(p_title, v_title, v_desc)
            # Guard against buying a giant 100-pack wholesale pallet when the user needs 3 boxes.
            if pack_size > max(36, qty_needed * 6):
                continue

            packs_to_order = max(1, math.ceil(qty_needed / pack_size))
            units_total = packs_to_order * pack_size
            line_total_cents = packs_to_order * price_cents
            eff_unit_cents = round(line_total_cents / max(1, qty_needed))

            # Reject absurdly overpriced industrial freight listings (> $260 for a single supply line unless >25 boxes).
            max_line_cap = max(26000, qty_needed * 3200)
            if line_total_cents > max_line_cap:
                continue

            # Dimension closeness bonus when buying moving boxes.
            dim_bonus = 0.0
            if target_dims and parsed_dims:
                td = sorted((float(x) for x in target_dims), reverse=True)
                diff = sum(abs(a - b) for a, b in zip(td, parsed_dims))
                dim_bonus = max(0.0, 28.0 - diff * 3.0)
            elif min_max_dim > 0 and parsed_dims is None:
                # Slight penalty if box listing doesn't state dimensions at all.
                dim_bonus = -8.0

            overshoot_ratio = (units_total - qty_needed) / max(1, qty_needed)
            overshoot_penalty = overshoot_ratio * 14.0
            rank_bonus = max(0.0, 12.0 - rank_idx * 2.5)
            est_cents = int(need.get("default_unit_est_cents") or 500)
            price_score = max(-35.0, min(25.0, ((est_cents - eff_unit_cents) / max(100, est_cents)) * 22.0))

            fit_score = round(50.0 + dim_bonus + rank_bonus + price_score - overshoot_penalty, 2)

            candidates.append({
                "product_id": str(prod.get("id") or ""),
                "variant_id": vid,
                "title": p_title,
                "variant_title": v_title if v_title != p_title else ("Single Unit" if pack_size == 1 else f"{pack_size}-Pack"),
                "pack_size": pack_size,
                "packs_to_order": packs_to_order,
                "units_supplied": units_total,
                "price_cents": price_cents,
                "line_total_cents": line_total_cents,
                "effective_unit_cents": eff_unit_cents,
                "currency": currency,
                "parsed_dims_in": list(parsed_dims) if parsed_dims else None,
                "seller_id": str(seller.get("id") or ""),
                "seller_name": str(seller.get("name") or shop_domain),
                "seller_domain": shop_domain,
                "seller_url": str(seller.get("url") or f"https://{shop_domain}"),
                "product_url": str(var.get("url") or seller.get("url") or f"https://{shop_domain}"),
                "checkout_url": str(var.get("checkout_url") or var.get("url") or ""),
                "image_url": img_url,
                "highlights": ((prod.get("metadata") or {}).get("top_features") or [])[:2],
                "fit_score": fit_score,
                "source": "shop_mcp_live",
            })

    # Deduplicate by (seller_domain, variant_id) and sort by fit_score descending.
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for c in sorted(candidates, key=lambda x: (-x["fit_score"], x["line_total_cents"])):
        if c["variant_id"] in seen:
            continue
        seen.add(c["variant_id"])
        uniq.append(c)
    return uniq


# ---------------------------------------------------------------------------
# Step 1: Compute Physics-Grounded Move Supply Bill of Materials
# ---------------------------------------------------------------------------

def compute_supply_needs(
    inventory: dict[str, Any],
    plan: dict[str, Any] | None = None,
    *,
    tier: str = "standard",
    custom_additions: list[dict[str, Any]] | None = None,
    excluded_ids: set[str] | None = None,
    qty_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Derive exact moving boxes and protection supplies from `inventory_v2` + `plan`."""
    tier = tier if tier in ("essential", "standard", "pro_heavy_duty") else "standard"
    buffer_mult = 1.0 if tier == "essential" else (1.20 if tier == "pro_heavy_duty" else 1.10)
    excluded = set(excluded_ids or set())
    overrides = dict(qty_overrides or {})

    # Prefer placed items across solved trucks if `plan` is provided, else expand inventory directly.
    if plan and isinstance(plan.get("trucks"), list) and plan["trucks"]:
        pieces: list[dict[str, Any]] = []
        for t in plan["trucks"]:
            pieces.extend(t.get("items") or [])
    else:
        pieces = expand.expand_inventory(inventory)

    box_counts: dict[str, int] = {}
    box_rooms: dict[str, set[str]] = {}
    furniture_pieces: list[dict[str, Any]] = []
    fragile_items: list[str] = []
    two_person_items: list[str] = []
    disassemble_items: list[str] = []
    mattress_count = 0

    for p in pieces:
        cid = str(p.get("catalog_id") or "")
        label = str(p.get("label") or "item")
        rname = str(p.get("room_name") or "Room")
        if p.get("is_box") or cid.startswith("box_"):
            bkey = cid if cid in BOX_SUPPLY_SPECS else "box_medium"
            box_counts[bkey] = box_counts.get(bkey, 0) + 1
            box_rooms.setdefault(bkey, set()).add(rname)
        else:
            furniture_pieces.append(p)
            if p.get("fragile"):
                fragile_items.append(label)
            if p.get("two_person") or float(p.get("weight_lb") or 0) > 50.0:
                two_person_items.append(label)
            if p.get("disassemble"):
                disassemble_items.append(label)
            if cid.startswith("mattress_") or cid.startswith("box_spring_"):
                mattress_count += 1

    # Guarantee starter hardware/cable moving boxes if a room has movable furniture/AV gear
    # but closed/unfilmed cabinets initially resolved to 0 container boxes.
    if not box_counts and furniture_pieces:
        starter_small = max(2, len(disassemble_items) + 1)
        box_counts["box_small"] = starter_small
        box_rooms["box_small"] = {"Hardware, cables & loose tabletop items"}
        if len(fragile_items) >= 2:
            box_counts["box_medium"] = 2
            box_rooms["box_medium"] = {"Fragile accessories & cords"}

    needs: list[dict[str, Any]] = []
    total_raw_boxes = 0
    total_buffered_boxes = 0

    for bkey in ("box_small", "box_medium", "box_large", "box_xl", "box_wardrobe", "box_dish_pack"):
        raw_qty = box_counts.get(bkey, 0)
        if raw_qty <= 0 or bkey in excluded:
            continue
        total_raw_boxes += raw_qty
        qty = overrides.get(bkey, max(raw_qty, math.ceil(raw_qty * buffer_mult)))
        total_buffered_boxes += qty
        spec = BOX_SUPPLY_SPECS[bkey]
        rooms_str = ", ".join(sorted(box_rooms.get(bkey, set()))[:3])
        spare_note = f" (+{qty - raw_qty} spare)" if qty > raw_qty else ""
        needs.append({
            "need_id": bkey,
            "title": spec["title"],
            "short_title": spec["short_title"],
            "category": "boxes",
            "qty_needed": qty,
            "raw_plan_qty": raw_qty,
            "query": spec["query_pro"] if tier == "pro_heavy_duty" else spec["query_standard"],
            "target_dims_in": spec["target_dims_in"],
            "min_max_dim_in": spec["min_max_dim_in"],
            "default_unit_est_cents": spec["default_unit_est_cents"],
            "reason": f"{raw_qty} planned in {rooms_str}{spare_note}",
        })

    # Tape rolls (always needed when packing boxes or wrapping blankets).
    if "supply_tape" not in excluded and (total_buffered_boxes > 0 or furniture_pieces):
        tape_qty = overrides.get(
            "supply_tape",
            max(2, math.ceil((total_buffered_boxes + len(furniture_pieces) * 0.3) / 10.0)),
        )
        t_spec = PROTECTION_SPECS["supply_tape"]
        needs.append({
            "need_id": "supply_tape",
            "title": t_spec["title"],
            "short_title": t_spec["short_title"],
            "category": t_spec["category"],
            "qty_needed": tape_qty,
            "raw_plan_qty": tape_qty,
            "query": t_spec["query_pro"] if tier == "pro_heavy_duty" else t_spec["query_standard"],
            "default_unit_est_cents": t_spec["default_unit_est_cents"],
            "reason": f"Seals {total_buffered_boxes} moving boxes + pad securing (~1 roll per 10 boxes)",
        })

    # Bubble wrap for fragile items or dish packs.
    fragile_total = len(fragile_items) + box_counts.get("box_dish_pack", 0)
    if "supply_bubble" not in excluded and fragile_total > 0:
        bub_qty = overrides.get("supply_bubble", max(1, math.ceil(fragile_total / 4.0)))
        b_spec = PROTECTION_SPECS["supply_bubble"]
        sample_frag = ", ".join(dict.fromkeys(fragile_items))[:75] or "packed glassware"
        needs.append({
            "need_id": "supply_bubble",
            "title": b_spec["title"],
            "short_title": b_spec["short_title"],
            "category": b_spec["category"],
            "qty_needed": bub_qty,
            "raw_plan_qty": bub_qty,
            "query": b_spec["query_pro"] if tier == "pro_heavy_duty" else b_spec["query_standard"],
            "default_unit_est_cents": b_spec["default_unit_est_cents"],
            "reason": f"Protects {fragile_total} fragile piece(s): {sample_frag}",
        })

    # Moving blankets & stretch wrap (included in standard & pro tiers when furniture > 0).
    if tier != "essential" and furniture_pieces:
        if "supply_blankets" not in excluded:
            # Standard 26-ft truck move uses 1-2 dozen furniture pads (folding tables/chairs share pads).
            pad_qty = overrides.get("supply_blankets", min(24, max(4, math.ceil(len(furniture_pieces) * 0.4))))
            m_spec = PROTECTION_SPECS["supply_blankets"]
            needs.append({
                "need_id": "supply_blankets",
                "title": m_spec["title"],
                "short_title": m_spec["short_title"],
                "category": m_spec["category"],
                "qty_needed": pad_qty,
                "raw_plan_qty": pad_qty,
                "query": m_spec["query_pro"] if tier == "pro_heavy_duty" else m_spec["query_standard"],
                "default_unit_est_cents": m_spec["default_unit_est_cents"],
                "reason": f"Pads {len(furniture_pieces)} furniture/venue pieces against truck rub (up to 2 doz/fleet)",
            })

        if "supply_stretch" not in excluded and len(furniture_pieces) >= 2:
            st_qty = overrides.get("supply_stretch", min(4, max(1, math.ceil(len(furniture_pieces) / 25.0))))
            s_spec = PROTECTION_SPECS["supply_stretch"]
            needs.append({
                "need_id": "supply_stretch",
                "title": s_spec["title"],
                "short_title": s_spec["short_title"],
                "category": s_spec["category"],
                "qty_needed": st_qty,
                "raw_plan_qty": st_qty,
                "query": s_spec["query_pro"] if tier == "pro_heavy_duty" else s_spec["query_standard"],
                "default_unit_est_cents": s_spec["default_unit_est_cents"],
                "reason": "Secures drawers, bundled legs & moving blankets residue-free",
            })

    if "supply_mattress_bag" not in excluded and mattress_count > 0:
        mb_qty = overrides.get("supply_mattress_bag", mattress_count)
        mb_spec = PROTECTION_SPECS["supply_mattress_bag"]
        needs.append({
            "need_id": "supply_mattress_bag",
            "title": mb_spec["title"],
            "short_title": mb_spec["short_title"],
            "category": mb_spec["category"],
            "qty_needed": mb_qty,
            "raw_plan_qty": mattress_count,
            "query": mb_spec["query_pro"] if tier == "pro_heavy_duty" else mb_spec["query_standard"],
            "default_unit_est_cents": mb_spec["default_unit_est_cents"],
            "reason": f"Covers {mattress_count} mattress/box-spring piece(s) loaded on edge",
        })

    if tier != "essential" and "supply_straps" not in excluded and len(two_person_items) > 0:
        str_qty = overrides.get("supply_straps", 1)
        sp_spec = PROTECTION_SPECS["supply_straps"]
        heavy_sample = ", ".join(dict.fromkeys(two_person_items))[:70]
        needs.append({
            "need_id": "supply_straps",
            "title": sp_spec["title"],
            "short_title": sp_spec["short_title"],
            "category": sp_spec["category"],
            "qty_needed": str_qty,
            "raw_plan_qty": 1,
            "query": sp_spec["query_pro"] if tier == "pro_heavy_duty" else sp_spec["query_standard"],
            "default_unit_est_cents": sp_spec["default_unit_est_cents"],
            "reason": f"{len(two_person_items)} two-person lift(s) (>50 lb): {heavy_sample}",
        })

    for idx, extra in enumerate(custom_additions or [], start=1):
        nid = str(extra.get("need_id") or f"custom_{idx}")
        if nid in excluded:
            continue
        q_cnt = max(1, int(overrides.get(nid, extra.get("qty_needed") or 1)))
        needs.append({
            "need_id": nid,
            "title": str(extra.get("title") or extra.get("query") or "Added Moving Supply"),
            "short_title": str(extra.get("short_title") or extra.get("title") or "Added Supply"),
            "category": "agent_added",
            "qty_needed": q_cnt,
            "raw_plan_qty": q_cnt,
            "query": str(extra.get("query") or extra.get("title") or "moving supplies"),
            "default_unit_est_cents": int(extra.get("default_unit_est_cents") or 1500),
            "reason": str(extra.get("reason") or "Added by Pack It Up Shopping Agent"),
        })

    return {
        "tier": tier,
        "buffer_pct": round((buffer_mult - 1.0) * 100),
        "summary": {
            "raw_boxes": total_raw_boxes,
            "buffered_boxes": total_buffered_boxes,
            "furniture_pieces": len(furniture_pieces),
            "fragile_pieces": len(fragile_items),
            "two_person_lifts": len(two_person_items),
            "supply_lines": len(needs),
        },
        "needs": needs,
    }


# ---------------------------------------------------------------------------
# Step 2: Live Shop.dev Discovery + Merchant Consolidation + Decisions API
# ---------------------------------------------------------------------------

def _verify_offer_with_decisions_api(
    need: dict[str, Any],
    candidates: list[dict[str, Any]],
    run_dir: Path | None = None,
) -> tuple[int, dict[str, Any] | None]:
    """Use `gemini-decision-1` (`for_job('decide')`) to pick the best genuine moving supply offer."""
    if len(candidates) < 2:
        return 0, None
    top = candidates[:3]
    options = [f"offer_{i}" for i in range(len(top))]
    criteria = {
        f"offer_{i}": (
            f"{c['title']} ({c['variant_title']}) from {c['seller_name']} — "
            f"{c['packs_to_order']}x ${c['price_cents']/100:.2f} = ${c['line_total_cents']/100:.2f} "
            f"for {c['units_supplied']} units"
        )
        for i, c in enumerate(top)
    }
    question = (
        f"Which Shopify offer best fulfills a real household/commercial move requirement for "
        f"{need['qty_needed']}x '{need['title']}' ({need['reason']})? "
        f"Prefer genuine moving-grade corrugated cartons/supplies with matching dimensions and best total value; "
        f"avoid tiny gift/jewelry mailers or mismatched sizes."
    )
    try:
        dec = for_job("decide", run_dir).decide(
            question,
            options=options,
            criteria=criteria,
            label=f"shop_verify:{need['need_id']}",
        )
        ans = str(dec.get("answer") or "offer_0")
        chosen_idx = int(ans.split("_")[1]) if "_" in ans and ans.split("_")[1].isdigit() else 0
        chosen_idx = max(0, min(len(top) - 1, chosen_idx))
        return chosen_idx, {
            "need_id": need["need_id"],
            "chosen": top[chosen_idx]["title"],
            "seller": top[chosen_idx]["seller_name"],
            "confidence": round(float(dec.get("confidence") or 0.0), 3),
            "via": dec.get("via", "decisions_api"),
            "rationale": dec.get("rationale", ""),
        }
    except Exception:
        return 0, None


def build_move_kit(
    inventory: dict[str, Any],
    plan: dict[str, Any] | None = None,
    *,
    client: ShopMCPClient | None = None,
    destination: dict[str, str] | None = None,
    tier: str = "standard",
    verify_with_decisions: bool = True,
    max_budget_cents: int | None = None,
    custom_additions: list[dict[str, Any]] | None = None,
    excluded_ids: set[str] | None = None,
    qty_overrides: dict[str, int] | None = None,
    query_overrides: dict[str, str] | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    """End-to-end Shop.dev pipeline: BOM -> Catalog Discovery -> Merchant Consolidation -> Live Carts."""
    mcp = client or ShopMCPClient()
    dest = {**DEFAULT_DESTINATION, **(destination or {})}
    bom = compute_supply_needs(
        inventory,
        plan,
        tier=tier,
        custom_additions=custom_additions,
        excluded_ids=excluded_ids,
        qty_overrides=qty_overrides,
    )
    needs = bom["needs"]
    q_overrides = dict(query_overrides or {})
    for n in needs:
        if n["need_id"] in q_overrides:
            n["query"] = q_overrides[n["need_id"]]

    agent_trace: list[dict[str, Any]] = []
    candidates_by_need: dict[str, list[dict[str, Any]]] = {}
    live_hits = 0

    # 1. Parallel Shop MCP `search_catalog` across all needed supplies.
    def _search_one(need: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        nid = need["need_id"]
        try:
            res = mcp.search_catalog(need["query"], destination=dest, limit=6)
            prods = res.get("products") or []
            cands = _normalize_catalog_offers(prods, need)
            trace_item = {
                "step": "search_catalog",
                "tool": "mcp.shop.com/search_catalog",
                "need_id": nid,
                "query": need["query"],
                "raw_products": len(prods),
                "verified_candidates": len(cands),
                "latency_ms": res.get("_latency_ms", 0),
                "cached": bool(res.get("_cached")),
            }
            return nid, cands, trace_item
        except ShopMCPError as exc:
            fb = OFFLINE_FALLBACK_OFFERS.get(nid) or OFFLINE_FALLBACK_OFFERS.get("box_medium")
            fallback_cand = []
            if fb:
                ps = int(fb["pack_size"])
                packs = max(1, math.ceil(need["qty_needed"] / ps))
                fallback_cand = [{
                    **fb,
                    "packs_to_order": packs,
                    "units_supplied": packs * ps,
                    "line_total_cents": packs * int(fb["price_cents"]),
                    "effective_unit_cents": round((packs * int(fb["price_cents"])) / max(1, need["qty_needed"])),
                    "highlights": ["Offline cached snapshot (mcp.shop.com unreachable)"],
                    "fit_score": 10.0,
                }]
            return nid, fallback_cand, {
                "step": "search_catalog_fallback",
                "tool": "mcp.shop.com/search_catalog",
                "need_id": nid,
                "error": str(exc)[:180],
            }

    if needs:
        with ThreadPoolExecutor(max_workers=min(6, len(needs))) as pool:
            futs = [pool.submit(_search_one, n) for n in needs]
            for fut in as_completed(futs):
                nid, cands, tr = fut.result()
                candidates_by_need[nid] = cands
                agent_trace.append(tr)
                if cands and cands[0].get("source") == "shop_mcp_live":
                    live_hits += 1

    # 2. Merchant consolidation pass: find top recurring Shopify supply merchants and check if
    #    they also carry any remaining box/supply lines so we minimize separate merchant shipments!
    domain_freq: dict[str, int] = {}
    for cands in candidates_by_need.values():
        seen_dom: set[str] = set()
        for c in cands[:4]:
            if c.get("source") == "shop_mcp_live":
                seen_dom.add(c["seller_domain"])
        for d in seen_dom:
            domain_freq[d] = domain_freq.get(d, 0) + 1

    anchor_domains = [d for d, cnt in sorted(domain_freq.items(), key=lambda kv: -kv[1]) if cnt >= 1][:2]
    if anchor_domains and live_hits > 0:
        anchor = anchor_domains[0]
        missing_needs = [
            n for n in needs
            if not any(c["seller_domain"] == anchor for c in candidates_by_need.get(n["need_id"], []))
        ][:3]
        for mn in missing_needs:
            try:
                res_shop = mcp.search_catalog(mn["query"], destination=dest, shops=[anchor], limit=3)
                extra_cands = _normalize_catalog_offers(res_shop.get("products") or [], mn)
                if extra_cands:
                    merged = extra_cands + candidates_by_need.get(mn["need_id"], [])
                    candidates_by_need[mn["need_id"]] = merged
                    agent_trace.append({
                        "step": "merchant_consolidation",
                        "tool": "mcp.shop.com/search_catalog",
                        "need_id": mn["need_id"],
                        "shop": anchor,
                        "matched": len(extra_cands),
                    })
            except ShopMCPError:
                pass

        # Apply consolidation score boost (+14 pts) for anchor merchants so ties & near-ties bundle cleanly.
        for nid, cands in candidates_by_need.items():
            for c in cands:
                if c["seller_domain"] in anchor_domains:
                    c["fit_score"] = round(c["fit_score"] + 14.0, 2)
            cands.sort(key=lambda x: (-x["fit_score"], x["line_total_cents"]))

    # 3. Optional Gemini Decisions API (`gemini-decision-1`) verification on key box/fragile lines.
    decision_checks: list[dict[str, Any]] = []
    _load_env()
    has_gemini_key = bool(os.environ.get("GEMINI_API_KEY"))
    if verify_with_decisions and has_gemini_key and live_hits > 0:
        verify_targets = [
            n for n in needs
            if len(candidates_by_need.get(n["need_id"], [])) >= 2
            and (n["category"] in ("boxes", "fragile_protection"))
        ][:2]
        for vn in verify_targets:
            cands = candidates_by_need[vn["need_id"]]
            idx, dcheck = _verify_offer_with_decisions_api(vn, cands, run_dir=run_dir)
            if dcheck:
                decision_checks.append(dcheck)
                agent_trace.append({
                    "step": "decisions_api_verify",
                    "tool": "gemini-decision-1",
                    "need_id": vn["need_id"],
                    "chosen": dcheck["chosen"],
                    "confidence": dcheck["confidence"],
                })
                if idx > 0:
                    chosen = cands.pop(idx)
                    cands.insert(0, chosen)

    # 4. Budget guardrail: if `max_budget_cents` is set and top picks exceed it, switch lines to
    #    cheapest valid candidate first.
    if max_budget_cents is not None and max_budget_cents > 0:
        current_sum = sum(
            (candidates_by_need[n["need_id"]][0]["line_total_cents"] if candidates_by_need.get(n["need_id"]) else 0)
            for n in needs
        )
        if current_sum > max_budget_cents:
            for n in needs:
                cands = candidates_by_need.get(n["need_id"], [])
                if len(cands) > 1:
                    cands.sort(key=lambda x: x["line_total_cents"])
            agent_trace.append({
                "step": "budget_optimization",
                "target_budget_usd": round(max_budget_cents / 100.0, 2),
            })

    # 5. Assemble line Selections & create live Self-Healing Shopify Carts + Shop Pay Checkouts!
    selected_lines: list[dict[str, Any]] = []
    for n in needs:
        cands = candidates_by_need.get(n["need_id"], [])
        if not cands:
            continue
        selected_lines.append({
            "need": n,
            "selected": cands[0],
            "alternatives": cands[1:4],
        })

    carts = _build_self_healing_carts(mcp, selected_lines, agent_trace)

    subtotal_cents = sum(line["selected"]["line_total_cents"] for line in selected_lines)
    unbundled_merchants = len(selected_lines)
    consolidated_merchants = len(carts)

    items_out = []
    for entry in selected_lines:
        n = entry["need"]
        sel = entry["selected"]
        items_out.append({
            "need_id": n["need_id"],
            "need_title": n["title"],
            "short_title": n["short_title"],
            "category": n["category"],
            "qty_needed": n["qty_needed"],
            "raw_plan_qty": n["raw_plan_qty"],
            "reason": n["reason"],
            "offer": sel,
            "alternatives": entry["alternatives"],
        })

    return {
        "source_mode": "shop_mcp_live" if live_hits > 0 else "offline_fallback",
        "mcp_endpoint": mcp.endpoint,
        "protocol_version": MCP_PROTOCOL_VERSION,
        "destination": dest,
        "tier": bom["tier"],
        "buffer_pct": bom["buffer_pct"],
        "bom_summary": bom["summary"],
        "items": items_out,
        "merchant_carts": carts,
        "totals": {
            "subtotal_cents": subtotal_cents,
            "subtotal_usd": round(subtotal_cents / 100.0, 2),
            "currency": "USD",
            "line_count": len(items_out),
            "merchant_count": consolidated_merchants,
            "shipments_saved": max(0, unbundled_merchants - consolidated_merchants),
        },
        "decision_checks": decision_checks,
        "agent_trace": agent_trace,
        "disclosure": (
            "Live prices and stock via Shopify Catalog MCP (mcp.shop.com). "
            "Review shipping options, taxes, and delivery dates on each merchant's checkout before paying; "
            "Pack It Up never completes payment without your confirmation."
        ),
    }


def _build_self_healing_carts(
    mcp: ShopMCPClient,
    selected_lines: list[dict[str, Any]],
    agent_trace: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group selected variants by Shopify store and create live Cart + Shop Pay Checkout links.

    If a store rejects an item during `create_cart`, automatically swap that supply line to its
    next ranked candidate merchant and retry (`self-healing checkout`).
    """
    by_shop: dict[str, list[dict[str, Any]]] = {}
    for entry in selected_lines:
        sel = entry["selected"]
        by_shop.setdefault(sel["seller_domain"], []).append(entry)

    carts_out: list[dict[str, Any]] = []

    def _create_for_shop(shop_domain: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        first_sel = entries[0]["selected"]
        seller_name = first_sel["seller_name"]
        seller_url = first_sel["seller_url"]
        line_payload = [
            {"item": {"id": e["selected"]["variant_id"]}, "quantity": int(e["selected"]["packs_to_order"])}
            for e in entries
        ]
        subtotal_cents = sum(int(e["selected"]["line_total_cents"]) for e in entries)

        if first_sel.get("source") == "offline_fallback":
            return {
                "shop_domain": shop_domain,
                "seller_name": seller_name,
                "seller_url": seller_url,
                "cart_id": None,
                "checkout_id": None,
                "cart_url": seller_url,
                "shop_pay_url": None,
                "continue_url": seller_url,
                "shop_pay_supported": False,
                "subtotal_cents": subtotal_cents,
                "subtotal_usd": round(subtotal_cents / 100.0, 2),
                "currency": "USD",
                "line_count": len(entries),
                "items": [
                    {
                        "need_id": e["need"]["need_id"],
                        "title": e["selected"]["title"],
                        "quantity": e["selected"]["packs_to_order"],
                        "units_supplied": e["selected"]["units_supplied"],
                        "line_total_cents": e["selected"]["line_total_cents"],
                        "product_url": e["selected"]["product_url"],
                    }
                    for e in entries
                ],
                "warnings": ["Offline snapshot mode — connect to internet for live Shopify cart URLs."],
                "source": "offline_fallback",
            }

        cart_url = ""
        cart_id = None
        shop_pay_url = ""
        checkout_id = None
        shop_pay_supported = False
        warnings: list[str] = []

        try:
            cart_res = mcp.create_cart(shop_domain, line_payload)
            cart_id = cart_res.get("id")
            cart_url = str(cart_res.get("continue_url") or "")
            returned_lines = cart_res.get("line_items") or []
            for m in cart_res.get("messages") or []:
                if isinstance(m, dict) and m.get("content"):
                    warnings.append(str(m["content"]))

            # Self-healing check: if cart came back empty when we sent items, swap to backup merchant!
            if not returned_lines and not cart_url:
                raise ShopMCPError("create_cart returned empty basket")
        except ShopMCPError as exc:
            agent_trace.append({
                "step": "cart_recovery_triggered",
                "shop": shop_domain,
                "reason": str(exc)[:140],
            })
            # Try swapping entries that have alternatives to their runner-up merchant.
            recovered_any = False
            for e in entries:
                alts = e.get("alternatives") or []
                if alts:
                    backup = alts.pop(0)
                    e["selected"] = backup
                    recovered_any = True
                    agent_trace.append({
                        "step": "cart_merchant_swapped",
                        "need_id": e["need"]["need_id"],
                        "new_shop": backup["seller_domain"],
                        "new_title": backup["title"],
                    })
            if recovered_any and len(entries) == 1:
                return _create_for_shop(entries[0]["selected"]["seller_domain"], entries)
            cart_url = first_sel.get("checkout_url") or first_sel.get("product_url") or seller_url

        # Also prepare Universal Checkout (`shop.app/checkouts/...`) for one-click Shop Pay!
        try:
            ck_res = mcp.create_checkout(shop_domain, line_payload)
            checkout_id = ck_res.get("id")
            ck_url = str(ck_res.get("continue_url") or "")
            handlers = ((ck_res.get("ucp") or {}).get("payment_handlers")) or {}
            shop_pay_supported = "dev.shopify.shop_pay" in handlers
            # Check if merchant flagged `delivery_no_delivery_available` without address.
            ck_msgs = [
                str(m.get("code") or "")
                for m in (ck_res.get("messages") or [])
                if isinstance(m, dict)
            ]
            if ck_url and "delivery_no_delivery_available" not in ck_msgs:
                shop_pay_url = ck_url
        except ShopMCPError:
            pass

        primary_continue = cart_url or shop_pay_url or first_sel.get("checkout_url") or first_sel.get("product_url")
        agent_trace.append({
            "step": "create_cart",
            "tool": "mcp.shop.com/create_cart",
            "shop": shop_domain,
            "lines": len(entries),
            "shop_pay": shop_pay_supported,
            "has_continue_url": bool(primary_continue),
        })

        return {
            "shop_domain": shop_domain,
            "seller_name": seller_name,
            "seller_url": seller_url,
            "cart_id": cart_id,
            "checkout_id": checkout_id,
            "cart_url": cart_url or primary_continue,
            "shop_pay_url": shop_pay_url or None,
            "continue_url": primary_continue,
            "shop_pay_supported": shop_pay_supported,
            "subtotal_cents": subtotal_cents,
            "subtotal_usd": round(subtotal_cents / 100.0, 2),
            "currency": "USD",
            "line_count": len(entries),
            "items": [
                {
                    "need_id": e["need"]["need_id"],
                    "title": e["selected"]["title"],
                    "variant_title": e["selected"]["variant_title"],
                    "quantity": e["selected"]["packs_to_order"],
                    "units_supplied": e["selected"]["units_supplied"],
                    "price_cents": e["selected"]["price_cents"],
                    "line_total_cents": e["selected"]["line_total_cents"],
                    "image_url": e["selected"]["image_url"],
                    "product_url": e["selected"]["product_url"],
                }
                for e in entries
            ],
            "warnings": warnings[:3],
            "source": "shop_mcp_live",
        }

    if by_shop:
        with ThreadPoolExecutor(max_workers=min(5, len(by_shop))) as pool:
            futs = [pool.submit(_create_for_shop, dom, grp) for dom, grp in by_shop.items()]
            for fut in as_completed(futs):
                carts_out.append(fut.result())

    carts_out.sort(key=lambda c: (-c["line_count"], -c["subtotal_cents"]))
    return carts_out


# ---------------------------------------------------------------------------
# Step 3: Haul vs. Replace & Sell-Item Comps (with Visual `like.image` Crops!)
# ---------------------------------------------------------------------------

def _crop_item_image_b64(item: dict[str, Any], run_dir: Path | None) -> str | None:
    """If `run_dir` has the source photo for `item`, crop `box_2d` as JPEG base64 for Shop MCP `like.image`."""
    if run_dir is None or not run_dir.exists():
        return None
    ev = item.get("evidence") or {}
    if ev.get("kind") != "image" or not ev.get("source"):
        return None
    media_dir = run_dir / "media"
    if not media_dir.exists():
        return None
    src_name = str(ev["source"])
    candidates = list(media_dir.glob(f"*{Path(src_name).name}"))
    if not candidates:
        return None
    try:
        from PIL import Image

        with Image.open(candidates[0]) as im:
            im = im.convert("RGB")
            w, h = im.size
            box = ev.get("box_2d")
            if isinstance(box, list) and len(box) == 4:
                ymin, xmin, ymax, xmax = [float(v) for v in box]
                left = max(0, int((xmin / 1000.0) * w))
                top = max(0, int((ymin / 1000.0) * h))
                right = min(w, int((xmax / 1000.0) * w))
                bottom = min(h, int((ymax / 1000.0) * h))
                if right - left >= 32 and bottom - top >= 32:
                    im = im.crop((left, top, right, bottom))
            im.thumbnail((512, 512))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def discover_item_comps(
    inventory: dict[str, Any],
    *,
    client: ShopMCPClient | None = None,
    destination: dict[str, str] | None = None,
    run_dir: Path | None = None,
    max_items: int = 4,
) -> list[dict[str, Any]]:
    """Find live Shopify comps for items marked `sell` AND bulky 'Haul vs. Replace' furniture."""
    mcp = client or ShopMCPClient()
    dest = {**DEFAULT_DESTINATION, **(destination or {})}

    targets: list[tuple[str, dict[str, Any], str]] = []
    for room_block in inventory.get("rooms", []):
        rname = str((room_block.get("room") or {}).get("name") or "Room")
        for it in room_block.get("items", []):
            disp = str(it.get("disposition") or "undecided").lower()
            vol_total = float((it.get("size") or {}).get("volume_cuft_total") or 0.0)
            vol_each = float((it.get("size") or {}).get("volume_cuft_each") or 0.0)
            if disp == "sell":
                targets.append(("sell_comp", it, rname))
            elif disp in ("keep", "undecided") and vol_total >= 15.0 and not it.get("heard_only"):
                # Bulky items where truck space (~$4.75/cu ft NYC move cost) can rival buying new at destination!
                targets.append(("haul_vs_replace", it, rname))

    # Prioritize `sell` items first, then largest truck-space hogs.
    targets.sort(key=lambda t: (0 if t[0] == "sell_comp" else 1, -float((t[1].get("size") or {}).get("volume_cuft_total") or 0)))
    targets = targets[:max_items]
    if not targets:
        return []

    results: list[dict[str, Any]] = []

    def _lookup_comp(mode: str, item: dict[str, Any], room_name: str) -> dict[str, Any] | None:
        label = str(item.get("label") or "furniture")
        qty = max(1, int(item.get("quantity") or 1))
        vol_total = float((item.get("size") or {}).get("volume_cuft_total") or 10.0)
        est_haul_cost_usd = round(vol_total * 4.75, 2)
        crop_b64 = _crop_item_image_b64(item, run_dir)
        try:
            res = mcp.search_catalog(
                label,
                destination=dest,
                like_image_b64=crop_b64,
                limit=3,
            )
            prods = res.get("products") or []
        except ShopMCPError:
            return None

        for p in prods:
            for v in (p.get("variants") or [])[:2]:
                if not (v.get("availability") or {}).get("available", True):
                    continue
                amt = int((v.get("price") or {}).get("amount") or 0)
                if amt < 800:
                    continue
                seller = v.get("seller") or {}
                media = p.get("media") or []
                img = str(((media[0].get("preview") or {}).get("url")) or media[0].get("url") or "") if media else ""
                unit_usd = round(amt / 100.0, 2)
                replace_total_usd = round(unit_usd * qty, 2)
                verdict = (
                    f"Suggested resale ask ~${round(unit_usd * 0.55)}–${round(unit_usd * 0.70)} each (new comp ${unit_usd:.2f})"
                    if mode == "sell_comp"
                    else (
                        f"Consider replacing at destination: occupies {vol_total:.1f} cu ft (~${est_haul_cost_usd:.0f} truck space) vs ${replace_total_usd:.0f} new"
                        if replace_total_usd <= est_haul_cost_usd * 1.25
                        else f"Worth hauling: ${replace_total_usd:.0f} to replace new vs ~${est_haul_cost_usd:.0f} of truck space ({vol_total:.1f} cu ft)"
                    )
                )
                return {
                    "mode": mode,
                    "used_visual_crop": bool(crop_b64),
                    "item_id": item.get("id"),
                    "item_label": label,
                    "room_name": room_name,
                    "quantity": qty,
                    "volume_cuft_total": round(vol_total, 1),
                    "est_haul_cost_usd": est_haul_cost_usd,
                    "verdict": verdict,
                    "comp": {
                        "title": p.get("title"),
                        "price_usd": unit_usd,
                        "replace_total_usd": replace_total_usd,
                        "seller_name": seller.get("name") or seller.get("domain"),
                        "seller_domain": seller.get("domain"),
                        "product_url": v.get("url"),
                        "checkout_url": v.get("checkout_url") or v.get("url"),
                        "image_url": img,
                    },
                }
        return None

    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        futs = [pool.submit(_lookup_comp, m, it, rn) for m, it, rn in targets]
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                results.append(r)

    return results


# ---------------------------------------------------------------------------
# Step 4: Conversational Gemini 4 + Shop.dev Shopping Agent
# ---------------------------------------------------------------------------

AGENT_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tier", "max_budget_usd", "add_items", "remove_need_ids", "qty_overrides", "query_overrides", "merchant_question", "reply"],
    "properties": {
        "tier": {
            "type": "string",
            "enum": ["keep", "essential", "standard", "pro_heavy_duty"],
            "description": "Change kit tier if user asks for budget/minimal ('essential'), balanced ('standard'), or heavy-duty/double-wall ('pro_heavy_duty'); else 'keep'.",
        },
        "max_budget_usd": {
            "type": ["number", "null"],
            "description": "Firm dollar ceiling if user stated a maximum budget (e.g. 150), else null.",
        },
        "add_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "query", "qty_needed", "reason"],
                "properties": {
                    "title": {"type": "string"},
                    "query": {"type": "string", "description": "Concise Shopify search_catalog query, e.g. 'heavy duty hand truck dolly' or 'recycled honeycomb packing paper'"},
                    "qty_needed": {"type": "integer", "minimum": 1, "maximum": 100},
                    "reason": {"type": "string"},
                },
            },
        },
        "remove_need_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "qty_overrides": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["need_id", "qty"],
                "properties": {
                    "need_id": {"type": "string"},
                    "qty": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            },
        },
        "query_overrides": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["need_id", "query"],
                "properties": {
                    "need_id": {"type": "string"},
                    "query": {"type": "string"},
                },
            },
        },
        "merchant_question": {
            "type": ["object", "null"],
            "required": ["shop_domain", "query"],
            "properties": {
                "shop_domain": {"type": "string"},
                "query": {"type": "string"},
            },
        },
        "reply": {
            "type": "string",
            "description": "Warm, concise plain-English reply explaining what you updated or found, using shopper language ('boxes', 'checkout', never schema jargon).",
        },
    },
}


def run_shopping_agent(
    message: str,
    inventory: dict[str, Any],
    plan: dict[str, Any] | None = None,
    *,
    current_state: dict[str, Any] | None = None,
    client: ShopMCPClient | None = None,
    destination: dict[str, str] | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    """Process a user prompt with Gemini 4 + live `mcp.shop.com` tools and return updated kit & reply."""
    mcp = client or ShopMCPClient()
    state = dict(current_state or {})
    cur_tier = str(state.get("tier") or "standard")
    custom_adds = list(state.get("custom_additions") or [])
    excluded = set(state.get("excluded_ids") or [])
    qty_ov = {str(k): int(v) for k, v in (state.get("qty_overrides") or {}).items()}
    query_ov = {str(k): str(v) for k, v in (state.get("query_overrides") or {}).items()}
    max_budget_cents = state.get("max_budget_cents")

    # Build a current snapshot first if caller didn't pass current items/merchants.
    preview_bom = compute_supply_needs(
        inventory,
        plan,
        tier=cur_tier,
        custom_additions=custom_adds,
        excluded_ids=excluded,
        qty_overrides=qty_ov,
    )
    known_shops = list(state.get("known_shops") or [])

    action: dict[str, Any] | None = None
    used_model = "rule_fallback"

    _load_env()
    if os.environ.get("GEMINI_API_KEY"):
        job_name = _shop_job_name()
        prompt = (
            "You are the Pack It Up Shopping Agent powered by Shopify (shop.dev / mcp.shop.com).\n"
            "Be a warm, practical moving & shopping assistant. Use everyday shopper language ('pack size', "
            "'checkout', never 'variant GID' or 'UCP'). Never claim an order has already been paid for.\n\n"
            f"Current kit tier: {cur_tier}\n"
            f"Current supply needs:\n{json.dumps(preview_bom['needs'], indent=2)}\n"
            f"Known merchant domains in current cart (pass '' for shop_domain to ask the primary merchant): {known_shops}\n\n"
            f"Shopper request: {message!r}\n\n"
            "Return JSON matching the schema to update tiers, quantities, custom items (such as hand trucks, "
            "packing paper, eco-friendly supplies, furniture sliders, box cutters, QR label pouches), "
            "refined search queries, budget cap, or a question to ask one of the merchants via `ask_business`."
        )
        try:
            job = for_job(job_name, run_dir)
            action = job.generate_json(
                prompt,
                schema=AGENT_ACTION_SCHEMA,
                prompt_version="shop_agent_v1",
                label="shopping_agent",
            )
            used_model = f"{job.provider.name}:{job.provider.model}"
        except LLMError:
            action = None

    # Deterministic fallback if no API key or model call failed, so tests & offline mode always work.
    if action is None:
        action = _heuristic_agent_action(message, preview_bom["needs"], known_shops)

    if action.get("tier") and action["tier"] != "keep":
        cur_tier = action["tier"]
    if action.get("max_budget_usd") is not None:
        max_budget_cents = int(round(float(action["max_budget_usd"]) * 100))
    for rid in action.get("remove_need_ids") or []:
        excluded.add(str(rid))
    for qo in action.get("qty_overrides") or []:
        qty_ov[str(qo["need_id"])] = int(qo["qty"])
    for qv in action.get("query_overrides") or []:
        query_ov[str(qv["need_id"])] = str(qv["query"])
    for idx, add in enumerate(action.get("add_items") or [], start=len(custom_adds) + 1):
        custom_adds.append({
            "need_id": f"agent_item_{idx}",
            "title": add["title"],
            "short_title": add["title"][:28],
            "query": add["query"],
            "qty_needed": int(add["qty_needed"]),
            "reason": add["reason"],
        })

    kit = build_move_kit(
        inventory,
        plan,
        client=mcp,
        destination=destination,
        tier=cur_tier,
        verify_with_decisions=False,
        max_budget_cents=max_budget_cents,
        custom_additions=custom_adds,
        excluded_ids=excluded,
        qty_overrides=qty_ov,
        query_overrides=query_ov,
        run_dir=run_dir,
    )

    merchant_answer: dict[str, Any] | None = None
    mq = action.get("merchant_question")
    if isinstance(mq, dict) and mq.get("query"):
        target_shop = str(mq.get("shop_domain") or "").strip()
        if not target_shop and kit["merchant_carts"]:
            target_shop = kit["merchant_carts"][0]["shop_domain"]
        if target_shop:
            try:
                ans_res = mcp.ask_business(target_shop, str(mq["query"]))
                ans_txt = str(ans_res.get("answer") or ans_res.get("text") or "").strip()
                msgs = [
                    str(m.get("content") or m) if isinstance(m, dict) else str(m)
                    for m in (ans_res.get("messages") or [])
                ]
                merchant_answer = {
                    "shop_domain": target_shop,
                    "question": mq["query"],
                    "answer": ans_txt or ("; ".join(msgs) if msgs else "This merchant hasn't published an automated Q&A response for that question—check their policy links on checkout."),
                }
                kit["agent_trace"].append({
                    "step": "ask_business",
                    "tool": "mcp.shop.com/ask_business",
                    "shop": target_shop,
                    "query": mq["query"],
                })
            except ShopMCPError as exc:
                merchant_answer = {
                    "shop_domain": target_shop,
                    "question": mq["query"],
                    "answer": f"Merchant Q&A wasn't available right now ({exc}); review policy links in checkout.",
                }

    reply_text = str(action.get("reply") or "").strip()
    if merchant_answer:
        reply_text = f"{reply_text}\n\nStore reply ({merchant_answer['shop_domain']}): {merchant_answer['answer']}".strip()
    reply_text += (
        f" Updated total: ${kit['totals']['subtotal_usd']:.2f} across "
        f"{kit['totals']['merchant_count']} Shopify cart(s)."
    )

    new_state = {
        "tier": cur_tier,
        "custom_additions": custom_adds,
        "excluded_ids": sorted(excluded),
        "qty_overrides": qty_ov,
        "query_overrides": query_ov,
        "max_budget_cents": max_budget_cents,
        "known_shops": [c["shop_domain"] for c in kit["merchant_carts"]],
    }

    return {
        "reply": reply_text,
        "model": used_model,
        "merchant_answer": merchant_answer,
        "state": new_state,
        "kit": kit,
    }


def _heuristic_agent_action(
    message: str,
    needs: list[dict[str, Any]],
    known_shops: list[str],
) -> dict[str, Any]:
    """Fast deterministic intent parser used when `GEMINI_API_KEY` is absent in unit/offline tests."""
    low = message.lower()
    tier = "keep"
    add_items: list[dict[str, Any]] = []
    query_ov: list[dict[str, str]] = []
    max_budget: float | None = None
    mq: dict[str, str] | None = None
    notes: list[str] = []

    m_bud = re.search(r"under\s*\$?\s*(\d{2,4})", low)
    if m_bud:
        max_budget = float(m_bud.group(1))
        notes.append(f"optimizing offers under ${max_budget:.0f}")

    if any(w in low for w in ("heavy-duty", "heavy duty", "double-wall", "double wall", "pro ")):
        tier = "pro_heavy_duty"
        notes.append("upgraded to Heavy-Duty Pro double-wall cartons & protection")
    elif any(w in low for w in ("cheapest", "essential", "boxes only", "minimal", "bare minimum")):
        tier = "essential"
        notes.append("trimmed kit to Essential boxes, tape & fragile wrap")

    if any(w in low for w in ("eco", "recycled", "plastic-free", "biodegradable", "honeycomb")):
        for n in needs:
            if n["need_id"] == "supply_bubble":
                query_ov.append({"need_id": "supply_bubble", "query": "honeycomb kraft packing paper roll eco moving"})
        notes.append("swapped plastic bubble wrap for recyclable honeycomb kraft cushioning paper")

    if any(w in low for w in ("dolly", "hand truck", "cart")):
        add_items.append({
            "title": "Heavy-Duty Convertible Hand Truck / Moving Dolly",
            "query": "heavy duty folding hand truck dolly moving",
            "qty_needed": 1,
            "reason": "Requested moving dolly for stacked boxes & heavy pieces",
        })
        notes.append("added a heavy-duty moving hand truck")

    if "packing paper" in low and not query_ov:
        add_items.append({
            "title": "Newsprint Packing Paper Sheets for Dish & Fragile Wrapping",
            "query": "newsprint packing paper sheets moving boxes",
            "qty_needed": 1,
            "reason": "Requested clean newsprint wrapping sheets",
        })
        notes.append("added newsprint packing paper sheets")

    if any(w in low for w in ("return", "refund", "shipping policy", "warranty", "ask")):
        shop_dom = known_shops[0] if known_shops else ""
        mq = {"shop_domain": shop_dom, "query": message}
        notes.append(f"asked {shop_dom or 'the primary store'} directly")

    summary = "; ".join(notes).capitalize() if notes else "Refreshed your Shopify Move Supply Kit"
    return {
        "tier": tier,
        "max_budget_usd": max_budget,
        "add_items": add_items,
        "remove_need_ids": [],
        "qty_overrides": [],
        "query_overrides": query_ov,
        "merchant_question": mq,
        "reply": f"{summary}.",
    }
