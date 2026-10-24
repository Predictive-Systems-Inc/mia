"""Data standard 1.8 (D39, ADR 020): customer orders move to core as customer_orders with the
same fields and redaction; the customers stay with the customer service."""

from mia.agents.customer_service import MANIFEST
from mia.agents.customer_service.models import Complaint, Customer
from mia.core.models import STANDARD_VERSION, CustomerOrder


def test_customer_orders_keep_their_fields_and_redaction() -> None:
    assert (
        CustomerOrder.__tablename__,
        CustomerOrder.__module__,
        CustomerOrder.__redact__,
        MANIFEST.standard_version,
    ) == ("customer_orders", "mia.core.models", frozenset({"delivery_note"}), STANDARD_VERSION)
    assert set(CustomerOrder.model_fields) == {
        "id",
        "created_at",
        "updated_at",
        "branch_id",
        "customer_id",
        "lines",
        "total",
        "currency",
        "fulfilment",
        "pickup_at",
        "delivery_area",
        "delivery_note",
        "status",
        "approval_id",
        "decided_by",
        "source_message_id",
    }
    columns = (CustomerOrder.__table__.c.customer_id, Complaint.__table__.c.order_id)
    fks = {fk.target_fullname for c in columns for fk in c.foreign_keys}
    assert fks == {"customer_service_customers.id", "customer_orders.id"}
    assert Customer.__module__ == "mia.agents.customer_service.models"
