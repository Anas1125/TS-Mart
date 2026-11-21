export const money=(n:number)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:n%100?2:0}).format(n/100);
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
 const response=await fetch(`${import.meta.env.VITE_API_BASE||''}/api${path}`,{credentials:'include',...options,headers:options.body instanceof FormData?options.headers:{'Content-Type':'application/json',...options.headers}});
 const data=await response.json();
 if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map((e:any)=>`${e.loc.slice(1).join(' ')}: ${e.msg}`).join('; '):'Something went wrong. Please try again.');
 return data;
}
export const send=(path:string,data:unknown={},method='POST')=>api(path,{method,body:JSON.stringify(data)});
export type Product={id:number;name:string;description:string;sku:string;category:string;price:number;base_price:number;original_price:number;stock:number;active:boolean;discount:number;images:string[];featured:boolean;deal:null|{title:string;ends_at:string}};
