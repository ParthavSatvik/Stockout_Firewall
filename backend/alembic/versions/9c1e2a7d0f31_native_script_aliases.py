"""Native-script product aliases (Kannada, Hindi, Tamil, Telugu, Bengali) so orders written
in those scripts parse. Idempotent: only inserts aliases that are missing.

Revision ID: 9c1e2a7d0f31
Revises: b5477427b4db
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "9c1e2a7d0f31"
down_revision = "b5477427b4db"
branch_labels = depends_on = None

# A frozen copy: migrations must not import application code that may change later.
ALIASES = {
    "Rice": [("ಅಕ್ಕಿ", "kn"), ("चावल", "hi"), ("அரிசி", "ta"), ("బియ్యం", "te"), ("চাল", "bn")],
    "Wheat Atta": [("ಗೋಧಿ ಹಿಟ್ಟು", "kn"), ("आटा", "hi"), ("கோதுமை மாவு", "ta"), ("గోధుమ పిండి", "te"), ("আটা", "bn")],
    "Toor Dal": [("ತೊಗರಿ ಬೇಳೆ", "kn"), ("तूर दाल", "hi"), ("अरहर दाल", "hi"), ("துவரம் பருப்பு", "ta"), ("కంది పప్పు", "te"), ("অড়হর ডাল", "bn")],
    "Moong Dal": [("ಹೆಸರು ಬೇಳೆ", "kn"), ("मूंग दाल", "hi"), ("பாசிப் பருப்பு", "ta"), ("పెసర పప్పు", "te"), ("মুগ ডাল", "bn")],
    "Sugar": [("ಸಕ್ಕರೆ", "kn"), ("चीनी", "hi"), ("சர்க்கரை", "ta"), ("చక్కెర", "te"), ("চিনি", "bn")],
    "Sunflower Oil": [("ಎಣ್ಣೆ", "kn"), ("तेल", "hi"), ("எண்ணெய்", "ta"), ("నూనె", "te"), ("তেল", "bn")],
    "Salt": [("ಉಪ್ಪು", "kn"), ("नमक", "hi"), ("உப்பு", "ta"), ("ఉప్పు", "te"), ("লবণ", "bn")],
    "Besan": [("ಕಡಲೆ ಹಿಟ್ಟು", "kn"), ("बेसन", "hi"), ("கடலை மாவு", "ta"), ("శనగ పిండి", "te"), ("বেসন", "bn")],
    "Tea Powder": [("ಚಹಾ ಪುಡಿ", "kn"), ("चाय पत्ती", "hi"), ("டீ தூள்", "ta"), ("టీ పొడి", "te"), ("চা পাতা", "bn")],
}


def upgrade():
    conn = op.get_bind()
    for name, aliases in ALIASES.items():
        pid = conn.execute(sa.text("SELECT id FROM products WHERE name = :n"), {"n": name}).scalar()
        if pid is None:
            continue
        for text, lang in aliases:
            exists = conn.execute(sa.text("SELECT 1 FROM product_aliases WHERE product_id = :p AND alias_text = :t"),
                                  {"p": pid, "t": text}).first()
            if not exists:
                conn.execute(sa.text("INSERT INTO product_aliases (id, product_id, alias_text, language) VALUES (:i, :p, :t, :l)"),
                             {"i": str(uuid.uuid4()), "p": pid, "t": text, "l": lang})


def downgrade():
    conn = op.get_bind()
    for aliases in ALIASES.values():
        for text, _ in aliases:
            conn.execute(sa.text("DELETE FROM product_aliases WHERE alias_text = :t"), {"t": text})
