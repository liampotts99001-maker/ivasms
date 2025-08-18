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
CHANNEL_ID = "-1003026928669" # <-- নিশ্চিত করুন এই আইডিটি সঠিক

# আপনার দেওয়া কার্যকরী কুকিগুলো
COOKIES = {
    'cf_clearance': 'NGWed40DaqkeNnTo7R8JQKyV8h7Z5ajmYR3Igl6OdQA-1755452759-1.2.1.1-YoJh07NL5mRBqQBoK_5bwog5RQ48CHPnYisKrmcDymTDy.YHFaQyn3x74w0OwRiCBqTj9lDrwpDE5g7js.meezh08VFs9C16OeWbWCPqEIKcrMYtUbbPX9DbP96EaUniOwq8GBFOCkzyDdaM.OsFIyZHwF5WM0ny0Zz9_p4gqFNOu4seAsuaSWLbvtVQp4D9om4LWi9JT3RUUCNvxYutX30uyPhKFQCsmlxdT5LHkmM',
    'XSRF-TOKEN': unquote('eyJpdiI6IlRYRnd0RU94RWc1T1ZEd2NNYmZEcnc9PSIsInZhbHVlIjoiclRGcjVrTUgrWDRYZ0dVWm5qOW1jTkdodDg1Qmt6SXIvdklTUFBOYW91WjE0Z0JLYnJCaFBYTzc3K1U4UU5nZjl2SkZUOVZNVFNoU29GbUtJcnovV2kzcVBNVnpkSi9rVktkZ21BQUhOWnY3dWhVUko1SlBUMDdiY0p6NXVMcmYiLCJtYWMiOiI3NjkxOWQyMjY1ZDE1YWVjOGFmOWMzNjI4OTZmNzM4YzUxZTA5OGE3ZDFjNTQwODBhODA3ZGE1OTQ3YzdmZDY2IiwidGFnIjoiIn0%3D'),
    'ivas_sms_session': unquote('eyJpdiI6IjZaTXJXcDdRa3kxdzY5ekZvSkVXeWc9PSIsInZhbHVlIjoiRFRyaDM3QnowMXRyejY5cWRqYi9WVzd3dFphUXFQYUFzWjJFZGpndmxLMFpBc2RvVTFTWVBNcHhBUDhFNEY2TGlXNEs3R0dTQlIzdXdWeHVRdTdWQ1l5b1ZWTFVLYWo1aEI1TE9OdXgrbGVYTTdxU3NDMzByZWZjZWs5YURxVkUiLCJtYWMiOiJjOWRjMTU5NzZiOGQ2YjIzMDJhNTllMTNhN2Y3MGYzZTAyMjI1ZjI3ZTQyMjg0ZjJlYWVkZDEzMmMyNDUzMWQ4IiwidGFnIjoiIn0%3D')
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.ivasms.com/portal/live/my_sms',
    'Origin': 'https://www.ivasms.com',
    'X-XSRF-TOKEN': COOKIES.get('XSRF-TOKEN')
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

# --- [মডিউল: মূল বট কোড] ---
bot = telebot.TeleBot(BOT_TOKEN)

def get_all_live_sms():
    """শুধুমাত্র একটি API কল ব্যবহার করে সমস্ত SMS ডেটা নিয়ে আসে (উন্নত)।"""
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
            print(f"[{datetime.datetime.now()}] [WARN] অপ্রত্যাশিত API রেসপন্স ফরম্যাট।")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.datetime.now()}] [API Error]: {str(e)}")
        return []

def check_sms_loop():
    """ব্যাকগ্রাউন্ডে নিয়মিত SMS চেক করার জন্য একটি থ্রেড।"""
    while True:
        try:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [CHECK] নতুন SMS-এর জন্য চেক করা হচ্ছে...")
            all_sms = get_all_live_sms()

            if not all_sms:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [INFO] কোনো SMS পাওয়া যায়নি।")
            
            for msg in reversed(all_sms):
                sms_id = msg.get("id")
                
                if sms_id and not is_sms_processed(sms_id):
                    phone_number = msg.get("number", "N/A")
                    full_message = msg.get("message", "N/A")
                    sender = msg.get("from", "N/A")
                    timestamp = msg.get('received_at_tz', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    
                    print(f"--> [NEW SMS] নতুন SMS পাওয়া গেছে: ID {sms_id}")
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
                        print(f"[Telegram Error] {datetime.datetime.now()}: {str(e)}")

            time.sleep(8)
            
        except Exception as e:
            print(f"[Loop Error] {datetime.datetime.now()}: {str(e)}")
            time.sleep(60)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🤖 SMS OTP বট এখন অনলাইন আছে কোড পাঠান ।")

if __name__ == '__main__':
    print("IVASMS OTP বট চালু হচ্ছে...")
    setup_database()
    
    # স্টার্টআপ মেসেজ পাঠানোর চেষ্টা করা
    try:
        bot.send_message(CHANNEL_ID, "✅ **বট সফলভাবে অনলাইন!**\n_নতুন SMS-এর জন্য অপেক্ষা করা হচ্ছে..._", parse_mode='Markdown')
        print("✅ টেলিগ্রামে স্টার্টআপ মেসেজ সফলভাবে পাঠানো হয়েছে।")
    except Exception as e:
        print(f"❌ [Startup Error] টেলিগ্রামে স্টার্টআপ মেসেজ পাঠানো সম্ভব হয়নি: {e}")
        print("➡️ অনুগ্রহ করে নিশ্চিত করুন BOT_TOKEN এবং CHANNEL_ID সঠিক আছে এবং বটটি চ্যানেলের অ্যাডমিন।")
        
    # ব্যাকগ্রাউন্ডে SMS চেকিং থ্রেড শুরু করা
    sms_thread = threading.Thread(target=check_sms_loop, daemon=True)
    sms_thread.start()
    
    # টেলিগ্রাম বটকে অবিরাম চালানোর জন্য
    print("🚀 বট সফলভাবে চলছে... Press Ctrl+C to stop.")
    bot.infinity_polling(timeout=123)
