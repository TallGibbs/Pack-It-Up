"""Tests for Track B Shopify / shop.dev Commerce Bonus Track (`backend/commerce.py` & `backend/commerce_api.py`)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend import commerce, solver
from backend.app import app

ROOT = Path(__file__).resolve().parents[1]


class FakeShopMCPClient(commerce.ShopMCPClient):
    """Deterministic fake `mcp.shop.com` client for offline unit tests (including self-healing cart swap)."""

    def __init__(self, fail_cart_for_shop: str | None = None):
        super().__init__(use_cache=False)
        self.fail_cart_for_shop = fail_cart_for_shop
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def search_catalog(self, query: str | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search_catalog", {"query": query, **kwargs}))
        q = (query or "").lower()
        shops_filter = kwargs.get("shops")
        if shops_filter and "gpack-usa.myshopify.com" not in shops_filter:
            return {"products": [], "_latency_ms": 5, "_cached": False}

        # Include a noisy tiny 6x4x4 jewelry mailer first to prove the spec guardrail rejects it!
        noisy_mailer = {
            "id": "gid://shopify/p/noisy_mailer",
            "title": "100-Pack Corrugated Cardboard Shipping Boxes 8x6x4\" 6x4x4\" Small Mailer",
            "media": [{"url": "https://cdn.shopify.com/s/files/mailer.jpg"}],
            "variants": [{
                "id": "gid://shopify/ProductVariant/999001",
                "title": "100-Pack 6x4x4\"",
                "price": {"amount": 1999, "currency": "USD"},
                "availability": {"available": True},
                "url": "https://example.com/mailer",
                "seller": {"name": "TinyMailers", "domain": "tinymailers.myshopify.com"},
            }],
        }

        if "16x12x12" in q or "small" in q:
            return {
                "products": [
                    noisy_mailer,
                    {
                        "id": "gid://shopify/p/small_box",
                        "title": "10-Pack Small Moving Boxes 16x12x12\" (1.5 cu ft)",
                        "media": [{"url": "https://cdn.shopify.com/s/files/small10.jpg"}],
                        "variants": [{
                            "id": "gid://shopify/ProductVariant/1001",
                            "title": "10-Pack",
                            "price": {"amount": 1850, "currency": "USD"},
                            "availability": {"available": True},
                            "url": "https://gpack-usa.myshopify.com/products/small-10",
                            "checkout_url": "https://gpack-usa.myshopify.com/buy/1001:1",
                            "seller": {"name": "Gpack Supplies", "domain": "gpack-usa.myshopify.com"},
                        }],
                    },
                ],
                "_latency_ms": 12,
                "_cached": False,
            }

        if "18x18x16" in q or "medium" in q:
            return {
                "products": [
                    noisy_mailer,
                    {
                        "id": "gid://shopify/p/med_bad_shop",
                        "title": "18 x 18 x 16 Medium Moving Box (3.0 cu ft)",
                        "media": [{"url": "https://cdn.shopify.com/s/files/med_a.jpg"}],
                        "variants": [{
                            "id": "gid://shopify/ProductVariant/2001",
                            "title": "Single Box",
                            "price": {"amount": 210, "currency": "USD"},
                            "availability": {"available": True},
                            "url": "https://flaky-boxes.myshopify.com/products/med",
                            "seller": {"name": "Flaky Boxes", "domain": "flaky-boxes.myshopify.com"},
                        }],
                    },
                    {
                        "id": "gid://shopify/p/med_good_shop",
                        "title": "Moving Boxes 18 x 18 x 16 (Medium)",
                        "media": [{"url": "https://cdn.shopify.com/s/files/med_b.jpg"}],
                        "variants": [{
                            "id": "gid://shopify/ProductVariant/2002",
                            "title": "Single Box",
                            "price": {"amount": 225, "currency": "USD"},
                            "availability": {"available": True},
                            "url": "https://gpack-usa.myshopify.com/products/med",
                            "seller": {"name": "Gpack Supplies", "domain": "gpack-usa.myshopify.com"},
                        }],
                    },
                ],
                "_latency_ms": 14,
                "_cached": False,
            }

        if "blanket" in q:
            return {
                "products": [{
                    "id": "gid://shopify/p/blankets_12",
                    "title": "Moving Blankets 12 pcs (72x80) Quilted",
                    "media": [{"url": "https://cdn.shopify.com/s/files/blankets.jpg"}],
                    "variants": [{
                        "id": "gid://shopify/ProductVariant/3001",
                        "title": "12 pcs",
                        "price": {"amount": 5800, "currency": "USD"},
                        "availability": {"available": True},
                        "url": "https://gpack-usa.myshopify.com/products/blankets",
                        "seller": {"name": "Gpack Supplies", "domain": "gpack-usa.myshopify.com"},
                    }],
                }],
                "_latency_ms": 10,
                "_cached": False,
            }

        return {
            "products": [{
                "id": "gid://shopify/p/generic_supply",
                "title": f"Pro Moving Supply ({query})",
                "media": [{"url": "https://cdn.shopify.com/s/files/supply.jpg"}],
                "variants": [{
                    "id": f"gid://shopify/ProductVariant/{abs(hash(q)) % 90000 + 10000}",
                    "title": "Standard Pack",
                    "price": {"amount": 1299, "currency": "USD"},
                    "availability": {"available": True},
                    "url": "https://gpack-usa.myshopify.com/products/supply",
                    "seller": {"name": "Gpack Supplies", "domain": "gpack-usa.myshopify.com"},
                }],
            }],
            "_latency_ms": 9,
            "_cached": False,
        }

    def create_cart(self, shop_domain: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(("create_cart", {"shop": shop_domain, "line_items": line_items}))
        if self.fail_cart_for_shop and shop_domain == self.fail_cart_for_shop:
            raise commerce.ShopMCPError(f"Simulated out-of-stock on {shop_domain}")
        return {
            "id": f"gid://shopify/Cart/test_{shop_domain}",
            "line_items": line_items,
            "continue_url": f"https://{shop_domain}/cart/c/test_token_123",
            "messages": [],
        }

    def create_checkout(self, shop_domain: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(("create_checkout", {"shop": shop_domain}))
        return {
            "id": f"gid://shopify/Checkout/test_{shop_domain}",
            "continue_url": f"https://shop.app/checkouts/r/test_{shop_domain}",
            "ucp": {"payment_handlers": {"dev.shopify.shop_pay": [{"id": "shop_pay"}]}},
            "messages": [],
        }

    def ask_business(self, shop_domain: str, query: str, ids: list[str] | None = None) -> dict[str, Any]:
        self.calls.append(("ask_business", {"shop": shop_domain, "query": query}))
        return {"answer": "Unused flat moving boxes can be returned within 30 days."}


def test_pack_size_and_dimension_parsers() -> None:
    # Dimensions like 18x18x16 or 72x80 must NOT be misparsed as pack counts!
    assert commerce.parse_pack_size("Moving Boxes 18 x 18 x 16 (medium)") == 1
    assert commerce.parse_pack_size("18x18x16 (200 lb strength) | SINGLE BOX | MEDIUM MOVING BOX") == 1
    assert commerce.parse_pack_size("Moving Blankets 12 pcs (72x80)") == 12
    assert commerce.parse_pack_size("Scotch Heavy Duty Shipping Packaging Tape with Dispenser, 4 Rolls") == 4
    assert commerce.parse_pack_size("10-Pack Small Moving Boxes 16x12x12\"") == 10
    assert commerce.parse_pack_size("Bundle of 25 Medium Cartons") == 25

    assert commerce.parse_box_dims_in("18 X 18 X 16 Medium Moving Box") == (18.0, 18.0, 16.0)
    assert commerce.parse_box_dims_in("8x6x4\" Small Mailer") == (8.0, 6.0, 4.0)


def test_compute_supply_needs_and_reject_tiny_mailers() -> None:
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    plan = solver.solve(sample)
    bom = commerce.compute_supply_needs(sample, plan, tier="standard")

    assert bom["summary"]["raw_boxes"] == 42
    assert bom["summary"]["buffered_boxes"] >= 42
    need_ids = {n["need_id"] for n in bom["needs"]}
    assert "supply_tape" in need_ids
    assert "supply_blankets" in need_ids
    assert "supply_bubble" in need_ids
    assert "supply_straps" in need_ids

    fake_mcp = FakeShopMCPClient()
    kit = commerce.build_move_kit(sample, plan, client=fake_mcp, verify_with_decisions=False)
    assert kit["source_mode"] == "shop_mcp_live"
    assert kit["totals"]["subtotal_cents"] > 0
    assert len(kit["merchant_carts"]) >= 1

    # Verify the 8x6x4" tiny jewelry mailer was rejected on every box line!
    for item in kit["items"]:
        assert "TinyMailers" != item["offer"]["seller_name"]
        assert "999001" not in item["offer"]["variant_id"]

    # Verify Shop Pay + pre-filled Shopify Cart URLs are populated
    cart0 = kit["merchant_carts"][0]
    assert cart0["cart_url"].startswith("https://")
    assert cart0["shop_pay_url"].startswith("https://shop.app/checkouts/")


def test_self_healing_cart_recovery_swaps_failed_merchant() -> None:
    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))
    fake_mcp = FakeShopMCPClient(fail_cart_for_shop="flaky-boxes.myshopify.com")

    # Force flaky-boxes onto medium box by disabling anchor boost via single-item inventory
    mini_inv = {
        "rooms": [{
            "room": {"id": "r1", "name": "Hall"},
            "items": [],
            "containers": [{"id": "c1", "label": "shelf", "contents": "decor", "fullness": "half", "est_boxes": {"box_medium": 4}}],
        }]
    }
    kit = commerce.build_move_kit(mini_inv, client=fake_mcp, tier="essential", verify_with_decisions=False)
    domains = {c["shop_domain"] for c in kit["merchant_carts"]}
    # Either consolidated onto gpack-usa upfront OR self-healed away from flaky-boxes!
    assert "flaky-boxes.myshopify.com" not in domains
    assert "gpack-usa.myshopify.com" in domains


def test_consolidate_stores_trades_item_cost_for_fewer_shipments() -> None:
    def offer(shop: str, cents: int) -> dict[str, Any]:
        return {"seller_domain": shop, "line_total_cents": cents, "title": f"{shop} {cents}"}

    # Cheapest per line would use 3 stores (A boxes, B wrap, C tape).
    cands = {
        "boxes": [offer("a", 2025), offer("b", 2400)],
        "wrap": [offer("b", 999), offer("a", 1150)],
        "tape": [offer("c", 580), offer("a", 700), offer("b", 650)],
    }
    trace: list[dict[str, Any]] = []
    commerce.consolidate_stores(cands, trace, ship_cents=1500)
    # Moving tape (+$1.20 at A) then wrap (+$1.51 at A) beats paying two more shipping fees.
    assert {c[0]["seller_domain"] for c in cands.values()} == {"a"}
    assert [t["dropped_shop"] for t in trace] == ["c", "b"]
    # Every original offer is still in the list, just reordered.
    assert len(cands["tape"]) == 3

    # A store is kept when moving its lines costs more than the shipping it saves.
    cands2 = {
        "boxes": [offer("a", 2025)],
        "blankets": [offer("b", 3000), offer("a", 6000)],
    }
    commerce.consolidate_stores(cands2, ship_cents=1500)
    assert cands2["blankets"][0]["seller_domain"] == "b"


def test_shopping_agent_and_fastapi_routes(monkeypatch) -> None:
    # Ensure deterministic heuristic path runs fast without burning live API calls in unit tests
    commerce._load_env()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_mcp = FakeShopMCPClient()
    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))

    turn = commerce.run_shopping_agent(
        "Upgrade to heavy-duty double-wall boxes, add a hand truck dolly, and ask about their return policy",
        mock_inv,
        client=fake_mcp,
    )
    assert turn["kit"]["tier"] == "pro_heavy_duty"
    assert any("dolly" in it["need_title"].lower() for it in turn["kit"]["items"])
    assert turn["merchant_answer"] is not None
    assert "30 days" in turn["merchant_answer"]["answer"]

    # Also test FastAPI /commerce/kit endpoint with monkeypatched ShopMCPClient
    monkeypatch.setattr(commerce, "ShopMCPClient", lambda *a, **kw: FakeShopMCPClient())
    http = TestClient(app)
    resp = http.post("/commerce/kit", json={"run_id": "mock-demo", "tier": "standard", "include_comps": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "mock-demo"
    assert body["kit"]["totals"]["line_count"] >= 3


def test_malin_orior_venue_policy_and_cinema_production_rig() -> None:
    from backend import catalog

    catalog.load.cache_clear()
    catalog.load_penn_zones.cache_clear()

    # Verify new Orior & ARRI/Adorama production catalog entries
    assert catalog.lookup("pelican_1650") is not None
    assert catalog.lookup("pelican_1510")["stackable"] == "no"
    assert catalog.lookup("orior_travertine_table")["fragile"] is True

    http = TestClient(app)
    # 1. Full venue solve vs Malin x Orior rule (`orior_curated_stays=True`)
    full_resp = http.post("/solve", json={"run_id": "sample_venue"})
    assert full_resp.status_code == 200
    full_items = full_resp.json()["summary"]["total_items"]

    # 1. Full venue solve with Orior White-Glove Care (`orior_white_glove=True`) keeps EVERY piece in the move
    #    while upgrading bespoke stone/upholstery to `stackable="no"` + +2" pad clearance + cinema rig
    wg_resp = http.post(
        "/solve",
        json={
            "run_id": "sample_venue",
            "strategy": {"orior_white_glove": True},
            "extra_items": [
                {"id": "judge_p1650", "catalog_id": "pelican_1650", "quantity": 2},
                {"id": "judge_p1510", "catalog_id": "pelican_1510", "quantity": 2},
                {"id": "judge_cstand", "catalog_id": "c_stand_cart", "quantity": 1},
            ],
        },
    )
    assert wg_resp.status_code == 200
    wg_plan = wg_resp.json()
    assert wg_plan["venue_policy"]["policy"] == "orior_white_glove"
    assert wg_plan["venue_policy"]["white_glove_units"] > 10
    assert wg_plan["summary"]["total_items"] == full_items + 5
    assert wg_plan["score"]["valid"] is True

    # Verify bespoke sofas in white-glove mode have stackable == 'no' (nothing stacked on Orior upholstery!)
    sofas = [
        it for t in wg_plan["trucks"] for it in t["items"]
        if it.get("catalog_id") == "sofa_3seat"
    ]
    assert sofas and all(s["stackable"] == "no" for s in sofas)

    # 2. Verify commerce BOM includes BOTH Orior stone/mohair covers AND ARRI/Adorama E-Track kit
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    bom = commerce.compute_supply_needs(sample, wg_plan, tier="standard")
    need_ids = {n["need_id"] for n in bom["needs"]}
    assert "supply_orior_covers" in need_ids
    assert "supply_cinema_etrack" in need_ids
