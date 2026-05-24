from dataclasses import dataclass, field
from typing import Literal

Step = Literal["name", "event_type", "date", "done"]


@dataclass
class CallSession:
    step: Step = "name"
    caller_name: str = ""
    event_type: str = ""
    event_date: str = ""
    caller_phone: str = ""
    retries: dict[str, int] = field(default_factory=dict)


_sessions: dict[str, CallSession] = {}


def get_session(call_sid: str, caller_phone: str = "") -> CallSession:
    if call_sid not in _sessions:
        _sessions[call_sid] = CallSession(caller_phone=caller_phone)
    elif caller_phone and not _sessions[call_sid].caller_phone:
        _sessions[call_sid].caller_phone = caller_phone
    return _sessions[call_sid]


def clear_session(call_sid: str) -> None:
    _sessions.pop(call_sid, None)
