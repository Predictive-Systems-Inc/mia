import json
from typing import Any
from sqlmodel import select
from mia.core import jev
from mia.core.models import Event, EgressLog
from tests.jev_fake import answers_for, fake_jev
from tests.test_customer_service_chat import *  # noqa: F401,F403
from tests.test_customer_service_chat import _turn


def test_probe(staff, session, monkeypatch):
    seen: list[dict[str, Any]] = []
    def go(action):
        monkeypatch.setattr(jev, "_inner", lambda: fake_jev(lambda b: answers_for(b, action), seen))
    liza = staff.people["Liza"]
    go("staff_mark_ready")
    _turn(session, liza, "ready na yung kay Mila")
    go("staff_mark_picked_up")
    _turn(session, liza, "picked up na si Mila")
    print("Mila to Jev:", "Mila" in json.dumps(seen))
    for e in session.exec(select(Event)):
        s = json.dumps(e.model_dump(mode="json"))
        if "Mila" in s:
            print("CHAIN:", e.action, s[:300])
