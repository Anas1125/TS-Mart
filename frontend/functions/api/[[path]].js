// Same-origin proxy: browser -> Cloudflare Pages /api -> Vercel FastAPI.
// This keeps TS Mart's HttpOnly, Secure, SameSite=Lax session cookie
// first-party on the storefront domain.
export async function onRequest({ request, env }) {
  if (!env.API_ORIGIN) {
    return Response.json(
      { detail: "TS Mart API origin is not configured." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  let backend;
  try {
    backend = new URL(env.API_ORIGIN);
    if (backend.protocol !== "https:") {
      throw new Error("HTTPS backend required");
    }
  } catch {
    return Response.json(
      { detail: "TS Mart API origin configuration is invalid." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname + incoming.search, backend.origin);
  const upstreamRequest = new Request(target.toString(), request);
  upstreamRequest.headers.delete("host");

  try {
    // Preserve request cookies, Origin, and Fetch Metadata for FastAPI's
    // existing session handling and CSRF protections.
    // Preserve Set-Cookie from FastAPI on the response.
    const response = await fetch(upstreamRequest, { redirect: "manual" });
    return response;
  } catch {
    return Response.json(
      { detail: "The TS Mart API is temporarily unavailable." },
      { status: 502, headers: { "Cache-Control": "no-store" } }
    );
  }
}
