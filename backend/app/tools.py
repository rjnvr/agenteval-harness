from dataclasses import dataclass


# The decision surface for a coordination / scheduling agent. Each case expects the
# agent to choose exactly one of these actions for the incoming request.
SUPPORTED_ACTIONS = {
    "propose_times",        # offer one or more candidate slots for the group to confirm
    "book_meeting",         # commit a specific slot that works for everyone
    "decline",              # turn the request down (e.g. a hard preference blocks every slot)
    "propose_alternative",  # re-coordinate / reschedule around a conflict
    "request_availability",  # follow up because at least one attendee's calendar is unknown
    "escalate_to_human",    # ambiguous or out of policy; hand back to a person
}

# Actions that commit the agent to a concrete time slot, so the slot must be
# validated against every participant's calendar, working hours, and preferences.
SLOT_ACTIONS = {"propose_times", "book_meeting", "propose_alternative"}


@dataclass(frozen=True)
class ToolCall:
    action: str
    action_input: str


def propose_times(slots: str) -> ToolCall:
    return ToolCall("propose_times", slots)


def book_meeting(slot: str) -> ToolCall:
    return ToolCall("book_meeting", slot)


def decline(reason: str) -> ToolCall:
    return ToolCall("decline", reason)


def propose_alternative(slot: str) -> ToolCall:
    return ToolCall("propose_alternative", slot)


def request_availability(item: str) -> ToolCall:
    return ToolCall("request_availability", item)


def escalate_to_human(reason: str) -> ToolCall:
    return ToolCall("escalate_to_human", reason)
