import os
import re
import time
import sqlite3
import datetime
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
from urllib.parse import unquote

# --- [মডিউল ১: চূড়ান্ত কনফিগারেশন] ---
BOT_TOKEN = "7993238689:AAF-rPCYskHj366TyQsozBmYBbWMzdpMSic"
CHANNEL_ID = "-1003026928669"  # নিশ্চিত করুন এই আইডিটি সঠিক

# সঠিকভাবে ফরম্যাট করা কুকিগুলো
COOKIES = {
    '_fbp': 'fb.1.1746727142785.984507864783834243',
    'cf_clearance': 'NGWed40DaqkeNnTo7R8JQKyV8h7Z5ajmYR3Igl6OdQA-1755452759-1.2.1.1-YoJh07NL5mRBqQBoK_5bwog5RQ48CHPnYisKrmcDymTDy.YHFaQyn3x74w0OwRiCBqTj9lDrwpDE5g7js.meezh08VFs9C16OeWbWCPqEIKcrMYtUbbPX9DbP96EaUniOwq8GBFOCkzyDdaM.OsFIyZHwF5WM0ny0Zz9_p4gqFNOu4seAsuaSWLbvtVQp4D9om4LWi9JT3RUUCNvxYutX30uyPhKFQCsmlxdT5LHkmM',
    'XSRF-TOKEN': 'eyJpdiI6IkJpSStDNUZRTFl2MEczZVF2QzZhSkE9PSIsInZhbHVlIjoiS3pXWnNsekVyNFJPTlZ4a1cxY240T3lCbXVKaXZ4TGVBRW9SajU0ZVRKTXA5dlZiZGx0WDNmYzU3aVNaVGlBTlR1RU1wSlhSUEliRTVseWU1QlFNRld0WGtvc1RzQlpWaVU4dm1zMUZGRTYzankyUnh4cWltNnpmckhjRVVWODMiLCJtYWMiOiIyZWVmYTg2ZWFmMTBkMzY4OTczNGVkMGZjMmU5NDAyZDc2YmE5Y2FhYWQzZDc2MGFlNjQ4NzM5YmJmMGFhNGVhIiwidGFnIjoiIn0=',
    'ivas_sms_session': 'eyJpdiI6ImJxZ2czelRqY2dHOHhWSkllVWtLT3c9PSIsInZhbHVlIjoiSElqQWU1U05SVXVseDBJMENWQ0JOaGhHdTlnaHJuRmc2S3M0ZkFqUWgvY2I3YnRlTjN5cjBudnRudDBKZzZDeFNBcElPVWZNZDJ4NU5IeU9TK0VWUXpGTHI3M1c1YlFZYUE3aFhtcEZFaGM2SVJhTjNaSnhCdkc2dlQwT1Z3d1MiLCJtYWMiOiIyYjIxNmJkYTE4OTk1NGUyNmY1YTBlOTk2MzM2MmM4NTU2NmY0MzM1ZTUyMzYyNjliY2Q3ZTdkNDA4NmFhYTBhIiwidGFnIjoiIn0='
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.ivasms.com/portal/live/my_sms',
    'Origin': 'https://www.ivasms.com',
    'X-XSRF-TOKEN': COOKIES['XSRF-TOKEN']
}
# --- [শেষ] কনফিগারেশন ---

# --- [মডিউল: ডেটাবেস ম্যানেজমেন্ট] ---
DATABASE_FILE = "otp_bot.db"

def db_connect():
    return sqlite3.connect(DATABASE_FILE, check_same_thread=False)

def setup_database():
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS processed_sms (sms_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

def is_sms_processed(sms_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_sms WHERE sms_id = ?", (sms_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_sms_to_db(sms_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO processed_sms (sms_id) VALUES (?)", (sms_id,))
    conn.commit()
    conn.close()
# --- [শেষ] ডেটাবেস ম্যানেজমেন্ট ---

# --- [মডিউল: হেল্পার ফাংশন] ---
def extract_otp(text):
    if not text: return None
    match = re.search(r'\b\d{4,8}\b', text.replace(" ", ""))
    if match: return match.group(0)
    return None
# --- [শেষ] হেল্পার ফাংশন ---

# --- [মডিউল: মূল বট কোড] ---
bot = telebot.TeleBot(BOT_TOKEN)

def get_all_live_sms():
    """একটি API কল ব্যবহার করে সমস্ত SMS ডেটা নিয়ে আসে"""
    url = "https://www.ivasms.com/portal/live/getNumbers"
    try:
        response = requests.post(url, headers=HEADERS, cookies=COOKIES, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, dict) and 'numbers' in data:
            return data.get("numbers", [])
        elif isinstance(data, list):
            return data
        else:
            print(f"[{datetime.datetime.now()}] [সতর্কতা] API থেকে অপ্রত্যাশিত রেসপন্স ফরম্যাট")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.datetime.now()}] [API ত্রুটি]: {str(e)}")
        return []

def check_sms_loop():
    """ব্যাকগ্রাউন্ডে SMS চেক করার জন্য থ্রেড"""
    while True:
        try:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [চেক] নতুন SMS এর জন্য চেক করা হচ্ছে...")
            all_sms = get_all_live_sms()

            if not all_sms:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [তথ্য] কোনো SMS পাওয়া যায়নি")
            
            for msg in reversed(all_sms):
                sms_id = msg.get("id")
                
                if sms_id and not is_sms_processed(sms_id):
                    phone_number = msg.get("number", "N/A")
                    full_message = msg.get("message", "N/A")
                    sender = msg.get("from", "N/A")
                    timestamp = msg.get('received_at_tz', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    
                    print(f"--> [নতুন SMS] নতুন SMS পাওয়া গেছে: ID {sms_id}")
                    otp = extract_otp(full_message)
                    
                    message_to_send = f"""
📩 <b>নতুন SMS</b> 📩

📞 <b>নম্বর:</b> <code>{phone_number}</code>
👤 <b>প্রেরক:</b> <code>{sender}</code>
"""
                    if otp:
                        message_to_send += f"🔢 <b>OTP:</b> <code>{otp}</code>\n"
                    
                    message_to_send += f"""
📝 <b>সম্পূর্ণ বার্তা:</b>
<pre>{full_message}</pre>

🕒 <b>সময়:</b> {timestamp}
"""
                    try:
                        bot.send_message(CHANNEL_ID, message_to_send, parse_mode='HTML')
                        add_sms_to_db(sms_id)
                        time.sleep(1)
                    except Exception as e:
                        print(f"[টেলিগ্রাম ত্রুটি] {datetime.datetime.now()}: {str(e)}")

            time.sleep(8)
            
        except Exception as e:
            print(f"[লুপ ত্রুটি] {datetime.datetime.now()}: {str(e)}")
            time.sleep(60)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🤖 SMS OTP বট এখন অনলাইনে আছে। মেসেজ প্রসেস করার জন্য প্রস্তুত।")

if __name__ == '__main__':
    print("IVASMS OTP বট চালু হচ্ছে...")
    setup_database()
    
    # স্টার্টআপ মেসেজ পাঠানোর চেষ্টা
    try:
        bot.send_message(CHANNEL_ID, "✅ **বট সফলভাবে অনলাইনে!**\n_নতুন SMS এর জন্য অপেক্ষা করা হচ্ছে..._", parse_mode='Markdown')
        print("✅ টেলিগ্রামে স্টার্টআপ মেসেজ সফলভাবে পাঠানো হয়েছে")
    except Exception as e:
        print(f"❌ [স্টার্টআপ ত্রুটি] টেলিগ্রামে স্টার্টআপ মেসেজ পাঠানো যায়নি: {e}")
        print("➡️ অনুগ্রহ করে BOT_TOKEN এবং CHANNEL_ID চেক করুন এবং নিশ্চিত করুন বটটি চ্যানেলের অ্যাডমিন")
        
    # ব্যাকগ্রাউন্ডে SMS চেকিং থ্রেড শুরু
    sms_thread = threading.Thread(target=check_sms_loop, daemon=True)
    sms_thread.start()
    
    # টেলিগ্রাম বট চালু রাখা
    print("🚀 বট সফলভাবে চলছে... বন্ধ করতে Ctrl+C চাপুন")
    bot.infinity_polling(timeout=123)
