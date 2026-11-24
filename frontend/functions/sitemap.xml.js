// Generated from the public catalog so newly added real products are discoverable.
// Demo seed products are deliberately excluded until replaced with actual inventory.
const SITE = "https://ts-mart.pages.dev";
const escapeXml = (value) => String(value).replace(/[<>&"']/g, (c) => ({
  "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;"
}[c]));

export async function onRequestGet({ env }) {
  if (!env.API_ORIGIN) return new Response("Sitemap backend is not configured", { status: 503 });
  let url;
  try {
    const backend = new URL(env.API_ORIGIN);
    if (backend.protocol !== "https:") throw new Error("HTTPS required");
    url = new URL("/api/products", backend.origin);
  } catch {
    return new Response("Invalid sitemap backend configuration", { status: 503 });
  }
  try {
    const response = await fetch(url.toString(), {
      headers: { "Accept": "application/json" },
      signal: AbortSignal.timeout(8000)
    });
    if (!response.ok) throw new Error("Catalog unavailable");
    const products = await response.json();
    if (!Array.isArray(products)) throw new Error("Invalid catalog");
    const ids = [...new Set(products.filter((p) =>
      p && Number.isSafeInteger(p.id) && p.id > 0 && p.active !== false &&
      !String(p.sku || "").startsWith("DEMO-")
    ).map((p) => p.id))];
    const pages = ["/", "/arcade", ...ids.map((id) => `/product/${id}`)];
    const entries = pages.map((path) => `  <url><loc>${escapeXml(SITE + path)}</loc></url>`).join("\n");
    const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</urlset>\n`;
    return new Response(body, {
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": "public, max-age=300",
        "X-Content-Type-Options": "nosniff"
      }
    });
  } catch {
    // Never expose an incomplete sitemap as a successful 200 response.
    return new Response("Sitemap temporarily unavailable", {
      status: 503,
      headers: { "Cache-Control": "no-store" }
    });
  }
}
