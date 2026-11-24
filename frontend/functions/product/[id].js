// Server-set SEO metadata for public product pages on Cloudflare Pages.
// The storefront still renders interactively with React/Vite.
const SITE = "https://ts-mart.pages.dev";
const safeJson = (obj) => JSON.stringify(obj).replace(/</g, "\\u003c");

export async function onRequestGet({ request, env, params }) {
  const id = String(params.id || "");
  if (!/^[1-9]\d*$/.test(id)) return new Response("Product not found", { status: 404 });
  if (!env.API_ORIGIN) return new Response("Catalog unavailable", { status: 503 });
  let backend;
  try {
    backend = new URL(env.API_ORIGIN);
    if (backend.protocol !== "https:") throw new Error("HTTPS required");
  } catch {
    return new Response("Invalid catalog configuration", { status: 503 });
  }
  let product;
  try {
    const response = await fetch(new URL("/api/products/" + id, backend.origin).toString(), {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(8000)
    });
    if (response.status === 404) return new Response("Product not found", { status: 404 });
    if (!response.ok) throw new Error("Product unavailable");
    product = await response.json();
  } catch {
    return new Response("Product temporarily unavailable", {
      status: 503,
      headers: { "Cache-Control": "no-store" }
    });
  }

  const demo = String(product.sku || "").startsWith("DEMO-");
  const title = String(product.name || "Product").slice(0, 160) + " | TS Mart";
  const description = String(product.description || "Discover this product at TS Mart.").replace(/\s+/g, " ").slice(0, 160);
  const canonical = SITE + "/product/" + id;
  const price = Number(product.price);
  const structured = !demo && Number.isFinite(price) && price > 0 ? {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.description,
    sku: product.sku,
    url: canonical,
    ...(Array.isArray(product.images) && product.images.some((src) => /^\/uploads\/[^?]+\.webp$/.test(src)) ? {
      image: product.images.filter((src) => /^\/uploads\/[^?]+\.webp$/.test(src)).map((src) => SITE + src)
    } : {}),
    offers: {
      "@type": "Offer",
      url: canonical,
      priceCurrency: "INR",
      price: (price / 100).toFixed(2),
      availability: Number(product.stock) > 0 ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
      itemCondition: "https://schema.org/NewCondition",
      seller: { "@type": "Organization", name: "TS Mart" }
    }
  } : null;

  const asset = await env.ASSETS.fetch(new Request(new URL("/", request.url).toString()));
  if (!asset.ok) return asset;
  const rewritten = new HTMLRewriter()
    .on("title", { element(e) { e.setInnerContent(title); } })
    .on('meta[name="description"]', { element(e) { e.setAttribute("content", description); } })
    .on('link[rel="canonical"]', { element(e) { e.setAttribute("href", canonical); } })
    .on('meta[property="og:title"]', { element(e) { e.setAttribute("content", title); } })
    .on('meta[property="og:description"]', { element(e) { e.setAttribute("content", description); } })
    .on('meta[property="og:url"]', { element(e) { e.setAttribute("content", canonical); } })
    .on('meta[property="og:type"]', { element(e) { e.setAttribute("content", "product"); } })
    .on('meta[name="twitter:title"]', { element(e) { e.setAttribute("content", title); } })
    .on('meta[name="twitter:description"]', { element(e) { e.setAttribute("content", description); } })
    .on("head", { element(e) {
      if (demo) e.append('<meta name="robots" content="noindex, follow">', { html: true });
      if (structured) e.append('<script id="ts-product-schema" type="application/ld+json">' + safeJson(structured) + '</script>', { html: true });
    } })
    .transform(asset);
  const headers = new Headers(rewritten.headers);
  headers.set("Content-Type", "text/html; charset=utf-8");
  headers.set("Cache-Control", "public, max-age=120");
  if (demo) headers.set("X-Robots-Tag", "noindex, follow");
  return new Response(rewritten.body, { status: rewritten.status, headers });
}
