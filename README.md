# TS Mart

A React + FastAPI e-commerce application with a database-driven six-product homepage, COD checkout, protected store administration, price comparisons, and persistent shopping games.

## Run locally

Requirements: Python 3.11+ and Node.js 22.12+ (tested with Python 3.14 and Node 26). Use two terminals. Run backend commands from `backend/`, since the default SQLite path and `.env` are relative to that directory.

### Backend

```sh
cd "/Users/anas/Documents/TS Mart/backend"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```sh
cd "/Users/anas/Documents/TS Mart/frontend"
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Interactive API documentation: http://127.0.0.1:8000/docs.

Dependencies are already installed and the sample database is seeded in the delivered workspace. For subsequent runs, only the `uvicorn` and `npm run dev` commands are needed.

### Create your administrator

Set `ADMIN_EMAIL` and a unique `ADMIN_PASSWORD` of at least 12 characters in `backend/.env`, then run:

```sh
cd "/Users/anas/Documents/TS Mart/backend"
.venv/bin/python -m app.seed --admin
```

Sign in at `/admin`. No administrator or hardcoded admin password ships with the project. The command refuses to overwrite an existing admin. Remove the bootstrap password from `.env` after creation. Customer accounts can be created at `/account`.

## Pages and functionality

- `/`: exactly six database-selected featured products; 3 / 2 / 1 columns for desktop / tablet / mobile; backend-scheduled offers.
- `/shop`, `/deals`: search, category filtering, sorting, current promotions, stock, and prices.
- `/product/:id`: gallery, pricing, stock, comparisons, related products, and cart actions.
- `/cart`: persistent local cart, quantity changes, customer delivery details, server-calculated totals, reward selection, and COD order confirmation.
- `/orders`: authenticated customer's own orders and status history progression.
- `/arcade`: Scratch & Save and Guess the Price, rules, probabilities, daily eligibility, server deadlines, and refresh recovery.
- `/rewards`: available, redeemed, expired, and revoked coupons; unclaimed rewards; expiry countdowns and copy actions.
- `/games`: original Spin the Wheel and five-question Shopping Quiz.
- `/admin`: products, validated image uploads, six-product selection, manual comparison data, promotion scheduling, order lifecycle, inventory, store configuration, arcade rules, and metrics.

## Architecture

```text
frontend/src/
  api.ts            HTTP client, product type, integer-paise formatter
  store.tsx         cart, account, settings, toast state
  components.tsx    shared navigation, cards, modal, comparison, countdown
  pages.tsx         storefront, catalog, product, account, checkout, orders
  arcade.tsx        canvas scratch card, price game, rewards, classic games
  admin.tsx         store and arcade management
  styles.css        responsive visual system and reduced-motion support
backend/app/
  db.py             environment config, engine, sessions
  models.py         normalized store, order, coupon, game, session tables
  schemas.py        validated input contracts
  security.py       scrypt hashing, opaque sessions, persistent rate limits
  services.py       pricing, stock, coupon redemption, comparison provider
  main.py           store/auth/admin REST routes
  arcade.py         persistent arcade state machines and reward configuration
  seed.py           idempotent six-product sample catalog and admin bootstrap
backend/migrations/ Alembic baseline schema and migration environment
backend/tests/      integration and concurrency tests using isolated SQLite
```

All money is integer paise: ₹1,499 is `149900`. The admin labels monetary inputs explicitly. The frontend never supplies trusted order totals or game scores.

## Reward rules and guarantees

Scratch & Save reserves an attempt immediately, saves a cryptographically selected reward, and reveals it after the canvas is approximately 60% scratched. A keyboard-accessible reveal alternative is included. Revealing does not issue a coupon; the customer claims it. A unique game-reward record makes repeated and simultaneous claims idempotent.

Guess the Price snapshots five different active, in-stock products, their effective selling prices, and four distinct price options. The browser sees only the current question. Answers are recorded once and evaluated server-side against the snapshot and deadline. Refresh restores the same question/deadline. After a timeout the user can continue with a missed round. The final answer completes the challenge and creates a claimable result. With fewer than five eligible products, the game is disabled with an explanation.

Default arcade eligibility is one attempt per game per business day in **Asia/Kolkata**. The admin can change the timezone and limits (1–5); database uniqueness on customer/game/date/slot prevents duplicate reservations. Defaults: scratch 5% (cap ₹50, 35%), 10% (cap ₹100, 25%), 15% (cap ₹150, 10%), free delivery (10%), or no reward (20%). Guess 4/5 earns 10% (cap ₹100); 5/5 earns 15% (cap ₹150). These are editable configuration, not frontend decisions. Active attempts retain their original rules. Coupons expire 24 hours after claim by default.

The classic spin and shopping quiz preserve their separately disclosed once-per-UTC-day policy and configurable seven-day reward expiry. Scratch rewards are issued exclusively through `/api/arcade/scratch/*`.

Coupons belong to a customer, have a source, type, expiry, minimum, cap, and one successful redemption. Stacking is disabled. Free delivery discounts exactly the calculated delivery fee and never the merchandise subtotal. Fixed-amount rewards are also supported. An order records its coupon and applied discount; a redemption ledger drives analytics.

Checkout recalculates prices, validates every cart line and coupon, conditionally deducts stock, redeems the coupon, and creates the order in one transaction. An exception rolls back all changes. Unique idempotency keys return the original order for an identical request and reject different payloads using the same key. PostgreSQL row locks and conditional updates protect inventory; SQLite uses atomic writes and uniqueness constraints. Concurrent-request tests cover stock, coupons, starts, claims, and order duplication.

**Cancellation policy:** Pending → Confirmed → Packed → Shipped → Delivered. Cancellation is allowed before shipment. Cancellation restores inventory exactly once. Redeemed coupons remain redeemed, including cancelled COD orders, to prevent cancel/reorder reward farming. Delivered COD totals count as collected revenue; this is an admin-maintained operational status, not payment-provider confirmation.

## Price comparison

No scraping and no invented competitor prices. The sample catalog leaves Amazon and Flipkart prices unavailable. An admin must enter a verified matching model/variant, HTTPS marketplace URL, and price; updates receive server timestamps and a manual source label. Unknown values display “Price unavailable.” `ManualComparisonProvider` in `services.py` is the extension boundary for future authorized API/affiliate-feed adapters. No live marketplace integration or credentials are included.

The six sample products are fictional demo inventory with custom local SVG illustrations. Replace product descriptions, images, SKUs, stock, and prices with real merchandise before accepting real customers. The footer labels demo data. Initial launch offers are scheduled for three days from first seed; repeated seeding never renews them.

## Security and environment

`backend/.env.example` documents configuration:

- `DATABASE_URL`: defaults to local SQLite. PostgreSQL: `postgresql+psycopg://user:password@host/database`.
- `ALLOWED_ORIGINS`: explicit JSON array of approved browser origins. Add the production origin when deploying.
- `COOKIE_SECURE`: `false` for HTTP localhost; set `true` for production HTTPS.
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`: temporary admin bootstrap inputs only.

`frontend/.env.example`: `VITE_API_BASE` is empty for same-origin API use. Vite proxies `/api` and `/uploads` to port 8000. Production should use the same origin for frontend, API, and uploads.

Passwords are salted scrypt hashes; random session tokens are hashed in the database and sent only in HttpOnly, SameSite cookies. Admin and customer roles are enforced separately on APIs. Writes check the browser Origin and Fetch Metadata. Sensitive endpoints use persistent atomic IP rate buckets. CORS uses an explicit allowlist. Uploads are capped at 5 MB and 20 megapixels, decoded with Pillow, resized, stripped of metadata through re-encoding, and stored as random-name WebP files; SVG/HTML uploads are rejected.

Local account identity means possession of the signed-in session. Email/SMS ownership verification, password recovery, CAPTCHA, and cross-account fraud detection require external delivery/identity services and are not included. Daily limits are per account, with IP-based signup/play rate limits. Deploy behind a trusted proxy and configure Uvicorn's trusted proxy IPs explicitly; never trust arbitrary client-supplied forwarding headers. A shared database and shared/persistent upload storage are needed for multiple application instances.

## Database migrations

```sh
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

The baseline revision contains the complete initial store and arcade schema. No pre-existing project database existed. This workspace's already-created development database is stamped at the baseline. New databases should use `upgrade head`; do not stamp a database with an unknown schema. Future model changes require a reviewed migration:

```sh
.venv/bin/alembic revision --autogenerate -m "Describe the schema change"
.venv/bin/alembic upgrade head
```

Back up databases before production migrations. API startup and seeding can create missing tables for development, but do not alter existing columns; use Alembic for versioned upgrades.

## Validation

```sh
cd "/Users/anas/Documents/TS Mart/backend"
.venv/bin/python -m pytest -q
cd "/Users/anas/Documents/TS Mart/frontend"
npm run build
```

The tests create a disposable temporary SQLite database and never use your store database. They cover authorization, CSRF checks, registration, price calculation, promotion expiry, inventory, rollback, COD orders, private history, duplicate submissions, concurrent stock/coupon use, cancellation, image validation, daily attempts, concurrent starts/claims, saved game state, price snapshots, answer replay, deadlines, insufficient catalog, and reward analytics. PostgreSQL is supported by the model/query design; it has not been exercised against a live PostgreSQL server in this environment.

## Production hosting

Build with `npm run build`, serve `frontend/dist` with SPA fallback to `index.html`, and proxy `/api` plus `/uploads` to FastAPI. Run migrations before starting the API. Use HTTPS, secure cookies, persistent database/uploads, backups, appropriate request body limits at the reverse proxy, and your real stock/fulfilment policies. The project is delivered locally; it has not been published to a public host. COD orders are recorded and managed in the dashboard; courier booking and outbound notifications are not integrated.
