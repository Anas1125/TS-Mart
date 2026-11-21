import argparse
from datetime import timedelta
from sqlalchemy import select
from .db import Base,engine,SessionLocal,config
from .models import *
from .schemas import StoreInput
from .security import hash_password

SAMPLES=[('Airwave Pro Headphones','Audio','Immersive sound. Uninterrupted focus. Wireless over-ear headphones with soft memory-foam cushions and up to 40 hours of listening.',599900,349900,24,'headphones'),('Pulse Smartwatch','Wearables','Your everyday, elevated. A vivid AMOLED display, activity tracking, and a comfortable midnight silicone strap.',499900,279900,18,'watch'),('Nova Buds Pro','Audio','Small size. Full-spectrum sound. Pocket-ready wireless earbuds with a compact charging case.',299900,179900,32,'earbuds'),('Orbit Portable Speaker','Audio','Take the good energy with you. Rich portable sound in a beautifully textured, splash-resistant enclosure.',349900,229900,15,'speaker'),('Studio Mechanical Keyboard','Accessories','Make every keystroke count. A compact wireless keyboard with tactile switches and warm backlighting.',549900,399900,12,'keyboard'),('Volt 20K Power Bank','Accessories','Stay powered, wherever life goes. A compact 20,000 mAh power bank with USB-C fast charging.',249900,149900,30,'powerbank')]
def seed():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(Product.id).limit(1)):
            for i,(name,category,description,original,price,stock,art) in enumerate(SAMPLES):
                c=db.scalar(select(Category).where(Category.name==category))
                if not c: c=Category(name=category);db.add(c);db.flush()
                p=Product(name=name,category_id=c.id,description=description,sku='DEMO-'+art.upper(),original_price=original,price=price,stock=stock)
                db.add(p);db.flush();db.add(ProductImage(product_id=p.id,url=f'/images/{art}.svg'));db.add(Featured(position=i,product_id=p.id))
                if i in [0,2]: db.add(Promotion(product_id=p.id,title='Launch offer',price=price-20000,starts_at=now(),ends_at=now()+timedelta(days=3)))
        if not db.get(StoreSettings,1):db.add(StoreSettings(id=1,data=StoreInput().model_dump()))
        db.commit()
    print('Sample catalog ready. Six demo products; no invented competitor prices.')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--admin',action='store_true');args=parser.parse_args();seed()
    if args.admin:
        if not config.admin_email or len(config.admin_password)<12: raise SystemExit('Set ADMIN_EMAIL and ADMIN_PASSWORD (at least 12 characters) in backend/.env.')
        with SessionLocal() as db:
            existing=db.scalar(select(Admin).where(Admin.email==config.admin_email.lower()))
            if existing: raise SystemExit('Administrator already exists. No password changed.')
            db.add(Admin(email=config.admin_email.lower(),password_hash=hash_password(config.admin_password)));db.commit()
        print('Administrator created.')
