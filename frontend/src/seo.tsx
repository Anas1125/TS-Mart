import {useEffect} from 'react';
import {useLocation} from 'react-router-dom';
import {api,Product} from './api';

const SITE='https://ts-mart.pages.dev';
const DEFAULT_TITLE='TS Mart | Curated Tech, Better Prices & Rewards';
const DEFAULT_DESCRIPTION='Discover curated tech at TS Mart. Compare verified prices, explore everyday deals and play to unlock savings. Cash on delivery available.';
const hidden=new Set(['/admin','/account','/cart','/orders','/rewards','/games']);
function meta(attr:'name'|'property',name:string,value:string){
  let el=document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${name}"]`);
  if(!el){el=document.createElement('meta');el.setAttribute(attr,name);document.head.append(el);}
  el.content=value;
}
function canonical(url:string){
  let link=document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if(!link){link=document.createElement('link');link.rel='canonical';document.head.append(link);}
  link.href=url;
}
function schema(product:Product){
  const image=product.images?.filter(src=>/^\/uploads\/[a-f0-9]{32}\.webp$/.test(src)).map(src=>SITE+src);
  return {
    '@context':'https://schema.org','@type':'Product',
    name:product.name,description:product.description,sku:product.sku,
    url:SITE+'/product/'+product.id,
    ...(image?.length?{image}:{}),
    offers:{'@type':'Offer',url:SITE+'/product/'+product.id,priceCurrency:'INR',
      price:(product.price/100).toFixed(2),
      availability:product.stock>0?'https://schema.org/InStock':'https://schema.org/OutOfStock',
      itemCondition:'https://schema.org/NewCondition',
      seller:{'@type':'Organization',name:'TS Mart'}}
  };
}
export function Seo(){
  const location=useLocation();
  useEffect(()=>{
    const path=location.pathname;
    let active=true;
    const productPage=/^\/product\/([1-9]\d*)$/.exec(path);
    const defaults:Record<string,[string,string]>={
      '/':[DEFAULT_TITLE,DEFAULT_DESCRIPTION],
      '/arcade':['Play & Win Shopping Rewards | TS Mart','Play Scratch & Save and Guess the Price at TS Mart to earn shopping rewards. Terms and daily limits apply.'],
      '/admin':['Store Administration | TS Mart','Private TS Mart store administration.'],
      '/account':['Sign In or Register | TS Mart','Sign in to TS Mart or create a shopping account.'],
      '/cart':['Shopping Bag | TS Mart','Review your TS Mart shopping bag.'],
      '/orders':['My Orders | TS Mart','View your private TS Mart order history.'],
      '/rewards':['My Rewards | TS Mart','View your private shopping rewards and coupons.'],
      '/games':['Shopping Games | TS Mart','Explore TS Mart shopping games.']
    };
    const set=(title:string,description:string,url:string,robots:string,ogType:string)=>{
      document.title=title;
      meta('name','description',description);
      meta('name','robots',robots);
      meta('property','og:title',title);
      meta('property','og:description',description);
      meta('property','og:url',url);
      meta('property','og:type',ogType);
      meta('name','twitter:title',title);
      meta('name','twitter:description',description);
      canonical(url);
    };
    document.getElementById('ts-product-schema')?.remove();
    if(productPage){
      const id=Number(productPage[1]);
      set('Product | TS Mart',DEFAULT_DESCRIPTION,SITE+path,'noindex, follow','product');
      api<Product>('/products/'+id).then(product=>{
        if(!active)return;
        const demo=product.sku.startsWith('DEMO-');
        set(product.name+' | TS Mart',product.description.replace(/\s+/g,' ').slice(0,160),
          SITE+'/product/'+product.id,demo?'noindex, follow':'index, follow','product');
        if(!demo){
          const el=document.createElement('script');
          el.id='ts-product-schema';
          el.type='application/ld+json';
          el.textContent=JSON.stringify(schema(product)).replace(/</g,'\\u003c');
          document.head.append(el);
        }
      }).catch(()=>{if(active)set('Product unavailable | TS Mart',DEFAULT_DESCRIPTION,SITE+path,'noindex, follow','product');});
    }else{
      const [title,description]=defaults[path]||['Page not found | TS Mart','Explore TS Mart.'];
      set(title,description,SITE+path,hidden.has(path)||!defaults[path]?'noindex, nofollow':'index, follow','website');
    }
    return()=>{active=false;};
  },[location.pathname]);
  return null;
}
