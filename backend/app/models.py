from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Customer(Base):
    __tablename__ = 'customers'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(100))

class Admin(Base):
    __tablename__ = 'admin_users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    expires: Mapped[datetime] = mapped_column(DateTime)

class Category(Base):
    __tablename__ = 'product_categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)

class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (CheckConstraint('stock >= 0'), CheckConstraint('price > 0 AND original_price >= price'))
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category_id: Mapped[int] = mapped_column(ForeignKey('product_categories.id'))
    description: Mapped[str] = mapped_column(String(4000))
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    original_price: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class ProductImage(Base):
    __tablename__ = 'product_images'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'))
    url: Mapped[str] = mapped_column(String(500))

class Featured(Base):
    __tablename__ = 'featured_products'
    position: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), unique=True)

class CompetitorPrice(Base):
    __tablename__ = 'competitor_prices'
    __table_args__ = (UniqueConstraint('product_id', 'marketplace'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'))
    marketplace: Mapped[str] = mapped_column(String(20))
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), default='')
    source: Mapped[str] = mapped_column(String(160), default='manual')
    variant: Mapped[str] = mapped_column(String(160), default='')
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Promotion(Base):
    __tablename__ = 'promotions'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Coupon(Base):
    __tablename__ = 'coupons'
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    percent: Mapped[int] = mapped_column(Integer)
    max_discount: Mapped[int] = mapped_column(Integer)
    minimum: Mapped[int] = mapped_column(Integer)
    expires: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    source_game: Mapped[str] = mapped_column(String(20), default='promotion')
    discount_type: Mapped[str] = mapped_column(String(20), default='percent')
    amount: Mapped[int] = mapped_column(Integer, default=0)
    redemption_limit: Mapped[int] = mapped_column(Integer, default=1)

class GameAttempt(Base):
    __tablename__ = 'game_attempts'
    __table_args__ = (UniqueConstraint('customer_id', 'game', 'day'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    game: Mapped[str] = mapped_column(String(20))
    day: Mapped[str] = mapped_column(String(10))
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[int] = mapped_column(Integer, default=0)

class RewardClaim(Base):
    __tablename__ = 'reward_claims'
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey('game_attempts.id'), unique=True)
    coupon_code: Mapped[str] = mapped_column(ForeignKey('coupons.code'))

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    coupon_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[dict] = mapped_column(JSON)
    subtotal: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer)
    delivery: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='Pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)

class StoreSettings(Base):
    __tablename__ = 'store_settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    data: Mapped[dict] = mapped_column(JSON)

class RateBucket(Base):
    __tablename__ = 'rate_buckets'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    resets_at: Mapped[datetime] = mapped_column(DateTime)

class GameConfiguration(Base):
    __tablename__ = 'game_configuration'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    data: Mapped[dict] = mapped_column(JSON)

class ArcadeAttempt(Base):
    __tablename__ = 'arcade_attempts'
    __table_args__ = (UniqueConstraint('customer_id','game','business_date','slot'),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    game: Mapped[str] = mapped_column(String(20))
    business_date: Mapped[str] = mapped_column(String(10))
    slot: Mapped[int] = mapped_column(Integer, default=1)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    reward: Mapped[dict] = mapped_column(JSON)
    rules: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class GameQuestion(Base):
    __tablename__ = 'game_questions'
    __table_args__ = (UniqueConstraint('attempt_id','position'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('arcade_attempts.id'))
    position: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    name: Mapped[str] = mapped_column(String(160))
    image: Mapped[str] = mapped_column(String(500))
    correct_price: Mapped[int] = mapped_column(Integer)
    options: Mapped[list] = mapped_column(JSON)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class GameAnswer(Base):
    __tablename__ = 'game_answers'
    question_id: Mapped[int] = mapped_column(ForeignKey('game_questions.id'),primary_key=True)
    selected: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class GameReward(Base):
    __tablename__ = 'game_rewards'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('arcade_attempts.id'),primary_key=True)
    coupon_code: Mapped[str] = mapped_column(ForeignKey('coupons.code'), unique=True)

class CouponRedemption(Base):
    __tablename__ = 'coupon_redemptions'
    coupon_code: Mapped[str] = mapped_column(ForeignKey('coupons.code'),primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), unique=True)
    discount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
