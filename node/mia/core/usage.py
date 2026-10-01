"""usage_cloud_requests: the primary record of every cloud model request made by this node."""

from sqlmodel import Session

from mia.core import store
from mia.core.models import Actor, UsageCloudRequest


def record(
    session: Session,
    actor: Actor,
    *,
    organisation_id: str,
    agent_id: str,
    task: str,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    result: str = "success",
    subagent_id: str | None = None,
) -> UsageCloudRequest:
    """Store one metered request. Content is never stored, only counts."""
    row = UsageCloudRequest(
        branch_id=actor.branch_id,
        organisation_id=organisation_id,
        agent_id=agent_id,
        subagent_id=subagent_id,
        task=task,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        result=result,
    )
    return store.insert(session, row, actor, action="usage.recorded")
