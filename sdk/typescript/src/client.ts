import { APIError, QuotaExceededError, RateLimitError } from "./errors";
import type {
  ApprovalDecision,
  ApprovalRead,
  ApiKeyCreate,
  ApiKeyCreateResponse,
  ApiKeyListResponse,
  TaskCreate,
  TaskRead,
  TaskUpdate,
  UserMeRead,
  WebhookDeliveryListResponse,
  WebhookEndpointCreate,
  WebhookEndpointCreateResponse,
  WebhookEndpointListResponse,
} from "./types";

export interface ClientOptions {
  baseUrl: string;
  apiKey: string;
  maxRetries?: number;
  backoffMs?: number;
  onRequestEvent?: (event: RequestEvent) => void;
}

export interface RequestEvent {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  attempt: number;
  statusCode: number;
  durationMs: number;
  requestId?: string;
  retriable: boolean;
  retried: boolean;
  errorType?: string;
}

const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);

function parseRetryAfterSeconds(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return undefined;
  return parsed;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class NidinBOSClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly maxRetries: number;
  private readonly backoffMs: number;
  private readonly onRequestEvent?: (event: RequestEvent) => void;

  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.maxRetries = Math.max(0, options.maxRetries ?? 2);
    this.backoffMs = Math.max(0, options.backoffMs ?? 500);
    this.onRequestEvent = options.onRequestEvent;
  }

  private async request<T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path: string,
    opts: { body?: unknown; expectedStatus?: number[] } = {},
  ): Promise<T> {
    const expected = new Set(opts.expectedStatus ?? [200]);
    let lastError: APIError | undefined;

    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      const started = Date.now();
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      });

      if (expected.has(response.status)) {
        this.onRequestEvent?.({
          method,
          path,
          attempt: attempt + 1,
          statusCode: response.status,
          durationMs: Number((Date.now() - started).toFixed(3)),
          requestId: response.headers.get("x-correlation-id") ?? undefined,
          retriable: false,
          retried: attempt > 0,
          errorType: undefined,
        });
        if (response.status === 204) return undefined as T;
        const text = await response.text();
        return (text ? JSON.parse(text) : undefined) as T;
      }

      let body: unknown = undefined;
      try {
        body = await response.json();
      } catch {
        body = undefined;
      }
      const requestId = response.headers.get("x-correlation-id") ?? undefined;
      const detail =
        typeof body === "object" && body !== null && "detail" in body
          ? String((body as { detail?: unknown }).detail ?? "")
          : undefined;
      const retryAfterSeconds = parseRetryAfterSeconds(response.headers.get("retry-after"));

      if (response.status === 429) {
        const quota = (detail ?? "").toLowerCase().includes("quota");
        if (quota) {
          lastError = new QuotaExceededError(
            "Daily quota exceeded",
            429,
            detail,
            requestId,
            body,
            retryAfterSeconds,
          );
        } else {
          lastError = new RateLimitError(
            "Rate limited by API",
            429,
            detail,
            requestId,
            body,
            retryAfterSeconds,
          );
        }
      } else {
        lastError = new APIError(`API request failed with status ${response.status}`, response.status, detail, requestId, body);
      }

      this.onRequestEvent?.({
        method,
        path,
        attempt: attempt + 1,
        statusCode: response.status,
        durationMs: Number((Date.now() - started).toFixed(3)),
        requestId,
        retriable: RETRYABLE_STATUS.has(response.status),
        retried: attempt > 0,
        errorType: lastError.name,
      });

      if (!RETRYABLE_STATUS.has(response.status) || attempt >= this.maxRetries) {
        break;
      }
      const delayMs =
        retryAfterSeconds !== undefined
          ? retryAfterSeconds * 1000
          : this.backoffMs * (2 ** attempt);
      if (delayMs > 0) {
        await sleep(delayMs);
      }
    }

    throw lastError ?? new APIError("Unknown request failure", 0);
  }

  authMe(): Promise<UserMeRead> {
    return this.request<UserMeRead>("GET", "/api/v1/auth/me");
  }

  listApiKeys(): Promise<ApiKeyListResponse> {
    return this.request<ApiKeyListResponse>("GET", "/api/v1/api-keys");
  }

  createApiKey(payload: ApiKeyCreate): Promise<ApiKeyCreateResponse> {
    return this.request<ApiKeyCreateResponse>("POST", "/api/v1/api-keys", {
      body: payload,
      expectedStatus: [201],
    });
  }

  revokeApiKey(keyId: number): Promise<void> {
    return this.request<void>("DELETE", `/api/v1/api-keys/${keyId}`, {
      expectedStatus: [200, 204],
    });
  }

  listWebhooks(): Promise<WebhookEndpointListResponse> {
    return this.request<WebhookEndpointListResponse>("GET", "/api/v1/webhooks");
  }

  createWebhook(payload: WebhookEndpointCreate): Promise<WebhookEndpointCreateResponse> {
    return this.request<WebhookEndpointCreateResponse>("POST", "/api/v1/webhooks", {
      body: payload,
      expectedStatus: [201],
    });
  }

  listWebhookDeliveries(endpointId: number, limit = 50, offset = 0): Promise<WebhookDeliveryListResponse> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return this.request<WebhookDeliveryListResponse>(
      "GET",
      `/api/v1/webhooks/${endpointId}/deliveries?${params.toString()}`,
    );
  }

  listTasks(): Promise<TaskRead[]> {
    return this.request<TaskRead[]>("GET", "/api/v1/tasks");
  }

  createTask(payload: TaskCreate): Promise<TaskRead> {
    return this.request<TaskRead>("POST", "/api/v1/tasks", {
      body: payload,
      expectedStatus: [201],
    });
  }

  updateTask(taskId: number, payload: TaskUpdate): Promise<TaskRead> {
    return this.request<TaskRead>("PATCH", `/api/v1/tasks/${taskId}`, {
      body: payload,
      expectedStatus: [200],
    });
  }

  listApprovals(): Promise<ApprovalRead[]> {
    return this.request<ApprovalRead[]>("GET", "/api/v1/approvals");
  }

  approveApproval(approvalId: number, payload: ApprovalDecision): Promise<ApprovalRead> {
    return this.request<ApprovalRead>("POST", `/api/v1/approvals/${approvalId}/approve`, {
      body: payload,
      expectedStatus: [200],
    });
  }

  listOrganizations(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("GET", "/api/v1/orgs");
  }

  listAutomationTriggers(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("GET", "/api/v1/automations/triggers");
  }

  listAutomationWorkflows(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("GET", "/api/v1/automations/workflows");
  }
}
