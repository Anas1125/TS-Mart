import {createContext,useContext,useState,useEffect,ReactNode} from 'react';
import {api,send,Product} from './api';
type Item={product:Product;quantity:number};
const Context=createContext<any>(null);
export function Provider({children}:{children:ReactNode}){
 const [user,setUser]=useState<any>(null),[ready,setReady]=useState(false),[settings,setSettings]=useState<any>(null),[toast,setToast]=useState('');
 const [cart,setCart]=useState<Item[]>(()=>{try{return JSON.parse(localStorage.getItem('ts-cart')||'[]')}catch{return []}});
 useEffect(()=>{api('/me').then(setUser).catch(()=>{}).finally(()=>setReady(true));api('/settings').then(setSettings).catch(()=>{})},[]);
 useEffect(()=>{localStorage.setItem('ts-cart',JSON.stringify(cart))},[cart]);
 useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),4000);return()=>clearTimeout(t)}},[toast]);
 const add=(product:Product)=>{setCart((items)=>{const old=items.find(x=>x.product.id===product.id);return old?items.map(x=>x.product.id===product.id?{product,quantity:Math.min(x.quantity+1,product.stock,20)}:x):[...items,{product,quantity:1}]});setToast(`${product.name} added to your bag`)};
 const quantity=(id:number,n:number)=>setCart(items=>n<1?items.filter(x=>x.product.id!==id):items.map(x=>x.product.id===id?{...x,quantity:Math.min(n,x.product.stock,20)}:x));
 const logout=async()=>{await send('/logout');setUser(null);setToast('Signed out')};
 return <Context.Provider value={{user,setUser,ready,settings,setSettings,cart,setCart,add,quantity,toast:setToast,logout}}><div style={{'--accent':settings?.accent||'#a78bfa'} as React.CSSProperties}>{children}</div>{toast&&<div className="toast" role="status">✓ {toast}</div>}</Context.Provider>
}
export const useStore=()=>useContext(Context);
