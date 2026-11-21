import hashlib, json, secrets
from datetime import timedelta
from sqlalchemy import select, update
from fastapi import HTTPException
from .models import *
from .schemas import StoreInput

def settings(db):
    row = db.get(StoreSettings,1)
    return row.data if row else StoreInput().model_dump()

def effective_price(db, product):
    promotion = db.scalar(select(Promotion).where(Promotion.product_id==product.id, Promotion.active==True, Promotion.starts_at<=now(), Promotion.ends_at>now()))
    return (min(product.price,promotion.price), promotion) if promotion else (product.price,None)

def product_dict(db,p):
    price,deal = effective_price(db,p)
    return dict(id=p.id,name=p.name,description=p.description,sku=p.sku,category=db.get(Category,p.category_id).name,price=price,base_price=p.price,original_price=p.original_price,stock=p.stock,active=p.active,discount=round((p.original_price-price)*100/p.original_price),images=list(db.scalars(select(ProductImage.url).where(ProductImage.product_id==p.id))),featured=bool(db.scalar(select(Featured).where(Featured.product_id==p.id))),deal=dict(title=deal.title,ends_at=deal.ends_at.isoformat()+'Z') if deal else None)

class ManualComparisonProvider:
    """Provider boundary: authorized API/affiliate adapters can return this same schema."""
    def prices(self,db,product):
        result=[]
        for market in ['Amazon','Flipkart']:
            row=db.scalar(select(CompetitorPrice).where(CompetitorPrice.product_id==product.id,CompetitorPrice.marketplace==market))
            result.append(dict(marketplace=market,price=row.price if row and row.verified else None,url=row.url if row else '',source=row.source if row else 'unavailable',variant=row.variant if row else '',updated_at=row.updated_at.isoformat()+'Z' if row else None))
        return result

comparison_provider=ManualComparisonProvider()

def calculate(db,items,code,user_id,consume=False):
    ids=[item.product_id for item in items]
    if len(set(ids))!=len(ids): raise HTTPException(422,'Duplicate cart items are not allowed.')
    lines=[]
    # Stable locking order avoids opposite-cart deadlocks on PostgreSQL.
    for item in sorted(items,key=lambda x:x.product_id):
        query=select(Product).where(Product.id==item.product_id)
        if consume: query=query.with_for_update()
        p=db.scalar(query)
        if not p or not p.active: raise HTTPException(409,'A product is no longer available.')
        if p.stock<item.quantity: raise HTTPException(409,f'Only {p.stock} of {p.name} remain.')
        price,_=effective_price(db,p)
        lines.append(dict(product_id=p.id,name=p.name,price=price,quantity=item.quantity))
        if consume:
            changed=db.execute(update(Product).where(Product.id==p.id,Product.stock>=item.quantity,Product.active==True).values(stock=Product.stock-item.quantity)).rowcount
            if not changed: raise HTTPException(409,'Stock changed. Please review your cart.')
    subtotal=sum(x['price']*x['quantity'] for x in lines)
    discount=0
    cfg=settings(db)
    delivery=0 if subtotal>=cfg['free_delivery_minimum'] else cfg['delivery']
    if code:
        coupon=db.get(Coupon,code.strip().upper())
        if not coupon or coupon.customer_id!=user_id or coupon.used or coupon.revoked or coupon.expires<=now(): raise HTTPException(400,'This coupon is invalid, expired, or already used.')
        if subtotal<coupon.minimum: raise HTTPException(400,f'Coupon requires a minimum order of ₹{coupon.minimum/100:,.0f}.')
        if coupon.discount_type=='delivery': discount=delivery
        elif coupon.discount_type=='amount': discount=min(subtotal,coupon.amount,coupon.max_discount)
        else: discount=min(subtotal*coupon.percent//100,coupon.max_discount)
        if consume:
            changed=db.execute(update(Coupon).where(Coupon.code==coupon.code,Coupon.used==False,Coupon.revoked==False,Coupon.expires>now()).values(used=True)).rowcount
            if not changed: raise HTTPException(409,'Coupon was already redeemed.')
    cfg=settings(db)
    delivery=0 if subtotal>=cfg['free_delivery_minimum'] else cfg['delivery']
    return dict(items=lines,subtotal=subtotal,discount=discount,delivery=delivery,total=subtotal-discount+delivery)

def order_dict(db,o):
    return dict(id=o.id,address=o.address,subtotal=o.subtotal,discount=o.discount,delivery=o.delivery,total=o.total,status=o.status,coupon_code=o.coupon_code,created_at=o.created_at.isoformat()+'Z',items=[dict(product_id=i.product_id,name=i.name,price=i.price,quantity=i.quantity) for i in db.scalars(select(OrderItem).where(OrderItem.order_id==o.id))])

def checkout(db,data,user_id):
    digest=hashlib.sha256(json.dumps(data.model_dump(exclude={'idempotency_key'}),sort_keys=True).encode()).hexdigest()
    existing=db.scalar(select(Order).where(Order.idempotency_key==data.idempotency_key))
    if existing:
        if existing.customer_id!=user_id or existing.request_hash!=digest: raise HTTPException(409,'This checkout key was used for another request.')
        return order_dict(db,existing)
    if not settings(db)['cod']: raise HTTPException(400,'Cash on delivery is temporarily unavailable.')
    totals=calculate(db,data.items,data.coupon,user_id,consume=True)
    order=Order(id='TS-'+secrets.token_hex(6).upper(),customer_id=user_id,idempotency_key=data.idempotency_key,request_hash=digest,coupon_code=data.coupon.strip().upper() or None,address=data.address.model_dump(),**{k:v for k,v in totals.items() if k!='items'})
    db.add(order)
    db.flush()
    for line in totals['items']: db.add(OrderItem(order_id=order.id,**line))
    if order.coupon_code: db.add(CouponRedemption(coupon_code=order.coupon_code,order_id=order.id,discount=order.discount))
    db.commit()
    return order_dict(db,order)

def reward(db,attempt,percent):
    attempt.finished=True
    attempt.result=percent
    if not percent: return None
    cfg=settings(db)
    coupon=Coupon(code='TS-'+secrets.token_hex(5).upper(),customer_id=attempt.customer_id,percent=percent,max_discount=cfg['coupon_cap'],minimum=cfg['coupon_minimum'],expires=now()+timedelta(days=cfg['coupon_days']))
    db.add(coupon)
    db.flush()
    db.add(RewardClaim(attempt_id=attempt.id,coupon_code=coupon.code))
    return coupon.code
