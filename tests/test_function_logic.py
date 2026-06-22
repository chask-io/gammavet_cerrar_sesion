import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.function_logic import ACTOR_LAMBDA, FunctionBackend  # noqa: E402
from chask_foundation.backend.models import OrchestrationEvent  # noqa: E402


EVENT_ID = "11111111-2222-4333-8444-555555555555"
SESSION_ID = "66666666-2222-4333-8444-555555555555"


def _event(args=None):
    return OrchestrationEvent.model_validate(
        {
            "event_id": EVENT_ID,
            "event_type": "function_call",
            "branch": "test",
            "organization_customer_id": None,
            "customer": None,
            "connection_key": "test",
            "organization": {
                "organization_id": "99999999-aaaa-4bbb-8ccc-dddddddddddd",
                "organization_name": "Chask Dev",
            },
            "prompt": "",
            "pipeline_id": 27023,
            "orchestration_session_uuid": SESSION_ID,
            "internal_orchestration_session_uuid": None,
            "channel_id": None,
            "entry_point_channel": "whatsapp",
            "source": "agent",
            "target": "function",
            "plan": None,
            "extra_params": {
                "user_phone_number": "+56 9 1111 2222",
                "agent_phone_number": "1051240901403291",
                "tool_calls": [{"args": args or {"summary": "sin pendientes"}}],
            },
            "access_token": "access-token",
            "target_agent": None,
            "target_operator": None,
            "type": None,
            "status": None,
            "channels": None,
            "whatsapp_template_instance": None,
            "created_at": None,
        }
    )


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def call(self, endpoint, **kwargs):
        self.calls.append({"endpoint": endpoint, **kwargs})
        if endpoint == "evolve_event":
            return {
                "status_code": 201,
                "uuid": "22222222-2222-4222-8222-222222222222",
                "extra_params": kwargs["extra_params"],
            }
        return {"status_code": 200}


def test_cerrar_sesion_completes_session_and_emits_marker(monkeypatch):
    orchestrator = FakeOrchestrator()
    monkeypatch.setattr("backend.function_logic.orchestrator_api_manager", orchestrator)

    result = FunctionBackend(_event()).process_request()

    assert SESSION_ID in result
    assert any(
        call["endpoint"] == "change_orchestration_session_status"
        and call["orchestration_session_uuid"] == SESSION_ID
        and call["status"] == "completed"
        for call in orchestrator.calls
    )
    dispatch_call = next(
        call
        for call in orchestrator.calls
        if call["endpoint"] == "evolve_event" and call.get("event_type") == "dispatch_event"
    )
    assert dispatch_call["extra_params"]["event_type"] == "conductor_session_completed"
    assert dispatch_call["extra_params"]["actor_lambda"] == ACTOR_LAMBDA
    assert dispatch_call["extra_params"]["metadata"]["summary"] == "sin pendientes"
