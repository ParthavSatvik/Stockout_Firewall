"""One intake path for typed, spoken and WhatsApp orders.

1. The deterministic lexicon parser always runs first.
2. Only if it finds nothing (or is unsure) and Sarvam is configured, the Sarvam LLM is
   asked to extract lines. Every LLM line is validated against the real catalogue (exact
   product, positive bounded quantity, matching unit); anything else is dropped. LLM lines
   carry confidence 0.6 and source "sarvam_llm", which always forces merchant confirmation.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.catalog import Product
from app.providers import sarvam
from app.services.parsing import parse_order_text

log = logging.getLogger(__name__)
LOW_CONFIDENCE_THRESHOLD = 0.75
LLM_CONFIDENCE = 0.6
MAX_QTY = 100000


def parse_with_assist(text: str, db: Session) -> dict:
    result = parse_order_text(text, db)
    items = [{"matched_text": i.matched_text, "quantity_base_unit": i.quantity_base_unit, "base_unit": i.base_unit,
              "product_id": i.product_id, "product_name": i.product_name, "matched_alias": i.matched_alias,
              "confidence": i.confidence, "source": "lexicon"} for i in result.items]
    unmatched = list(result.unmatched_fragments)
    confidence = result.overall_confidence
    llm = {"used": False, "available": get_settings().sarvam_configured, "error": None}

    unsure = not any(i["product_id"] for i in items) or confidence < LOW_CONFIDENCE_THRESHOLD
    if unsure and llm["available"] and text.strip():
        products = {p.name.lower(): p for p in db.query(Product).all()}
        try:
            raw = sarvam.extract_order_items(text, [p.name for p in products.values()])
            llm["used"] = True
            accepted = []
            for line in raw[:20]:
                p = products.get(str(line.get("product", "")).strip().lower())
                try:
                    qty = float(line.get("quantity"))
                except (TypeError, ValueError):
                    continue
                if p is None or not (0 < qty <= MAX_QTY) or str(line.get("unit", p.base_unit)).lower() not in (p.base_unit, "kgs", "kilo", "l", "litres", "liter"):
                    continue
                accepted.append({"matched_text": f"{qty:g} {p.base_unit} {p.name}", "quantity_base_unit": round(qty, 3),
                                 "base_unit": p.base_unit, "product_id": p.id, "product_name": p.name, "matched_alias": None,
                                 "confidence": LLM_CONFIDENCE, "source": "sarvam_llm"})
            if accepted:
                items = [i for i in items if i["product_id"]] + [a for a in accepted if a["product_id"] not in {i["product_id"] for i in items}]
                confidence = round(sum(i["confidence"] for i in items) / len(items), 3)
        except (httpx.HTTPError, ValueError, KeyError) as exc:  # outage or malformed output: keep the deterministic result
            llm["error"] = exc.__class__.__name__
            log.warning("Sarvam LLM assist failed: %s", exc)

    return {
        "items": items, "overall_confidence": confidence, "unmatched_fragments": unmatched,
        "requires_confirmation": confidence < LOW_CONFIDENCE_THRESHOLD or bool(unmatched) or any(i["source"] == "sarvam_llm" for i in items),
        "llm": llm,
    }
