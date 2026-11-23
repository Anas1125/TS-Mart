from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from urllib.parse import urlparse
import re

class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    remember_me: bool = False
    name: str = Field(default='Customer', min_length=2, max_length=100)
    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value): raise ValueError('Enter a valid email address')
        return value.lower().strip()

class ProductInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=5, max_length=4000)
    sku: str = Field(min_length=2, max_length=80)
    price: int = Field(gt=0, le=100000000)
    original_price: int = Field(gt=0, le=100000000)
    stock: int = Field(ge=0, le=1000000)
    active: bool = True
    images: list[str] = Field(min_length=1, max_length=8)
    @field_validator('images')
    @classmethod
    def image_valid(cls, values):
        for v in values:
            if not re.fullmatch(r'/(uploads/[a-f0-9]{32}\.webp|images/[a-z0-9-]+\.svg)', v): raise ValueError('Use an uploaded image or a bundled sample image')
        return values
    @model_validator(mode='after')
    def prices(self):
        if self.original_price < self.price: raise ValueError('Original price must be at least selling price')
        return self

class ComparisonInput(BaseModel):
    marketplace: str = Field(pattern='^(Amazon|Flipkart)$')
    price: int | None = Field(default=None, gt=0, le=100000000)
    url: str = Field(default='', max_length=1000)
    source: str = Field(default='manual', min_length=3, max_length=160)
    variant: str = Field(min_length=2, max_length=160)
    verified: bool = False
    @model_validator(mode='after')
    def valid_url(self):
        if self.url:
            u = urlparse(self.url)
            domain = 'amazon.in' if self.marketplace == 'Amazon' else 'flipkart.com'
            if u.scheme != 'https' or not (u.hostname == domain or (u.hostname or '').endswith('.'+domain)) or u.username: raise ValueError('Use an HTTPS URL on the matching marketplace')
        if self.price is not None and (not self.verified or not self.url): raise ValueError('Verify the identical variant and provide a source URL before entering a price')
        return self

class PromotionInput(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    price: int = Field(gt=0)
    starts_at: datetime
    ends_at: datetime
    active: bool = True
    @model_validator(mode='after')
    def dates(self):
        if self.ends_at <= self.starts_at: raise ValueError('End must be after start')
        return self

class Address(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    mobile: str = Field(pattern=r'^[6-9]\d{9}$')
    email: str = Field(min_length=5, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    address: str = Field(min_length=8, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    pin: str = Field(pattern=r'^[1-9]\d{5}$')
    instructions: str = Field(default='', max_length=500)

class CartItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=20)
class Checkout(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=50)
    coupon: str = Field(default='', max_length=40)
    address: Address
    idempotency_key: str = Field(min_length=16, max_length=100)
class Quote(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=50)
    coupon: str = Field(default='', max_length=40)
class StoreInput(BaseModel):
    store_name: str = Field(default='TS Mart', min_length=2, max_length=60)
    logo: str = Field(default='', max_length=100)
    accent: str = Field(default='#a78bfa', pattern=r'^#[0-9a-fA-F]{6}$')
    delivery: int = Field(default=4900, ge=0, le=100000)
    free_delivery_minimum: int = Field(default=199900, ge=0)
    cod: bool = True
    low_stock: int = Field(default=5, ge=0)
    probabilities: list[int] = Field(default=[35,35,20,10], min_length=4, max_length=4)
    coupon_minimum: int = Field(default=99900, ge=0)
    coupon_cap: int = Field(default=50000, gt=0)
    coupon_days: int = Field(default=7, ge=1, le=90)
    quiz_required: int = Field(default=4, ge=1, le=5)
    @model_validator(mode='after')
    def valid(self):
        if sum(self.probabilities) != 100 or any(x<0 for x in self.probabilities): raise ValueError('Probabilities must be nonnegative and sum to 100')
        if self.logo and not re.fullmatch(r'/uploads/[a-f0-9]{32}\.webp',self.logo): raise ValueError('Upload the logo first')
        return self
