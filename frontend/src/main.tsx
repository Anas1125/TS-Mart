import React,{useEffect} from 'react';
import ReactDOM from 'react-dom/client';
import {BrowserRouter,Routes,Route,useLocation} from 'react-router-dom';
import {MotionConfig} from 'motion/react';
import {Provider} from './store';
import {Header,Footer,Empty} from './components';
import {Home, Detail, Cart, Account, Orders} from './pages';
import {ArcadePage,MyRewardsPage,ClassicGames} from './arcade';
import {Admin} from './admin';
import './styles.css';
function App(){const location=useLocation();useEffect(()=>{window.scrollTo(0,0)},[location.pathname]);return <><a className="skip-link" href="#content">Skip to content</a><Header/><div id="content"><Routes><Route path="/" element={<Home/>}/><Route path="/product/:id" element={<Detail/>}/><Route path="/cart" element={<Cart/>}/><Route path="/account" element={<Account/>}/><Route path="/orders" element={<Orders/>}/><Route path="/arcade" element={<ArcadePage/>}/><Route path="/rewards" element={<MyRewardsPage/>}/><Route path="/games" element={<ClassicGames/>}/><Route path="/admin" element={<Admin/>}/><Route path="*" element={<Empty title="A little off the beaten path." text="This page doesn’t exist." action="Back to Home"/>}/></Routes></div><Footer/></>}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><MotionConfig reducedMotion="user"><BrowserRouter><Provider><App/></Provider></BrowserRouter></MotionConfig></React.StrictMode>);
