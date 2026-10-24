"""Data standard 1.6 (ADR 018, D38): a tender on sales counts, and supplier orders and the HR
tables in core with their redactions kept. The rights table is in test_rbac."""

from sqlmodel import Session

from mia.agents.sales_supervisor import actions as sales_actions
from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.sales_supervisor.tools import CorrectCountInput, CountIn, RecordCountsInput
from mia.core.models import Branch, Contract, Leave, Payslip, Person, SupplierOrder
from mia.core.rbac import Rbac
from mia.settings import get_settings
from tests.test_branch_manager_tools import item
from tests.test_sales_tools import deps_for as sales_deps

Ferinos = tuple[Branch, dict[str, Person]]


def test_payslip_totals_are_read_all_for_owner_and_admin_only() -> None:
    rbac = Rbac(get_settings().config_dir / "policies")
    roles = ("staff", "clerk", "supervisor", "owner", "admin", "viewer", "accountant")
    allowed = [r for r in roles if rbac.enforcer.enforce(r, "B", "data:payslips", "read_all")]
    assert allowed == ["owner", "admin"]


def test_the_promoted_hr_tables_keep_their_redactions() -> None:
    assert (Contract.__redact__, Payslip.__redact__, Leave.__redact__) == (
        frozenset({"daily_rate"}),
        frozenset({"lines", "gross", "deductions", "net"}),
        frozenset({"kind", "reason"}),
    )
    assert [m.__module__ for m in (SupplierOrder, Contract, Payslip, Leave)] == [
        "mia.core.models"
    ] * 4


def test_a_count_carries_its_tender(session: Session, bk: Ferinos) -> None:
    deps, classic = sales_deps(session, bk[1]["Ana"]), item(session, "Classic").id
    paid = RecordCountsInput(items=[CountIn(item_id=classic, quantity=2)], tender="gcash")
    assert sales_tools.record_counts(deps, paid, "c1").recorded[0].tender == "gcash"
    fixed = sales_tools.correct_count(deps, CorrectCountInput(item_id=classic, quantity=3), "c2")
    assert fixed.corrected.tender == "gcash"  # a correction keeps the corrected row's tender
    plain = RecordCountsInput(items=[CountIn(item_id=classic, quantity=1)])
    assert sales_tools.record_counts(deps, plain, "c3").recorded[0].tender == "cash"
    assert sales_actions.build_query(deps, "gcash 3 classic", "").tender == "gcash"
