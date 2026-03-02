# Python SDK (`nidin_bos_sdk`)

## Install (local)

```bash
cd sdk/python
py -3.12 -m pip install -e .
```

## Usage

```python
from nidin_bos_sdk import NidinBOSClient

with NidinBOSClient(base_url="https://your-host", api_key="nbos_...") as client:
    me = client.auth_me()
    keys = client.list_api_keys()
```

```python
def log_event(event: dict[str, object]) -> None:
    print(event)

with NidinBOSClient(
    base_url="https://your-host",
    api_key="nbos_...",
    on_request_event=log_event,
) as client:
    client.list_tasks()
    client.list_organizations()
    client.list_automation_triggers()
    client.list_automation_workflows()
```

Client behavior:

- automatic retries with exponential backoff for `429`, `502`, `503`, `504`
- `Retry-After` support
- raises `QuotaExceededError` when `429` indicates quota exhaustion
- optional request observability callback via `on_request_event`
