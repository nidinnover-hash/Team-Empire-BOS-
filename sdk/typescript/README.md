# TypeScript SDK (`@nidin/bos-sdk`)

## Install dependencies

```bash
cd sdk/typescript
npm install
```

## Build

```bash
npm run build
```

## Usage

```ts
import { NidinBOSClient } from "./dist/index.js";

const client = new NidinBOSClient({
  baseUrl: "https://your-host",
  apiKey: "nbos_...",
  onRequestEvent: (event) => console.log(event),
});

const me = await client.authMe();
await client.listOrganizations();
await client.listAutomationTriggers();
await client.listAutomationWorkflows();
```

Client behavior:

- retry/backoff for `429`, `502`, `503`, `504`
- `Retry-After` aware
- throws `QuotaExceededError` for quota-specific `429` responses
- optional request observability callback via `onRequestEvent`
