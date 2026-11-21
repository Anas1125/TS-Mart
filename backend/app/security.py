import hashlib, hmac, secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .db import get_db, SessionLocal
from .models import Session, now, RateBucket

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f'{salt}${digest}'

def verify_password(password, stored):
    salt, expected = stored.split('$')
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex(), expected)

DUMMY_PASSWORD = hash_password(secrets.token_urlsafe(30))

def identity(request: Request, db=Depends(get_db)):
    token = request.cookies.get('ts_session', '')
    session = db.get(Session, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires < now():
        raise HTTPException(401, 'Please sign in to continue.')
    return session

def customer(user=Depends(identity)):
    if user.role != 'customer': raise HTTPException(403, 'Sign in with a customer account.')
    return user.user_id

def admin(user=Depends(identity)):
    if user.role != 'admin': raise HTTPException(403, 'Administrator access required.')
    return user.user_id

def rate_limit(request: Request, action: str, limit=10, seconds=900):
    # Persistent atomic buckets work across workers. Trust socket IP, never arbitrary forwarded headers.
    key = hashlib.sha256(f'{request.client.host}:{action}'.encode()).hexdigest()
    with SessionLocal() as db:
        bucket = db.get(RateBucket, key)
        if bucket is None:
            try:
                db.add(RateBucket(key=key, count=0, resets_at=now()+timedelta(seconds=seconds)))
                db.commit()
            except IntegrityError: db.rollback()
        db.execute(update(RateBucket).where(RateBucket.key==key, RateBucket.resets_at <= now()).values(count=0, resets_at=now()+timedelta(seconds=seconds)))
        changed = db.execute(update(RateBucket).where(RateBucket.key==key, RateBucket.count < limit).values(count=RateBucket.count+1)).rowcount
        db.commit()
        if not changed: raise HTTPException(429, 'Too many attempts. Please try again later.')
