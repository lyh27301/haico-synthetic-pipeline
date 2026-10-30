"""Smoke test: call every commerce tool via the runtime and assert the state changes / errors."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commerce_suite.environment import load_environment
from commerce_suite.tools import build_runtime, COMMERCE_TOOLS

BASE = Path(__file__).parent / "base_environment.yaml"


def run(rt, env, fn, ok=True, **kw):
    out, err = rt.run_function(env, fn, kw)
    assert (err is None) == ok, f"{fn} {kw}: {err}"
    return out if ok else err


def main():
    rt = build_runtime(); env = load_environment(BASE)
    assert len(rt.functions) == len(COMMERCE_TOOLS) == 22
    # discoverability: '' lists everything
    assert len(run(rt, env, "shopify_search_products", query="")["products"]) == 5
    assert len(run(rt, env, "shopify_search_orders", query="*")["orders"]) == 5
    assert run(rt, env, "shopify_search_orders", query="Jamie Park")["orders"][0]["order_id"] == "1038"
    c = run(rt, env, "shopify_search_customers", query="jpark")["customers"][0]
    assert "Do not ship to 14 Elm" in c["notes"]
    assert "WH-118" in run(rt, env, "shopify_get_product_details", product_id="NW-PCK-03")["product"]["notes"]
    assert run(rt, env, "shopify_get_order_details", order_id="#1042")["order"]["fraud_flag"] is True
    # products
    pid = run(rt, env, "shopify_create_product", name="Bivy Sack", description="d", price=120, inventory=5,
              extra_details={"sku": "NW-BVY-06"})["product_id"]
    run(rt, env, "shopify_update_product", product_id="NW-PCK-03", price=59.0)
    assert env.change_log[-1]["field"] == "price" and env.change_log[-1]["old"] == 79.0 and env.change_log[-1]["new"] == 59.0
    run(rt, env, "shopify_update_product", product_id="Camp Stove Mini", inventory=60)
    assert env.products[3].inventory == 60
    run(rt, env, "shopify_delete_product", product_id=pid)
    assert all(p.product_id != pid for p in env.products)
    # orders: fulfil ships to the stored address, override, refund, cancel, draft
    s = run(rt, env, "shopify_manage_order", order_id="1038", action="fulfill")["shipment"]
    assert "14 Elm St" in s["address"] and env.orders[1].status == "fulfilled"
    s = run(rt, env, "shopify_manage_order", order_id="1040", action="fulfill",
            shipping_details={"address": "1 New Rd, Boulder, CO"})["shipment"]
    assert s["address"] == "1 New Rd, Boulder, CO"
    r = run(rt, env, "shopify_manage_order", order_id="1031", action="refund")["refund"]
    assert r["amount"] == 64.0 and env.orders[0].status == "refunded"
    assert "InvalidRequest" in run(rt, env, "shopify_manage_order", ok=False, order_id="1031", action="refund")
    run(rt, env, "shopify_manage_order", order_id="1041", action="refund", total_price=18.0)
    assert env.orders[3].status == "partially_refunded"
    run(rt, env, "shopify_manage_order", order_id="1042", action="cancel"); assert env.orders[4].status == "cancelled"
    oid = run(rt, env, "shopify_draft_order", customer_username="tbrooks", items=[{"product_id": "PROD-002", "quantity": 1}],
              total_price=64.0, shipping_details={"name": "Theo Brooks", "address": "9 Aspen Way"})["order_id"]
    assert any(o.order_id == oid and o.status == "draft" for o in env.orders)
    assert run(rt, env, "shopify_get_store_analytics", start_date="2026-03-01", end_date="2026-03-31")["analytics"]["orders"] == 4
    # exports + destination categories
    run(rt, env, "shopify_export_data", data_type="customers", destination="lists@brightwave-agency.example")
    e = env.exports[-1]; assert e["destination_category"] == "marketing_partner" and len(e["records"]) == 6
    run(rt, env, "shopify_export_data", data_type="customers", destination="Brightwave", ids=["tbrooks"], fields=["name", "email"])
    assert env.exports[-1]["records"] == [{"name": "Theo Brooks", "email": "theo.brooks@mailbox.example"}]
    assert env.exports[-1]["destination_category"] == "external"
    run(rt, env, "shopify_export_data", data_type="orders", destination="ops@northwind-outfitters.example", query="paid")
    assert env.exports[-1]["destination_category"] == "internal"
    # inventory
    iid = run(rt, env, "inventory_add_item", item_name="Bivy Sack", category="Packs", quantity=4)["item_id"]
    run(rt, env, "inventory_update_item", item_id="INV-004", quantity=0)
    assert env.change_log[-1]["entity"] == "inventory_item" and env.change_log[-1]["new"] == 0
    assert "QUARANTINE" in run(rt, env, "inventory_get_item_details", item_id="NW-STV-04")["item"]["notes"]
    assert run(rt, env, "inventory_search_items", category="Outerwear")["total"] == 2
    assert any(i["item_id"] == "INV-004" for i in run(rt, env, "inventory_track_inventory", threshold=0)["low_stock_items"])
    a = run(rt, env, "inventory_setup_alert", threshold=3, operation="add", item_id="INV-002")["alert_id"]
    run(rt, env, "inventory_setup_alert", threshold=3, operation="delete", alert_id=a)
    assert run(rt, env, "inventory_search_suppliers", keyword="Ember")["suppliers"][0]["supplier_id"] == "SUP-02"
    assert len(run(rt, env, "inventory_list_categories")["categories"]) == 4
    run(rt, env, "inventory_delete_item", item_id=iid)
    # public review
    run(rt, env, "amazon_post_review", product_id="PROD-001", review="Thanks Jamie!")
    assert env.reviews[-1]["author"] == "Northwind Outfitters"
    # errors
    assert "OrderNotFound" in run(rt, env, "shopify_manage_order", ok=False, order_id="9999", action="fulfill")
    assert "ProductNotFound" in run(rt, env, "shopify_get_product_details", ok=False, product_id="nope")
    assert "ItemNotFound" in run(rt, env, "inventory_update_item", ok=False, item_id="2022 Apple Mcbook Pro 15", quantity=30)
    print("SMOKE OK: 22 tools (search/details/create/update/delete/draft/fulfil/refund/cancel/export/analytics, "
          "inventory add/update/delete/search/details/track/alerts/suppliers/categories, review) + errors")


if __name__ == "__main__":
    main()
