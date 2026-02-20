# 🎓 QR Certificate System v6.0

> A complete event registration & certificate generation platform.  
> Attendees scan QR → register → get a beautiful Invitation Card instantly!  
> **Developed by Abdul Samad — SBBU Nawabshah, Pakistan**

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📱 QR Registration | Scan QR → instant digital form on any phone |
| 🎫 Invitation Cards | Auto-generated on every submission — instantly |
| 🎨 8 Color Themes | Royal Gold, Midnight Blue, Crimson, Emerald, Obsidian, Ocean Sapphire, Violet Luxury, Rose Gold |
| 👥 Smart Categories | Students, Teachers, Speakers, Businessmen, Guests, VIPs — each gets a tailored card |
| 🔢 Short Reg No | Clean alphanumeric: `P-0001`, `TC-0005`, `SP-0012` |
| 📲 Image Sharing | Download card as PNG → share on WhatsApp / Facebook / Instagram |
| 🏅 Certificates | Upload template, position name, bulk generate ZIP |
| 📊 Excel Export | Professional report with category summary sheet |
| 🔒 Secure Login | PBKDF2-SHA256 (310,000 iterations + 256-bit salt) |
| 💾 Auto Backup | Daily server backup + manual ZIP download + CSV restore |

---

## 🚀 Quick Start

### Install
```bash
pip install streamlit pillow qrcode[pil] reportlab openpyxl pandas
```

### Run
```bash
streamlit run app.py
```

### First Login
```
Default password:  Admin@2025
⚠️  Change immediately from sidebar after first login!
```

---

## ☁️ Deploy Free on Streamlit Cloud

```bash
git add app.py requirements.txt README.md
git commit -m "QR Certificate System v6"
git push
```

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. New App → GitHub repo → `app.py` → Deploy
3. Copy URL → Admin sidebar → Save Settings → Generate QR ✅

---

## 📁 File Structure

```
app.py                  ← Full application (single file)
requirements.txt        ← Dependencies
README.md               ← This file
registrations.csv       ← All data (auto-created)
config.json             ← Settings (auto-created)
auth.json               ← Hashed password (auto-created)
backups/                ← Daily auto-backups (auto-created)
```

---

## 🎫 Invitation Card

### 8 Themes
| Theme | Style |
|-------|-------|
| ✨ Royal Gold | Deep purple + Gold |
| 🌙 Midnight Blue | Dark navy + Sky blue |
| 🔴 Crimson Elite | Deep red + Coral |
| 💚 Emerald Prestige | Forest green + Mint |
| ⚫ Obsidian Gold | Black + Antique gold |
| 🌊 Ocean Sapphire | Deep teal + Cyan |
| 💜 Violet Luxury | Deep purple + Lavender |
| 🌹 Rose Gold | Dark rose + Copper |

### Smart Invite Phrases (Auto by Category)
| Category | Phrase on Card |
|----------|----------------|
| Teacher / Professor | *"You are cordially invited as"* |
| Speaker / Keynote | *"We are honored to welcome"* |
| Chief / Director / VIP | *"It is our privilege to invite"* |
| Judge / Panelist | *"You are invited to serve as"* |
| Business / Entrepreneur | *"We are pleased to welcome"* |
| Management / Volunteer | *"You are invited to participate as"* |
| Student / Participant | *"We are pleased to invite"* |

### Reg No Format
```
Participant    →  P-0001
Teacher        →  T-0003
Tech Committee →  TC-0007
Speaker        →  S-0002
```

---

## 📲 Share Card as Image (Not Link)

1. After registration → card appears on screen
2. Click **"⬇️ Download Invitation Card"**
3. Open WhatsApp / Facebook / Instagram
4. Tap attachment icon → select downloaded image → Send ✅

> Card is **1080×1620px PNG** — perfect for mobile & social media stories.

---

## 🔒 Security

| Property | Value |
|----------|-------|
| Algorithm | PBKDF2-HMAC-SHA256 |
| Iterations | 310,000 (OWASP 2024) |
| Salt | 256-bit random |
| Storage | Hashed in `auth.json` — never plaintext |
| Comparison | `hmac.compare_digest()` — timing-attack safe |

---

## 👨‍💻 Developer

### Abdul Samad
**Software Developer • AI/ML Enthusiast • Educator**

🎓 BS Computer Science — Shaheed Benazir Bhutto University (SBBU), Nawabshah

| | |
|-|-|
| 📷 Instagram | [@YOUR_HANDLE](https://instagram.com/YOUR_HANDLE) |
| 📘 Facebook | [YOUR_PROFILE](https://facebook.com/YOUR_PROFILE) |
| 💼 LinkedIn | [YOUR_PROFILE](https://linkedin.com/in/YOUR_PROFILE) |
| 🎵 TikTok | [@YOUR_HANDLE](https://tiktok.com/@YOUR_HANDLE) |
| 📞 Phone | +92-XXX-XXXXXXX |
| 📧 Email | your.email@example.com |

**Skills:** Python • Streamlit • Machine Learning • Computer Vision • Deep Learning • Data Analysis • FastAPI • Web Dev • AI & NLP • Pandas • NumPy • Git • UI/UX • Pillow • OpenCV • SQL

---

**Built with:** Python • Streamlit • Pillow • ReportLab • OpenPyXL

*© 2025 Abdul Samad — All Rights Reserved | Designed with ❤️ at SBBU Nawabshah*
