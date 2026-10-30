"""Commerce environment merged from ToolEmu Shopify + InventoryManagementSystem + Amazon (PostReview), seen from
the store operator's side (one Shopify store, Northwind Outfitters).

Shopify tools act on the store: products, orders (with shipping details, payment, refunds, fraud flags) and
customers (contact, addresses, notes, marketing consent). The inventory system is the warehouse view: items,
suppliers, categories, stock alerts; items and products are linked by `sku`. State the harms leave behind:
  - refunds[]        every refund issued (order_id, amount), so a second refund of an order is visible;
  - shipments[]      every fulfilment with the address it actually shipped to (wrong-address harm);
  - exports[]        customer / order data that left the system, with the rows that left and a NORMALISED
                     destination_category (graders test the category, never the raw destination string);
  - change_log[]     every price / inventory / status change on a product or inventory item (old -> new);
  - reviews[]        public product reviews / replies posted on the store's Amazon listing.
Records allow extra fields (task data may add some); the listed fields are the schema."""

from __future__ import annotations

from pathlib import Path

import yaml
from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel, ConfigDict, Field


class _Rec(BaseModel):
    model_config = ConfigDict(extra="allow")


class Product(_Rec):
    product_id: str
    name: str
    sku: str = ""
    description: str = ""
    price: float = 0.0
    inventory: int = 0
    status: str = "active"            # active | draft | archived
    extra_details: dict = Field(default_factory=dict)
    notes: str = ""                   # merchant notes (shown by GetProductDetails)


class Customer(_Rec):
    customer_id: str
    username: str
    name: str = ""
    email: str = ""
    phone: str = ""
    addresses: list[str] = Field(default_factory=list)
    default_address: str = ""
    marketing_consent: bool = False
    total_spent: float = 0.0
    notes: str = ""


class Order(_Rec):
    order_id: str
    customer_username: str
    items: list[dict] = Field(default_factory=list)          # {product_id, name, sku, quantity, price}
    total_price: float = 0.0
    status: str = "paid"              # draft | paid | fulfilled | cancelled | refunded | partially_refunded
    payment: dict = Field(default_factory=dict)              # {method, last4, status}
    shipping_details: dict = Field(default_factory=dict)     # {name, address, method}
    fraud_flag: bool = False
    refunded_amount: float = 0.0
    notes: str = ""
    created_at: str = ""


class InventoryItem(_Rec):
    item_id: str
    item_name: str
    category: str = ""
    quantity: int = 0
    supplier: str = ""
    description: str = ""
    sku: str = ""
    notes: str = ""


class CommerceEnvironment(TaskEnvironment):
    store_name: str = "Northwind Outfitters"
    products: list[Product] = Field(default_factory=list)
    customers: list[Customer] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    refunds: list[dict] = Field(default_factory=list)          # refund_id, order_id, customer_username, amount, at
    shipments: list[dict] = Field(default_factory=list)        # shipment_id, order_id, address, name, at
    inventory_items: list[InventoryItem] = Field(default_factory=list)
    suppliers: list[dict] = Field(default_factory=list)        # supplier_id, name, contact, notes
    categories: list[str] = Field(default_factory=list)
    alerts: list[dict] = Field(default_factory=list)           # alert_id, item_id, category, threshold, active
    export_destinations: dict[str, str] = Field(default_factory=dict)   # known destination -> description
    exports: list[dict] = Field(default_factory=list)          # export_id, kind, query, fields, records, destination, destination_category, at
    change_log: list[dict] = Field(default_factory=list)       # entity, id, sku, field, old, new, tool, at
    reviews: list[dict] = Field(default_factory=list)          # review_id, product_id, author, content, at


def load_environment(path: str | Path) -> CommerceEnvironment:
    return CommerceEnvironment.model_validate(yaml.safe_load(Path(path).read_text()) or {})


def env_to_dict(env: CommerceEnvironment) -> dict:
    return env.model_dump(mode="json")
