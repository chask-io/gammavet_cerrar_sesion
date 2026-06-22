"""
Business logic for CerrarSesionFn.

Org-specific Gammavet lambda: complete the conductor orchestration session
without mutating tenant route state.
"""

import logging
import re
from typing import Any

from chask_foundation.backend.models import OrchestrationEvent

try:
    from api.orchestrator_requests import orchestrator_api_manager
except ModuleNotFoundError:
    from chask_foundation.api.orchestrator_requests import orchestrator_api_manager

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ACTOR_LAMBDA = "gammavet_cerrar_sesion"


class FunctionBackend:
    def __init__(self, orchestration_event: OrchestrationEvent):
        self.orchestration_event = orchestration_event
        logger.info(
            "CerrarSesionFn initialized for org=%s",
            orchestration_event.organization.organization_id,
        )

    def process_request(self) -> str:
        args = self._extract_tool_args()
        session_uuid = str(
            args.get("ticket_id") or self.orchestration_event.orchestration_session_uuid or ""
        ).strip()
        if not session_uuid:
            raise ValueError("No se encontro orchestration_session_uuid para cerrar la sesion")

        summary = str(args.get("summary") or "Sesion de conductor cerrada.").strip()
        response = orchestrator_api_manager.call(
            "change_orchestration_session_status",
            orchestration_session_uuid=session_uuid,
            status="completed",
            access_token=self.orchestration_event.access_token,
            organization_id=self.orchestration_event.organization.organization_id,
        )
        if response.get("status_code") not in (200, 201, None):
            raise RuntimeError(f"Failed to complete orchestration session: {response}")

        self._emit_dispatch_event(
            "conductor_session_completed",
            {
                "summary": summary,
                "driver_id": str(args.get("driver_id") or ""),
                "driver_phone": str(args.get("driver_phone") or self._event_phone() or ""),
                "session_uuid": session_uuid,
                "event_id": str(self.orchestration_event.event_id),
            },
        )
        return f"Sesion de conductor {session_uuid} completada."

    def _emit_dispatch_event(self, event_type: str, metadata: dict[str, Any]) -> None:
        orchestrator_api_manager.call(
            "evolve_event",
            parent_event_uuid=str(self.orchestration_event.event_id),
            event_type="dispatch_event",
            source="agent",
            target="orchestrator",
            prompt=event_type,
            extra_params={
                "event_type": event_type,
                "actor_lambda": ACTOR_LAMBDA,
                "metadata": metadata,
            },
            access_token=self.orchestration_event.access_token,
            organization_id=self.orchestration_event.organization.organization_id,
        )

    def _event_phone(self) -> str:
        customer = getattr(self.orchestration_event, "customer", None)
        if customer and getattr(customer, "phone", None):
            return str(customer.phone).strip()

        extra_params = self.orchestration_event.extra_params or {}
        for key in ("driver_phone", "user_phone_number", "phone", "from"):
            value = str(extra_params.get(key) or "").strip()
            if value:
                return value

        prompt = str(getattr(self.orchestration_event, "prompt", "") or "")
        digits = "".join(re.findall(r"\d+", prompt))
        return digits if len(digits) >= 8 else ""

    def _extract_tool_args(self) -> dict[str, Any]:
        extra_params = self.orchestration_event.extra_params or {}
        tool_calls = extra_params.get("tool_calls", [])
        if not tool_calls:
            return {}
        args = tool_calls[0].get("args", {}) or {}
        return args if isinstance(args, dict) else {}
