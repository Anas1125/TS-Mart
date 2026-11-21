import hashlib, secrets, io
from datetime import timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, delete, update, func
from sqlalchemy.exc import IntegrityError
from .db import Base, engine, get_db, config
from .models import *
from .schemas import *
from .security import admin, customer, identity, hash_password, verify_password, DUMMY_PASSWORD, rate_limit
from .services import *

UPLOADS=Path(__file__).resolve().parent.parent/'uploads'
UPLOADS.mkdir(exist_ok=True)
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield
app=FastAPI(title='TS Mart API',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=config.allowed_origins,allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type'])
app.mount('/uploads',StaticFiles(directory=UPLOADS),name='uploads')

@app.middleware('http')
async def protect(request,call_next):
    if request.method in {'POST','PUT','DELETE','PATCH'}:
        origin=request.headers.get('origin')
        if origin and origin not in config.allowed_origins: return JSONResponse({'detail':'Untrusted request origin.'},403)
        if request.headers.get('sec-fetch-site')=='cross-site': return JSONResponse({'detail':'Cross-site writes are not allowed.'},403)
        try: length=int(request.headers.get('content-length','0') or '0')
        except ValueError: return JSONResponse({'detail':'Invalid content length.'},400)
        if length>6*1024*1024: return JSONResponse({'detail':'Request too large.'},413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(IntegrityError)
async def conflict(request,exc):
    return JSONResponse({'detail':'This action conflicts with an existing record. Refresh and try again.'},409)

@app.get('/api/health')
def health(): return {'status':'ok'}
@app.get('/api/settings')
def get_settings(db=Depends(get_db)): return settings(db)
@app.get('/api/products')
def products(featured: bool=False,q: str='',category: str='',deals: bool=False,db=Depends(get_db)):
    query=select(Product).where(Product.active==True)
    if featured: query=query.join(Featured,Featured.product_id==Product.id).order_by(Featured.position)
    else: query=query.order_by(Product.id)
    if q: query=query.where(Product.name.ilike('%'+q[:100]+'%'))
    if category: query=query.join(Category).where(Category.name==category)
    result=[product_dict(db,p) for p in db.scalars(query)]
    return [p for p in result if p['deal']] if deals else result
@app.get('/api/categories')
def categories(db=Depends(get_db)): return list(db.scalars(select(Category.name).order_by(Category.name)))
@app.get('/api/products/{pid}')
def detail(pid:int,db=Depends(get_db)):
    p=db.get(Product,pid)
    if not p or not p.active: raise HTTPException(404,'Product not found.')
    return product_dict(db,p)
@app.get('/api/products/{pid}/comparison')
def comparison(pid:int,db=Depends(get_db)):
    p=db.get(Product,pid)
    if not p or not p.active: raise HTTPException(404,'Product not found.')
    return {'ts_price':effective_price(db,p)[0],'competitors':comparison_provider.prices(db,p)}

@app.post('/api/auth/{action}')
def authenticate(action:str,data:Credentials,request:Request,response:Response,db=Depends(get_db)):
    if action not in ['register','login','admin']: raise HTTPException(404)
    rate_limit(request,'auth',15)
    cls=Admin if action=='admin' else Customer
    user=db.scalar(select(cls).where(cls.email==data.email))
    if action=='register':
        rate_limit(request,'register',4,86400)
        if user: raise HTTPException(409,'An account with this email already exists.')
        user=Customer(email=data.email,name=data.name,password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
    else:
        valid=verify_password(data.password,user.password_hash if user else DUMMY_PASSWORD)
        if not user or not valid: raise HTTPException(401,'Email or password is incorrect.')
    old=request.cookies.get('ts_session','')
    db.execute(delete(Session).where(Session.token_hash==hashlib.sha256(old.encode()).hexdigest()))
    token=secrets.token_urlsafe(32)
    db.add(Session(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=user.id,role='admin' if action=='admin' else 'customer',expires=now()+timedelta(days=7)))
    db.commit()
    response.set_cookie('ts_session',token,httponly=True,secure=config.cookie_secure,samesite='lax',max_age=604800,path='/')
    return {'name':getattr(user,'name','Administrator'),'role':'admin' if action=='admin' else 'customer','email':user.email}
@app.get('/api/me')
def me(user=Depends(identity),db=Depends(get_db)):
    person=db.get(Admin if user.role=='admin' else Customer,user.user_id)
    return {'name':getattr(person,'name','Administrator'),'role':user.role,'email':person.email}
@app.post('/api/logout')
def logout(request:Request,response:Response,db=Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash==hashlib.sha256(request.cookies.get('ts_session','').encode()).hexdigest()))
    db.commit(); response.delete_cookie('ts_session',path='/')
    return {'ok':True}
@app.post('/api/quote')
def quote(data:Quote,uid=Depends(customer),db=Depends(get_db)): return calculate(db,data.items,data.coupon,uid)
@app.post('/api/orders')
def create_order(data:Checkout,request:Request,uid=Depends(customer),db=Depends(get_db)):
    rate_limit(request,'checkout',30)
    try: return checkout(db,data,uid)
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Order).where(Order.idempotency_key==data.idempotency_key))
        if existing: return checkout(db,data,uid)
        raise
@app.get('/api/orders')
def orders(uid=Depends(customer),db=Depends(get_db)):
    return [order_dict(db,o) for o in db.scalars(select(Order).where(Order.customer_id==uid).order_by(Order.created_at.desc()))]
@app.get('/api/coupons')
def coupons(uid=Depends(customer),db=Depends(get_db)):
    return [dict(code=c.code,percent=c.percent,max_discount=c.max_discount,minimum=c.minimum,expires=c.expires.isoformat()+'Z') for c in db.scalars(select(Coupon).where(Coupon.customer_id==uid,Coupon.used==False,Coupon.expires>now()))]

QUESTIONS=[{'question':'Which payment method lets you pay when your order arrives?','options':['Cash on Delivery','Gift wrapping','Wishlisting'],'answer':0},{'question':'A ₹1,000 item has a 10% discount. What is its new price?','options':['₹990','₹900','₹100'],'answer':1},{'question':'What should you match when comparing product prices?','options':['Only the colour of the website','Only the brand','The exact model and variant'],'answer':2},{'question':'Which detail helps deliver a parcel to the correct area?','options':['Your PIN code','Your favourite colour','Your browser'],'answer':0},{'question':'Where should you check a coupon’s expiry date?','options':['Guess it','The coupon terms','A different store'],'answer':1}]
class QuizAnswers(BaseModel):
    answers:list[int]=Field(min_length=5,max_length=5)
@app.get('/api/games')
def game_info(uid=Depends(customer),db=Depends(get_db)):
    attempts=db.scalars(select(GameAttempt).where(GameAttempt.customer_id==uid,GameAttempt.day==now().date().isoformat()))
    return {'attempts':{a.game:{'finished':a.finished,'result':a.result} for a in attempts},'questions':[{k:v for k,v in q.items() if k!='answer'} for q in QUESTIONS],'rules':settings(db)}
@app.post('/api/games/{game}')
def play(game:str,request:Request,uid=Depends(customer),db=Depends(get_db)):
    if game not in ['spin','quiz']: raise HTTPException(404)
    rate_limit(request,'games',30,86400)
    a=GameAttempt(customer_id=uid,game=game,day=now().date().isoformat())
    db.add(a)
    try: db.flush()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'You have already played this game today. Come back after 00:00 UTC.')
    if game=='quiz': db.commit(); return {'started':True}
    weights=settings(db)['probabilities']; pick=secrets.randbelow(100); cumulative=0; percent=0
    for value,weight in zip([0,5,10,15],weights):
        cumulative+=weight
        if pick<cumulative: percent=value; break
    code=reward(db,a,percent)
    db.commit()
    return {'percent':percent,'coupon':code}
@app.post('/api/games/quiz/submit')
def quiz(data:QuizAnswers,uid=Depends(customer),db=Depends(get_db)):
    a=db.scalar(select(GameAttempt).where(GameAttempt.customer_id==uid,GameAttempt.game=='quiz',GameAttempt.day==now().date().isoformat()).with_for_update())
    if not a or a.finished: raise HTTPException(409,'Start today’s quiz before submitting. Results can only be submitted once.')
    changed=db.execute(update(GameAttempt).where(GameAttempt.id==a.id,GameAttempt.finished==False).values(finished=True)).rowcount
    if not changed: raise HTTPException(409,'Quiz already submitted.')
    score=sum(answer==q['answer'] for answer,q in zip(data.answers,QUESTIONS))
    code=reward(db,a,10 if score>=settings(db)['quiz_required'] else 0)
    db.commit()
    return {'score':score,'percent':a.result,'coupon':code}

@app.get('/api/admin/products',dependencies=[Depends(admin)])
def admin_products(db=Depends(get_db)): return [product_dict(db,p) for p in db.scalars(select(Product).order_by(Product.id))]
def save_product(db,data,p=None):
    cat=db.scalar(select(Category).where(Category.name==data.category))
    if not cat: cat=Category(name=data.category); db.add(cat); db.flush()
    if p and not data.active and db.scalar(select(Featured).where(Featured.product_id==p.id)): raise HTTPException(400,'Replace this product in the featured selection before disabling it.')
    values=data.model_dump(exclude={'category','images'})
    if p:
        for k,v in values.items(): setattr(p,k,v)
        db.execute(delete(ProductImage).where(ProductImage.product_id==p.id))
    else: p=Product(**values,category_id=cat.id); db.add(p)
    p.category_id=cat.id
    db.flush()
    for url in data.images: db.add(ProductImage(product_id=p.id,url=url))
    db.commit()
    return product_dict(db,p)
@app.post('/api/admin/products',dependencies=[Depends(admin)])
def add_product(data:ProductInput,db=Depends(get_db)): return save_product(db,data)
@app.put('/api/admin/products/{pid}',dependencies=[Depends(admin)])
def edit_product(pid:int,data:ProductInput,db=Depends(get_db)):
    p=db.get(Product,pid)
    if not p: raise HTTPException(404)
    return save_product(db,data,p)
@app.delete('/api/admin/products/{pid}',dependencies=[Depends(admin)])
def delete_product(pid:int,db=Depends(get_db)):
    p=db.get(Product,pid)
    if not p: raise HTTPException(404)
    if db.scalar(select(Featured).where(Featured.product_id==pid)): raise HTTPException(400,'Replace this product in the featured selection before deleting it.')
    if db.scalar(select(OrderItem).where(OrderItem.product_id==pid)) or db.scalar(select(GameQuestion).where(GameQuestion.product_id==pid)):
        p.active=False # Preserve order references; ordered products are archived.
    else:
        for cls in [ProductImage,CompetitorPrice,Promotion]: db.execute(delete(cls).where(cls.product_id==pid))
        db.delete(p)
    db.commit(); return {'ok':True}
class FeaturedInput(BaseModel):
    ids:list[int]=Field(min_length=6,max_length=6)
@app.put('/api/admin/featured',dependencies=[Depends(admin)])
def featured(data:FeaturedInput,db=Depends(get_db)):
    if len(set(data.ids))!=6 or db.scalar(select(func.count()).select_from(Product).where(Product.id.in_(data.ids),Product.active==True))!=6: raise HTTPException(400,'Choose exactly six different active products.')
    db.execute(delete(Featured)); db.flush()
    for pos,pid in enumerate(data.ids): db.add(Featured(position=pos,product_id=pid))
    db.commit(); return {'ok':True}
@app.put('/api/admin/products/{pid}/comparison',dependencies=[Depends(admin)])
def set_comparison(pid:int,data:ComparisonInput,db=Depends(get_db)):
    if not db.get(Product,pid): raise HTTPException(404)
    row=db.scalar(select(CompetitorPrice).where(CompetitorPrice.product_id==pid,CompetitorPrice.marketplace==data.marketplace))
    if not row: row=CompetitorPrice(product_id=pid); db.add(row)
    for k,v in data.model_dump().items(): setattr(row,k,v)
    row.updated_at=now(); db.commit(); return {'ok':True}
@app.put('/api/admin/products/{pid}/promotion',dependencies=[Depends(admin)])
def promotion(pid:int,data:PromotionInput,db=Depends(get_db)):
    p=db.get(Product,pid)
    if not p: raise HTTPException(404)
    if data.price>p.price: raise HTTPException(400,'Deal price must not exceed the selling price.')
    row=db.scalar(select(Promotion).where(Promotion.product_id==pid))
    if not row: row=Promotion(product_id=pid); db.add(row)
    for k,v in data.model_dump().items():
        if isinstance(v,datetime) and v.tzinfo: v=v.astimezone(timezone.utc).replace(tzinfo=None)
        setattr(row,k,v)
    db.commit(); return {'ok':True}
@app.get('/api/admin/products/{pid}/promotion',dependencies=[Depends(admin)])
def get_promotion(pid:int,db=Depends(get_db)):
    p=db.scalar(select(Promotion).where(Promotion.product_id==pid))
    return dict(title=p.title,price=p.price,starts_at=p.starts_at.isoformat()+'Z',ends_at=p.ends_at.isoformat()+'Z',active=p.active) if p else None
@app.post('/api/admin/upload',dependencies=[Depends(admin)])
async def upload(file:UploadFile=File(...)):
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: raise HTTPException(413,'Images must be smaller than 5 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ['JPEG','PNG','WEBP'] or im.width*im.height>20000000: raise ValueError()
            im.load(); im.thumbnail((1600,1600))
            output=im.convert('RGB'); name=secrets.token_hex(16)+'.webp'
            output.save(UPLOADS/name,'WEBP',quality=85)
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError): raise HTTPException(400,'Upload a valid JPEG, PNG, or WebP image under 20 megapixels.')
    return {'url':'/uploads/'+name}
@app.get('/api/admin/orders',dependencies=[Depends(admin)])
def all_orders(db=Depends(get_db)): return [order_dict(db,o) for o in db.scalars(select(Order).order_by(Order.created_at.desc()))]
class StatusInput(BaseModel):
    status:str=Field(pattern='^(Pending|Confirmed|Packed|Shipped|Delivered|Cancelled)$')
@app.put('/api/admin/orders/{oid}',dependencies=[Depends(admin)])
def order_status(oid:str,data:StatusInput,db=Depends(get_db)):
    o=db.scalar(select(Order).where(Order.id==oid).with_for_update())
    if not o: raise HTTPException(404)
    transitions={'Pending':['Confirmed','Cancelled'],'Confirmed':['Packed','Cancelled'],'Packed':['Shipped','Cancelled'],'Shipped':['Delivered'],'Delivered':[],'Cancelled':[]}
    if data.status==o.status: return order_dict(db,o)
    if data.status not in transitions[o.status]: raise HTTPException(400,'Invalid order status transition.')
    changed=db.execute(update(Order).where(Order.id==oid,Order.status==o.status).values(status=data.status)).rowcount
    if not changed: raise HTTPException(409,'Order status changed; refresh and try again.')
    if data.status=='Cancelled':
        for i in db.scalars(select(OrderItem).where(OrderItem.order_id==oid)):
            db.execute(update(Product).where(Product.id==i.product_id).values(stock=Product.stock+i.quantity))
    db.commit(); db.refresh(o); return order_dict(db,o)
@app.get('/api/admin/stats',dependencies=[Depends(admin)])
def stats(db=Depends(get_db)):
    return {'total_orders':db.scalar(select(func.count()).select_from(Order)),'pending_orders':db.scalar(select(func.count()).select_from(Order).where(Order.status=='Pending')),'delivered_orders':db.scalar(select(func.count()).select_from(Order).where(Order.status=='Delivered')),'revenue':db.scalar(select(func.coalesce(func.sum(Order.total),0)).where(Order.status=='Delivered')),'low_stock':db.scalar(select(func.count()).select_from(Product).where(Product.active==True,Product.stock<=settings(db)['low_stock']))}
@app.put('/api/admin/settings',dependencies=[Depends(admin)])
def save_settings(data:StoreInput,db=Depends(get_db)):
    row=db.get(StoreSettings,1)
    if not row: row=StoreSettings(id=1); db.add(row)
    row.data=data.model_dump(); db.commit(); return row.data

from .arcade import router as arcade_router
app.include_router(arcade_router)
