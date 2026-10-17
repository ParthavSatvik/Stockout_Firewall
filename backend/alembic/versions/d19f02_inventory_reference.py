"""Track the source offer for atomic confirmations."""
from alembic import op
import sqlalchemy as sa
revision = "d19f02"
down_revision = "c782ddd7dc52"
branch_labels = depends_on = None
def upgrade():
    with op.batch_alter_table("allocations") as batch:
        batch.add_column(sa.Column("inventory_id", sa.String(), nullable=True))
        batch.create_foreign_key("fk_allocation_inventory", "supplier_inventory", ["inventory_id"], ["id"])
def downgrade():
    with op.batch_alter_table("allocations") as batch:
        batch.drop_constraint("fk_allocation_inventory", type_="foreignkey")
        batch.drop_column("inventory_id")
