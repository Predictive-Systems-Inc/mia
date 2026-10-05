from mia.learning.schema import IntentSpec, RoleSpec
from mia.skills.routing import Route, route
from mia.skills.runtime import Alternative, Classification

ROLE = RoleSpec(
    id="dispatcher",
    job_summary="j",
    responsibilities=["x"],
    counterparts=[],
    languages=["en"],
    countries=["FI"],
    styles={"informal": 1.0},
    intents=[
        IntentSpec(
            id="dispatcher.report_absence",
            description="d",
            counterparts=["c"],
            risk="write",
            label_en="Report I'm sick",
        ),
        IntentSpec(
            id="dispatcher.thanks_reply",
            description="d",
            counterparts=["c"],
            risk="read",
            label_en="Thanks",
            handler="template",
        ),
    ],
)


def c(intent: str, band: str, safety: float = 0.0, alts: list[str] | None = None) -> Classification:
    return Classification(
        intent=intent,
        confidence=0.9,
        band=band,
        lang="en",
        slots={},
        safety=safety,
        version="v1",
        alternatives=[Alternative(intent=a, confidence=0.4) for a in (alts or [])],
    )  # type: ignore[arg-type]


def test_safety_wins_over_everything() -> None:
    r = route(c("dispatcher.report_absence", "high", safety=0.3), ROLE)
    assert r == Route(kind="emergency", intent="dispatcher.report_absence")
    assert route(c("other", "low", safety=0.9), None).kind == "emergency"


def test_safety_floor_boundary() -> None:
    assert route(c("dispatcher.thanks_reply", "high", safety=0.2), ROLE).kind == "emergency"
    just_below = route(c("dispatcher.thanks_reply", "high", safety=0.2 - 1e-6), ROLE)
    assert just_below.kind == "template"
    assert route(c("x", "high", safety=0.5), ROLE, safety_floor=0.5).kind == "emergency"
    assert route(c("dispatcher.thanks_reply", "high", safety=0.5 - 1e-6), ROLE, 0.5).kind == (
        "template"
    )


def test_high_band_template_and_agent() -> None:
    r = route(c("dispatcher.thanks_reply", "high"), ROLE)
    assert r == Route(kind="template", intent="dispatcher.thanks_reply")
    assert route(c("conversation.greeting", "high"), ROLE) == Route(
        kind="template", intent="conversation.greeting"
    )
    r = route(c("dispatcher.report_absence", "high"), ROLE)
    assert r == Route(kind="agent", intent="dispatcher.report_absence")


def test_high_band_unknown_or_non_template_conversation_intent_runs_agent() -> None:
    assert route(c("dispatcher.unknown", "high"), ROLE) == Route(
        kind="agent", intent="dispatcher.unknown"
    )
    assert route(c("conversation.venting", "high"), ROLE).kind == "agent"


def test_other_never_templated() -> None:
    for band in ("high", "medium", "low"):
        assert route(c("other", band, alts=["conversation.venting"]), ROLE) == Route(kind="agent")


def test_medium_clarifies_with_alternatives() -> None:
    r = route(
        c(
            "dispatcher.report_absence",
            "medium",
            alts=["dispatcher.report_absence", "conversation.venting"],
        ),
        ROLE,
    )
    assert r == Route(kind="clarify", options=["dispatcher.report_absence", "conversation.venting"])


def test_medium_excludes_other_and_caps_at_three() -> None:
    alts = ["a", "other", "b", "c", "d", "e"]
    assert route(c("a", "medium", alts=alts), ROLE).options == ["a", "b", "c"]


def test_medium_with_no_usable_alternatives_runs_agent() -> None:
    assert route(c("a", "medium", alts=["other"]), ROLE) == Route(kind="agent")
    assert route(c("a", "medium"), ROLE) == Route(kind="agent")


def test_low_runs_agent_without_intent() -> None:
    assert route(c("dispatcher.report_absence", "low"), ROLE) == Route(kind="agent")


def test_no_role_plan_means_agent() -> None:
    assert route(c("dispatcher.report_absence", "high"), None) == Route(kind="agent")
    assert route(c("conversation.greeting", "medium", alts=["a"]), None) == Route(kind="agent")
