"""
╔══════════════════════════════════════════════════════════════════╗
║   QR Certificate System  v6.0                                   ║
║   Developed by: Abdul Samad | SBBU Nawabshah                    ║
╠══════════════════════════════════════════════════════════════════╣
║   pip install streamlit pillow qrcode[pil] reportlab openpyxl pandas
║   streamlit run app.py                                          ║
╚══════════════════════════════════════════════════════════════════╝
v6.0:
  ✅ Short alphanumeric Reg No  (e.g. P-0012, TC-0005)
  ✅ Redesigned invitation card — theme-focused, beautiful typography
  ✅ Image-based sharing (card embedded as base64 in HTML share page)
  ✅ Organizer name on card + category-aware invite phrase
  ✅ Works for students, teachers, businessmen, speakers, guests etc.
  ✅ Full English UI on card
  ✅ Developer credits page with social links
  ✅ README page inside app
  ✅ Secure PBKDF2-SHA256 password (310k iterations)
  ✅ Persistent CSV + JSON data (survives restarts)
  ✅ Daily auto-backup + manual backup/restore
"""

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import qrcode
import io, zipfile, csv, os, json, base64, hashlib, hmac, secrets, shutil
import pandas as pd
import openpyxl
from openpyxl.styles import Font as XFont, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.utils import ImageReader
from datetime import datetime

# ══════════════════════════════════════════════════════════════════
#  FILE PATHS
# ══════════════════════════════════════════════════════════════════
DATA_FILE   = "registrations.csv"
CONFIG_FILE = "config.json"
AUTH_FILE   = "auth.json"
BACKUP_DIR  = "backups"
CSV_HEADERS = ["ref_no","name","roll_no","department","batch",
               "category","event","date","time"]

# ══════════════════════════════════════════════════════════════════
#  SECURE PASSWORD  (PBKDF2-HMAC-SHA256)
# ══════════════════════════════════════════════════════════════════
def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(),
                               salt.encode(), 310_000)
    return key.hex(), salt

def _verify_password(password, stored_hash, salt):
    candidate, _ = _hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)

def load_auth():
    if not os.path.exists(AUTH_FILE):
        h, s = _hash_password("Admin@2025")
        auth = {"hash":h,"salt":s,"created":datetime.now().isoformat(),
                "note":"Change password immediately after first login!"}
        with open(AUTH_FILE,"w") as f: json.dump(auth,f,indent=2)
        return auth
    with open(AUTH_FILE) as f: return json.load(f)

def save_password(new_password):
    h, s = _hash_password(new_password)
    auth  = load_auth()
    auth.update({"hash":h,"salt":s,"changed":datetime.now().isoformat()})
    with open(AUTH_FILE,"w") as f: json.dump(auth,f,indent=2)

def check_password(password):
    auth = load_auth()
    return _verify_password(password, auth["hash"], auth["salt"])

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
CFG_DEFAULTS = {
    "event_name":   "Certificate of Participation",
    "event_date":   datetime.now().strftime("%Y-%m-%d"),
    "event_venue":  "",
    "event_topic":  "",
    "organizer":    "",
    "categories":   "Participant,Teacher,Speaker,Management",
    "student_cats": "Participant",
    "app_url":      "",
    "inv_theme":    "royal_gold",
    "logo1_b64":    "",
    "logo2_b64":    "",
    "logo3_b64":    "",
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return CFG_DEFAULTS.copy()
    try:
        with open(CONFIG_FILE,"r",encoding="utf-8") as f:
            saved = json.load(f)
        out = CFG_DEFAULTS.copy(); out.update(saved); return out
    except: return CFG_DEFAULTS.copy()

def save_config(cfg):
    with open(CONFIG_FILE,"w",encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════════════════════════════
#  CSV DATABASE
# ══════════════════════════════════════════════════════════════════
def generate_ref_no(category):
    """Short alphanumeric: e.g. P-0042  TC-0017  SP-0003"""
    regs  = load_registrations()
    count = len(regs) + 1
    words = category.strip().split()
    code  = words[0][0].upper() if words else "R"
    if len(words) > 1: code += words[1][0].upper()
    return f"{code}-{count:04d}"

def save_registration(rec):
    exists = os.path.exists(DATA_FILE)
    with open(DATA_FILE,"a",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not exists: w.writeheader()
        w.writerow({k: rec.get(k,"") for k in CSV_HEADERS})

def load_registrations():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE,"r",encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except: return []

def clear_registrations():
    if os.path.exists(DATA_FILE): os.remove(DATA_FILE)

# ══════════════════════════════════════════════════════════════════
#  BACKUP
# ══════════════════════════════════════════════════════════════════
def create_backup():
    buf = io.BytesIO()
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for fname in [DATA_FILE, CONFIG_FILE]:
            if os.path.exists(fname): zf.write(fname, f"backup_{ts}/{fname}")
        zf.writestr(f"backup_{ts}/README.txt",
            f"Backup: {datetime.now().isoformat()}\n"
            "Restore: copy files back to app folder.\n"
            "auth.json excluded for security.")
    return buf.getvalue()

def auto_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bfile = os.path.join(BACKUP_DIR, f"backup_{datetime.now().strftime('%Y%m%d')}.zip")
    if not os.path.exists(bfile):
        with open(bfile,"wb") as f: f.write(create_backup())

# ══════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════════
st.set_page_config(page_title="QR Certificate Generator Pro",
                   page_icon="🎓", layout="wide",
                   initial_sidebar_state="expanded")

# ══════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
.stApp{background:linear-gradient(135deg,#0b132b 0%,#1c2541 100%);}
section[data-testid="stSidebar"]{background:#1e1b4b!important;}
section[data-testid="stSidebar"] *{color:#7ecefd!important;}
h1{color:#ffd159!important;text-align:center;}
h2,h3{color:#7ecefd!important;}
label,.stTextInput label,.stSelectbox label,
.stSlider label,.stTextArea label{color:#7ecefd!important;font-weight:600;}
p{color:#c5d8f0;}
.stTextInput>div>div>input,
.stNumberInput>div>div>input,
.stTextArea textarea{background:#0d1b35!important;color:white!important;
    border:1.5px solid #7ecefd55!important;border-radius:8px!important;font-size:1rem!important;}
.stTextInput>div>div>input:focus,.stTextArea textarea:focus{
    border-color:#7ecefd!important;box-shadow:0 0 0 2px #7ecefd33!important;}
.stSelectbox>div>div{background:#0d1b35!important;color:white!important;
    border:1.5px solid #7ecefd55!important;border-radius:8px!important;}
.stButton>button{background:linear-gradient(90deg,#2e6bef,#7ecefd)!important;
    color:white!important;border:none!important;border-radius:10px!important;
    font-weight:bold!important;font-size:1rem!important;padding:.6rem 1.2rem!important;transition:all .2s!important;}
.stButton>button:hover{opacity:.85!important;transform:scale(1.01)!important;}
.card{background:rgba(20,30,70,.92);border:1px solid #7ecefd33;border-radius:16px;padding:24px;margin:10px 0;}
.card-green{background:rgba(10,60,40,.9);border:1px solid #2ecc7166;border-radius:14px;padding:20px;margin:12px 0;}
.card-warn{background:rgba(80,40,0,.85);border:1px solid #f39c1266;border-radius:14px;padding:16px;margin:10px 0;}
.card-blue{background:rgba(10,40,80,.9);border:1px solid #3498db66;border-radius:14px;padding:18px;margin:10px 0;}
[data-testid="stMetricValue"]{color:#ffd159!important;font-size:2rem!important;}
[data-testid="stMetricLabel"]{color:#7ecefd!important;}
.stTabs [data-baseweb="tab"]{color:#7ecefd;background:#1e1b4b;border-radius:8px 8px 0 0;font-weight:600;}
.stTabs [aria-selected="true"]{background:#2e6bef!important;color:white!important;}
.stDataFrame{border-radius:10px;overflow:hidden;}
hr{border-color:#7ecefd22!important;}
/* Dev card */
.dev-card{background:linear-gradient(135deg,rgba(14,20,60,.98),rgba(8,12,38,.99));
    border:2px solid #ffd159;border-radius:24px;padding:40px 32px;text-align:center;}
.dev-avatar{font-size:5.5rem;display:block;margin-bottom:8px;}
.dev-name{font-size:2.6rem;font-weight:900;color:#ffd159;letter-spacing:3px;margin:10px 0 4px;}
.dev-title{font-size:1.05rem;color:#7ecefd;letter-spacing:1px;margin-bottom:6px;}
.dev-edu{font-size:1rem;color:#c5d8f0;margin:4px 0;}
.social-row{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin:20px 0;}
.soc-btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;
    border-radius:30px;font-weight:700;font-size:.9rem;text-decoration:none;
    transition:all .2s;border:none;}
.soc-btn:hover{transform:translateY(-3px);opacity:.92;}
.skill-row{display:flex;gap:9px;flex-wrap:wrap;justify-content:center;margin:14px 0;}
.skill{background:rgba(46,107,239,.3);border:1px solid #2e6bef66;color:#7ecefd;
    padding:6px 16px;border-radius:20px;font-size:.88rem;font-weight:600;}
.dev-divider{border:none;border-top:1px solid #ffd15933;margin:18px 0;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════
_cfg = load_config()
auto_backup()

# ══════════════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════════════
SESS = {
    "admin_auth":False,"template_bytes":None,"qr_data":None,
    "event_name":_cfg["event_name"],"event_date":_cfg["event_date"],
    "event_venue":_cfg["event_venue"],"event_topic":_cfg["event_topic"],
    "organizer":_cfg["organizer"],"categories":_cfg["categories"],
    "student_cats_input":_cfg["student_cats"],"app_url":_cfg["app_url"],
    "inv_theme":_cfg["inv_theme"],
    "logo1_b64":_cfg["logo1_b64"],"logo2_b64":_cfg["logo2_b64"],"logo3_b64":_cfg["logo3_b64"],
    "text_x":50,"text_y":60,"font_size":72,"text_color":"#1a1a1a","selected_font":"Arial Bold",
    "form_submitted":False,"last_submission":{},"invitation_png":None,
}
for k,v in SESS.items():
    if k not in st.session_state: st.session_state[k]=v

# ══════════════════════════════════════════════════════════════════
#  FONTS
# ══════════════════════════════════════════════════════════════════
FONTS = {
    "Arial Regular":["arial.ttf","DejaVuSans.ttf"],
    "Arial Bold":["arialbd.ttf","DejaVuSans-Bold.ttf"],
    "Arial Italic":["ariali.ttf","DejaVuSans-Oblique.ttf"],
    "Calibri Regular":["calibri.ttf","DejaVuSans.ttf"],
    "Calibri Bold":["calibrib.ttf","DejaVuSans-Bold.ttf"],
    "Tahoma Regular":["tahoma.ttf","DejaVuSans.ttf"],
    "Tahoma Bold":["tahomabd.ttf","DejaVuSans-Bold.ttf"],
    "Verdana Regular":["verdana.ttf","DejaVuSans.ttf"],
    "Verdana Bold":["verdanab.ttf","DejaVuSans-Bold.ttf"],
    "Trebuchet MS":["trebuc.ttf","DejaVuSans.ttf"],
    "Trebuchet Bold":["trebucbd.ttf","DejaVuSans-Bold.ttf"],
    "Segoe UI":["segoeui.ttf","DejaVuSans.ttf"],
    "Segoe UI Bold":["segoeuib.ttf","DejaVuSans-Bold.ttf"],
    "Times New Roman":["times.ttf","DejaVuSerif.ttf"],
    "Times New Roman Bold":["timesbd.ttf","DejaVuSerif-Bold.ttf"],
    "Times New Roman Italic":["timesi.ttf","DejaVuSerif-Italic.ttf"],
    "Georgia Regular":["georgia.ttf","DejaVuSerif.ttf"],
    "Georgia Bold":["georgiab.ttf","DejaVuSerif-Bold.ttf"],
    "Palatino Linotype":["pala.ttf","DejaVuSerif.ttf"],
    "Palatino Bold":["palab.ttf","DejaVuSerif-Bold.ttf"],
    "Book Antiqua":["bkant.ttf","DejaVuSerif.ttf"],
    "Garamond":["GARA.TTF","DejaVuSerif.ttf"],
    "Garamond Bold":["GARABD.TTF","DejaVuSerif-Bold.ttf"],
    "Courier New":["cour.ttf","DejaVuSansMono.ttf"],
    "Courier New Bold":["courbd.ttf","DejaVuSansMono-Bold.ttf"],
    "Consolas":["consola.ttf","DejaVuSansMono.ttf"],
    "Consolas Bold":["consolab.ttf","DejaVuSansMono-Bold.ttf"],
    "Century Gothic":["GOTHIC.TTF","DejaVuSans.ttf"],
    "Century Gothic Bold":["GOTHICB.TTF","DejaVuSans-Bold.ttf"],
    "Impact":["impact.ttf","DejaVuSans-Bold.ttf"],
    "Franklin Gothic":["framd.ttf","DejaVuSans-Bold.ttf"],
    "Candara Bold":["Candarab.ttf","DejaVuSans-Bold.ttf"],
    "Rockwell":["ROCK.TTF","DejaVuSerif.ttf"],
    "Rockwell Bold":["ROCKB.TTF","DejaVuSerif-Bold.ttf"],
    "Brush Script MT":["BRUSHSCI.TTF","DejaVuSerif-Italic.ttf"],
    "Lucida Handwriting":["lhandw.ttf","DejaVuSerif-Italic.ttf"],
    "Comic Sans MS":["comic.ttf","DejaVuSans.ttf"],
    "Comic Sans Bold":["comicbd.ttf","DejaVuSans-Bold.ttf"],
    "DejaVu Sans":["DejaVuSans.ttf","DejaVuSans.ttf"],
    "DejaVu Sans Bold":["DejaVuSans-Bold.ttf","DejaVuSans-Bold.ttf"],
    "DejaVu Serif":["DejaVuSerif.ttf","DejaVuSerif.ttf"],
    "DejaVu Serif Bold":["DejaVuSerif-Bold.ttf","DejaVuSerif-Bold.ttf"],
    "DejaVu Mono":["DejaVuSansMono.ttf","DejaVuSansMono.ttf"],
}
FONT_CATS = {
    "🔤 Sans Serif":[k for k in FONTS if any(x in k for x in ["Arial","Calibri","Tahoma","Verdana","Trebuchet","Segoe"])],
    "📜 Serif/Formal":[k for k in FONTS if any(x in k for x in ["Times","Georgia","Palatino","Book","Garamond"])],
    "💻 Monospace":[k for k in FONTS if any(x in k for x in ["Courier","Consolas"])],
    "✨ Display":[k for k in FONTS if any(x in k for x in ["Century","Impact","Franklin","Candara","Rockwell"])],
    "🖋️ Script":[k for k in FONTS if any(x in k for x in ["Brush","Handwriting","Comic"])],
    "🛡️ Fallback":[k for k in FONTS if "DejaVu" in k],
}

# ══════════════════════════════════════════════════════════════════
#  INVITATION CARD THEMES  — 8 rich themes
# ══════════════════════════════════════════════════════════════════
THEMES = {
    "royal_gold": {
        "bg":(12,8,32),"bg2":(28,18,60),"bg3":(45,30,90),
        "acc":(255,215,0),"acc2":(255,180,50),
        "txt":(255,255,255),"sub":(220,190,255),"brd":(140,90,220),
        "badge_bg":(255,215,0),"badge_txt":(20,10,50),
        "label":"✨ Royal Gold"
    },
    "midnight_blue": {
        "bg":(5,15,40),"bg2":(10,30,70),"bg3":(15,50,100),
        "acc":(100,180,255),"acc2":(60,140,220),
        "txt":(255,255,255),"sub":(160,210,255),"brd":(46,107,239),
        "badge_bg":(46,107,239),"badge_txt":(255,255,255),
        "label":"🌙 Midnight Blue"
    },
    "crimson_elite": {
        "bg":(25,5,10),"bg2":(55,10,20),"bg3":(80,20,30),
        "acc":(255,80,100),"acc2":(220,50,70),
        "txt":(255,255,255),"sub":(255,180,190),"brd":(180,40,60),
        "badge_bg":(200,30,50),"badge_txt":(255,255,255),
        "label":"🔴 Crimson Elite"
    },
    "emerald_prestige": {
        "bg":(5,22,15),"bg2":(8,45,28),"bg3":(12,70,42),
        "acc":(50,220,130),"acc2":(30,180,100),
        "txt":(255,255,255),"sub":(150,240,200),"brd":(30,160,90),
        "badge_bg":(20,150,80),"badge_txt":(255,255,255),
        "label":"💚 Emerald Prestige"
    },
    "obsidian_gold": {
        "bg":(8,8,8),"bg2":(20,18,14),"bg3":(30,26,18),
        "acc":(212,175,55),"acc2":(180,140,30),
        "txt":(255,255,255),"sub":(200,185,140),"brd":(180,145,40),
        "badge_bg":(180,145,40),"badge_txt":(10,8,5),
        "label":"⚫ Obsidian Gold"
    },
    "ocean_sapphire": {
        "bg":(3,25,40),"bg2":(5,50,70),"bg3":(8,75,100),
        "acc":(0,210,200),"acc2":(0,170,165),
        "txt":(255,255,255),"sub":(120,235,230),"brd":(0,160,155),
        "badge_bg":(0,180,175),"badge_txt":(5,30,40),
        "label":"🌊 Ocean Sapphire"
    },
    "violet_luxury": {
        "bg":(18,5,40),"bg2":(35,10,75),"bg3":(55,20,110),
        "acc":(200,130,255),"acc2":(170,100,230),
        "txt":(255,255,255),"sub":(220,180,255),"brd":(130,60,210),
        "badge_bg":(130,60,210),"badge_txt":(255,255,255),
        "label":"💜 Violet Luxury"
    },
    "rose_gold": {
        "bg":(30,12,18),"bg2":(55,22,30),"bg3":(80,35,45),
        "acc":(240,170,120),"acc2":(210,140,95),
        "txt":(255,255,255),"sub":(255,210,190),"brd":(190,100,70),
        "badge_bg":(200,110,75),"badge_txt":(255,255,255),
        "label":"🌹 Rose Gold"
    },
}
THEME_LABELS = {k: v["label"] for k,v in THEMES.items()}

# ══════════════════════════════════════════════════════════════════
#  CATEGORY → INVITE PHRASE (English)
# ══════════════════════════════════════════════════════════════════
def get_invite_phrase(category):
    c = category.lower()
    if any(x in c for x in ["teacher","professor","faculty","lecturer","principal"]):
        return "You are cordially invited as"
    elif any(x in c for x in ["speaker","keynote","presenter"]):
        return "We are honored to welcome"
    elif any(x in c for x in ["chief","director","ceo","vip","guest of honor"]):
        return "It is our privilege to invite"
    elif any(x in c for x in ["judge","panelist","reviewer","evaluator"]):
        return "You are invited to serve as"
    elif any(x in c for x in ["business","entrepreneur","sponsor","investor","industry"]):
        return "We are pleased to welcome"
    elif any(x in c for x in ["management","organizer","volunteer","coordinator"]):
        return "You are invited to participate as"
    elif any(x in c for x in ["alumni","graduate","ex-student"]):
        return "We warmly welcome our distinguished alumnus"
    else:
        return "We are pleased to invite"

# ══════════════════════════════════════════════════════════════════
#  PIL HELPERS
# ══════════════════════════════════════════════════════════════════
def _fnt(size, bold=False):
    cands = (["arialbd.ttf","DejaVuSans-Bold.ttf","calibrib.ttf","timesbd.ttf"]
             if bold else ["arial.ttf","DejaVuSans.ttf","calibri.ttf","times.ttf"])
    for f in cands:
        try: return ImageFont.truetype(f, size)
        except: pass
    return ImageFont.load_default()

def _rr(draw, x1,y1,x2,y2, r, fill, outline=None, ow=2):
    """Draw filled rounded rectangle with optional outline."""
    if x2 <= x1 or y2 <= y1: return
    r = min(r, (x2-x1)//2, (y2-y1)//2)
    draw.rectangle([x1+r,y1,x2-r,y2],fill=fill)
    draw.rectangle([x1,y1+r,x2,y2-r],fill=fill)
    for ex,ey in [(x1,y1),(x2-2*r,y1),(x1,y2-2*r),(x2-2*r,y2-2*r)]:
        draw.ellipse([ex,ey,ex+2*r,ey+2*r],fill=fill)
    if outline:
        for ex,ey,s,e in [(x1,y1,180,270),(x2-2*r,y1,270,360),
                           (x1,y2-2*r,90,180),(x2-2*r,y2-2*r,0,90)]:
            draw.arc([ex,ey,ex+2*r,ey+2*r],s,e,fill=outline,width=ow)
        draw.line([x1+r,y1,x2-r,y1],fill=outline,width=ow)
        draw.line([x1+r,y2,x2-r,y2],fill=outline,width=ow)
        draw.line([x1,y1+r,x1,y2-r],fill=outline,width=ow)
        draw.line([x2,y1+r,x2,y2-r],fill=outline,width=ow)

def _wrap_text(draw, text, font, max_w):
    """Word-wrap text, return list of lines."""
    words = text.split(); lines = []; cur = ""
    for w in words:
        test = (cur+" "+w).strip()
        if draw.textbbox((0,0),test,font=font)[2] > max_w:
            if cur: lines.append(cur)
            cur = w
        else: cur = test
    if cur: lines.append(cur)
    return lines if lines else [text]

def _gradient(draw, x1,y1,x2,y2, c1, c2, vertical=True):
    steps = (y2-y1) if vertical else (x2-x1)
    for i in range(max(1,steps)):
        a = i/max(1,steps-1)
        col = tuple(int(c1[j]*(1-a)+c2[j]*a) for j in range(3))
        if vertical: draw.line([(x1,y1+i),(x2,y1+i)],fill=col)
        else:        draw.line([(x1+i,y1),(x1+i,y2)],fill=col)

# ══════════════════════════════════════════════════════════════════
#  INVITATION CARD GENERATOR  — v6 Beautiful Design
# ══════════════════════════════════════════════════════════════════
def generate_invitation_card(rec, cfg, l1=None, l2=None, l3=None):
    W, H = 1080, 1620   # 2:3 ratio — perfect for phone screens & sharing

    th  = THEMES.get(cfg.get("inv_theme","royal_gold"), THEMES["royal_gold"])
    bg  = th["bg"];   bg2 = th["bg2"];  bg3 = th["bg3"]
    acc = th["acc"];  acc2= th["acc2"]
    txt = th["txt"];  sub = th["sub"];  brd = th["brd"]
    bbg = th["badge_bg"]; btxt= th["badge_txt"]

    img  = Image.new("RGB",(W,H),bg)
    draw = ImageDraw.Draw(img)

    # ── Full 3-stop gradient background ──────────────────────────
    mid = H//2
    _gradient(draw, 0,0,W,mid,   bg,  bg2, vertical=True)
    _gradient(draw, 0,mid,W,H,   bg2, bg3, vertical=True)

    # ── Decorative geometric background pattern ───────────────────
    # Large faint circles
    for cx,cy,cr,alpha in [(150,200,280,12),(W-120,H-300,320,10),(W//2,H//2,400,8)]:
        for dr in range(0,cr,24):
            opacity = max(0, alpha - dr//30)
            draw.ellipse([cx-dr,cy-dr,cx+dr,cy+dr],
                         outline=(*acc[:3], opacity), width=1)
    # Diagonal accent lines
    for xi in range(-200, W+200, 120):
        draw.line([(xi,0),(xi+300,H)], fill=(*brd[:3],14), width=1)

    # ── Double border frame ───────────────────────────────────────
    _rr(draw, 16,16, W-16,H-16, 36, bg2, outline=acc,  ow=3)
    _rr(draw, 26,26, W-26,H-26, 28, bg,  outline=brd,  ow=1)

    # ── Top gradient accent bar ───────────────────────────────────
    _gradient(draw, 16,16, W-16,28, acc2,acc, vertical=False)
    _gradient(draw, 16,H-28, W-16,H-16, acc,acc2, vertical=False)

    # ── Corner diamond ornaments ─────────────────────────────────
    for cx,cy in [(16+28,16+28),(W-16-28,16+28),(16+28,H-16-28),(W-16-28,H-16-28)]:
        sz = 18
        pts = [(cx,cy-sz),(cx+sz,cy),(cx,cy+sz),(cx-sz,cy)]
        draw.polygon(pts, fill=acc)
        draw.polygon([(cx,cy-sz//2),(cx+sz//2,cy),(cx,cy+sz//2),(cx-sz//2,cy)], fill=bg2)

    y = 70  # Y cursor

    # ── Logos ────────────────────────────────────────────────────
    LH   = 110
    lraw = [b for b in [l1,l2,l3] if b]
    limgs= []
    for lb in lraw:
        try:
            li = Image.open(io.BytesIO(lb)).convert("RGBA")
            r  = LH/li.height
            li = li.resize((max(1,int(li.width*r)),LH),Image.LANCZOS)
            limgs.append(li)
        except: pass

    if limgs:
        gap   = 48
        total = sum(l.width for l in limgs)+(len(limgs)-1)*gap
        xs    = (W-total)//2
        for li in limgs:
            img.paste(li,(xs,y),li); xs+=li.width+gap
    else:
        # Elegant graduation cap symbol
        cap_font = _fnt(90)
        draw.text((W//2, y+LH//2), "🎓", font=cap_font, fill=acc, anchor="mm")
    y += LH + 16

    # ── Organizer name  ───────────────────────────────────────────
    org = cfg.get("organizer","")
    if org:
        org_font = _fnt(26, True)
        draw.text((W//2, y), org.upper(), font=org_font, fill=acc, anchor="mt")
        y += 38

    # ── Gold rule line ────────────────────────────────────────────
    _gradient(draw, 80,y, W-80,y+3, acc2,acc, vertical=False); y += 14

    # ── "INVITATION" word ─────────────────────────────────────────
    draw.text((W//2,y), "✦  I N V I T A T I O N  ✦",
              font=_fnt(24), fill=sub, anchor="mt"); y += 46

    # ── Event name ───────────────────────────────────────────────
    ev_font = _fnt(56, True)
    ev_lines = _wrap_text(draw, cfg.get("event_name","Event"), ev_font, W-140)
    for ln in ev_lines:
        draw.text((W//2,y), ln, font=ev_font, fill=acc, anchor="mt"); y+=66
    y += 4

    # ── Topic pill ───────────────────────────────────────────────
    topic = cfg.get("event_topic","")
    if topic:
        tp_font = _fnt(26)
        tb  = draw.textbbox((0,0),topic,font=tp_font)
        tw_ = tb[2]-tb[0]+64
        _rr(draw, W//2-tw_//2,y, W//2+tw_//2,y+46, 23, brd)
        draw.text((W//2,y+23), topic, font=tp_font, fill=sub, anchor="mm"); y+=60
    y += 8

    # ── Thin divider ─────────────────────────────────────────────
    draw.rectangle([90,y,W-90,y+1], fill=(*brd[:3],120)); y += 20

    # ── Invite phrase (category-aware) ───────────────────────────
    phrase = get_invite_phrase(rec.get("category",""))
    draw.text((W//2,y), phrase, font=_fnt(27), fill=sub, anchor="mt"); y += 44

    # ── NAME — hero ───────────────────────────────────────────────
    name     = rec.get("name","Participant")
    nm_font  = _fnt(62, True)
    nm_lines = _wrap_text(draw, name, nm_font, W-120)
    name_h   = len(nm_lines)*72+32

    # Glowing name box
    _rr(draw, 44,y,W-44,y+name_h, 22, bg3, outline=acc, ow=3)
    # Inner shimmer
    _gradient(draw, 46,y+2, W-46,y+name_h//3, (*acc,8), (*bg3,0), vertical=True)

    ny = y + (name_h - len(nm_lines)*72)//2
    for ln in nm_lines:
        draw.text((W//2, ny+36), ln, font=nm_font, fill=acc, anchor="mm"); ny+=72
    y += name_h + 14

    # ── Category badge ────────────────────────────────────────────
    cat_text = rec.get("category","")
    cb   = draw.textbbox((0,0), cat_text, font=_fnt(30,True))
    cw   = cb[2]-cb[0]+90
    bx1  = W//2-cw//2; bx2 = W//2+cw//2
    _gradient(draw, bx1,y, bx2,y+56, acc,acc2, vertical=False)
    # Round corners manually
    for corner_x,corner_y in [(bx1,y),(bx2-56,y),(bx1,y+2),(bx2-56,y+2)]:
        pass  # gradient handles fill
    draw.text((W//2, y+28), cat_text, font=_fnt(30,True), fill=btxt, anchor="mm")
    y += 70

    # ── Details block ────────────────────────────────────────────
    y += 10
    dets = []
    if rec.get("department"): dets.append(("🏛  Department", rec["department"]))
    if rec.get("roll_no"):    dets.append(("🔢  Roll No",    rec["roll_no"]))
    if rec.get("batch"):      dets.append(("📅  Batch",      rec["batch"]))

    if dets:
        box_h = len(dets)*56+24
        _rr(draw, 46,y, W-46,y+box_h, 18, bg2, outline=brd, ow=1)
        dy = y+20
        for i,(lbl,val) in enumerate(dets):
            draw.text((100,dy), lbl, font=_fnt(24), fill=sub, anchor="lt")
            draw.text((W-100,dy), val, font=_fnt(26,True), fill=txt, anchor="rt")
            if i < len(dets)-1:
                draw.line([(100,dy+38),(W-100,dy+38)], fill=(*brd[:3],70), width=1)
            dy += 56
        y += box_h+16

    # ── Event info block ─────────────────────────────────────────
    y += 6
    evd = cfg.get("event_date","")
    try: evd = datetime.strptime(evd,"%Y-%m-%d").strftime("%B %d, %Y  (%A)")
    except: pass
    ev_items = [(i,v) for i,v in [
        ("📅  Date",      evd),
        ("📍  Venue",     cfg.get("event_venue","")),
        ("🏛  Organizer", cfg.get("organizer","")),
    ] if v]
    if ev_items:
        ev_box_h = len(ev_items)*50+24
        _rr(draw, 46,y, W-46,y+ev_box_h, 18, bg, outline=acc, ow=2)
        ey = y+18
        for icon,val in ev_items:
            ev_lines_w = _wrap_text(draw, f"{icon}:  {val}", _fnt(24), W-140)
            for ln in ev_lines_w:
                draw.text((W//2,ey), ln, font=_fnt(24), fill=sub, anchor="mt"); ey+=34
        y += ev_box_h+16

    # ── Reg No badge ─────────────────────────────────────────────
    y += 6
    ref      = rec.get("ref_no","—")
    reg_text = f"Reg No:  {ref}"
    rf_font  = _fnt(32, True)
    rb  = draw.textbbox((0,0),reg_text,font=rf_font)
    rw  = rb[2]-rb[0]+80
    rx1 = W//2-rw//2; rx2 = W//2+rw//2
    _rr(draw, rx1,y, rx2,y+62, 31, bbg)
    # Small shine strip
    _gradient(draw, rx1+4,y+4, rx2-4,y+18, (*txt,60),(*txt,0), vertical=True)
    draw.text((W//2,y+31), reg_text, font=rf_font, fill=btxt, anchor="mm"); y+=78

    # ── "Officially Registered" stamp ────────────────────────────
    draw.text((W//2,y), "✦  Officially Registered  ✦",
              font=_fnt(22), fill=sub, anchor="mt"); y+=34

    # ── Bottom bar ────────────────────────────────────────────────
    bar_y = H-62
    _gradient(draw, 16,bar_y, W-16,H-16, brd,bg2, vertical=True)
    _gradient(draw, 16,bar_y, W-16,bar_y+3, acc,acc2, vertical=False)
    footer_str = f"{cfg.get('organizer','')}  •  {cfg.get('event_date','')}"
    draw.text((W//2, bar_y+(H-16-bar_y)//2), footer_str,
              font=_fnt(21), fill=acc, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150,150))
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════════
#  CERTIFICATE GENERATOR
# ══════════════════════════════════════════════════════════════════
def load_pil_font(name, size):
    for path in FONTS.get(name,["DejaVuSans-Bold.ttf"]):
        try: return ImageFont.truetype(path,size)
        except: pass
    return ImageFont.load_default()

def hex_rgba(h,a=255):
    h=h.lstrip("#")
    return (int(h[0:2],16),int(h[2:4],16),int(h[4:6],16),a)

def generate_cert(name, template, cfg_c):
    img=Image.open(io.BytesIO(template)).convert("RGBA")
    w,h=img.size
    font=load_pil_font(cfg_c["font"],cfg_c["size"])
    px=int(w*cfg_c["x"]/100); py=int(h*cfg_c["y"]/100)
    layer=Image.new("RGBA",img.size,(255,255,255,0))
    draw=ImageDraw.Draw(layer)
    bbox=draw.textbbox((0,0),name,font=font)
    tw,th2=bbox[2]-bbox[0],bbox[3]-bbox[1]
    draw.text((px-tw//2,py-th2//2),name,font=font,fill=hex_rgba(cfg_c["color"]))
    out=Image.alpha_composite(img,layer).convert("RGB")
    buf=io.BytesIO(); out.save(buf,format="PNG",dpi=(300,300))
    return buf.getvalue()

def cert_to_pdf(png, name):
    buf=io.BytesIO(); pw,ph=landscape(A4)
    c=pdf_canvas.Canvas(buf,pagesize=(pw,ph))
    img=Image.open(io.BytesIO(png)).convert("RGB")
    iw,ih=img.size; sc=min(pw/iw,ph/ih); nw,nh=iw*sc,ih*sc
    tmp=io.BytesIO(); img.save(tmp,format="PNG"); tmp.seek(0)
    c.drawImage(ImageReader(tmp),(pw-nw)/2,(ph-nh)/2,nw,nh,mask="auto")
    c.setFont("Helvetica-Bold",9); c.setFillColorRGB(.5,.5,.5)
    c.drawCentredString(pw/2,14,
        f"{name}  |  {st.session_state.event_name}  |  {datetime.now().strftime('%Y-%m-%d')}")
    c.save(); return buf.getvalue()

def make_qr(url):
    qr=qrcode.QRCode(version=1,error_correction=qrcode.constants.ERROR_CORRECT_H,
                     box_size=10,border=4)
    qr.add_data(url); qr.make(fit=True)
    buf=io.BytesIO()
    qr.make_image(fill_color="#0b132b",back_color="white").save(buf,format="PNG")
    return buf.getvalue()

def cur_cfg():
    return {"x":st.session_state.text_x,"y":st.session_state.text_y,
            "size":st.session_state.font_size,"color":st.session_state.text_color,
            "font":st.session_state.selected_font}

# ══════════════════════════════════════════════════════════════════
#  EXCEL REPORT
# ══════════════════════════════════════════════════════════════════
def build_excel(regs):
    wb=openpyxl.Workbook()
    hf=PatternFill("solid",fgColor="1E1B4B"); hf2=PatternFill("solid",fgColor="0B132B")
    hfn=XFont(bold=True,color="FFFFFF",size=12)
    bdr=Border(bottom=Side(style="thin",color="334466"))
    ws=wb.active; ws.title="Registrations"
    ws.merge_cells("A1:I1"); t=ws["A1"]
    t.value=f"  {st.session_state.event_name} — Registration Data"
    t.font=XFont(bold=True,color="FFD159",size=14); t.fill=hf2
    t.alignment=Alignment(horizontal="center",vertical="center"); ws.row_dimensions[1].height=34
    ws.merge_cells("A2:I2"); info=ws["A2"]
    try: day=datetime.strptime(st.session_state.event_date,"%Y-%m-%d").strftime("%A")
    except: day=""
    info.value=(f"Date:{st.session_state.event_date}({day}) | "
                f"Venue:{st.session_state.event_venue} | "
                f"Organizer:{st.session_state.organizer} | Total:{len(regs)}")
    info.font=XFont(color="7ECEFD",size=10); info.fill=hf
    info.alignment=Alignment(horizontal="center"); ws.row_dimensions[2].height=18
    cols=[("Ref No",12),("#",5),("Full Name",28),("Roll No",14),
          ("Department",22),("Batch",12),("Category",16),("Date",14),("Time",10)]
    for ci,(h,w) in enumerate(cols,1):
        cell=ws.cell(row=3,column=ci,value=h)
        cell.font=hfn; cell.fill=hf
        cell.alignment=Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(ci)].width=w
    ws.row_dimensions[3].height=22
    for ri,rec in enumerate(regs,4):
        alt=PatternFill("solid",fgColor="0F1B35" if ri%2==0 else "1A2550")
        vals=[rec.get("ref_no",""),ri-3,rec.get("name",""),rec.get("roll_no",""),
              rec.get("department",""),rec.get("batch",""),rec.get("category",""),
              rec.get("date",""),rec.get("time","")]
        for ci,val in enumerate(vals,1):
            c=ws.cell(row=ri,column=ci,value=val)
            c.font=XFont(color="E0E0E0",size=11); c.fill=alt; c.border=bdr
            c.alignment=Alignment(horizontal="center" if ci in[1,2,7,8,9] else "left",vertical="center")
        ws.row_dimensions[ri].height=20
    ws2=wb.create_sheet("Summary")
    ws2.merge_cells("A1:C1"); t2=ws2["A1"]; t2.value="Category Summary"
    t2.font=XFont(bold=True,color="FFD159",size=13); t2.fill=hf2
    t2.alignment=Alignment(horizontal="center"); ws2.row_dimensions[1].height=28
    for ci,h in enumerate(["Category","Count","Members"],1):
        c=ws2.cell(row=2,column=ci,value=h); c.font=hfn; c.fill=hf
        c.alignment=Alignment(horizontal="center")
    cats={}
    for rec in regs: cats.setdefault(rec.get("category","Other"),[]).append(f"{rec.get('name','')}[{rec.get('roll_no','')}]")
    for ri,(cat,names) in enumerate(cats.items(),3):
        ws2.cell(row=ri,column=1,value=cat).font=XFont(bold=True,color="FFD159")
        ws2.cell(row=ri,column=2,value=len(names)).font=XFont(color="E0E0E0")
        ws2.cell(row=ri,column=3,value=", ".join(names)).font=XFont(color="E0E0E0")
        for col in range(1,4): ws2.cell(row=ri,column=col).fill=hf
    ws2.column_dimensions["A"].width=20; ws2.column_dimensions["B"].width=10; ws2.column_dimensions["C"].width=80
    buf=io.BytesIO(); wb.save(buf); return buf.getvalue()

def save_all_settings():
    save_config({
        "event_name":st.session_state.event_name,"event_date":st.session_state.event_date,
        "event_venue":st.session_state.event_venue,"event_topic":st.session_state.event_topic,
        "organizer":st.session_state.organizer,"categories":st.session_state.categories,
        "student_cats":st.session_state.student_cats_input,"app_url":st.session_state.app_url,
        "inv_theme":st.session_state.inv_theme,
        "logo1_b64":st.session_state.logo1_b64,
        "logo2_b64":st.session_state.logo2_b64,
        "logo3_b64":st.session_state.logo3_b64,
    })

# ══════════════════════════════════════════════════════════════════
#  ROUTING
# ══════════════════════════════════════════════════════════════════
qp   = st.query_params
page = qp.get("page","admin")

# ══════════════════════════════════════════════════════════════════
#  STUDENT FORM PAGE
# ══════════════════════════════════════════════════════════════════
if page == "form":
    cfg      = load_config()
    event    = cfg.get("event_name","Certificate Event")
    cats     = [c.strip() for c in cfg.get("categories","Participant").split(",") if c.strip()]
    s_cats   = [c.strip().lower() for c in cfg.get("student_cats","Participant").split(",")]
    l1b = base64.b64decode(cfg["logo1_b64"]) if cfg.get("logo1_b64") else None
    l2b = base64.b64decode(cfg["logo2_b64"]) if cfg.get("logo2_b64") else None
    l3b = base64.b64decode(cfg["logo3_b64"]) if cfg.get("logo3_b64") else None

    # Header
    st.markdown(f"""
    <div style="text-align:center;padding:24px 0 8px;">
      <div style="font-size:3rem;">🎓</div>
      <h1 style="color:#ffd159;font-size:2rem;margin:8px 0;">{event}</h1>
      <p style="color:#7ecefd;margin:4px 0;font-size:1rem;">
        {'📍 '+cfg.get('event_venue','') if cfg.get('event_venue') else ''}
        {'&nbsp; | &nbsp; 📅 '+cfg.get('event_date','') if cfg.get('event_date') else ''}
      </p>
      <p style="color:#7ecefd88;font-size:.9rem;">Organized by {cfg.get('organizer','')}</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    # ── CONFIRMATION + INVITATION CARD ───────────────────────────
    if st.session_state.get("form_submitted") and st.session_state.get("invitation_png"):
        rec     = st.session_state.last_submission
        inv_png = st.session_state.invitation_png

        st.markdown("""
        <div style="text-align:center;padding:10px 0;">
          <h2 style="color:#2ecc71;margin:0;">🎉 Registration Successful!</h2>
          <p style="color:#7ecefd;font-size:1.1rem;margin:8px 0;">
            Your Invitation Card is ready — download &amp; share!
          </p>
        </div>
        """, unsafe_allow_html=True)

        # ── Card display centered ─────────────────────────────────
        _,mid,_ = st.columns([1,3,1])
        with mid:
            st.image(inv_png, use_container_width=True)

        st.markdown("---")

        # ── Download button (image file — not link) ───────────────
        ref = rec.get("ref_no","")
        fn  = f"Invitation_{rec.get('name','').replace(' ','_')}_{ref}.png"

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️  Download Invitation Card",
                data=inv_png, file_name=fn,
                mime="image/png", use_container_width=True)
        with c2:
            # WhatsApp — text + instruction to share the downloaded image
            wa_msg = (
                f"🎓 *{event}*%0A%0A"
                f"I have successfully registered!%0A"
                f"👤 *Name:* {rec.get('name','')}%0A"
                f"🏷️ *Category:* {rec.get('category','')}%0A"
                f"🆔 *Reg No:* {ref}%0A"
                f"📅 *Date:* {cfg.get('event_date','')}%0A"
                f"📍 *Venue:* {cfg.get('event_venue','')}%0A%0A"
                f"_(Download my invitation card above)_")
            st.markdown(
                f'<a href="https://api.whatsapp.com/send?text={wa_msg}" target="_blank"'
                f' style="display:block;text-align:center;'
                f'background:linear-gradient(90deg,#25D366,#128C7E);'
                f'color:white;font-weight:bold;font-size:1rem;'
                f'padding:.7rem;border-radius:10px;text-decoration:none;">'
                f'📲 Share on WhatsApp</a>', unsafe_allow_html=True)

        # ── Share image tip ───────────────────────────────────────
        st.markdown("""
        <div class="card-blue" style="text-align:center;padding:14px;margin-top:10px;">
          💡 <b>How to share your card as IMAGE:</b><br>
          <small style="color:#7ecefd;">
            1. Download card above &nbsp;→&nbsp;
            2. Open WhatsApp / Facebook / Instagram &nbsp;→&nbsp;
            3. Attach the downloaded image &nbsp;→&nbsp; Share! 📸
          </small>
        </div>
        """, unsafe_allow_html=True)

        # ── Social share ─────────────────────────────────────────
        st.markdown("#### 🔗 Share on Social Media")
        s1,s2,s3 = st.columns(3)
        app_url  = cfg.get("app_url","")
        with s1:
            st.markdown(
                f'<a href="https://www.facebook.com/sharer/sharer.php?u={app_url}" '
                f'target="_blank" style="display:block;text-align:center;'
                f'background:#1877F2;color:white;font-weight:bold;'
                f'padding:.6rem;border-radius:10px;text-decoration:none;">'
                f'📘 Facebook</a>', unsafe_allow_html=True)
        with s2:
            st.markdown(
                f'<a href="https://www.linkedin.com/sharing/share-offsite/?url={app_url}" '
                f'target="_blank" style="display:block;text-align:center;'
                f'background:#0A66C2;color:white;font-weight:bold;'
                f'padding:.6rem;border-radius:10px;text-decoration:none;">'
                f'💼 LinkedIn</a>', unsafe_allow_html=True)
        with s3:
            tw = f"I just registered for {event}! Reg No: {ref}"
            st.markdown(
                f'<a href="https://twitter.com/intent/tweet?text={tw}" '
                f'target="_blank" style="display:block;text-align:center;'
                f'background:#1DA1F2;color:white;font-weight:bold;'
                f'padding:.6rem;border-radius:10px;text-decoration:none;">'
                f'🐦 Twitter / X</a>', unsafe_allow_html=True)

        # ── Details ──────────────────────────────────────────────
        st.markdown("---")
        with st.expander("📋 View Registration Details"):
            r = rec
            st.markdown(f"""
| Field | Value |
|-------|-------|
| 🆔 Reg No | `{r.get('ref_no','')}` |
| 👤 Name | {r.get('name','')} |
| 🏷️ Category | {r.get('category','')} |
| 🏫 Department | {r.get('department','—')} |
| 🔢 Roll No | {r.get('roll_no','—')} |
| 📅 Batch | {r.get('batch','—')} |
| 🗓️ Date | {r.get('date','')} |
| 🕐 Time | {r.get('time','')} |
""")

        if st.button("🔄 New Registration", use_container_width=True):
            st.session_state.form_submitted  = False
            st.session_state.last_submission = {}
            st.session_state.invitation_png  = None
            st.rerun()

    # ── FORM ─────────────────────────────────────────────────────
    else:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("#### 📝 Fill Your Details")

        c1,c2 = st.columns(2)
        with c1:
            name = st.text_input("👤 Full Name ✱", placeholder="Muhammad Ali Khan")
            dept = st.text_input("🏫 Department / Organization",
                                  placeholder="Computer Science / XYZ Company")
        with c2:
            category = st.selectbox("🏷️ Category ✱", cats)
            is_stud  = category.lower() in s_cats
            rollno   = st.text_input(
                "🔢 Roll No" + (" ✱" if is_stud else " (Optional)"),
                placeholder="CS-2022-45" if is_stud else "N/A")
            batch = st.text_input(
                "📅 Batch / Year" + (" ✱" if is_stud else " (Optional)"),
                placeholder="2022-2026" if is_stud else "—") if is_stud else ""

        st.markdown("---")
        if st.button("✅  Submit Registration", use_container_width=True):
            n=name.strip(); r=rollno.strip(); d=dept.strip()
            b=batch.strip() if batch else ""
            missing=[]
            if not n: missing.append("Full Name")
            if is_stud and not r: missing.append("Roll No")
            if is_stud and not b: missing.append("Batch")
            if missing:
                st.error("❌ Required fields missing: **" + "  |  ".join(missing) + "**")
            else:
                now    = datetime.now()
                ref_no = generate_ref_no(category)
                rec    = {"ref_no":ref_no,"name":n,"roll_no":r,"department":d,
                          "batch":b,"category":category,"event":event,
                          "date":now.strftime("%Y-%m-%d"),"time":now.strftime("%H:%M:%S")}
                save_registration(rec)
                inv_png = generate_invitation_card(rec, cfg, l1b, l2b, l3b)
                st.session_state.form_submitted  = True
                st.session_state.last_submission = rec
                st.session_state.invitation_png  = inv_png
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<p style="text-align:center;color:#7ecefd33;font-size:.8rem;margin-top:20px;">'
        'Developed by Abdul Samad Rind— SBBU SBA</p>', unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════
#  ADMIN PAGE
# ══════════════════════════════════════════════════════════════════
st.markdown("# 🎓 QR Certificate Gtor Pro V3.01")
st.markdown('<p style="text-align:center;color:#7ecefd;">Abdul Samad | SBBU Nawabshah</p>',
            unsafe_allow_html=True)
st.markdown("---")

# ── Auth ─────────────────────────────────────────────────────────
if not st.session_state.admin_auth:
    _,col,_ = st.columns([1,2,1])
    with col:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🔐 Admin Login")
        if not os.path.exists(AUTH_FILE):
            st.markdown('<div class="card-warn">🔑 <b>First Run!</b> Default: <code>Admin@2025</code><br>Change immediately after login!</div>', unsafe_allow_html=True)
        pwd = st.text_input("Password", type="password")
        if st.button("🔓 Login", use_container_width=True):
            if check_password(pwd):
                st.session_state.admin_auth=True; st.rerun()
            else: st.error("❌ Wrong password!")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 Event Settings")
    st.session_state.event_name  = st.text_input("Event Name",         st.session_state.event_name)
    st.session_state.event_topic = st.text_input("Topic",              st.session_state.event_topic)
    st.session_state.event_date  = st.text_input("Date (YYYY-MM-DD)",  st.session_state.event_date)
    st.session_state.event_venue = st.text_input("Venue",              st.session_state.event_venue)
    st.session_state.organizer   = st.text_input("Organizer",          st.session_state.organizer)
    st.session_state.categories  = st.text_input("Categories (comma)", st.session_state.categories)
    st.session_state.student_cats_input = st.text_input(
        "Student categories", st.session_state.student_cats_input)
    st.markdown("---")
    st.markdown("## 🌐 App URL")
    st.session_state.app_url = st.text_input("Deployed URL",
        value=st.session_state.app_url, placeholder="https://yourname-app.streamlit.app")
    if st.button("💾 Save All Settings", use_container_width=True):
        save_all_settings(); st.success("✅ Saved!")
    st.markdown("---")
    st.markdown("## 🎨 Certificate Text")
    st.session_state.font_size  = st.slider("Font Size",         20,250,st.session_state.font_size)
    st.session_state.text_x    = st.slider("Horizontal % (←→)", 0,100, st.session_state.text_x)
    st.session_state.text_y    = st.slider("Vertical %   (↑↓)", 0,100, st.session_state.text_y)
    st.session_state.text_color= st.color_picker("Text Color",  st.session_state.text_color)
    st.markdown("---")
    st.markdown("## 🎨 Invitation Card Theme")
    st.session_state.inv_theme = st.selectbox(
        "Theme", list(THEMES.keys()),
        format_func=lambda x: THEME_LABELS[x],
        index=list(THEMES.keys()).index(
            st.session_state.inv_theme if st.session_state.inv_theme in THEMES else "royal_gold"))
    st.markdown("**Logos (up to 3):**")
    for li,lkey in enumerate(["logo1_b64","logo2_b64","logo3_b64"],1):
        lupl=st.file_uploader(f"Logo {li}",type=["png","jpg","jpeg"],key=f"lu{li}")
        if lupl:
            st.session_state[lkey]=base64.b64encode(lupl.read()).decode()
            st.success(f"✅ Logo {li} saved!")
        elif st.session_state.get(lkey):
            try: st.image(base64.b64decode(st.session_state[lkey]),width=65)
            except: pass
            if st.button(f"🗑️ Remove",key=f"rm{li}"):
                st.session_state[lkey]=""; st.rerun()
    st.markdown("---")
    st.markdown("## 🔤 Font")
    sq=st.text_input("🔍 Search font...",placeholder="bold, times, gothic")
    all_fonts=list(FONTS.keys())
    if sq.strip():
        matched=[f for f in all_fonts if sq.strip().lower() in f.lower()]
        if matched:
            idx=matched.index(st.session_state.selected_font) if st.session_state.selected_font in matched else 0
            st.session_state.selected_font=st.selectbox("Results:",matched,index=idx,key="fss")
        else: st.warning("No fonts found")
    else:
        for cl,cf in FONT_CATS.items():
            if not cf: continue
            with st.expander(cl,expanded="Sans" in cl):
                for fn in cf:
                    lbl=("✅ " if st.session_state.selected_font==fn else "")+fn
                    if st.button(lbl,key=f"fb_{fn}",use_container_width=True):
                        st.session_state.selected_font=fn; st.rerun()
    st.markdown(f"**Selected:** `{st.session_state.selected_font}`")
    st.markdown("---")
    with st.expander("🔑 Change Password"):
        st.caption("Strong password: 8+ chars, uppercase, numbers, symbols")
        cur_p=st.text_input("Current",type="password",key="cp")
        new_p=st.text_input("New",type="password",key="np")
        cnf_p=st.text_input("Confirm",type="password",key="cfp")
        if st.button("🔒 Update",use_container_width=True):
            if not check_password(cur_p): st.error("❌ Wrong current password!")
            elif len(new_p)<8: st.error("❌ Min 8 characters!")
            elif new_p!=cnf_p: st.error("❌ Passwords don't match!")
            elif new_p==cur_p: st.warning("⚠️ Same as current!")
            else: save_password(new_p); st.success("✅ Password updated securely!")
    if st.button("🚪 Logout"):
        st.session_state.admin_auth=False; st.rerun()

# ══════════════════════════════════════════════════════════════════
#  ADMIN TABS
# ══════════════════════════════════════════════════════════════════
tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8,tab9 = st.tabs([
    "🔳 QR Generate",
    "📊 Registrations",
    "🃏 Invitation Card",
    "🖼️ Certificate",
    "🚀 Bulk Generate",
    "💾 Backup & Security",
    "☁️ Deploy Guide",
    "👨‍💻 Developer",
    "📖 README",
])

# ─────────────────────────────────────────────
#  TAB 1 — QR Generate
# ─────────────────────────────────────────────
with tab1:
    cl,cr=st.columns(2)
    with cl:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🔳 Registration QR Code")
        if st.session_state.app_url:
            st.markdown(f'<div class="card-blue">✅ <b>URL:</b><br><code style="color:#ffd159;">{st.session_state.app_url}</code></div>', unsafe_allow_html=True)
            qr_url=f"{st.session_state.app_url.rstrip('/')}/?page=form"
            if st.button("🔳 Refresh QR"): st.session_state.qr_data=make_qr(qr_url)
            if not st.session_state.qr_data: st.session_state.qr_data=make_qr(qr_url)
            st.image(st.session_state.qr_data,width=260)
            st.download_button("⬇️ Download QR",st.session_state.qr_data,
                file_name="registration_qr.png",mime="image/png",use_container_width=True)
            st.code(qr_url,language=None)
        else:
            st.markdown('<div class="card-warn">⚠️ Set App URL in sidebar first!</div>', unsafe_allow_html=True)
        st.markdown('</div>',unsafe_allow_html=True)
    with cr:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 📱 Registration Flow")
        st.markdown("""
**Student scans QR → Form → Submit → Instant Card!**

| Step | Action |
|------|--------|
| 1 | 📱 Scan QR code |
| 2 | 📝 Fill Name, Dept, Roll No |
| 3 | 🏷️ Select Category |
| 4 | ✅ Submit |
| 5 | 🎉 Invitation Card instantly! |
| 6 | 📲 Download & Share |

**Works for:** Students, Teachers, Speakers, Businessmen, Guests, Alumni, VIPs...
        """)
        st.markdown('</div>',unsafe_allow_html=True)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### ✏️ Manual Entry")
        with st.form("mf"):
            m1,m2=st.columns(2)
            with m1: mn=st.text_input("Name"); md=st.text_input("Department")
            with m2: mr=st.text_input("Roll No"); mb=st.text_input("Batch")
            mcl=[c.strip() for c in st.session_state.categories.split(",") if c.strip()]
            mc=st.selectbox("Category",mcl)
            if st.form_submit_button("➕ Add",use_container_width=True):
                if mn.strip():
                    now=datetime.now(); ref=generate_ref_no(mc)
                    save_registration({"ref_no":ref,"name":mn.strip(),"roll_no":mr.strip(),
                        "department":md.strip(),"batch":mb.strip(),"category":mc,
                        "event":st.session_state.event_name,
                        "date":now.strftime("%Y-%m-%d"),"time":now.strftime("%H:%M:%S")})
                    st.success(f"✅ {mn} added!")
                else: st.error("Name required!")
        st.markdown('</div>',unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  TAB 2 — Registrations
# ─────────────────────────────────────────────
with tab2:
    regs=load_registrations()
    st.markdown("### 📊 Registration Data")
    if st.button("🔄 Refresh"): st.rerun()
    cat_list=[c.strip() for c in st.session_state.categories.split(",") if c.strip()]
    mcols=st.columns(min(len(cat_list)+1,6))
    mcols[0].metric("Total",len(regs))
    for i,cat in enumerate(cat_list[:5]):
        mcols[i+1].metric(cat,sum(1 for r in regs if r.get("category","")==cat))
    st.markdown("---")
    if regs:
        df=pd.DataFrame(regs)
        rename={"ref_no":"Reg No","name":"Full Name","roll_no":"Roll No",
                "department":"Department","batch":"Batch","category":"Category",
                "event":"Event","date":"Date","time":"Time"}
        df=df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
        fc=st.selectbox("Filter:",["All"]+cat_list,key="flt")
        st.dataframe(df if fc=="All" else df[df["Category"]==fc],
                     use_container_width=True,height=380)
        st.markdown("---")
        e1,e2,e3=st.columns(3)
        with e1:
            st.download_button("📊 Excel",build_excel(regs),
                file_name=f"{st.session_state.event_name.replace(' ','_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        with e2:
            st.download_button("📄 TXT",
                "\n".join(f"{r.get('ref_no','')}|{r['name']}|{r.get('roll_no','')}|{r.get('department','')}|{r.get('category','')}" for r in regs).encode(),
                file_name="registrations.txt",mime="text/plain",use_container_width=True)
        with e3:
            if st.button("🗑️ Clear All",use_container_width=True):
                clear_registrations(); st.success("Cleared!"); st.rerun()
    else:
        st.info("📭 No registrations yet.")

# ─────────────────────────────────────────────
#  TAB 3 — Invitation Card
# ─────────────────────────────────────────────
with tab3:
    st.markdown("### 🃏 Invitation Card — Preview & Batch")
    cfg_n=load_config(); cfg_n["inv_theme"]=st.session_state.inv_theme
    l1b=base64.b64decode(st.session_state.logo1_b64) if st.session_state.logo1_b64 else None
    l2b=base64.b64decode(st.session_state.logo2_b64) if st.session_state.logo2_b64 else None
    l3b=base64.b64decode(st.session_state.logo3_b64) if st.session_state.logo3_b64 else None

    st.info(f"Theme: **{THEME_LABELS.get(st.session_state.inv_theme,'—')}** | "
            f"Logos: **{sum(1 for x in [l1b,l2b,l3b] if x)}** uploaded | "
            f"Change in sidebar → Save Settings")

    pc1,pc2,pc3=st.columns(3)
    with pc1: pname=st.text_input("Preview name:","Muhammad Ali Khan",key="inv_pn")
    with pc2:
        pcatl=[c.strip() for c in st.session_state.categories.split(",") if c.strip()]
        pcat=st.selectbox("Category:",pcatl,key="inv_pc")
    with pc3: proll=st.text_input("Roll No:","CS-2022-45",key="inv_pr")

    pdept=st.text_input("Department/Organization:","Computer Science",key="inv_pd")
    srec={"ref_no":"P-0001","name":pname,"roll_no":proll,"department":pdept,
          "batch":"2022-2026","category":pcat,"event":st.session_state.event_name,
          "date":datetime.now().strftime("%Y-%m-%d")}
    iprev=generate_invitation_card(srec,cfg_n,l1b,l2b,l3b)
    _,mid,_=st.columns([1,3,1])
    with mid: st.image(iprev,use_container_width=True,caption="Preview")
    pd1,pd2=st.columns(2)
    with pd1:
        st.download_button("⬇️ Preview Download",iprev,
            file_name=f"Preview_{pname.replace(' ','_')}.png",
            mime="image/png",use_container_width=True)
    with pd2:
        if st.button("💾 Save Theme",use_container_width=True):
            save_all_settings(); st.success("✅ Saved!")
    st.markdown("---")
    regs_inv=load_registrations()
    if regs_inv:
        if st.button(f"🚀 Generate All {len(regs_inv)} Invitation Cards",use_container_width=True):
            p=st.progress(0); s=st.empty(); bz=io.BytesIO()
            with zipfile.ZipFile(bz,"w",zipfile.ZIP_DEFLATED) as zf:
                for i,rec in enumerate(regs_inv):
                    s.markdown(f"⏳ **{rec.get('name','')}** ({i+1}/{len(regs_inv)})")
                    card=generate_invitation_card(rec,cfg_n,l1b,l2b,l3b)
                    zf.writestr(f"Invitations/{rec.get('category','Other')}/{rec.get('ref_no','')}-{rec.get('name','')}.png",card)
                    p.progress((i+1)/len(regs_inv))
            s.success("✅ Done!")
            st.download_button("⬇️ All Cards ZIP",bz.getvalue(),
                file_name="All_Invitations.zip",mime="application/zip",use_container_width=True)
    else: st.info("No registrations yet.")

# ─────────────────────────────────────────────
#  TAB 4 — Certificate Preview
# ─────────────────────────────────────────────
with tab4:
    cl,cr=st.columns(2)
    with cl:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🖼️ Template Upload")
        tpl=st.file_uploader("Template (.png/.jpg)",type=["png","jpg","jpeg"])
        if tpl:
            st.session_state.template_bytes=tpl.read()
            img_t=Image.open(io.BytesIO(st.session_state.template_bytes))
            st.success(f"✅ {tpl.name} — {img_t.width}×{img_t.height}px")
        if st.session_state.template_bytes:
            st.image(st.session_state.template_bytes,use_container_width=True)
        st.markdown('</div>',unsafe_allow_html=True)
    with cr:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 👁️ Live Preview")
        if st.session_state.template_bytes:
            pn=st.text_input("Preview name:","Muhammad Ali Khan",key="cpn")
            pp=generate_cert(pn,st.session_state.template_bytes,cur_cfg())
            st.image(pp,use_container_width=True)
            a,b_=st.columns(2)
            with a: st.download_button("⬇️ PNG",pp,file_name=f"{pn}.png",mime="image/png",use_container_width=True)
            with b_: st.download_button("⬇️ PDF",cert_to_pdf(pp,pn),file_name=f"{pn}.pdf",mime="application/pdf",use_container_width=True)
        else: st.warning("Upload template first")
        st.markdown('</div>',unsafe_allow_html=True)
    regs_p=load_registrations()
    if st.session_state.template_bytes and regs_p:
        st.markdown("---"); st.markdown("### 👁️ Preview All")
        names_all=[r["name"] for r in regs_p]
        sn=st.slider("How many?",1,min(len(names_all),24),min(6,len(names_all)))
        for i in range(0,sn,3):
            rn=names_all[i:i+3]; cs=st.columns(3)
            for ci,nm in enumerate(rn):
                with cs[ci]:
                    pv=generate_cert(nm,st.session_state.template_bytes,cur_cfg())
                    st.image(pv,caption=nm,use_container_width=True)
                    st.download_button(f"⬇️ {nm[:14]}",pv,file_name=f"{nm}.png",mime="image/png",key=f"pv_{i}_{ci}")

# ─────────────────────────────────────────────
#  TAB 5 — Bulk Generate
# ─────────────────────────────────────────────
with tab5:
    st.markdown("### 🚀 Bulk Certificate Generation")
    regs=load_registrations()
    if not st.session_state.template_bytes:
        st.markdown('<div class="card-warn">⚠️ Upload template in Tab 4 first!</div>',unsafe_allow_html=True)
    elif not regs:
        st.markdown('<div class="card-warn">⚠️ No registrations yet.</div>',unsafe_allow_html=True)
    else:
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Total",len(regs)); c2.metric("Font",st.session_state.selected_font[:14])
        c3.metric("Size",st.session_state.font_size); c4.metric("Pos",f"{st.session_state.text_x}%,{st.session_state.text_y}%")
        f1,f2=st.columns(2)
        with f1: do_png=st.checkbox("PNG",value=True)
        with f2: do_pdf=st.checkbox("PDF",value=True)
        if st.button(f"🚀 Generate All {len(regs)}",use_container_width=True):
            cn=cur_cfg(); p=st.progress(0); s=st.empty(); bz=io.BytesIO()
            with zipfile.ZipFile(bz,"w",zipfile.ZIP_DEFLATED) as zf:
                for i,rec in enumerate(regs):
                    nm=rec["name"]; cat=rec.get("category","Other")
                    s.markdown(f"⏳ **{nm}** ({i+1}/{len(regs)})")
                    png=generate_cert(nm,st.session_state.template_bytes,cn)
                    if do_png: zf.writestr(f"PNG/{cat}/{nm}.png",png)
                    if do_pdf: zf.writestr(f"PDF/{cat}/{nm}.pdf",cert_to_pdf(png,nm))
                    p.progress((i+1)/len(regs))
            s.success(f"✅ {len(regs)} done!"); st.balloons()
            st.download_button("⬇️ Download ZIP",bz.getvalue(),
                file_name=f"{st.session_state.event_name.replace(' ','_')}_Certificates.zip",
                mime="application/zip",use_container_width=True)

# ─────────────────────────────────────────────
#  TAB 6 — Backup & Security
# ─────────────────────────────────────────────
with tab6:
    st.markdown("### 💾 Backup & Security")
    auth_info=load_auth()
    sc1,sc2,sc3=st.columns(3)
    sc1.metric("Algorithm","PBKDF2-SHA256","Secure")
    sc2.metric("Iterations","310,000","OWASP 2024")
    sc3.metric("Salt","256-bit random","Unique")
    if "changed" in auth_info: st.success(f"✅ Password changed: {auth_info['changed'][:10]}")
    else: st.markdown('<div class="card-warn">⚠️ Still using default password — change it!</div>',unsafe_allow_html=True)
    st.markdown("---")
    regs_b=load_registrations()
    bc1,bc2=st.columns(2)
    with bc1:
        st.metric("Registrations",len(regs_b))
        st.download_button("⬇️ Download Backup ZIP",create_backup(),
            file_name=f"Backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip",use_container_width=True)
        st.caption("Includes: registrations.csv + config.json")
    with bc2:
        bfiles=sorted(os.listdir(BACKUP_DIR)) if os.path.exists(BACKUP_DIR) else []
        st.markdown(f"**Auto-backups on server:** {len(bfiles)}")
        for bf in bfiles[-5:]: st.caption(f"📁 {bf}")
    st.markdown("---")
    st.markdown("#### 🔄 Restore Data")
    upl_r=st.file_uploader("Upload CSV to restore:",type=["csv"])
    if upl_r:
        try:
            rdf=pd.read_csv(upl_r)
            st.success(f"✅ {len(rdf)} records found")
            st.dataframe(rdf.head(5),use_container_width=True)
            if st.button("⚠️ Confirm Restore (overwrites current data)"):
                rdf.to_csv(DATA_FILE,index=False); st.success("✅ Restored!"); st.rerun()
        except Exception as e: st.error(f"❌ {e}")
    st.markdown("---")
    st.markdown("#### ⚠️ Danger Zone")
    with st.expander("🗑️ Delete All Registrations"):
        conf=st.text_input("Type DELETE to confirm:")
        if st.button("🗑️ Delete All") and conf=="DELETE":
            bak=create_backup(); clear_registrations()
            st.warning("Deleted! Auto-backup taken.")
            st.download_button("⬇️ Pre-delete Backup",bak,file_name="pre_delete.zip",mime="application/zip")
            st.rerun()

# ─────────────────────────────────────────────
#  TAB 7 — Deploy Guide
# ─────────────────────────────────────────────
with tab7:
    st.markdown("""
<div class="card">

## ☁️ Deployment Guide

### Files to push to GitHub:
```
app.py
requirements.txt
```

### Commands:
```bash
cd d:/Avalon.AI
git add app.py requirements.txt
git commit -m "v6 - improved invitation cards"
git push
```

### Streamlit Cloud steps:
1. [share.streamlit.io](https://share.streamlit.io) → GitHub login
2. New App → select repo → `app.py` → Deploy
3. Copy URL → Sidebar → Save Settings → Generate QR ✅

### Default password: `Admin@2025` — change immediately!

</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  TAB 8 — Developer Credits
# ─────────────────────────────────────────────
with tab8:
    st.markdown("""
<style>
.dev-card{background:linear-gradient(135deg,rgba(14,20,60,.98),rgba(8,12,38,.99));
    border:2px solid #ffd159;border-radius:24px;padding:44px 36px;text-align:center;margin:10px 0;}
.dev-name{font-size:2.8rem;font-weight:900;color:#ffd159;letter-spacing:3px;margin:14px 0 6px;}
.dev-title{font-size:1.1rem;color:#7ecefd;letter-spacing:1px;margin-bottom:8px;}
.social-row{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin:22px 0;}
.soc-btn{display:inline-flex;align-items:center;gap:8px;padding:11px 22px;
    border-radius:30px;font-weight:700;font-size:.95rem;text-decoration:none;transition:all .2s;}
.soc-btn:hover{transform:translateY(-3px);filter:brightness(1.1);}
.skill-row{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin:14px 0;}
.skill{background:rgba(46,107,239,.3);border:1px solid #2e6bef66;color:#7ecefd;
    padding:7px 18px;border-radius:20px;font-size:.9rem;font-weight:600;}
.dev-hr{border:none;border-top:1px solid #ffd15933;margin:20px 0;}
</style>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="dev-card">
  <div style="font-size:5.5rem;">👨‍💻</div>

  <div class="dev-name">Abdul Samad</div>
  <div class="dev-title">Web Developer  •  AI/ML Enthusiast  •  Digital Marketer</div>

  <hr class="dev-hr">

  <p style="color:#c5d8f0;font-size:1rem;margin:4px 0;">🎓 <b>BS Computer Science</b></p>
  <p style="color:#c5d8f0;font-size:1rem;margin:4px 0;">Shaheed Benazir Bhutto University (SBBU), Nawabshah, Sindh, Pakistan</p>

  <hr class="dev-hr">

  <div style="color:#7ecefd;font-weight:700;font-size:1rem;margin-bottom:6px;">🔗 Connect With Me</div>
  <div class="social-row">
    <a class="soc-btn" href="https://instagram.com/isamad.rind" target="_blank"
       style="background:linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);color:white;">
      📷 Instagram
    </a>
    <a class="soc-btn" href="https://facebook.com/isamadrind" target="_blank"
       style="background:#1877F2;color:white;">
      📘 Facebook
    </a>
    <a class="soc-btn" href="https://linkedin.com/in/abdulsamadrind" target="_blank"
       style="background:#0A66C2;color:white;">
      💼 LinkedIn
    </a>
    <a class="soc-btn" href="https://tiktok.com/@isamadrind" target="_blank"
       style="background:linear-gradient(90deg,#010101,#69C9D0);color:white;">
      🎵 TikTok
    </a>
    <a class="soc-btn" href="tel:+923130328282"
       style="background:#25D366;color:white;">
      📞 +92-313-0328282
    </a>
  </div>

  <hr class="dev-hr">

  <div style="color:#7ecefd;font-weight:700;margin-bottom:8px;">💡 Skills & Technologies</div>
  <div class="skill-row">
    <span class="skill">Python</span>
    <span class="skill">Streamlit</span>
    <span class="skill">Machine Learning</span>
    <span class="skill">Web Development</span>
    <span class="skill">SQL & Databases</span>
    <span class="skill">Pandas & NumPy</span>
    <span class="skill">Git & GitHub</span>
    <span class="skill">Pillow / PIL</span>
    <span class="skill">OpenCV</span>
  </div>

  <hr class="dev-hr">

  <div style="color:#7ecefd;font-size:.95rem;line-height:1.9;padding:0 10px;">
    <b style="color:#ffd159;">QR Certificate Generator Pro V3.01</b><br>
    A complete event registration &amp; certificate generation platform.<br>
    Built with <b>Python • Streamlit • Pillow • ReportLab • OpenPyXL</b>
  </div>

  <p style="color:#7ecefd44;font-size:.85rem;margin-top:22px;">
    © 2026 Abdul Samad Rind— All Rights Reserved<br>
    Designed &amp; Developed with ❤️ at SBBU SBA
  </p>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 📬 Contact")
    gc1,gc2,gc3=st.columns(3)
    with gc1:
        st.markdown('<div class="card" style="text-align:center;"><div style="font-size:2rem;">📧</div><p style="color:#ffd159;font-weight:700;">Email</p><p style="color:#7ecefd;">asamad009@outlook.com</p></div>', unsafe_allow_html=True)
    with gc2:
        st.markdown('<div class="card" style="text-align:center;"><div style="font-size:2rem;">🌐</div><p style="color:#ffd159;font-weight:700;">Portfolio</p><p style="color:#7ecefd;">isamadrind.kesug.com</p></div>', unsafe_allow_html=True)
    with gc3:
        st.markdown('<div class="card" style="text-align:center;"><div style="font-size:2rem;">📍</div><p style="color:#ffd159;font-weight:700;">Location</p><p style="color:#7ecefd;">Kazi Ahmed, Nawabshah, Sindh, Pakistan</p></div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  TAB 9 — README
# ─────────────────────────────────────────────
with tab9:
    st.markdown("""
<div class="card">

# 📖 QR Certificate Generator Pro — User Guide

## 🎯 What is This?
A complete **event management platform** that lets you:
- Generate QR codes for instant registration
- Collect attendee data (students, teachers, businessmen, guests)
- Generate beautiful **Invitation Cards** automatically on registration
- Create and bulk-distribute **Participation Certificates**
- Export data to Excel with professional formatting

---

## 🚀 Quick Start

### Step 1 — Setup (One Time)
1. Deploy `app.py` on Streamlit Cloud (see Deploy Guide tab)
2. Login with default password: `Admin@2025`
3. **Change password immediately** from sidebar
4. Fill in event details in sidebar
5. Save settings → Generate QR code

### Step 2 — Event Day
1. Print the QR code and display at venue
2. Attendees scan QR → fill form → get invitation card instantly
3. Monitor registrations live in Tab 2

### Step 3 — Post-Event
1. Download Excel report from Tab 2
2. Upload certificate template in Tab 4
3. Adjust font/position in sidebar
4. Generate all certificates in Tab 5 → Download ZIP

---

## 🎫 Invitation Card Features
| Feature | Detail |
|---------|--------|
| **Themes** | 8 professional themes (Royal Gold, Midnight Blue, Crimson, Emerald, Obsidian, Ocean, Violet, Rose Gold) |
| **Reg No** | Short alphanumeric: P-0001, TC-0005, SP-0012 |
| **Smart phrases** | Auto-changes based on category (teacher/speaker/business/student) |
| **Logos** | Upload 1-3 logos (university, department, sponsor) |
| **Details** | Name, Category, Department, Roll No, Batch, Date, Venue, Organizer |
| **Sharing** | Download as image → share on WhatsApp/Facebook/Instagram |

---

## 👥 Category System
| Category Type | Roll No Required | Invite Phrase |
|--------------|-----------------|---------------|
| Student/Participant | ✅ Yes | "We are pleased to invite" |
| Teacher/Professor | ❌ No | "You are cordially invited as" |
| Speaker/Keynote | ❌ No | "We are honored to welcome" |
| CEO/VIP/Director | ❌ No | "It is our privilege to invite" |
| Business/Entrepreneur | ❌ No | "We are pleased to welcome" |
| Judge/Panelist | ❌ No | "You are invited to serve as" |

---

## 🔒 Security
- Password hashed with **PBKDF2-HMAC-SHA256** (310,000 iterations)
- 256-bit random salt per password
- Timing-attack safe comparison
- Password stored in `auth.json` — never in source code
- Default password: `Admin@2025` — **change immediately!**

---

## 💾 Data & Backup
- All data saved in `registrations.csv` — survives app restarts
- Config saved in `config.json`
- **Auto backup** daily to `backups/` folder
- Manual backup download anytime (Tab 6)
- Restore from CSV file (Tab 6)

---

## 📁 File Structure
```
app.py              ← Main application
requirements.txt    ← Python dependencies
registrations.csv   ← All registration data (auto-created)
config.json         ← Event settings (auto-created)
auth.json           ← Hashed password (auto-created)
backups/            ← Auto-backup folder (auto-created)
```

---

## ⚙️ Requirements
```
streamlit>=1.32.0
Pillow>=10.0.0
qrcode[pil]>=7.4.2
reportlab>=4.1.0
openpyxl>=3.1.2
pandas>=2.0.0
```

---

## 🧑‍💻 Developer
**Abdul Samad** — SBBU Nawabshah, Pakistan  
BS Computer Science | Python • AI/ML • Streamlit • Web Dev

---

*QR Certificate Generator Pro V3.01 — © 2025 Abdul Samad*

</div>
""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<p style="text-align:center;color:#7ecefd44;font-size:.85rem;">'
    '© QR Certificate System v3.01 | Developed by Abdul Samad | SBBU Nawabshah, Pakistan</p>',
    unsafe_allow_html=True)
