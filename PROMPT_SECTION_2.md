# بخش ۲ — تکمیل سیستم کیف پول (Wallet System) — لایه ارائه

## وضعیت فعلی

مدل‌ها و سرویس کیف پول کامل هستند. فقط لایه ارائه (هندلرها، کیبوردها، FSM) نیاز به پیاده‌سازی دارد.

---

## ۱. تغییرات `bot/keyboards/admin.py`

### کلاس AdminCallback — کالبک‌های جدید

```
wallet = "admin:wallet"
wallet_back = "admin:wallet:back"
recharge_package_menu = "admin:wallet:packages"
recharge_package_add = "admin:wallet:packages:add"
recharge_package_delete_menu = "admin:wallet:packages:delete_menu"
recharge_package_toggle = "admin:wallet:packages:toggle"
pending_transactions = "admin:wallet:pending"
```

### تابع admin_panel_keyboard

دکمه «مدیریت کیف پول» به ردیف جدید اضافه شود.

### توابع کیبورد جدید

- `wallet_management_keyboard()` — منوی مدیریت کیف پول
- `recharge_package_management_keyboard()` — مدیریت پکیج‌ها
- `delete_recharge_packages_keyboard(packages)` — لیست برای حذف
- `toggle_recharge_packages_keyboard(packages)` — لیست برای فعال/غیرفعال
- `pending_transactions_keyboard(transactions)` — تراکنش‌های در انتظار
- `transaction_details_keyboard(transaction_id)` — دکمه تایید/رد
- `wallet_notification_keyboard(transaction_id)` — دکمه مشاهده برای اعلان

---

## ۲. تغییرات `bot/states/admin.py`

```python
class RechargePackageStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_amount = State()
```

---

## ۳. هندلرهای ادمین (`bot/handlers/admin/panel.py`)

### هندلرهای مدیریت کیف پول

1. `wallet_panel` — callback `admin:wallet`: نمایش منوی مدیریت کیف پول
2. `wallet_back` — callback `admin:wallet:back`: بازگشت به پنل اصلی
3. `recharge_package_panel` — callback `admin:wallet:packages`: منوی مدیریت پکیج‌ها
4. `add_recharge_package_start` — callback `admin:wallet:packages:add`: ورود به state انتظار عنوان
5. `add_recharge_package_title` — state `waiting_for_title`: دریافت عنوان، رفتن به state انتظار مبلغ
6. `add_recharge_package_finish` — state `waiting_for_amount`: ایجاد پکیج، نمایش مجدد منو
7. `delete_recharge_package_menu` — callback `admin:wallet:packages:delete_menu`: لیست پکیج‌ها برای حذف
8. `delete_recharge_package` — callback `admin:wallet:packages:delete:{id}`: حذف پکیج
9. `toggle_recharge_package_menu` — callback `admin:wallet:packages:toggle`: لیست پکیج‌ها
10. `toggle_recharge_package` — callback `admin:wallet:packages:toggle:{id}`: تغییر وضعیت
11. `recharge_package_list` — callback `admin:wallet:packages:list`: لیست کامل پکیج‌ها
12. `recharge_package_back` — callback `admin:wallet:packages:back`: بازگشت به منوی کیف پول
13. `pending_transactions_list` — callback `admin:wallet:pending`: تراکنش‌های در انتظار
14. `view_pending_transaction` — callback `admin:wallet:pending:view:{id}`: جزئیات + فیش
15. `approve_wallet_transaction` — callback `admin:wallet:approve:{id}`: تایید + ارسال پیام به کاربر
16. `reject_wallet_transaction` — callback `admin:wallet:reject:{id}`: رد + ارسال پیام به کاربر
17. `pending_transactions_back` — callback `admin:wallet:pending:back`: بازگشت

---

## ۴. تغییرات `bot/keyboards/user.py`

### کلاس UserCallback — کالبک‌های جدید

```
my_wallet = "user:wallet"
wallet_recharge = "user:wallet:recharge"
wallet_transactions = "user:wallet:transactions"
```

### تابع main_menu_keyboard

دکمه «کیف پول من» اضافه شود.

### توابع کیبورد جدید

- `wallet_keyboard()` — منوی کیف پول با موجودی
- `recharge_packages_keyboard(packages)` — لیست پکیج‌های فعال
- `wallet_transactions_keyboard(transactions)` — تاریخچه تراکنش‌ها
- `wallet_back_keyboard()` — بازگشت به منوی اصلی

---

## ۵. تغییرات `bot/states/user.py`

```python
class UserWalletStates(StatesGroup):
    waiting_for_receipt = State()
```

---

## ۶. هندلرهای کاربر (`bot/handlers/user/start.py`)

### هندلرهای کیف پول

1. `user_wallet` — callback `user:wallet`: نمایش منوی کیف پول با موجودی
2. `user_wallet_recharge` — callback `user:wallet:recharge`: لیست پکیج‌های فعال شارژ
3. `select_recharge_package` — callback `user:wallet:recharge:select:{id}`: انتخاب پکیج + نمایش کارت بانکی
4. `wallet_receipt_upload` — state `waiting_for_receipt`: دریافت فیش + ایجاد تراکنش pending + اعلان به ادمین
5. `user_wallet_transactions` — callback `user:wallet:transactions`: تاریخچه تراکنش‌ها
6. `user_wallet_back` — callback `user:wallet:back`: بازگشت به منوی اصلی

---

## ۷. اعلان‌ها

- ارسال فیش → اعلان به ادمین با دکمه مشاهده تراکنش
- تایید/رد → ارسال پیام مناسب به کاربر

---

## ۸. نکات فنی

- استفاده از WalletService موجود بدون تغییر
- الگوی کد با بقیه هندلرها یکسان باشد
- کالبک‌های ادمین با AdminFilter فیلتر شوند
- FSM states در فایل‌های states تعریف شوند
