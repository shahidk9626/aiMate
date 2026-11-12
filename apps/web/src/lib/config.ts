/**
 * Public runtime configuration for the browser bundle.
 *
 * NEXT_PUBLIC_* values are inlined by `next build`: changing them requires a
 * rebuild. Only non-secret values may ever use the NEXT_PUBLIC_ prefix.
 */

const DEV_DEFAULT_API_URL = "http://localhost:8000";

export function resolveApiBaseUrl(
  raw: string | undefined,
  nodeEnv: string | undefined,
): string {
  const value = raw?.trim();
  if (!value) {
    if (nodeEnv === "production") {
      throw new Error("NEXT_PUBLIC_API_URL must be set for production builds");
    }
    return DEV_DEFAULT_API_URL;
  }

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`NEXT_PUBLIC_API_URL is not a valid URL: ${value}`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_API_URL must use http or https");
  }
  // Base URL without a trailing slash; paths are appended by the client.
  return url.toString().replace(/\/+$/, "");
}

// Must be referenced literally so Next.js can inline it at build time.
export const API_BASE_URL = resolveApiBaseUrl(
  process.env.NEXT_PUBLIC_API_URL,
  process.env.NODE_ENV,
);
