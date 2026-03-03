export class SDKError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SDKError";
  }
}

export class APIError extends SDKError {
  statusCode: number;
  detail?: string;
  requestId?: string;
  body?: unknown;

  constructor(message: string, statusCode: number, detail?: string, requestId?: string, body?: unknown) {
    super(message);
    this.name = "APIError";
    this.statusCode = statusCode;
    this.detail = detail;
    this.requestId = requestId;
    this.body = body;
  }
}

export class RateLimitError extends APIError {
  retryAfterSeconds?: number;

  constructor(
    message: string,
    statusCode: number,
    detail?: string,
    requestId?: string,
    body?: unknown,
    retryAfterSeconds?: number,
  ) {
    super(message, statusCode, detail, requestId, body);
    this.name = "RateLimitError";
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export class QuotaExceededError extends RateLimitError {
  constructor(
    message: string,
    statusCode: number,
    detail?: string,
    requestId?: string,
    body?: unknown,
    retryAfterSeconds?: number,
  ) {
    super(message, statusCode, detail, requestId, body, retryAfterSeconds);
    this.name = "QuotaExceededError";
  }
}
