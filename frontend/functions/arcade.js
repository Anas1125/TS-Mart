// SEO-friendly public arcade landing page while React handles interactivity.
const TITLE = "Play & Win Shopping Rewards | TS Mart";
const DESCRIPTION = "Play Scratch & Save and Guess the Price at TS Mart to earn shopping rewards. Terms and daily limits apply.";
const CANONICAL = "https://ts-mart.pages.dev/arcade";
export async function onRequestGet({ request, env }) {
  const asset = await env.ASSETS.fetch(new Request(new URL("/", request.url).toString()));
  if (!asset.ok) return asset;
  const response = new HTMLRewriter()
    .on("title", {element(e){e.setInnerContent(TITLE);}})
    .on('meta[name="description"]',{element(e){e.setAttribute("content",DESCRIPTION);}})
    .on('link[rel="canonical"]',{element(e){e.setAttribute("href",CANONICAL);}})
    .on('meta[property="og:title"]',{element(e){e.setAttribute("content",TITLE);}})
    .on('meta[property="og:description"]',{element(e){e.setAttribute("content",DESCRIPTION);}})
    .on('meta[property="og:url"]',{element(e){e.setAttribute("content",CANONICAL);}})
    .on('meta[name="twitter:title"]',{element(e){e.setAttribute("content",TITLE);}})
    .on('meta[name="twitter:description"]',{element(e){e.setAttribute("content",DESCRIPTION);}})
    .transform(asset);
  const headers = new Headers(response.headers);
  headers.set("Content-Type","text/html; charset=utf-8");
  return new Response(response.body,{status:response.status,headers});
}
