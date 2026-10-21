import type { components } from "./schema";
export type Schemas = components["schemas"] & {
  AssessmentRead: components["schemas"]["ObservationRead"]["assessments"][number];
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
    public retryAfter?: string,
  ) {
    super(message);
  }
}
export class ApiClient {
  readonly origin: string;
  constructor(
    base: string,
    private token: () => string | null,
  ) {
    this.origin = base.replace(/\/$/, "");
    if (!/^https?:\/\//.test(this.origin))
      throw Error("Укажите адрес API с http:// или https://");
  }
  async request<T>(
    path: string,
    options: RequestInit = {},
    signal?: AbortSignal,
  ): Promise<T> {
    const headers = new Headers(options.headers);
    const token = this.token();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    const response = await fetch(`${this.origin}${path}`, {
      ...options,
      headers,
      signal,
    });
    if (!response.ok) {
      let b: any = {};
      try {
        b = await response.json();
      } catch {}
      throw new ApiError(
        response.status,
        b.code ?? "http_error",
        b.message ?? "Сервис временно недоступен",
        b.request_id,
        response.headers.get("Retry-After") ?? undefined,
      );
    }
    if (response.status === 204) return undefined as T;
    return response.json();
  }
  catalog(signal?: AbortSignal) {
    return this.request<Schemas["CatalogRead"]>("/v1/catalog", {}, signal);
  }
  me(signal?: AbortSignal) {
    return this.request<Schemas["MeRead"]>("/v1/me", {}, signal);
  }
  history(cursor?: string, signal?: AbortSignal) {
    return this.request<Schemas["ObservationPage"]>(
      `/v1/observations?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      {},
      signal,
    );
  }
  observation(id: string, signal?: AbortSignal) {
    return this.request<Schemas["ObservationRead"]>(
      `/v1/observations/${id}`,
      {},
      signal,
    );
  }
  createObservation(body: Schemas["ObservationCreate"], signal?: AbortSignal) {
    return this.request<Schemas["ObservationRead"]>(
      "/v1/observations",
      { method: "POST", body: JSON.stringify(body) },
      signal,
    );
  }
  uploadPhoto(id: string, clientId: string, uri: string, signal?: AbortSignal) {
    const form = new FormData();
    form.append("client_photo_id", clientId);
    form.append("purpose", "primary");
    form.append("file", {
      uri,
      name: "leaf.jpg",
      type: "image/jpeg",
    } as unknown as Blob);
    return this.request<Schemas["PhotoRead"]>(
      `/v1/observations/${id}/photos`,
      { method: "POST", body: form },
      signal,
    );
  }
  createAssessment(
    body: Schemas["AssessmentCreate"],
    key: string,
    signal?: AbortSignal,
  ) {
    return this.request<Schemas["AssessmentRead"]>(
      "/v1/assessments",
      {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": key },
      },
      signal,
    );
  }
  assessment(id: string, signal?: AbortSignal) {
    return this.request<Schemas["AssessmentRead"]>(
      `/v1/assessments/${id}`,
      {},
      signal,
    );
  }
  contentUrl(id: string, signal?: AbortSignal) {
    return this.request<{ url: string; expires_at: string }>(
      `/v1/photos/${id}/content-url`,
      {},
      signal,
    );
  }
  privateImage(url: string) {
    const target = new URL(url, this.origin);
    if (target.origin !== new URL(this.origin).origin)
      throw Error("Адрес изображения не принадлежит API");
    return {
      uri: target.href,
      headers: { Authorization: `Bearer ${this.token() ?? ""}` },
    };
  }
  feedback(id: string, body: Schemas["FeedbackCreate"], signal?: AbortSignal) {
    return this.request(
      `/v1/assessments/${id}/feedback`,
      { method: "POST", body: JSON.stringify(body) },
      signal,
    );
  }
  deleteObservation(id: string, signal?: AbortSignal) {
    return this.request(`/v1/observations/${id}`, { method: "DELETE" }, signal);
  }
}
