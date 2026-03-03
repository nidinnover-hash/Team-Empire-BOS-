# Agent Orchestration Overview

This document summarises how the **Agent Orchestrator** decides which clone role should
respond to a user message and how multi-turn operations unfold.

The orchestrator lives in `app/agents/orchestrator.py` and is exercised by the
`/api/v1/agents` endpoints.

```mermaid
flowchart LR
    U[User message] --> RO{route_role()}
    RO -->|sales keywords| SL[Sales Lead Clone]
    RO -->|ops keywords| OM[Ops Manager Clone]
    RO -->|tech keywords| TP[Tech PM Clone]
    RO -->|fallback| CEO[CEO Clone]
    RO -->|force_role override| FR[forced role lookup]

    subgraph Multi-turn work
        click U "app/agents/orchestrator.py#run_agent_multi_turn" "multi-turn logic"
        UM(("_decompose_plan")) --> Step1["step 1 AI call"]
        Step1 --> Step2["step 2 AI call"]
        Step2 --> Output["MultiTurnResponse"]
    end

    style U fill:#f9f,stroke:#333,stroke-width:2px
    style CEO fill:#ffc,stroke:#333
    style SL fill:#cfc,stroke:#333
    style OM fill:#ccf,stroke:#333
    style TP fill:#fcf,stroke:#333
```
```

> **Note:** forcing a role that's not recognised still falls through to the
> keyword logic, avoiding KeyError exceptions.

The code also includes helper mappings for `ROLE_PROMPTS` and `AVATAR_PROMPTS` which
control the system prompt used for each clone when calling the AI router.

Further details and example JSON schemas are available in the Python file
itself; this doc is intended for quick onboarding.«
