import json
import os
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'data' / 'stocks.json'
ENV_FILE = BASE / '.env'

app = Flask(__name__)


def load_env_file():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file()


def get_config():
    return {
        'ALPHA_VANTAGE_API_KEY': os.getenv('ALPHA_VANTAGE_API_KEY', ''),
        'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN', ''),
        'TELEGRAM_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID', ''),
        'DISCORD_WEBHOOK_URL': os.getenv('DISCORD_WEBHOOK_URL', ''),
    }


def save_env(updates):
    existing = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                existing[k.strip()] = v.strip()
    existing.update({k: str(v).strip() for k, v in updates.items()})
    lines = [f'{k}={v}' for k, v in existing.items()]
    ENV_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for k, v in updates.items():
        os.environ[k] = str(v).strip()


def sample_stocks():
    return [
        {
            'id': 1,
            'symbol': 'AAPL',
            'company': 'Apple Inc.',
            'market': 'US',
            'api_symbol': 'AAPL',
            'entry': 213.80,
            'target': 221.00,
            'stop': 209.90,
            'confidence': 74,
            'reason': 'اختراق محتمل مع زخم يومي إيجابي.',
            'price': None,
            'daily_change': None,
            'weekly_change': None,
            'status': 'مراقبة',
            'updated_at': '--',
            'last_alert_status': ''
        },
        {
            'id': 2,
            'symbol': '2222',
            'company': 'أرامكو السعودية',
            'market': 'SA',
            'api_symbol': '2222.SR',
            'entry': 29.10,
            'target': 30.20,
            'stop': 28.70,
            'confidence': 68,
            'reason': 'خطة أسبوعية بهدف واضح ووقف قريب.',
            'price': None,
            'daily_change': None,
            'weekly_change': None,
            'status': 'مراقبة',
            'updated_at': '--',
            'last_alert_status': ''
        }
    ]


def load_stocks():
    if not DATA_FILE.exists():
        stocks = sample_stocks()
        save_stocks(stocks)
        return stocks
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))


def save_stocks(stocks):
    DATA_FILE.write_text(json.dumps(stocks, ensure_ascii=False, indent=2), encoding='utf-8')


def rr(entry, stop, target):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk else 0


def evaluate_status(item):
    price = item.get('price')
    if price is None:
        return 'مراقبة'
    if price <= item['stop']:
        return 'وقف/خروج'
    if price >= item['target']:
        return 'خروج / جني ربح'
    daily = item.get('daily_change')
    weekly = item.get('weekly_change')
    close_to_entry = item['entry'] * 0.995 <= price <= item['entry'] * 1.01
    trend_up = (daily or 0) > 0 and (weekly or 0) > 0
    if price > item['entry'] and trend_up:
        return 'دخول مؤكد'
    if close_to_entry or (price > item['entry'] and (daily or 0) > 0):
        return 'دخول محتمل'
    return 'مراقبة'


def alpha_request(params):
    cfg = get_config()
    key = cfg['ALPHA_VANTAGE_API_KEY']
    if not key:
        raise ValueError('Alpha Vantage API key غير موجود.')
    params['apikey'] = key
    r = requests.get('https://www.alphavantage.co/query', params=params, timeout=20)
    data = r.json()
    if data.get('Error Message'):
        raise ValueError(data['Error Message'])
    if data.get('Note'):
        raise ValueError('تم الوصول إلى حد الطلبات عند المزود. خفف عدد التحديثات أو انتظر.')
    return data


def fetch_daily(symbol):
    data = alpha_request({'function': 'TIME_SERIES_DAILY', 'symbol': symbol, 'outputsize': 'compact'})
    series = data.get('Time Series (Daily)')
    if not series:
        raise ValueError(f'لا توجد بيانات يومية لـ {symbol}')
    dates = sorted(series.keys(), reverse=True)
    d0 = series[dates[0]]
    d1 = series[dates[1]]
    close0 = float(d0['4. close'])
    close1 = float(d1['4. close'])
    daily_change = ((close0 - close1) / close1) * 100 if close1 else None
    return close0, round(daily_change, 2) if daily_change is not None else None


def fetch_weekly(symbol):
    data = alpha_request({'function': 'TIME_SERIES_WEEKLY', 'symbol': symbol})
    series = data.get('Weekly Time Series')
    if not series:
        return None
    dates = sorted(series.keys(), reverse=True)
    w0 = float(series[dates[0]]['4. close'])
    w1 = float(series[dates[1]]['4. close'])
    weekly_change = ((w0 - w1) / w1) * 100 if w1 else None
    return round(weekly_change, 2) if weekly_change is not None else None


def build_alert_message(item, old_status, new_status):
    return (
        f"تنبيه سهم {item['symbol']}\n"
        f"الحالة السابقة: {old_status or 'بدون'}\n"
        f"الحالة الحالية: {new_status}\n"
        f"السعر: {item['price']}\n"
        f"الدخول: {item['entry']} | الهدف: {item['target']} | الوقف: {item['stop']}\n"
        f"اليومي: {item.get('daily_change')}% | الأسبوعي: {item.get('weekly_change')}%\n"
        f"السبب: {item['reason']}"
    )


def send_telegram(message):
    cfg = get_config()
    token = cfg['TELEGRAM_BOT_TOKEN']
    chat_id = cfg['TELEGRAM_CHAT_ID']
    if not token or not chat_id:
        return False
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    requests.post(url, json={'chat_id': chat_id, 'text': message}, timeout=15)
    return True


def send_discord(message):
    cfg = get_config()
    webhook = cfg['DISCORD_WEBHOOK_URL']
    if not webhook:
        return False
    requests.post(webhook, json={'content': message}, timeout=15)
    return True


def notify_status_change(item, old_status, new_status):
    if not new_status or old_status == new_status:
        return
    msg = build_alert_message(item, old_status, new_status)
    send_telegram(msg)
    send_discord(msg)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'GET':
        cfg = get_config()
        return jsonify({
            'alpha_configured': bool(cfg['ALPHA_VANTAGE_API_KEY']),
            'telegram_configured': bool(cfg['TELEGRAM_BOT_TOKEN'] and cfg['TELEGRAM_CHAT_ID']),
            'discord_configured': bool(cfg['DISCORD_WEBHOOK_URL'])
        })
    payload = request.json or {}
    save_env({
        'ALPHA_VANTAGE_API_KEY': payload.get('ALPHA_VANTAGE_API_KEY', ''),
        'TELEGRAM_BOT_TOKEN': payload.get('TELEGRAM_BOT_TOKEN', ''),
        'TELEGRAM_CHAT_ID': payload.get('TELEGRAM_CHAT_ID', ''),
        'DISCORD_WEBHOOK_URL': payload.get('DISCORD_WEBHOOK_URL', ''),
    })
    return jsonify({'ok': True})


@app.route('/api/stocks', methods=['GET', 'POST'])
def api_stocks():
    stocks = load_stocks()
    if request.method == 'GET':
        for item in stocks:
            item['rr'] = rr(item['entry'], item['stop'], item['target'])
        return jsonify(stocks)
    payload = request.json or {}
    item = {
        'id': int(datetime.utcnow().timestamp() * 1000),
        'symbol': payload['symbol'].strip().upper(),
        'company': payload['company'].strip(),
        'market': payload['market'],
        'api_symbol': payload['api_symbol'].strip().upper(),
        'entry': float(payload['entry']),
        'target': float(payload['target']),
        'stop': float(payload['stop']),
        'confidence': int(payload.get('confidence') or 0),
        'reason': payload['reason'].strip(),
        'price': None,
        'daily_change': None,
        'weekly_change': None,
        'status': 'مراقبة',
        'updated_at': '--',
        'last_alert_status': ''
    }
    stocks.insert(0, item)
    save_stocks(stocks)
    return jsonify(item)


@app.route('/api/stocks/<int:item_id>', methods=['PUT', 'DELETE'])
def api_stock_item(item_id):
    stocks = load_stocks()
    idx = next((i for i, x in enumerate(stocks) if x['id'] == item_id), None)
    if idx is None:
        return jsonify({'error': 'غير موجود'}), 404
    if request.method == 'DELETE':
        deleted = stocks.pop(idx)
        save_stocks(stocks)
        return jsonify({'ok': True, 'deleted': deleted})
    payload = request.json or {}
    current = stocks[idx]
    current.update({
        'symbol': payload['symbol'].strip().upper(),
        'company': payload['company'].strip(),
        'market': payload['market'],
        'api_symbol': payload['api_symbol'].strip().upper(),
        'entry': float(payload['entry']),
        'target': float(payload['target']),
        'stop': float(payload['stop']),
        'confidence': int(payload.get('confidence') or 0),
        'reason': payload['reason'].strip(),
    })
    save_stocks(stocks)
    return jsonify(current)


@app.route('/api/sync', methods=['POST'])
def api_sync():
    stocks = load_stocks()
    updated = []
    for item in stocks:
        price, daily = fetch_daily(item['api_symbol'])
        weekly = fetch_weekly(item['api_symbol'])
        old_status = item.get('status', '')
        item['price'] = round(price, 2)
        item['daily_change'] = daily
        item['weekly_change'] = weekly
        item['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        item['status'] = evaluate_status(item)
        notify_status_change(item, item.get('last_alert_status', ''), item['status'])
        item['last_alert_status'] = item['status']
        item['rr'] = rr(item['entry'], item['stop'], item['target'])
        updated.append({'symbol': item['symbol'], 'old_status': old_status, 'new_status': item['status']})
    save_stocks(stocks)
    return jsonify({'ok': True, 'items': updated, 'count': len(updated)})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
