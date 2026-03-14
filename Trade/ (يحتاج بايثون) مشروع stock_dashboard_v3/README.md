# Stock Dashboard V3

لوحة توصيات أسهم شخصية بواجهة عربية + Flask backend.

## المزايا
- إخفاء مفتاح Alpha Vantage داخل الخادم بدل وضعه في HTML.
- مزامنة أسعار يومية وأسبوعية من Alpha Vantage.
- تقييم حالة السهم تلقائيًا: مراقبة، دخول محتمل، دخول مؤكد، جني ربح، وقف/خروج.
- إرسال تنبيه إلى Telegram وDiscord عند تغيّر حالة السهم.
- حفظ قائمة الأسهم في `data/stocks.json`.
- حفظ الإعدادات في `.env` داخل المشروع.

## التشغيل
1. ثبّت المتطلبات:
   `pip install -r requirements.txt`
2. شغّل التطبيق:
   `python app.py`
3. افتح المتصفح على:
   `http://127.0.0.1:5000`

## الإعدادات
من داخل الواجهة اضغط "الإعدادات" ثم أدخل:
- Alpha Vantage API Key
- Telegram Bot Token
- Telegram Chat ID
- Discord Webhook URL

## ملاحظات
- Alpha Vantage يفرض limits على عدد الطلبات، لذلك لا تكثر الأسهم أو المزامنات السريعة.
- Telegram يعتمد على `sendMessage` عبر HTTP Bot API.
- Discord يعتمد على إرسال JSON إلى عنوان Webhook.
- تستطيع لاحقًا استبدال Alpha Vantage بمزود أسرع، أو إضافة scheduler مثل APScheduler أو Celery.
