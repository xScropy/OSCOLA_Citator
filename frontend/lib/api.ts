const TOKEN_KEY = "citeright.token";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(messageOf(detail));
    this.status = status;
    this.detail = detail;
  }
}

function messageOf(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors
    return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return "Something went wrong. Please try again.";
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session lasts until the page is closed */
  }
}

async function request(path: string, method: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const form = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !form) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : form ? (body as FormData) : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "The CiteRight server could not be reached.");
  }
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* non-JSON error body */
    }
    if (response.status >= 500 && !detail) detail = "The CiteRight server is unavailable. Check that the backend is running.";
    throw new ApiError(response.status, detail);
  }
  return response;
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await request(path, method, body);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** POST and save the response as a file, using the server's filename. */
export async function download(path: string, body: unknown): Promise<void> {
  const response = await request(path, "POST", body);
  const blob = await response.blob();
  const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "")?.[1] || "references";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Copy a citation with its italics (rich text) and a plain-text fallback. */
export async function copyCitation(text: string, html?: string): Promise<boolean> {
  try {
    if (html && typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      const styled = html.replace(/<span class="sc">/g, '<span style="font-variant:small-caps">');
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([styled], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" }),
        }),
      ]);
      return true;
    }
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }
}
