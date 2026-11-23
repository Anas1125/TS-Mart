import uuid, io
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.models import *
from app.db import SessionLocal
from app.arcade import ArcadeConfig

ADDRESS=dict(name='Test Shopper',mobile='9876543210',email='shopper@example.com',address='12 Test Street',city='Mumbai',state='Maharashtra',pin='400001')
def payload(coupon='',quantity=1,pid=1):return dict(items=[dict(product_id=pid,quantity=quantity)],coupon=coupon,address=ADDRESS,idempotency_key=str(uuid.uuid4()))
def coupon(code='TEST',uid=1,kind='percent',expiry=1,minimum=0,cap=10000):
    with SessionLocal() as db:
        db.add(Coupon(code=code,customer_id=uid,percent=10,max_discount=cap,minimum=minimum,discount_type=kind,expires=now()+timedelta(days=expiry)));db.commit()
def winning_scratch():
    cfg=ArcadeConfig().model_dump()
    for i,r in enumerate(cfg['scratch_rewards']):r['weight']=100 if i==0 else 0
    with SessionLocal() as db:db.add(GameConfiguration(id=1,data=cfg));db.commit()
def parallel(path,bodies):
    def run(body):
        with TestClient(app) as c:
            c.cookies.set('ts_session','customer-token');return c.post(path,json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,bodies))

def test_featured_exact_six_and_comparison(client,admin_client):
    p=client.get('/api/products?featured=true').json();assert len(p)==6
    assert all(x['price']>0 and x['stock']>=0 for x in p)
    assert all(x['price'] is None for x in client.get('/api/products/1/comparison').json()['competitors'])
    assert admin_client.put('/api/admin/featured',json={'ids':[1,2,3]}).status_code==422
    assert admin_client.delete('/api/admin/products/1').status_code==400

def test_auth_protection_and_csrf(client):
    assert client.get('/api/admin/products').status_code==403
    with TestClient(app) as anon:
        assert anon.get('/api/orders').status_code==401
        assert anon.post('/api/arcade/scratch/start').status_code==401
    assert client.post('/api/arcade/scratch/start',headers={'Origin':'https://evil.example'}).status_code==403

def test_registration_login_and_logout():
    with TestClient(app) as c:
        credentials={'email':'new@example.com','password':'a-long-new-password','name':'New Shopper'}
        assert c.post('/api/auth/register',json=credentials).status_code==200
        assert c.get('/api/me').json()['name']=='New Shopper'
        c.post('/api/logout');assert c.get('/api/me').status_code==401
        assert c.post('/api/auth/login',json={**credentials,'password':'incorrect-password'}).status_code==401
        assert c.post('/api/auth/login',json=credentials).status_code==200
        assert 'httponly' in c.post('/api/auth/login',json=credentials).headers['set-cookie'].lower()

def test_remember_me_cookie_security_and_role_separation():
    with TestClient(app) as client:
        admin_credentials = {'email':'admin@example.com','password':'admin-test-password'}
        customer_credentials = {'email':'shopper@example.com','password':'test-password-strong'}

        # Existing customer credentials do not authenticate as administrator.
        response = client.post('/api/auth/admin', json=customer_credentials)
        assert response.status_code == 401

        # Without opt-in: session cookie only, no browser persistence.
        response = client.post('/api/auth/admin', json=admin_credentials)
        assert response.status_code == 200
        assert 'max-age=' not in response.headers['set-cookie'].lower()
        assert 'httponly' in response.headers['set-cookie'].lower()

        # Opt-in: bounded persistent session, shorter for administrators.
        response = client.post('/api/auth/admin', json={**admin_credentials, 'remember_me': True})
        assert response.status_code == 200
        assert 'max-age=604800' in response.headers['set-cookie'].lower()
        assert client.get('/api/me').json()['role'] == 'admin'

        response = client.post('/api/auth/login', json={**customer_credentials, 'remember_me': True})
        assert response.status_code == 200
        assert 'max-age=2592000' in response.headers['set-cookie'].lower()
        assert client.get('/api/me').json()['role'] == 'customer'


def test_server_pricing_and_successful_cod(client):
    data=payload();data['total']=1;data['items'][0]['price']=1
    r=client.post('/api/orders',json=data);assert r.status_code==200,r.text
    order=r.json();assert order['total']==329900;assert order['status']=='Pending'
    with SessionLocal() as db:assert db.get(Product,1).stock==23
    assert client.get('/api/orders').json()[0]['id']==order['id']

def test_coupon_cap_and_ownership(client):
    coupon();q=client.post('/api/quote',json={k:v for k,v in payload('TEST').items() if k in ['items','coupon']});assert q.json()['discount']==10000
    client.cookies.set('ts_session','other-token')
    assert client.post('/api/orders',json=payload('TEST')).status_code==400

def test_coupon_expiry_minimum_revocation(client):
    coupon('EXPIRED',expiry=-1);coupon('MIN',minimum=999999);coupon('REVOKED')
    with SessionLocal() as db:db.get(Coupon,'REVOKED').revoked=True;db.commit()
    for code in ['EXPIRED','MIN','REVOKED']:assert client.post('/api/orders',json=payload(code)).status_code==400
    with SessionLocal() as db:assert db.get(Product,1).stock==24

def test_free_delivery_waives_only_fee(client):
    coupon(kind='delivery');r=client.post('/api/orders',json=payload('TEST',pid=6));assert r.status_code==200,r.text
    o=r.json();assert o['delivery']==4900;assert o['discount']==4900;assert o['total']==149900

def test_duplicate_order_and_conflicting_key(client):
    coupon();data=payload('TEST');a=client.post('/api/orders',json=data);b=client.post('/api/orders',json=data)
    assert a.json()==b.json();data['items'][0]['quantity']=2
    assert client.post('/api/orders',json=data).status_code==409
    with SessionLocal() as db:assert db.get(Product,1).stock==23;assert db.scalar(select(func.count()).select_from(Order))==1

def test_concurrent_idempotency(client):
    data=payload();responses=parallel('/api/orders',[data,data]);assert all(x.status_code==200 for x in responses),[x.text for x in responses]
    assert responses[0].json()['id']==responses[1].json()['id']
    with SessionLocal() as db:assert db.get(Product,1).stock==23

def test_concurrent_coupon_redemption(client):
    coupon();responses=parallel('/api/orders',[payload('TEST'),payload('TEST')]);assert sum(x.status_code==200 for x in responses)==1,[x.text for x in responses]
    with SessionLocal() as db:
        assert db.get(Product,1).stock==23;assert db.scalar(select(func.count()).select_from(CouponRedemption))==1

def test_stock_atomic_no_negative(client):
    with SessionLocal() as db:db.get(Product,1).stock=1;db.commit()
    responses=parallel('/api/orders',[payload(),payload()]);assert sum(x.status_code==200 for x in responses)==1
    with SessionLocal() as db:assert db.get(Product,1).stock==0

def test_failed_order_rolls_back_stock_and_coupon(client):
    coupon();data=payload('TEST');data['items'].append({'product_id':2,'quantity':20})
    assert client.post('/api/orders',json=data).status_code==409
    with SessionLocal() as db:
        assert db.get(Product,1).stock==24;assert not db.get(Coupon,'TEST').used
        assert db.scalar(select(func.count()).select_from(Order))==0

def test_cancellation_restores_once_and_keeps_coupon_redeemed(client,admin_client):
    coupon();o=client.post('/api/orders',json=payload('TEST')).json()
    for _ in range(2):assert admin_client.put('/api/admin/orders/'+o['id'],json={'status':'Cancelled'}).status_code==200
    with SessionLocal() as db:assert db.get(Product,1).stock==24;assert db.get(Coupon,'TEST').used
    assert admin_client.put('/api/admin/orders/'+o['id'],json={'status':'Delivered'}).status_code==400

def test_private_orders(client):
    client.post('/api/orders',json=payload());client.cookies.set('ts_session','other-token')
    assert client.get('/api/orders').json()==[]

def test_expired_promotion_no_longer_applies(client):
    with SessionLocal() as db:p=db.scalar(select(Promotion).where(Promotion.product_id==1));p.ends_at=now()-timedelta(seconds=1);db.commit()
    p=client.get('/api/products/1').json();assert p['price']==349900;assert p['deal'] is None

def test_upload_validation(admin_client):
    assert admin_client.post('/api/admin/upload',files={'file':('bad.svg',b'<svg/>','image/svg+xml')}).status_code==400
    from PIL import Image
    b=io.BytesIO();Image.new('RGB',(20,20)).save(b,'PNG')
    r=admin_client.post('/api/admin/upload',files={'file':('test.png',b.getvalue(),'image/png')});assert r.status_code==200
    assert r.json()['url'].endswith('.webp')
    from app.main import UPLOADS
    (UPLOADS/r.json()['url'].split('/')[-1]).unlink()

def test_scratch_daily_persistent_secure_reward_and_claim(client):
    winning_scratch();a=client.post('/api/arcade/scratch/start').json();assert a['reward'] is None
    assert client.get('/api/arcade/scratch/current').json()['id']==a['id']
    assert client.post('/api/arcade/scratch/start').json()['id']==a['id']
    assert client.post('/api/arcade/scratch/claim',json={'attempt_id':a['id']}).status_code==400
    revealed=client.post('/api/arcade/scratch/reveal').json();assert revealed['reward']['percent']==5
    claims=[client.post('/api/arcade/scratch/claim',json={'attempt_id':a['id']}).json() for _ in range(2)]
    assert claims[0]==claims[1]
    assert client.post('/api/arcade/scratch/start').json()['id']==a['id']
    eligibility=client.get('/api/arcade/eligibility').json();assert eligibility['used']['scratch']==1;assert eligibility['timezone']=='Asia/Kolkata'
    assert '+05:30' in eligibility['next_eligible_at']
    assert client.get('/api/rewards').json()['coupons'][0]['status']=='available'

def test_simultaneous_scratch_start_and_claim(client):
    winning_scratch();responses=parallel('/api/arcade/scratch/start',[{},{}]);assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    a=responses[0].json();assert responses[1].json()['id']==a['id'];client.post('/api/arcade/scratch/reveal')
    claims=parallel('/api/arcade/scratch/claim',[{'attempt_id':a['id']}]*2);assert all(r.status_code==200 for r in claims),[r.text for r in claims]
    assert claims[0].json()==claims[1].json()
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Coupon))==1

def test_guess_snapshot_unique_rounds_refresh_and_validation(client):
    a=client.post('/api/arcade/guess/start').json();assert 'correct_price' not in a['question']
    assert client.get('/api/arcade/guess/current').json()==a
    with SessionLocal() as db:
        qs=list(db.scalars(select(GameQuestion).where(GameQuestion.attempt_id==a['id'])))
        assert len({q.product_id for q in qs})==5
        assert all(len(set(q.options))==4 for q in qs)
        answers={q.id:q.correct_price for q in qs}
        for p in db.scalars(select(Product)):p.price-=50000
        db.commit()
    for i in range(5):
        q=a['question'];body={'attempt_id':a['id'],'question_id':q['id'],'selected':answers[q['id']]}
        r=client.post('/api/arcade/guess/answer',json=body);assert r.status_code==200,r.text;assert r.json()['correct'];a=r.json()['attempt']
        assert client.post('/api/arcade/guess/answer',json=body).status_code==409
    assert a['score']==5 and a['finished'];assert a['reward']['percent']==15
    assert client.post('/api/arcade/guess/claim',json={'attempt_id':a['id']}).status_code==200

def test_guess_time_expiry_and_bad_option(client):
    a=client.post('/api/arcade/guess/start').json();q=a['question']
    assert client.post('/api/arcade/guess/answer',json={'attempt_id':a['id'],'question_id':q['id'],'selected':123}).status_code==422
    with SessionLocal() as db:
        row=db.get(GameQuestion,q['id']);row.deadline=now()-timedelta(seconds=1);correct=row.correct_price;db.commit()
    r=client.post('/api/arcade/guess/answer',json={'attempt_id':a['id'],'question_id':q['id'],'selected':correct}).json()
    assert not r['correct'];assert r['attempt']['score']==0

def test_guess_insufficient_products_and_config_protection(client,admin_client):
    with SessionLocal() as db:db.get(Product,1).stock=0;db.get(Product,2).stock=0;db.commit()
    assert not client.get('/api/arcade/games').json()['guess_available']
    assert client.post('/api/arcade/guess/start').status_code==400
    assert client.put('/api/admin/arcade',json=ArcadeConfig().model_dump()).status_code==403
    cfg=ArcadeConfig().model_dump();cfg['scratch_rewards'][0]['weight']=1
    assert admin_client.put('/api/admin/arcade',json=cfg).status_code==422

def test_foreign_claim_blocked(client):
    winning_scratch();a=client.post('/api/arcade/scratch/start').json();client.post('/api/arcade/scratch/reveal')
    client.cookies.set('ts_session','other-token');assert client.post('/api/arcade/scratch/claim',json={'attempt_id':a['id']}).status_code==400

def test_coupon_saved_with_order_and_analytics(client,admin_client):
    winning_scratch();a=client.post('/api/arcade/scratch/start').json();client.post('/api/arcade/scratch/reveal')
    code=client.post('/api/arcade/scratch/claim',json={'attempt_id':a['id']}).json()['coupon']
    o=client.post('/api/orders',json=payload(code)).json();assert o['coupon_code']==code;assert o['discount']==5000
    rewards=client.get('/api/rewards').json();assert rewards['coupons'][0]['status']=='redeemed'
    metrics=admin_client.get('/api/admin/arcade').json()['analytics'];assert metrics['coupons_redeemed']==1 and metrics['discount_used']==5000

def test_admin_crud_feature_selection_and_verified_comparison(client,admin_client):
    data=dict(name='Actual Test Product',category='Accessories',description='A test product description.',sku='NEW-SKU',price=50000,original_price=100000,stock=10,images=['/images/headphones.svg'],active=True)
    created=admin_client.post('/api/admin/products',json=data);assert created.status_code==200,created.text
    pid=created.json()['id'];assert len(client.get('/api/products').json())==7
    assert len(client.get('/api/products?featured=true').json())==6
    data['stock']=8;assert admin_client.put(f'/api/admin/products/{pid}',json=data).json()['stock']==8
    assert admin_client.put('/api/admin/featured',json={'ids':[2,3,4,5,6,pid]}).status_code==200
    comp=dict(marketplace='Amazon',price=60000,url='https://www.amazon.in/dp/EXAMPLE',source='manual',variant='Exact test model',verified=False)
    assert admin_client.put(f'/api/admin/products/{pid}/comparison',json=comp).status_code==422
    comp['verified']=True;assert admin_client.put(f'/api/admin/products/{pid}/comparison',json=comp).status_code==200
    result=client.get(f'/api/products/{pid}/comparison').json()['competitors'][0]
    assert result['price']==60000 and result['source']=='manual' and result['updated_at']
    assert admin_client.put('/api/admin/featured',json={'ids':[1,2,3,4,5,6]}).status_code==200
    assert admin_client.delete(f'/api/admin/products/{pid}').status_code==200
    assert client.get(f'/api/products/{pid}').status_code==404

def test_four_correct_reward_and_no_score_injection(client):
    a=client.post('/api/arcade/guess/start').json()
    with SessionLocal() as db:prices={q.id:q.correct_price for q in db.scalars(select(GameQuestion).where(GameQuestion.attempt_id==a['id']))}
    for i in range(5):
        q=a['question'];selected=prices[q['id']] if i<4 else next(v for v in q['options'] if v!=prices[q['id']])
        r=client.post('/api/arcade/guess/answer',json={'attempt_id':a['id'],'question_id':q['id'],'selected':selected,'score':500})
        assert r.status_code==200,r.text;a=r.json()['attempt']
    assert a['score']==4 and a['reward']['percent']==10

def test_simultaneous_guess_answer_records_once(client):
    a=client.post('/api/arcade/guess/start').json();q=a['question'];body={'attempt_id':a['id'],'question_id':q['id'],'selected':q['options'][0]}
    results=parallel('/api/arcade/guess/answer',[body,body]);assert sorted(r.status_code for r in results)==[200,409]
    assert client.get('/api/arcade/guess/current').json()['round']==2
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(GameAnswer))==1

def test_config_daily_limit_and_immutable_existing_rules(client,admin_client):
    winning_scratch();a=client.post('/api/arcade/scratch/start').json()
    cfg=ArcadeConfig().model_dump();cfg['scratch_daily_limit']=2;cfg['scratch_rewards'][0]['percent']=7
    assert admin_client.put('/api/admin/arcade',json=cfg).status_code==200
    revealed=client.post('/api/arcade/scratch/reveal').json();assert revealed['reward']['percent']==5
    client.post('/api/arcade/scratch/claim',json={'attempt_id':a['id']})
    second=client.post('/api/arcade/scratch/start').json();assert second['id']!=a['id'];assert second['slot']==2
    assert client.post('/api/arcade/scratch/start').json()['id']==second['id']
