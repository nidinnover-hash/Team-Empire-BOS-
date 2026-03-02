from __future__ import annotations

from nidin_bos_sdk import NidinBOSClient


def log_event(event: dict[str, object]) -> None:
    print(
        f"[sdk] {event.get('method')} {event.get('path')} "
        f"status={event.get('status_code')} duration_ms={event.get('duration_ms')}"
    )


with NidinBOSClient(
    base_url="https://your-host",
    api_key="nbos_...",
    on_request_event=log_event,
) as client:
    me = client.auth_me()
    print("Authenticated as:", me["email"])
