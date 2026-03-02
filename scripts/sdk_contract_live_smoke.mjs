import { NidinBOSClient } from "../sdk/typescript/dist/index.js";

function env(name, fallback) {
  const value = (process.env[name] ?? fallback ?? "").toString().trim();
  if (!value) {
    throw new Error(`Required env var ${name} is empty`);
  }
  return value;
}

async function login(baseUrl, email, password) {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${baseUrl}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new Error(`Login failed: ${response.status}`);
  }
  const payload = await response.json();
  const token = String(payload.access_token ?? "").trim();
  if (!token) {
    throw new Error("Missing access_token in login response");
  }
  return token;
}

async function createApiKey(baseUrl, bearerToken) {
  const response = await fetch(`${baseUrl}/api/v1/api-keys`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${bearerToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: "TS SDK Contract Key", scopes: "*" }),
  });
  if (!response.ok) {
    throw new Error(`Create API key failed: ${response.status}`);
  }
  const payload = await response.json();
  const key = String(payload.key ?? "").trim();
  if (!key) {
    throw new Error("Missing key in API key create response");
  }
  return key;
}

async function main() {
  const baseUrl = env("SDK_BASE_URL", "http://127.0.0.1:8000");
  const adminEmail = env("ADMIN_EMAIL", "demo@ai.com");
  const adminPassword = env("ADMIN_PASSWORD", "DemoPass123!");

  const jwt = await login(baseUrl, adminEmail, adminPassword);
  const sdkKey = await createApiKey(baseUrl, jwt);

  const client = new NidinBOSClient({ baseUrl, apiKey: sdkKey });
  const me = await client.authMe();
  if (String(me.email ?? "").toLowerCase() !== adminEmail.toLowerCase()) {
    throw new Error("authMe returned unexpected email");
  }

  await client.listApiKeys();
  await client.listWebhooks();

  const created = await client.createTask({
    title: "sdk-contract-task-ts",
    description: "created from ts sdk contract smoke",
  });
  const taskId = Number(created.id);
  const updated = await client.updateTask(taskId, {
    description: "updated from ts sdk",
  });
  if (Number(updated.id) !== taskId) {
    throw new Error("updateTask returned mismatched task id");
  }

  await client.listTasks();
  await client.listApprovals();
  await client.listOrganizations();
  await client.listAutomationTriggers();
  await client.listAutomationWorkflows();
}

await main();
process.stdout.write("TypeScript SDK live contract smoke passed.\n");
