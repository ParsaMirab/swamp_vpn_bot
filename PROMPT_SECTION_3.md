# بخش ۳ — خرید از کیف پول + اتصال خودکار به پنل 3x-ui

## خلاصه جریان — Flow نهایی خرید

```
┌─────────────────────────────────────────────────────────┐
│  ۱. کاربر سرویس و پلن را انتخاب می‌کند                  │
├─────────────────────────────────────────────────────────┤
│  ۲. بررسی موجودی کیف پول                                 │
│     ├── موجودی کافی → ادامه                              │
│     └── موجودی ناکافی → پیام خطا + پیشنهاد شارژ         │
├─────────────────────────────────────────────────────────┤
│  ۳. کسر مبلغ از کیف پول                                  │
├─────────────────────────────────────────────────────────┤
│  ۴. ثبت سفارش (status=pending)                          │
├─────────────────────────────────────────────────────────┤
│  ۵. ارسال درخواست به SanaeiService.create_user()        │
├─────────────────────────────────────────────────────────┤
│  ۶. دریافت لینک ساب از SanaeiService.get_config()       │
├─────────────────────────────────────────────────────────┤
│  ۷. ذخیره لینک ساب در سفارش (status=completed)          │
│     و ارسال اطلاعات به کاربر                             │
├─────────────────────────────────────────────────────────┤
│  ۸. ⚠️ خطا در هر مرحله → Rollback:                      │
│     ├── status=failed                                   │
│     └── بازگشت وجه به کیف پول                            │
└─────────────────────────────────────────────────────────┘
```

---

## ۱. تغییرات دیتابیس

### مدل Plan — فیلدهای جدید (`bot/database/models.py`)

به مدل `Plan` سه فیلد اضافه شود:

- `inbound_id` — شناسه inbound در پنل 3x-ui (Integer, nullable)
- `traffic_limit_gb` — محدودیت ترافیک به گیگابایت، صفر یعنی نامحدود (Integer, default=0)
- `duration_days` — مدت اعتبار اکانت به روز (Integer, default=30)

### Migration (`bot/database/base.py`)

سه دستور `ALTER TABLE plans ADD COLUMN` برای فیلدهای بالا اضافه شود.

### فایل `.env` — متغیرهای جدید

```
SANAIE_BASE_URL=https://your-panel.com
SANAIE_API_KEY=your_api_key_here
```

### مدل Settings — تنظیمات پنل

نیازی به مدل جدید نیست. متغیرهای محیطی کافی هستند.

---

## ۲. سرویس جدید: SanaeiService (API Layer)

فایل جدید: `bot/services/sanaei_service.py`

تمام ارتباط با پنل سنایی در این سرویس جدا مدیریت می‌شود.

### ساختار کلاس

```python
from __future__ import annotations
import logging
from uuid import uuid4
import httpx
from bot.config import settings

logger = logging.getLogger(__name__)


class SanaeiService:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def create_user(
        self,
        inbound_id: int,
        traffic_gb: int = 0,
        duration_days: int = 30,
    ) -> dict:
        """ساخت کاربر جدید در پنل و برگرداندن اطلاعات اکانت"""
        email = f"bot_{uuid4().hex[:12]}"
        traffic_bytes = traffic_gb * 1073741824 if traffic_gb > 0 else 0

        payload = {
            "email": email,
            "inboundIds": [inbound_id],
            "trafficLimit": traffic_bytes,
            "expireDays": duration_days,
        }

        async with httpx.AsyncClient(verify=True, timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/panel/api/clients/add",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise ValueError(data.get("msg", "خطا در ساخت اکانت کاربر"))

        return {"email": email, "inbound_id": inbound_id, "raw": data}

    async def buy_service(self, user_data: dict, product_data: dict) -> dict:
        """خرید سرویس — معادل create_user با ورودی ساختاریافته"""
        return await self.create_user(
            inbound_id=product_data["inbound_id"],
            traffic_gb=product_data.get("traffic_gb", 0),
            duration_days=product_data.get("duration_days", 30),
        )

    async def get_config(self, email: str) -> list[str]:
        """دریافت لینک‌های اشتراک (sub links) برای یک کاربر"""
        async with httpx.AsyncClient(verify=True, timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/panel/api/clients/links/{email}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise ValueError(data.get("msg", "خطا در دریافت کانفیگ"))

        return data.get("obj", [])

    async def check_status(self) -> dict:
        """بررسی وضعیت اتصال به پنل"""
        async with httpx.AsyncClient(verify=True, timeout=15) as client:
            resp = await client.get(
                f"{self.base_url}/panel/api/server/status",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
```

### متدهای اصلی

| متد | API Endpoint | توضیح |
|---|---|---|
| `create_user()` | `POST /panel/api/clients/add` | ساخت اکانت جدید با inbound, traffic, expiry |
| `buy_service()` | — | ورپر ساختاریافته دور create_user |
| `get_config()` | `GET /panel/api/clients/links/{email}` | دریافت لینک ساب (vless://, vmess://, ...) |
| `check_status()` | `GET /panel/api/server/status` | بررسی سلامت اتصال به پنل |

### نمونه استفاده

```python
service = SanaeiService(api_key=settings.sanaei_api_key, base_url=settings.sanaei_base_url)

# ساخت اکانت
result = await service.create_user(inbound_id=3, traffic_gb=50, duration_days=30)

# دریافت لینک ساب
links = await service.get_config(email=result["email"])

# بررسی وضعیت
status = await service.check_status()
```

### مدیریت خطا

- خطای HTTP: `httpx.HTTPStatusError` لاگ شود
- خطای پنل: `ValueError` با پیام فارسی raise شود
- در صورت خطا، سفارش وضعیت `failed` بگیرد و وجه بازگردد

### Rollback (بازگشت وجه)

در صورت خطا در هر مرحله از فرآیند (ساخت اکانت یا دریافت لینک ساب):

```python
# مثال در هندلر
try:
    result = await sanaei.create_user(...)
    links = await sanaei.get_config(result["email"])
    # ذخیره موفق
except Exception as e:
    await WalletService.approve_transaction(...)  # بازگشت وجه
    await OrderService.fail_order(order_id)
    await message.answer("خطا در ساخت اکانت. وجه به کیف پول بازگردانده شد.")
```

---

## ۳. به‌روزرسانی تنظیمات (`bot/config.py`)

دو فیلد جدید به `Settings` dataclass اضافه شود:

- `sanaei_base_url: str` — از متغیر محیطی `SANAIE_BASE_URL`
- `sanaei_api_key: str` — از متغیر محیطی `SANAIE_API_KEY`

این دو فیلد اختیاری باشند (مقدار پیش‌فرض خالی) تا ربات بدون پنل هم کار کند.

---

## ۴. به‌روزرسانی PlanService

متد `create_plan` و `update_plan` برای پذیرش فیلدهای جدید تغییر کند.

متد جدید `get_plan_with_inbound` که inbound_id پلن را برگرداند.

---

## ۵. به‌روزرسانی OrderService

### متد جدید: create_wallet_order

```python
@staticmethod
async def create_wallet_order(
    user_id: int,
    service_id: int,
    plan_id: int,
    original_price: int,
    final_price: int,
    discount_id: int | None = None,
) -> Order:
```

این متد سفارش را با `payment_type=wallet` و `status=pending` ایجاد می‌کند.

### متد جدید: complete_wallet_order

پس از موفقیت در ساخت اکانت در پنل، وضعیت سفارش به `completed` تغییر کند و `sub_link` ذخیره شود.

### متد جدید: fail_order

در صورت خطا در اتصال به پنل، وضعیت به `failed` تغییر کند و وجه به کیف پول بازگردد.

### متن‌های جدید

- `wallet_order_text(order)` — متن تایید سفارش موفق برای کاربر
- `wallet_order_failed_text(order)` — متن اطلاع‌رسانی خطا
- `admin_wallet_order_text(order)` — اطلاع‌رسانی سفارش کیف‌پولی به ادمین (اختیاری)

---

## ۶. جریان خرید کاربر — تغییرات در `bot/handlers/user/start.py`

### مراحل جریان جدید

مرحله ۱: کاربر پلن را انتخاب می‌کند (همانند فعلی — `user:buy:plan:{service_id}:{plan_id}`)

مرحله ۲: صفحه جزئیات پلن + دکمه «پرداخت از کیف پول» + دکمه «بازگشت»

مرحله ۳: کلیک روی «پرداخت از کیف پول» → بررسی موجودی

مرحله ۴ الف (موجودی کافی):
- کسر وجه از کیف پول
- ایجاد سفارش
- فراخوانی SanaeiService.create_user
- دریافت لینک ساب
- ذخیره لینک در سفارش + تغییر وضعیت به completed
- ارسال لینک ساب به کاربر

مرحله ۴ ب (موجودی ناکافی):
- پیام «موجودی کیف پول کافی نیست»
- پیشنهاد شارژ کیف پول

### State جدید در `bot/states/user.py`

```python
class UserWalletPaymentStates(StatesGroup):
    confirming_payment = State()
```

### کالبک‌های جدید در UserCallback

```
pay_with_wallet = "user:order:pay_wallet"
```

### حذف جریان فیش پرداختی

مرحله ارسال فیش و انتظار برای تایید ادمین حذف شود. پرداخت فقط از کیف پول انجام گیرد.

---

## ۷. کیبورد جدید — جزئیات پلن (`bot/keyboards/user.py`)

تابع جدید `wallet_plan_details_keyboard(service_id)` شامل:

- دکمه «پرداخت از کیف پول» با callback مربوطه
- دکمه «بازگشت» به لیست پلن‌ها

---

## ۸. اعلان به ادمین (اختیاری)

پس از تکمیل موفق سفارش، پیام کوتاهی به ادمین ارسال شود:

```
✅ سفارش #{order_id} — کاربر {user_id} — {plan_name} — اکانت خودکار ساخته شد
```

این اعلان اختیاری است. در صورت نیاز، با استفاده از `bot.send_message` به `settings.admin_id` ارسال شود.

---

## ۹. صفحه مدیریت پلن‌ها در پنل ادمین

### فرم افزودن پلن — فیلدهای جدید

در هندلر افزودن پلن (`admin:plans:add`)، پس از دریافت قیمت:

- درخواست inbound_id (عدد) — توضیح: «شناسه inbound در پنل 3x-ui را وارد کنید»
- درخواست محدودیت ترافیک (GB) — توضیح: «محدودیت ترافیک به گیگابایت (0 برای نامحدود)»
- درخواست مدت اعتبار (روز) — توضیح: «مدت اعتبار اکانت به روز (پیش‌فرض 30)»

### State جدید در `bot/states/admin.py`

```python
class PlanStates(StatesGroup):
    waiting_for_name = State()          # موجود
    waiting_for_price = State()         # موجود
    waiting_for_inbound_id = State()    # جدید
    waiting_for_traffic_limit = State() # جدید
    waiting_for_duration_days = State() # جدید
```

### نمایش جزئیات پلن

در متن نمایش پلن، اطلاعات جدید نیز نشان داده شود:
- inbound_id
- محدودیت ترافیک
- مدت اعتبار

---

## ۱۰. تست‌ها

فایل جدید: `tests/test_sanaei_service.py`

تست‌های مورد نیاز:
- تست create_user با response موفق
- تست buy_service با response موفق
- تست get_config با response موفق
- تست check_status با response موفق
- تست مدیریت خطا (خطای HTTP، توکن نامعتبر)
- تست تبدیل traffic_gb به بایت

---

## ۱۱. خلاصه فایل‌های تغییریافته

| فایل | تغییرات |
|---|---|
| `bot/database/models.py` | سه فیلد جدید در Plan |
| `bot/database/base.py` | Migration برای فیلدهای جدید |
| `bot/config.py` | دو فیلد جدید در Settings |
| `.env` | SANAIE_BASE_URL, SANAIE_API_KEY, SANAIE_SECRET, WALLET_ENABLED |
| `bot/services/sanaei_service.py` | فایل جدید — API Layer پنل |
| `bot/services/order_service.py` | متدهای جدید برای پرداخت کیف‌پولی |
| `bot/services/plan_service.py` | پشتیبانی از فیلدهای جدید Plan |
| `bot/handlers/user/start.py` | جریان خرید بازنویسی شود |
| `bot/keyboards/user.py` | کیبورد جدید پرداخت کیف‌پولی |
| `bot/states/user.py` | State جدید |
| `bot/states/admin.py` | State های جدید برای فیلدهای پلن |
| `bot/handlers/admin/panel.py` | فرم افزودن پلن به‌روز شود |
| `bot/keyboards/admin.py` | نمایش فیلدهای جدید پلن |
| `tests/test_sanaei_service.py` | فایل جدید |

---

## ۱۲. نکات فنی مهم

- فراخوانی API پنل با `httpx` (async) انجام شود
- ایمیل کلاینت با فرمت `bot_{uuid4().hex[:12]}` ساخته شود
- در صورت خطا در ساخت اکانت، وجه از کیف پول بازگردد
- لاگ خطاها در فایل ذخیره شود
- API پنل با SSL verify باشد
- تایم‌اوت فراخوانی API حداکثر ۳۰ ثانیه
- SanaeiService مستقل باشد و فقط از config تنظیمات بگیرد

---

## ۱۳. امنیت و تراکنش‌ها (Atomicity, Idempotency, Logging)

### الف) تراکنش اتمی (Atomicity)

تمام عملیات مالی در یک تراکنش دیتابیس انجام شود:

```python
async with async_session_factory() as session:
    async with session.begin():
        # ۱. کسر موجودی کیف پول
        wallet.balance -= amount
        # ۲. ثبت تراکنش debit
        session.add(WalletTransaction(...))
        # ۳. ثبت سفارش
        session.add(Order(...))
    # اگر هر کدام خطا بدهد، همه rollback می‌شود
```

### ب) جلوگیری از دوبار خرید (Idempotency)

هر سفارش یک `idempotency_key` یکتا داشته باشد:

```python
# در مدل Order فیلد جدید
idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
```

قبل از ایجاد سفارش، بررسی شود کلید تکراری نباشد:

```python
existing = await session.execute(
    select(Order).where(Order.idempotency_key == key)
)
if existing.scalar_one_or_none():
    raise ValueError("سفارش قبلاً ثبت شده است.")
```

نحوه ساخت کلید: `f"{user_id}:{plan_id}:{unix_timestamp}"` یا UUID.

### ج) لاگ کردن عملیات مالی

هر تراکنش مالی در لاگ ثبت شود:

```python
import logging
wallet_logger = logging.getLogger("wallet")

wallet_logger.info(
    "WALLET_DEBIT user=%s amount=%d order_id=%d balance_after=%d",
    user_id, amount, order_id, wallet.balance,
)
wallet_logger.info(
    "WALLET_CREDIT user=%s amount=%d transaction_id=%d balance_after=%d",
    user_id, amount, tx.id, wallet.balance,
)
wallet_logger.warning(
    "WALLET_ROLLBACK user=%s amount=%d reason=%s",
    user_id, amount, str(error),
)
```

سطوح لاگ:
- `INFO`: عملیات موفق (کسر، واریز، تایید)
- `WARNING`: بازگشت وجه (rollback)، تلاش دوباره
- `ERROR`: خطا در اتصال به پنل، خطای غیرمنتظره

### د) جلوگیری از Race Condition

برای جلوگیری از همزمانی در کسر موجودی:

```python
# قفل سطری (Row-level locking)
result = await session.execute(
    select(UserWallet)
    .where(UserWallet.user_id == user_id)
    .with_for_update()  # SELECT ... FOR UPDATE
)
wallet = result.scalar_one()
if wallet.balance < amount:
    raise ValueError("موجودی کافی نیست.")
wallet.balance -= amount
```

یا با SQLite از `BEGIN IMMEDIATE` استفاده شود.

### ه) میدلور لاگ تراکنش

یک میدلور یا دکوراتور برای لاگ کردن خودکار عملیات مالی:

```python
def log_financial_operation(operation: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            wallet_logger.info(f"START: {operation}")
            try:
                result = await func(*args, **kwargs)
                wallet_logger.info(f"SUCCESS: {operation}")
                return result
            except Exception as e:
                wallet_logger.error(f"FAILED: {operation} error={e}")
                raise
        return wrapper
    return decorator
```

---

## ۱۴. تنظیمات محیطی (.env)

```bash
# ──────────────────────────────────────────
# Wallet System
# ──────────────────────────────────────────
WALLET_ENABLED=true

# ──────────────────────────────────────────
# Sanaei Panel API
# ──────────────────────────────────────────
SANAIE_BASE_URL=https://api.sanaei-panel.com
SANAIE_API_KEY=your_api_key_here
SANAIE_SECRET=your_secret_here

# Optional: Webhook for async notifications
SANAIE_WEBHOOK_URL=https://your-domain.com/webhook/sanaei
```

### تغییرات در `bot/config.py`

```python
@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_id: int
    database_url: str
    # Wallet
    wallet_enabled: bool
    # Sanaei Panel
    sanaei_base_url: str
    sanaei_api_key: str
    sanaei_secret: str
    sanaei_webhook_url: str
```

نحوه بارگذاری:

```python
settings = Settings(
    ...
    wallet_enabled=os.getenv("WALLET_ENABLED", "true").lower() == "true",
    sanaei_base_url=os.getenv("SANAIE_BASE_URL", ""),
    sanaei_api_key=os.getenv("SANAIE_API_KEY", ""),
    sanaei_secret=os.getenv("SANAIE_SECRET", ""),
    sanaei_webhook_url=os.getenv("SANAIE_WEBHOOK_URL", ""),
)
```

### فایل `.env` نمونه

```
BOT_TOKEN=your_bot_token
ADMIN_IDS=6879456250
DATABASE_URL=sqlite+aiosqlite:///database/database.db

WALLET_ENABLED=true

SANAIE_BASE_URL=https://your-panel.com
SANAIE_API_KEY=your_api_key_here
SANAIE_SECRET=your_secret_here
SANAIE_WEBHOOK_URL=
```

---

## ۱۵. خلاصه نهایی تمام فایل‌های تغییریافته

| فایل | تغییرات |
|---|---|
| `bot/database/models.py` | فیلدهای جدید در Plan + idempotency_key در Order |
| `bot/database/base.py` | Migration برای فیلدهای جدید |
| `bot/config.py` | فیلدهای جدید در Settings |
| `.env` | متغیرهای جدید |
| `bot/services/sanaei_service.py` | فایل جدید |
| `bot/services/wallet_service.py` | تراکنش اتمی + لاگ + Race Condition |
| `bot/services/order_service.py` | متدهای جدید + Idempotency |
| `bot/services/plan_service.py` | فیلدهای جدید Plan |
| `bot/handlers/user/start.py` | جریان خرید بازنویسی |
| `bot/keyboards/user.py` | کیبورد پرداخت کیف‌پولی |
| `bot/keyboards/admin.py` | نمایش فیلدهای جدید |
| `bot/states/user.py` | State جدید |
| `bot/states/admin.py` | State های جدید |
| `bot/handlers/admin/panel.py` | فرم افزودن پلن به‌روز شود |
| `tests/test_sanaei_service.py` | فایل جدید |

---

## ۱۶. قوانین مهم پروژه

1. **هیچ مهاجرت به PHP یا زبان دیگر** — پروژه فقط Python باقی بماند
2. **ساختار فعلی پروژه حفظ شود** — الگوی handlers/services/models/keyboards/states
3. **API calls فقط از service layer** — هندلرها مستقیماً API صدا نزنند
4. **هندلرها فقط logic ساده** — تمام منطق پیچیده در service layer
5. **پرداخت فقط از کیف پول** — در خرید سرویس، کارت به کارت مستقیم حذف شود
6. **پرداخت دستی فقط برای شارژ کیف پول** — فیش پرداختی فقط در recharge باقی بماند

---

## ۱۷. خروجی مورد انتظار

AI باید موارد زیر را پیاده‌سازی و تست کند:

1. مدل‌های wallet (قبلاً انجام شده)
2. Migration و ORM کامل
3. SanaeiService — پیاده‌سازی کامل
4. Checkout flow جدید (پرداخت از کیف پول)
5. سیستم پرداخت دستی فقط برای شارژ کیف پول
6. سیستم خرید خودکار
7. تست‌ها نوشته شود
8. سیستم ران و بررسی شود
9. در صورت مشکل، رفع شود
