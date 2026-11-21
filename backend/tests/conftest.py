import os, tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(prefix='tsmart-tests-',suffix='.db')
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import Customer,Admin,Session,now
from app.seed import seed
from app.security import hash_password
from datetime import timedelta
import hashlib

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine);seed()
    with SessionLocal() as db:
        db.add(Customer(id=1,email='shopper@example.com',name='Shopper',password_hash=hash_password('test-password-strong')))
        db.add(Customer(id=2,email='other@example.com',name='Other',password_hash=hash_password('test-password-strong')))
        db.add(Admin(id=1,email='admin@example.com',password_hash=hash_password('admin-test-password')))
        for token,uid,role in [('customer-token',1,'customer'),('other-token',2,'customer'),('admin-token',1,'admin')]:
            db.add(Session(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=uid,role=role,expires=now()+timedelta(days=1)))
        db.commit()
    yield

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.cookies.set('ts_session','customer-token');yield c
@pytest.fixture
def admin_client():
    with TestClient(app) as c:
        c.cookies.set('ts_session','admin-token');yield c
