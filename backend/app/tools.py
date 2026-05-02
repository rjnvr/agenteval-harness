from dataclasses import dataclass


SUPPORTED_ACTIONS = {
    "flag_risk",
    "create_task",
    "request_more_info",
    "flag_cost_risk",
    "approve_invoice",
    "escalate_compliance_review",
}


@dataclass(frozen=True)
class ToolCall:
    action: str
    action_input: str


def flag_risk(reason: str) -> ToolCall:
    return ToolCall("flag_risk", reason)


def create_task(title: str) -> ToolCall:
    return ToolCall("create_task", title)


def request_more_info(item: str) -> ToolCall:
    return ToolCall("request_more_info", item)


def flag_cost_risk(reason: str) -> ToolCall:
    return ToolCall("flag_cost_risk", reason)


def approve_invoice(note: str) -> ToolCall:
    return ToolCall("approve_invoice", note)


def escalate_compliance_review(reason: str) -> ToolCall:
    return ToolCall("escalate_compliance_review", reason)

