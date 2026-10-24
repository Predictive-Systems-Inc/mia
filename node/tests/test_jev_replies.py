from mia.agents.shift_supervisor import replies
from mia.chat.blocks import TextBlock
from mia.i18n.strings import STRINGS


def test_tool_reply_uses_the_rules_wording() -> None:
    out = {"status": "ok", "visit": {"location": "Kamppi"}, "time": "09:02"}
    blocks = replies.tool_reply("check_in", out, "en")
    assert isinstance(blocks[0], TextBlock)
    assert "Kamppi" in blocks[0].text and "09:02" in blocks[0].text


def test_absence_reply_asks_the_scope_with_quick_replies() -> None:
    visit = {
        "date": "2026-10-18",
        "start": "06:30",
        "end": "09:00",
        "location": "Kalasatama",
        "job": "Office",
    }
    out = {
        "absence_id": "a",
        "person": "Juha",
        "date": "2026-10-18",
        "partial_day": None,
        "updated": False,
        "affected_visits": [visit],
    }
    types = [b.type for b in replies.tool_reply("record_absence", out, "fi")]
    assert "quick_replies" in types and "card" in types


def test_every_conversation_kind_has_a_string_in_both_languages() -> None:
    for kind, key in replies.CONVERSATION_KEYS.items():
        assert key in STRINGS["en"] and key in STRINGS["fi"], kind


def test_unknown_kind_falls_back_to_help() -> None:
    assert replies.conversation_reply("nonsense", "en") == replies.conversation_reply("other", "en")
