"""Persistent arcade state machine sharing store identity, catalog and checkout coupons."""
import secrets
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from .db import get_db
from .models import *
from .security import customer, admin, rate_limit
from .services import effective_price

router=APIRouter(prefix='/api')
class RewardRule(BaseModel):
    label:str=Field(min_length=2,max_length=80)
    type:str=Field(pattern='^(percent|delivery|amount|none)$')
    percent:int=Field(default=0,ge=0,le=50)
    cap:int=Field(default=5000,ge=0,le=1000000)
    amount:int=Field(default=0,ge=0,le=1000000)
    minimum:int=Field(default=0,ge=0,le=10000000)
    weight:int=Field(default=0,ge=0,le=100)
class ArcadeConfig(BaseModel):
    timezone:str='Asia/Kolkata'
    scratch_enabled:bool=True
    guess_enabled:bool=True
    scratch_daily_limit:int=Field(default=1,ge=1,le=5)
    guess_daily_limit:int=Field(default=1,ge=1,le=5)
    expiry_hours:int=Field(default=24,ge=1,le=720)
    question_seconds:int=Field(default=30,ge=10,le=300)
    qualifying_score:int=Field(default=4,ge=1,le=5)
    scratch_rewards:list[RewardRule]=Field(default_factory=lambda:[RewardRule(label='5% off',type='percent',percent=5,cap=5000,weight=35),RewardRule(label='10% off',type='percent',percent=10,cap=10000,weight=25),RewardRule(label='15% off',type='percent',percent=15,cap=15000,weight=10),RewardRule(label='Free delivery',type='delivery',weight=10),RewardRule(label='Better luck next time',type='none',weight=20)],min_length=2,max_length=10)
    guess_reward:RewardRule=Field(default_factory=lambda:RewardRule(label='10% off',type='percent',percent=10,cap=10000))
    perfect_reward:RewardRule=Field(default_factory=lambda:RewardRule(label='15% off',type='percent',percent=15,cap=15000))
    @model_validator(mode='after')
    def validate_rules(self):
        try: ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError: raise ValueError('Use a valid IANA timezone')
        if sum(x.weight for x in self.scratch_rewards)!=100: raise ValueError('Scratch probabilities must sum to 100')
        return self

def config(db):
    row=db.get(GameConfiguration,1)
    return row.data if row else ArcadeConfig().model_dump()

def day_and_next(cfg):
    local=datetime.now(ZoneInfo(cfg['timezone']))
    next_day=datetime.combine(local.date()+timedelta(days=1),time(),tzinfo=ZoneInfo(cfg['timezone']))
    return local.date().isoformat(),next_day.isoformat()

def current(db,uid,game):
    day,_=day_and_next(config(db))
    return db.scalar(select(ArcadeAttempt).where(ArcadeAttempt.customer_id==uid,ArcadeAttempt.game==game,ArcadeAttempt.business_date==day).order_by(ArcadeAttempt.slot.desc()))

def questions(db,a): return list(db.scalars(select(GameQuestion).where(GameQuestion.attempt_id==a.id).order_by(GameQuestion.position)))
def view(db,a):
    if not a: return None
    claimed=db.get(GameReward,a.id)
    result=dict(id=a.id,game=a.game,revealed=a.revealed,finished=a.finished,score=a.score,reward=a.reward if a.revealed or a.finished else None,coupon=claimed.coupon_code if claimed else None,slot=a.slot)
    if a.game=='guess':
        qs=questions(db,a)
        answers=[db.get(GameAnswer,q.id) for q in qs]
        idx=next((i for i,x in enumerate(answers) if not x),5)
        result['round']=idx+1
        result['history']=[dict(correct=x.correct,selected=x.selected,correct_price=q.correct_price) for q,x in zip(qs,answers) if x]
        if idx<5:
            q=qs[idx]
            result['question']=dict(id=q.id,name=q.name,image=q.image,options=q.options,deadline=q.deadline.isoformat()+'Z')
        else: result['question']=None
    return result

@router.get('/arcade/games')
def games(db=Depends(get_db)):
    cfg=config(db)
    eligible=db.scalar(select(func.count()).select_from(Product).where(Product.active==True,Product.stock>0))
    return {**cfg,'guess_available':eligible>=5,'unavailable_reason':None if eligible>=5 else 'Guess the Price needs at least five different in-stock products. Please check back soon.'}
@router.get('/arcade/eligibility')
def eligibility(uid=Depends(customer),db=Depends(get_db)):
    cfg=config(db); day,next_time=day_and_next(cfg)
    counts={game:db.scalar(select(func.count()).select_from(ArcadeAttempt).where(ArcadeAttempt.customer_id==uid,ArcadeAttempt.game==game,ArcadeAttempt.business_date==day)) for game in ['scratch','guess']}
    return {'business_date':day,'timezone':cfg['timezone'],'next_eligible_at':next_time,'used':counts,'limits':{g:cfg[g+'_daily_limit'] for g in counts}}
@router.get('/arcade/{game}/current')
def get_current(game:str,uid=Depends(customer),db=Depends(get_db)):
    if game not in ['scratch','guess']: raise HTTPException(404)
    return view(db,current(db,uid,game))
@router.post('/arcade/{game}/start')
def start(game:str,request:Request,uid=Depends(customer),db=Depends(get_db)):
    if game not in ['scratch','guess']: raise HTTPException(404)
    rate_limit(request,'arcade-start',40,86400)
    cfg=config(db)
    if not cfg[game+'_enabled']: raise HTTPException(400,'This game is currently paused.')
    existing=current(db,uid,game)
    claimed=db.get(GameReward,existing.id) if existing else None
    if existing and (not existing.finished or (existing.reward.get('type')!='none' and not claimed) or existing.slot>=cfg[game+'_daily_limit']): return view(db,existing)
    day,_=day_and_next(cfg)
    a=ArcadeAttempt(id=secrets.token_hex(16),customer_id=uid,game=game,business_date=day,slot=existing.slot+1 if existing else 1,reward={},rules=cfg)
    if game=='scratch':
        pick=secrets.randbelow(100); total=0
        for rule in cfg['scratch_rewards']:
            total+=rule['weight']
            if pick<total: a.reward=rule; break
    else:
        products=list(db.scalars(select(Product).where(Product.active==True,Product.stock>0)))
        if len(products)<5: raise HTTPException(400,'At least five in-stock products are needed to play.')
        products=secrets.SystemRandom().sample(products,5)
    db.add(a)
    try:
        db.flush()
        if game=='guess':
            for i,p in enumerate(products):
                price,_=effective_price(db,p)
                options={price}
                for delta in secrets.SystemRandom().sample([-50000,-30000,-20000,-10000,10000,20000,30000,50000],8):
                    if price+delta>0: options.add(price+delta)
                    if len(options)==4: break
                choices=list(options); secrets.SystemRandom().shuffle(choices)
                db.add(GameQuestion(attempt_id=a.id,position=i,product_id=p.id,name=p.name,image=db.scalar(select(ProductImage.url).where(ProductImage.product_id==p.id)) or '',correct_price=price,options=choices,deadline=now()+timedelta(seconds=cfg['question_seconds']) if i==0 else None))
        db.commit()
    except IntegrityError:
        db.rollback()
        return view(db,current(db,uid,game))
    return view(db,a)
@router.post('/arcade/scratch/reveal')
def reveal(uid=Depends(customer),db=Depends(get_db)):
    a=current(db,uid,'scratch')
    if not a: raise HTTPException(404,'Start a scratch card first.')
    a.revealed=True; a.finished=True; db.commit()
    return view(db,a)
class AnswerInput(BaseModel):
    attempt_id:str=Field(min_length=32,max_length=32)
    question_id:int
    selected:int=Field(ge=-1)
@router.post('/arcade/guess/answer')
def answer(data:AnswerInput,uid=Depends(customer),db=Depends(get_db)):
    a=db.scalar(select(ArcadeAttempt).where(ArcadeAttempt.id==data.attempt_id,ArcadeAttempt.customer_id==uid,ArcadeAttempt.game=='guess').with_for_update())
    if not a: raise HTTPException(404)
    qs=questions(db,a)
    q=next((q for q in qs if not db.get(GameAnswer,q.id)),None)
    if not q or q.id!=data.question_id: raise HTTPException(409,'This round was already answered. Refresh to restore progress.')
    if data.selected!=-1 and data.selected not in q.options: raise HTTPException(422,'Select one of the offered prices.')
    correct=data.selected==q.correct_price and now()<=q.deadline
    db.add(GameAnswer(question_id=q.id,selected=data.selected,correct=correct))
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409,'This answer was already submitted.')
    a.score=db.scalar(select(func.count()).select_from(GameAnswer).join(GameQuestion).where(GameQuestion.attempt_id==a.id,GameAnswer.correct==True))
    if q.position<4: qs[q.position+1].deadline=now()+timedelta(seconds=a.rules['question_seconds'])
    else:
        a.finished=True; a.revealed=True
        a.reward=a.rules['perfect_reward'] if a.score==5 else a.rules['guess_reward'] if a.score>=a.rules['qualifying_score'] else {'type':'none','label':'Better luck next time'}
    db.commit()
    return {'correct':correct,'correct_price':q.correct_price,'attempt':view(db,a)}
class ClaimInput(BaseModel):
    attempt_id:str=Field(min_length=32,max_length=32)
@router.post('/arcade/{game}/claim')
def claim(game:str,data:ClaimInput,uid=Depends(customer),db=Depends(get_db)):
    a=db.scalar(select(ArcadeAttempt).where(ArcadeAttempt.id==data.attempt_id,ArcadeAttempt.customer_id==uid,ArcadeAttempt.game==game).with_for_update())
    if not a or not a.finished: raise HTTPException(400,'Finish and reveal your game first.')
    old=db.get(GameReward,a.id)
    if old: return {'coupon':old.coupon_code}
    r=a.reward
    if r['type']=='none': raise HTTPException(400,'This attempt did not earn a reward.')
    c=Coupon(code='TS-'+secrets.token_hex(6).upper(),customer_id=uid,source_game=game,discount_type=r['type'],percent=r.get('percent',0),amount=r.get('amount',0),max_discount=r.get('cap',0),minimum=r.get('minimum',0),expires=now()+timedelta(hours=a.rules['expiry_hours']))
    db.add(c); db.flush(); db.add(GameReward(attempt_id=a.id,coupon_code=c.code))
    try: db.commit()
    except IntegrityError:
        db.rollback(); return {'coupon':db.get(GameReward,a.id).coupon_code}
    return {'coupon':c.code}
@router.get('/rewards')
def rewards(uid=Depends(customer),db=Depends(get_db)):
    coupons=[dict(code=c.code,source_game=c.source_game,discount_type=c.discount_type,percent=c.percent,amount=c.amount,max_discount=c.max_discount,minimum=c.minimum,expires=c.expires.isoformat()+'Z',redemption_limit=c.redemption_limit,status='revoked' if c.revoked else 'redeemed' if c.used else 'expired' if c.expires<=now() else 'available') for c in db.scalars(select(Coupon).where(Coupon.customer_id==uid).order_by(Coupon.expires.desc()))]
    unclaimed=[view(db,a) for a in db.scalars(select(ArcadeAttempt).where(ArcadeAttempt.customer_id==uid,ArcadeAttempt.finished==True)) if a.reward.get('type')!='none' and not db.get(GameReward,a.id)]
    return {'coupons':coupons,'unclaimed':unclaimed}
@router.get('/admin/arcade',dependencies=[Depends(admin)])
def admin_arcade(db=Depends(get_db)):
    return {'config':config(db),'analytics':{'attempts':db.scalar(select(func.count()).select_from(ArcadeAttempt)),'rewards_issued':db.scalar(select(func.count()).select_from(GameReward)),'coupons_redeemed':db.scalar(select(func.count()).select_from(CouponRedemption)),'discount_used':db.scalar(select(func.coalesce(func.sum(CouponRedemption.discount),0))),'participation':dict(db.execute(select(ArcadeAttempt.game,func.count()).group_by(ArcadeAttempt.game)).all())}}
@router.put('/admin/arcade',dependencies=[Depends(admin)])
def update_arcade(data:ArcadeConfig,db=Depends(get_db)):
    row=db.get(GameConfiguration,1)
    if not row: row=GameConfiguration(id=1); db.add(row)
    row.data=data.model_dump(); db.commit(); return row.data
@router.post('/admin/rewards/{code}/revoke',dependencies=[Depends(admin)])
def revoke(code:str,db=Depends(get_db)):
    c=db.get(Coupon,code)
    if not c or c.used: raise HTTPException(400,'Only unredeemed coupons can be revoked.')
    c.revoked=True; db.commit(); return {'ok':True}
