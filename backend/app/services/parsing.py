"""Deterministic, rule/lexicon-based parser for free-text wholesale orders.

This is intentionally NOT an LLM call. Per the brief: "AI extracts intent and
explains results; deterministic backend services calculate and execute." This parser
is the primary path for every order, including the Kannada/Hindi/English code-mixed
examples in the demo script. A Sarvam/Gemini LLM parser could be bolted on later as an
*optional* assist behind the same strict-schema validation, but none is wired in yet --
no result from one is ever labelled as if it came from this deterministic parser, and
none is fabricated.

Low confidence (no lexicon match near a quantity, or ambiguous unit) must make the
caller require merchant confirmation before the order is planned -- see
OrderCreate.parse_confidence / requires_confirmation in the orders router.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.catalog import Product, ProductAlias

# Unit words in Kannada, Hindi, Tamil, Telugu and Bengali scripts, mapped to English units.
NATIVE_UNITS = {
    "ಕೆಜಿ": "kg", "ಕಿಲೋ": "kg", "ಲೀಟರ್": "litre",
    "किलो": "kg", "केजी": "kg", "किग्रा": "kg", "लीटर": "litre",
    "கிலோ": "kg", "லிட்டர்": "litre",
    "కిలో": "kg", "కేజీ": "kg", "లీటర్": "litre",
    "কেজি": "kg", "কিলো": "kg", "লিটার": "litre",
}
QUANTITY_UNIT_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kg|kilo|kilos|kilogram|kilograms|g|gram|grams|litre|litres|liter|liters|l|"
    r"piece|pieces|pc|pcs|packet|packets|bag|bags|" + "|".join(sorted(NATIVE_UNITS, key=len, reverse=True)) + ")"
    # Not \b: Indic vowel signs are combining marks, so \b fails right after e.g. "ಕೆಜಿ".
    r"(?!\w)",
    re.IGNORECASE,
)

UNIT_TO_BASE = {
    "kg": ("kg", 1.0), "kilo": ("kg", 1.0), "kilos": ("kg", 1.0),
    "kilogram": ("kg", 1.0), "kilograms": ("kg", 1.0),
    "g": ("kg", 0.001), "gram": ("kg", 0.001), "grams": ("kg", 0.001),
    "litre": ("litre", 1.0), "litres": ("litre", 1.0), "liter": ("litre", 1.0), "liters": ("litre", 1.0),
    "l": ("litre", 1.0),
    "piece": ("piece", 1.0), "pieces": ("piece", 1.0), "pc": ("piece", 1.0), "pcs": ("piece", 1.0),
    "packet": ("piece", 1.0), "packets": ("piece", 1.0),
    "bag": ("kg", 25.0), "bags": ("kg", 25.0),  # common kirana default bag size; coarse assumption
}

WINDOW_WORDS_BEFORE = 4
WINDOW_WORDS_AFTER = 2


@dataclass
class ParsedItem:
    matched_text: str
    quantity_base_unit: float
    base_unit: str
    product_id: str | None
    product_name: str | None
    matched_alias: str | None
    confidence: float


@dataclass
class ParseResult:
    items: list[ParsedItem]
    overall_confidence: float
    unmatched_fragments: list[str]


def _load_alias_lexicon(db: Session) -> list[tuple[str, Product]]:
    rows = db.query(ProductAlias, Product).join(Product, ProductAlias.product_id == Product.id).all()
    lexicon = [(unicodedata.normalize("NFC", alias.alias_text).lower(), product) for alias, product in rows]
    # longest alias first so "basmati rice" matches before plain "rice"
    lexicon.sort(key=lambda t: -len(t[0]))
    return lexicon


def _find_product_near(window_text: str, lexicon: list[tuple[str, Product]]) -> tuple[Product | None, str | None, float]:
    window_lower = window_text.lower()
    for alias_text, product in lexicon:
        if alias_text in window_lower:
            confidence = 1.0 if window_lower.strip() == alias_text else 0.85
            return product, alias_text, confidence
    return None, None, 0.0


def parse_order_text(text: str, db: Session) -> ParseResult:
    lexicon = _load_alias_lexicon(db)
    text = unicodedata.normalize("NFC", text)  # Indic text may arrive decomposed
    items: list[ParsedItem] = []
    unmatched: list[str] = []

    for match in QUANTITY_UNIT_RE.finditer(text):
        qty_raw = float(match.group("qty"))  # float() accepts Indic digits such as ೧೦೦ / १००
        unit_raw = NATIVE_UNITS.get(match.group("unit"), match.group("unit").lower())
        base_unit, multiplier = UNIT_TO_BASE.get(unit_raw, (unit_raw, 1.0))
        qty_base = qty_raw * multiplier

        # Build a word window around the match to search for a product name.
        prefix = text[: match.start()].split()
        suffix = text[match.end():].split()
        window = " ".join(prefix[-WINDOW_WORDS_BEFORE:] + suffix[:WINDOW_WORDS_AFTER])

        product, alias, confidence = _find_product_near(window, lexicon)
        if qty_base <= 0:
            unmatched.append(match.group(0))  # a zero quantity is never an order line
            continue
        if product is None:
            unmatched.append(match.group(0))
        items.append(
            ParsedItem(
                matched_text=match.group(0),
                quantity_base_unit=round(qty_base, 3),
                base_unit=base_unit,
                product_id=product.id if product else None,
                product_name=product.name if product else None,
                matched_alias=alias,
                confidence=confidence,
            )
        )

    overall_confidence = (
        round(sum(i.confidence for i in items) / len(items), 3) if items else 0.0
    )
    return ParseResult(items=items, overall_confidence=overall_confidence, unmatched_fragments=unmatched)
