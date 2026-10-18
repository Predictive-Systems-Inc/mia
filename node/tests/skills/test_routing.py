from mia.learning.schema import IntentSpec, RoleSpec
from mia.skills.routing import Route, route
from mia.skills.runtime import Alternative, Classification

ROLE = RoleSpec(
    id="shift_supervisor",
    job_summary="j",
    responsibilities=["x"],
    counterparts=[],
    languages=["en"],
    countries=["FI"],
    styles={"informal": 1.0},
    intents=[
        IntentSpec(
            id="shift_supervisor.report_absence",
            description="d",
            counterparts=["c"],
            risk="write",
            label_en="Report I'm sick",
        ),
        IntentSpec(
            id="shift_supervisor.thanks_reply",
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
    r = route(c("shift_supervisor.report_absence", "high", safety=0.3), ROLE)
    assert r == Route(kind="emergency", intent="shift_supervisor.report_absence")
    assert route(c("other", "low", safety=0.9), None).kind == "emergency"


def test_safety_floor_boundary() -> None:
    assert route(c("shift_supervisor.thanks_reply", "high", safety=0.2), ROLE).kind == "emergency"
    just_below = route(c("shift_supervisor.thanks_reply", "high", safety=0.2 - 1e-6), ROLE)
    assert just_below.kind == "template"
    assert route(c("x", "high", safety=0.5), ROLE, safety_floor=0.5).kind == "emergency"
    assert route(c("shift_supervisor.thanks_reply", "high", safety=0.5 - 1e-6), ROLE, 0.5).kind == (
        "template"
    )


def test_high_band_template_and_agent() -> None:
    r = route(c("shift_supervisor.thanks_reply", "high"), ROLE)
    assert r == Route(kind="template", intent="shift_supervisor.thanks_reply")
    assert route(c("conversation.greeting", "high"), ROLE) == Route(
        kind="template", intent="conversation.greeting"
    )
    r = route(c("shift_supervisor.report_absence", "high"), ROLE)
    assert r == Route(kind="agent", intent="shift_supervisor.report_absence")


def test_high_band_unknown_or_non_template_conversation_intent_runs_agent() -> None:
    assert route(c("shift_supervisor.unknown", "high"), ROLE) == Route(
        kind="agent", intent="shift_supervisor.unknown"
    )
    assert route(c("conversation.venting", "high"), ROLE).kind == "agent"


def test_other_never_templated() -> None:
    for band in ("high", "medium", "low"):
        assert route(c("other", band, alts=["conversation.venting"]), ROLE) == Route(kind="agent")


def test_medium_clarifies_with_alternatives() -> None:
    r = route(
        c(
            "shift_supervisor.report_absence",
            "medium",
            alts=["shift_supervisor.report_absence", "conversation.venting"],
        ),
        ROLE,
    )
    assert r == Route(
        kind="clarify", options=["shift_supervisor.report_absence", "conversation.venting"]
    )


def test_medium_excludes_other_and_caps_at_three() -> None:
    alts = [
        "shift_supervisor.report_absence",
        "other",
        "conversation.greeting",
        "conversation.venting",
        "shift_supervisor.thanks_reply",
    ]
    assert route(c("a", "medium", alts=alts), ROLE).options == [
        "shift_supervisor.report_absence",
        "conversation.greeting",
        "conversation.venting",
    ]


def test_medium_with_no_usable_alternatives_runs_agent() -> None:
    assert route(c("a", "medium", alts=["other"]), ROLE) == Route(kind="agent")
    assert route(c("a", "medium"), ROLE) == Route(kind="agent")
    assert route(c("a", "medium", alts=["conversation.prompt_injection"]), ROLE) == Route(
        kind="agent"
    )


def test_low_runs_agent_without_intent() -> None:
    assert route(c("shift_supervisor.report_absence", "low"), ROLE) == Route(kind="agent")


def test_no_role_plan_means_agent() -> None:
    assert route(c("shift_supervisor.report_absence", "high"), None) == Route(kind="agent")
    assert route(
        c("conversation.greeting", "medium", alts=["shift_supervisor.report_absence"]), None
    ) == Route(kind="agent")


def test_injection_never_acts_at_any_band() -> None:
    for band in ("high", "medium", "low"):
        assert route(c("conversation.prompt_injection", band), ROLE) == Route(kind="agent")
        assert route(c("conversation.legal_advice", band), ROLE) == Route(kind="agent")


def test_role_cannot_shadow_conversation_ids() -> None:
    shadow = ROLE.model_copy(
        update={
            "intents": [
                IntentSpec(
                    id=i,
                    description="d",
                    counterparts=["c"],
                    risk="read",
                    label_en="x",
                    handler="template",
                )
                for i in (
                    "conversation.prompt_injection",
                    "conversation.venting",
                    "conversation.request_human",
                )
            ]
        }
    )
    assert route(c("conversation.prompt_injection", "high"), shadow) == Route(kind="agent")
    assert route(c("conversation.venting", "high"), shadow) == Route(
        kind="agent", intent="conversation.venting"
    )
    assert route(c("conversation.request_human", "high"), shadow) == Route(
        kind="agent", intent="conversation.request_human"
    )
    assert route(c("conversation.greeting", "high"), shadow).kind == "template"


def test_medium_options_drop_injection_handoff_emergency_and_unknown() -> None:
    alts = [
        "conversation.prompt_injection",
        "conversation.request_human",
        "conversation.emergency",
        "conversation.no_such_intent",
        "shift_supervisor.no_such_intent",
        "conversation.thanks",
        "shift_supervisor.thanks_reply",
    ]
    assert route(c("x", "medium", alts=alts), ROLE).options == [
        "conversation.thanks",
        "shift_supervisor.thanks_reply",
    ]
