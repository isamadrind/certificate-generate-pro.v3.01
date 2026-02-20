"""
╔══════════════════════════════════════════════════════════════════╗
║   QR Certificate System  v5.0                                   ║
║   Developed by: Abdul Samad | SBBU Nawabshah                    ║
╠══════════════════════════════════════════════════════════════════╣
║   pip install streamlit pillow qrcode[pil] reportlab openpyxl pandas ║
║   streamlit run app.py                                          ║
╚══════════════════════════════════════════════════════════════════╝
v5.0 Changes:
  ✅ bcrypt-free secure hashing (PBKDF2-HMAC-SHA256) — no plaintext password
  ✅ Password stored in auth.json — never in code
  ✅ Data persists across app restarts (CSV + JSON files)
  ✅ Backup system — download ZIP of all data anytime
  ✅ Invitation card generated INSTANTLY on form submit
  ✅ Category-wise smart fields (Roll No optional for non-students)
  ✅ 6 invitation card themes + 1-3 logos
  ✅ Social share: WhatsApp, Facebook, LinkedIn, Twitter
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
AUTH_FILE   = "auth.json"          # hashed password stored here
BACKUP_DIR  = "backups"

CSV_HEADERS = ["ref_no","name","roll_no","department",
               "batch","category","event","date","time"]

# ══════════════════════════════════════════════════════════════════
#  SECURE PASSWORD  (PBKDF2-HMAC-SHA256 — no bcrypt needed)
# ══════════════════════════════════════════════════════════════════
def _hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with PBKDF2-HMAC-SHA256. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = secrets.token_hex(32)          # 256-bit random salt
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=310_000                     # OWASP recommended 2024
    )
    return key.hex(), salt

def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password in constant time (timing-attack safe)."""
    candidate, _ = _hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)

def load_auth() -> dict:
    """Load auth.json. Create default on first run."""
    if not os.path.exists(AUTH_FILE):
        # First run — hash default password and save
        h, s = _hash_password("Admin@2025")
        auth = {"hash": h, "salt": s,
                "created": datetime.now().isoformat(),
                "note": "Change password from Admin Panel immediately!"}
        with open(AUTH_FILE, "w") as f:
            json.dump(auth, f, indent=2)
        return auth
    with open(AUTH_FILE, "r") as f:
        return json.load(f)

def save_password(new_password: str):
    """Hash and save new password."""
    h, s = _hash_password(new_password)
    auth  = load_auth()
    auth.update({"hash": h, "salt": s,
                 "changed": datetime.now().isoformat()})
    with open(AUTH_FILE, "w") as f:
        json.dump(auth, f, indent=2)

def check_password(password: str) -> bool:
    auth = load_auth()
    return _verify_password(password, auth["hash"], auth["salt"])

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
CONFIG_DEFAULTS = {
    "event_name":    "Certificate of Participation",
    "event_date":    datetime.now().strftime("%Y-%m-%d"),
    "event_venue":   "",
    "event_topic":   "",
    "organizer":     "",
    "categories":    "Participant,Teacher,Speaker,Management",
    "student_cats":  "Participant",
    "app_url":       "",
    "inv_theme":     "dark_blue",
    "logo1_b64":     "",
    "logo2_b64":     "",
    "logo3_b64":     "",
}

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return CONFIG_DEFAULTS.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        out = CONFIG_DEFAULTS.copy()
        out.update(saved)
        return out
    except Exception:
        return CONFIG_DEFAULTS.copy()

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════════════════════════════
#  CSV DATABASE
# ══════════════════════════════════════════════════════════════════
def generate_ref_no(category: str) -> str:
    regs     = load_registrations()
    count    = len(regs) + 1
    cat_code = "".join(w[0].upper() for w in category.split()[:2])
    date_code= datetime.now().strftime("%y%m%d")
    return f"{cat_code}-{date_code}-{count:04d}"

def save_registration(rec: dict):
    exists = os.path.exists(DATA_FILE)
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not exists:
            w.writeheader()
        w.writerow({k: rec.get(k, "") for k in CSV_HEADERS})

def load_registrations() -> list:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def clear_registrations():
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)

# ══════════════════════════════════════════════════════════════════
#  BACKUP
# ══════════════════════════════════════════════════════════════════
def create_backup() -> bytes:
    """ZIP all data files for download."""
    buf = io.BytesIO()
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in [DATA_FILE, CONFIG_FILE]:
            if os.path.exists(fname):
                zf.write(fname, f"backup_{ts}/{fname}")
        # Never backup auth.json (contains hash — still sensitive)
        zf.writestr(f"backup_{ts}/README.txt",
                    f"Backup created: {datetime.now().isoformat()}\n"
                    "Files: registrations.csv, config.json\n"
                    "Note: auth.json NOT included for security.\n"
                    "Restore: copy files back to app folder.")
    return buf.getvalue()

def auto_backup():
    """Save daily backup to backups/ folder on server."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    bfile = os.path.join(BACKUP_DIR, f"backup_{today}.zip")
    if not os.path.exists(bfile):   # once per day
        data = create_backup()
        with open(bfile, "wb") as f:
            f.write(data)

# ══════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="QR Certificate System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
.stTextArea textarea{
    background:#0d1b35!important;color:white!important;
    border:1.5px solid #7ecefd55!important;border-radius:8px!important;
    font-size:1rem!important;}
.stTextInput>div>div>input:focus,.stTextArea textarea:focus{
    border-color:#7ecefd!important;box-shadow:0 0 0 2px #7ecefd33!important;}
.stSelectbox>div>div{background:#0d1b35!important;color:white!important;
    border:1.5px solid #7ecefd55!important;border-radius:8px!important;}
.stButton>button{
    background:linear-gradient(90deg,#2e6bef,#7ecefd)!important;
    color:white!important;border:none!important;border-radius:10px!important;
    font-weight:bold!important;font-size:1rem!important;
    padding:.6rem 1.2rem!important;transition:all .2s!important;}
.stButton>button:hover{opacity:.85!important;transform:scale(1.01)!important;}
.card{background:rgba(20,30,70,.92);border:1px solid #7ecefd33;
      border-radius:16px;padding:24px;margin:10px 0;}
.card-green{background:rgba(10,60,40,.9);border:1px solid #2ecc7166;
            border-radius:14px;padding:20px;margin:12px 0;}
.card-warn{background:rgba(80,40,0,.85);border:1px solid #f39c1266;
           border-radius:14px;padding:16px;margin:10px 0;}
.card-blue{background:rgba(10,40,80,.9);border:1px solid #3498db66;
           border-radius:14px;padding:18px;margin:10px 0;}
.card-red{background:rgba(80,10,10,.88);border:1px solid #e74c3c88;
          border-radius:14px;padding:16px;margin:10px 0;}
[data-testid="stMetricValue"]{color:#ffd159!important;font-size:2rem!important;}
[data-testid="stMetricLabel"]{color:#7ecefd!important;}
.stTabs [data-baseweb="tab"]{color:#7ecefd;background:#1e1b4b;
    border-radius:8px 8px 0 0;font-weight:600;}
.stTabs [aria-selected="true"]{background:#2e6bef!important;color:white!important;}
.stDataFrame{border-radius:10px;overflow:hidden;}
hr{border-color:#7ecefd22!important;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  LOAD CONFIG ON STARTUP (persistent across restarts)
# ══════════════════════════════════════════════════════════════════
_cfg = load_config()

# ── Auto daily backup on server
auto_backup()

# ══════════════════════════════════════════════════════════════════
#  SESSION STATE  (loads from files — not lost on refresh)
# ══════════════════════════════════════════════════════════════════
SESS = {
    "admin_auth":         False,
    "template_bytes":     None,
    "qr_data":            None,
    # All from config file
    "event_name":         _cfg["event_name"],
    "event_date":         _cfg["event_date"],
    "event_venue":        _cfg["event_venue"],
    "event_topic":        _cfg["event_topic"],
    "organizer":          _cfg["organizer"],
    "categories":         _cfg["categories"],
    "student_cats_input": _cfg["student_cats"],
    "app_url":            _cfg["app_url"],
    "inv_theme":          _cfg["inv_theme"],
    "logo1_b64":          _cfg["logo1_b64"],
    "logo2_b64":          _cfg["logo2_b64"],
    "logo3_b64":          _cfg["logo3_b64"],
    # Text / cert settings (not in config — reset on restart is fine)
    "text_x":             50,
    "text_y":             60,
    "font_size":          72,
    "text_color":         "#1a1a1a",
    "selected_font":      "Arial Bold",
    # Form state
    "form_submitted":     False,
    "last_submission":    {},
    "invitation_png":     None,
}
for k, v in SESS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════
#  FONTS  (50+)
# ══════════════════════════════════════════════════════════════════
FONTS = {
    "Arial Regular":          ["arial.ttf","DejaVuSans.ttf"],
    "Arial Bold":             ["arialbd.ttf","DejaVuSans-Bold.ttf"],
    "Arial Italic":           ["ariali.ttf","DejaVuSans-Oblique.ttf"],
    "Arial Bold Italic":      ["arialbi.ttf","DejaVuSans-BoldOblique.ttf"],
    "Calibri Regular":        ["calibri.ttf","DejaVuSans.ttf"],
    "Calibri Bold":           ["calibrib.ttf","DejaVuSans-Bold.ttf"],
    "Calibri Italic":         ["calibrii.ttf","DejaVuSans-Oblique.ttf"],
    "Tahoma Regular":         ["tahoma.ttf","DejaVuSans.ttf"],
    "Tahoma Bold":            ["tahomabd.ttf","DejaVuSans-Bold.ttf"],
    "Verdana Regular":        ["verdana.ttf","DejaVuSans.ttf"],
    "Verdana Bold":           ["verdanab.ttf","DejaVuSans-Bold.ttf"],
    "Trebuchet MS":           ["trebuc.ttf","DejaVuSans.ttf"],
    "Trebuchet Bold":         ["trebucbd.ttf","DejaVuSans-Bold.ttf"],
    "Segoe UI":               ["segoeui.ttf","DejaVuSans.ttf"],
    "Segoe UI Bold":          ["segoeuib.ttf","DejaVuSans-Bold.ttf"],
    "Segoe UI Light":         ["segoeuil.ttf","DejaVuSans.ttf"],
    "Times New Roman":        ["times.ttf","DejaVuSerif.ttf"],
    "Times New Roman Bold":   ["timesbd.ttf","DejaVuSerif-Bold.ttf"],
    "Times New Roman Italic": ["timesi.ttf","DejaVuSerif-Italic.ttf"],
    "Times NR Bold Italic":   ["timesbi.ttf","DejaVuSerif-BoldItalic.ttf"],
    "Georgia Regular":        ["georgia.ttf","DejaVuSerif.ttf"],
    "Georgia Bold":           ["georgiab.ttf","DejaVuSerif-Bold.ttf"],
    "Georgia Italic":         ["georgiai.ttf","DejaVuSerif-Italic.ttf"],
    "Palatino Linotype":      ["pala.ttf","DejaVuSerif.ttf"],
    "Palatino Bold":          ["palab.ttf","DejaVuSerif-Bold.ttf"],
    "Book Antiqua":           ["bkant.ttf","DejaVuSerif.ttf"],
    "Garamond":               ["GARA.TTF","DejaVuSerif.ttf"],
    "Garamond Bold":          ["GARABD.TTF","DejaVuSerif-Bold.ttf"],
    "Courier New":            ["cour.ttf","DejaVuSansMono.ttf"],
    "Courier New Bold":       ["courbd.ttf","DejaVuSansMono-Bold.ttf"],
    "Courier Italic":         ["couri.ttf","DejaVuSansMono-Oblique.ttf"],
    "Consolas":               ["consola.ttf","DejaVuSansMono.ttf"],
    "Consolas Bold":          ["consolab.ttf","DejaVuSansMono-Bold.ttf"],
    "Lucida Console":         ["lucon.ttf","DejaVuSansMono.ttf"],
    "Century Gothic":         ["GOTHIC.TTF","DejaVuSans.ttf"],
    "Century Gothic Bold":    ["GOTHICB.TTF","DejaVuSans-Bold.ttf"],
    "Century Gothic Italic":  ["GOTHICI.TTF","DejaVuSans-Oblique.ttf"],
    "Impact":                 ["impact.ttf","DejaVuSans-Bold.ttf"],
    "Franklin Gothic":        ["framd.ttf","DejaVuSans-Bold.ttf"],
    "Candara Regular":        ["Candara.ttf","DejaVuSans.ttf"],
    "Candara Bold":           ["Candarab.ttf","DejaVuSans-Bold.ttf"],
    "Corbel Regular":         ["corbel.ttf","DejaVuSans.ttf"],
    "Corbel Bold":            ["corbelb.ttf","DejaVuSans-Bold.ttf"],
    "Rockwell":               ["ROCK.TTF","DejaVuSerif.ttf"],
    "Rockwell Bold":          ["ROCKB.TTF","DejaVuSerif-Bold.ttf"],
    "Brush Script MT":        ["BRUSHSCI.TTF","DejaVuSerif-Italic.ttf"],
    "Lucida Handwriting":     ["lhandw.ttf","DejaVuSerif-Italic.ttf"],
    "Lucida Calligraphy":     ["LCALLIG.TTF","DejaVuSerif-Italic.ttf"],
    "Comic Sans MS":          ["comic.ttf","DejaVuSans.ttf"],
    "Comic Sans Bold":        ["comicbd.ttf","DejaVuSans-Bold.ttf"],
    "DejaVu Sans":            ["DejaVuSans.ttf","DejaVuSans.ttf"],
    "DejaVu Sans Bold":       ["DejaVuSans-Bold.ttf","DejaVuSans-Bold.ttf"],
    "DejaVu Serif":           ["DejaVuSerif.ttf","DejaVuSerif.ttf"],
    "DejaVu Serif Bold":      ["DejaVuSerif-Bold.ttf","DejaVuSerif-Bold.ttf"],
    "DejaVu Mono":            ["DejaVuSansMono.ttf","DejaVuSansMono.ttf"],
    "DejaVu Mono Bold":       ["DejaVuSansMono-Bold.ttf","DejaVuSansMono-Bold.ttf"],
}
FONT_CATS = {
    "🔤 Sans Serif":    [k for k in FONTS if any(x in k for x in ["Arial","Calibri","Tahoma","Verdana","Trebuchet","Segoe"])],
    "📜 Serif/Formal":  [k for k in FONTS if any(x in k for x in ["Times","Georgia","Palatino","Book","Garamond"])],
    "💻 Monospace":     [k for k in FONTS if any(x in k for x in ["Courier","Consolas","Lucida Console"])],
    "✨ Display":       [k for k in FONTS if any(x in k for x in ["Century","Impact","Franklin","Candara","Corbel","Rockwell"])],
    "🖋️ Script":       [k for k in FONTS if any(x in k for x in ["Brush","Handwriting","Calligraphy","Comic"])],
    "🛡️ Fallback":     [k for k in FONTS if "DejaVu" in k],
}

# ══════════════════════════════════════════════════════════════════
#  INVITATION CARD THEMES
# ══════════════════════════════════════════════════════════════════
THEMES = {
    "dark_blue":     {"bg":(11,19,43),   "bg2":(28,37,65),  "acc":(255,215,0),  "txt":(255,255,255),"sub":(126,206,253),"brd":(46,107,239)},
    "deep_maroon":   {"bg":(40,5,20),    "bg2":(70,15,35),  "acc":(255,180,60), "txt":(255,255,255),"sub":(255,160,120),"brd":(180,40,60)},
    "forest_green":  {"bg":(10,35,25),   "bg2":(20,60,40),  "acc":(100,220,130),"txt":(255,255,255),"sub":(160,230,190),"brd":(50,180,80)},
    "royal_purple":  {"bg":(25,10,55),   "bg2":(45,20,85),  "acc":(220,180,255),"txt":(255,255,255),"sub":(190,150,255),"brd":(130,80,220)},
    "elegant_black": {"bg":(10,10,10),   "bg2":(28,28,28),  "acc":(200,160,60), "txt":(255,255,255),"sub":(180,180,180),"brd":(200,160,60)},
    "ocean_teal":    {"bg":(5,40,50),    "bg2":(10,70,80),  "acc":(60,220,200), "txt":(255,255,255),"sub":(130,230,220),"brd":(30,180,170)},
}
THEME_LABELS = {
    "dark_blue":"🔵 Dark Blue","deep_maroon":"🔴 Deep Maroon",
    "forest_green":"🟢 Forest Green","royal_purple":"🟣 Royal Purple",
    "elegant_black":"⚫ Elegant Black","ocean_teal":"🩵 Ocean Teal",
}

# ══════════════════════════════════════════════════════════════════
#  CORE HELPERS
# ══════════════════════════════════════════════════════════════════
def _fnt(size, bold=False):
    cands = (["arialbd.ttf","DejaVuSans-Bold.ttf","calibrib.ttf"]
             if bold else ["arial.ttf","DejaVuSans.ttf","calibri.ttf"])
    for f in cands:
        try: return ImageFont.truetype(f, size)
        except: pass
    return ImageFont.load_default()

def _rr(draw, x1,y1,x2,y2, r, fill, outline=None, ow=3):
    draw.rectangle([x1+r,y1,x2-r,y2],fill=fill)
    draw.rectangle([x1,y1+r,x2,y2-r],fill=fill)
    for ex,ey in [(x1,y1),(x2-2*r,y1),(x1,y2-2*r),(x2-2*r,y2-2*r)]:
        draw.ellipse([ex,ey,ex+2*r,ey+2*r],fill=fill)
    if outline:
        draw.arc([x1,y1,x1+2*r,y1+2*r],180,270,fill=outline,width=ow)
        draw.arc([x2-2*r,y1,x2,y1+2*r],270,360,fill=outline,width=ow)
        draw.arc([x1,y2-2*r,x1+2*r,y2],90,180,fill=outline,width=ow)
        draw.arc([x2-2*r,y2-2*r,x2,y2],0,90,fill=outline,width=ow)
        draw.line([x1+r,y1,x2-r,y1],fill=outline,width=ow)
        draw.line([x1+r,y2,x2-r,y2],fill=outline,width=ow)
        draw.line([x1,y1+r,x1,y2-r],fill=outline,width=ow)
        draw.line([x2,y1+r,x2,y2-r],fill=outline,width=ow)

def load_pil_font(name, size):
    for path in FONTS.get(name, ["DejaVuSans-Bold.ttf"]):
        try: return ImageFont.truetype(path, size)
        except: pass
    return ImageFont.load_default()

def hex_rgba(h, a=255):
    h=h.lstrip("#")
    return (int(h[0:2],16),int(h[2:4],16),int(h[4:6],16),a)

def make_qr(url):
    qr=qrcode.QRCode(version=1,error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=10,border=4)
    qr.add_data(url); qr.make(fit=True)
    buf=io.BytesIO()
    qr.make_image(fill_color="#0b132b",back_color="white").save(buf,format="PNG")
    return buf.getvalue()

def cur_cfg():
    return {"x":st.session_state.text_x,"y":st.session_state.text_y,
            "size":st.session_state.font_size,"color":st.session_state.text_color,
            "font":st.session_state.selected_font}

def generate_cert(name, template, cfg):
    img=Image.open(io.BytesIO(template)).convert("RGBA")
    w,h=img.size
    font=load_pil_font(cfg["font"],cfg["size"])
    px=int(w*cfg["x"]/100); py=int(h*cfg["y"]/100)
    layer=Image.new("RGBA",img.size,(255,255,255,0))
    draw=ImageDraw.Draw(layer)
    bbox=draw.textbbox((0,0),name,font=font)
    tw,th=bbox[2]-bbox[0],bbox[3]-bbox[1]
    draw.text((px-tw//2,py-th//2),name,font=font,fill=hex_rgba(cfg["color"]))
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
    c.drawCentredString(pw/2,14,f"{name}  |  {st.session_state.event_name}  |  {datetime.now().strftime('%Y-%m-%d')}")
    c.save(); return buf.getvalue()

# ══════════════════════════════════════════════════════════════════
#  INVITATION CARD GENERATOR
# ══════════════════════════════════════════════════════════════════
def generate_invitation_card(rec, cfg, l1=None, l2=None, l3=None):
    W,H = 1080,1400
    th  = THEMES.get(cfg.get("inv_theme","dark_blue"), THEMES["dark_blue"])

    img  = Image.new("RGB",(W,H),th["bg"])
    draw = ImageDraw.Draw(img)

    # Gradient background
    for i in range(H):
        a=i/H
        draw.line([(0,i),(W,i)],fill=(
            int(th["bg"][0]*(1-a)+th["bg2"][0]*a),
            int(th["bg"][1]*(1-a)+th["bg2"][1]*a),
            int(th["bg"][2]*(1-a)+th["bg2"][2]*a)))

    # Top accent bar + outer border
    draw.rectangle([0,0,W,10],fill=th["acc"])
    _rr(draw,24,24,W-24,H-24,30,th["bg2"],outline=th["brd"],ow=3)

    # ── Logos ─────────────────────────────────────────────────────
    LH=120; y=60
    logos=[b for b in [l1,l2,l3] if b]
    limgs=[]
    for lb in logos:
        try:
            li=Image.open(io.BytesIO(lb)).convert("RGBA")
            r=LH/li.height; li=li.resize((max(1,int(li.width*r)),LH),Image.LANCZOS)
            limgs.append(li)
        except: pass
    if limgs:
        gap=50; total=sum(li.width for li in limgs)+(len(limgs)-1)*gap
        xst=(W-total)//2
        for li in limgs:
            img.paste(li,(xst,y),li); xst+=li.width+gap
    else:
        draw.text((W//2,y+LH//2),"🎓",font=_fnt(80),fill=th["acc"],anchor="mm")
    y+=LH+20

    # Divider
    draw.rectangle([80,y,W-80,y+2],fill=th["acc"]); y+=20

    # ── Event Title (word-wrapped) ────────────────────────────────
    ev=cfg.get("event_name","Event"); ft=_fnt(50,True)
    lines_out=[]; cur=""
    for w in ev.split():
        test=(cur+" "+w).strip()
        if draw.textbbox((0,0),test,font=ft)[2]>W-180:
            lines_out.append(cur); cur=w
        else: cur=test
    if cur: lines_out.append(cur)
    for ln in lines_out:
        draw.text((W//2,y),ln,font=ft,fill=th["acc"],anchor="mt"); y+=62

    topic=cfg.get("event_topic","")
    if topic:
        draw.text((W//2,y),topic,font=_fnt(28),fill=th["sub"],anchor="mt"); y+=44
    y+=12

    # ── Invite line ───────────────────────────────────────────────
    draw.rectangle([120,y,W-120,y+1],fill=th["brd"]); y+=22
    cat=rec.get("category","").lower()
    itxt=("We are honored to invite"
          if any(x in cat for x in ["teacher","speaker","management","guest","chief"])
          else "This card confirms participation of")
    draw.text((W//2,y),itxt,font=_fnt(26),fill=th["sub"],anchor="mt"); y+=44

    # ── Name big ─────────────────────────────────────────────────
    name=rec.get("name","Participant")
    _rr(draw,60,y,W-60,y+92,18,th["brd"],outline=th["acc"],ow=2)
    draw.text((W//2,y+46),name,font=_fnt(52,True),fill=th["acc"],anchor="mm"); y+=110

    # ── Details ──────────────────────────────────────────────────
    y+=6
    dets=[("Category",rec.get("category",""))]
    if rec.get("department"): dets.append(("Department",rec["department"]))
    if rec.get("roll_no"):    dets.append(("Roll No",   rec["roll_no"]))
    if rec.get("batch"):      dets.append(("Batch",     rec["batch"]))
    for lbl,val in dets:
        draw.text((120,y),lbl+":",font=_fnt(24),fill=th["sub"],anchor="lt")
        draw.text((W-120,y),val,  font=_fnt(26,True),fill=th["txt"],anchor="rt")
        draw.line([(120,y+34),(W-120,y+34)],fill=(*th["brd"][:3],100),width=1)
        y+=52
    y+=14

    # ── Event info box ────────────────────────────────────────────
    _rr(draw,60,y,W-60,y+200,16,th["bg"],outline=th["brd"],ow=2)
    ey=y+30
    evd=cfg.get("event_date","")
    try: evd=datetime.strptime(evd,"%Y-%m-%d").strftime("%B %d, %Y  (%A)")
    except: pass
    for icon,val in [("📅  Date",evd),("📍  Venue",cfg.get("event_venue","")),
                     ("🏛️  Organizer",cfg.get("organizer",""))]:
        if val:
            draw.text((W//2,ey),f"{icon}:  {val}",font=_fnt(26),fill=th["sub"],anchor="mt")
            ey+=46
    y+=218

    # ── Ref badge ────────────────────────────────────────────────
    ref=rec.get("ref_no","—")
    _rr(draw,W//2-230,y,W//2+230,y+58,29,th["acc"])
    draw.text((W//2,y+29),f"Registration ID:  {ref}",
              font=_fnt(28,True),fill=th["bg"],anchor="mm"); y+=76

    # ── Bottom bar ───────────────────────────────────────────────
    draw.rectangle([0,H-60,W,H],fill=th["brd"])
    draw.rectangle([0,H-62,W,H-60],fill=th["acc"])
    draw.text((W//2,H-30),
        f"Verified  •  {cfg.get('organizer','')}  •  {cfg.get('event_date','')}",
        font=_fnt(22),fill=th["acc"],anchor="mm")

    buf=io.BytesIO(); img.save(buf,format="PNG",dpi=(150,150))
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════════
#  EXCEL REPORT
# ══════════════════════════════════════════════════════════════════
def build_excel(regs):
    wb=openpyxl.Workbook()
    hf=PatternFill("solid",fgColor="1E1B4B")
    hf2=PatternFill("solid",fgColor="0B132B")
    hfn=XFont(bold=True,color="FFFFFF",size=12)
    bdr=Border(bottom=Side(style="thin",color="334466"))
    ws=wb.active; ws.title="Registrations"
    ws.merge_cells("A1:I1"); t=ws["A1"]
    t.value=f"  {st.session_state.event_name} — Registration Data"
    t.font=XFont(bold=True,color="FFD159",size=14); t.fill=hf2
    t.alignment=Alignment(horizontal="center",vertical="center")
    ws.row_dimensions[1].height=34
    ws.merge_cells("A2:I2"); info=ws["A2"]
    try: day=datetime.strptime(st.session_state.event_date,"%Y-%m-%d").strftime("%A")
    except: day=""
    info.value=(f"Date:{st.session_state.event_date}({day}) | "
                f"Venue:{st.session_state.event_venue} | "
                f"Organizer:{st.session_state.organizer} | Total:{len(regs)}")
    info.font=XFont(color="7ECEFD",size=10); info.fill=hf
    info.alignment=Alignment(horizontal="center"); ws.row_dimensions[2].height=18
    cols=[("Ref No",14),("#",5),("Full Name",28),("Roll No",14),
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
    ws2=wb.create_sheet("Category Summary")
    ws2.merge_cells("A1:C1"); t2=ws2["A1"]; t2.value="Category-wise Summary"
    t2.font=XFont(bold=True,color="FFD159",size=13); t2.fill=hf2
    t2.alignment=Alignment(horizontal="center"); ws2.row_dimensions[1].height=28
    for ci,h in enumerate(["Category","Count","Members (Roll No)"],1):
        c=ws2.cell(row=2,column=ci,value=h); c.font=hfn; c.fill=hf
        c.alignment=Alignment(horizontal="center")
    cats={}
    for rec in regs:
        cats.setdefault(rec.get("category","Other"),[]).append(
            f"{rec.get('name','')}[{rec.get('roll_no','')}]")
    for ri,(cat,names) in enumerate(cats.items(),3):
        ws2.cell(row=ri,column=1,value=cat).font=XFont(bold=True,color="FFD159")
        ws2.cell(row=ri,column=2,value=len(names)).font=XFont(color="E0E0E0")
        ws2.cell(row=ri,column=3,value=", ".join(names)).font=XFont(color="E0E0E0")
        for col in range(1,4): ws2.cell(row=ri,column=col).fill=hf
    ws2.column_dimensions["A"].width=20; ws2.column_dimensions["B"].width=10; ws2.column_dimensions["C"].width=80
    buf=io.BytesIO(); wb.save(buf); return buf.getvalue()

def save_all_settings():
    save_config({
        "event_name":   st.session_state.event_name,
        "event_date":   st.session_state.event_date,
        "event_venue":  st.session_state.event_venue,
        "event_topic":  st.session_state.event_topic,
        "organizer":    st.session_state.organizer,
        "categories":   st.session_state.categories,
        "student_cats": st.session_state.student_cats_input,
        "app_url":      st.session_state.app_url,
        "inv_theme":    st.session_state.inv_theme,
        "logo1_b64":    st.session_state.logo1_b64,
        "logo2_b64":    st.session_state.logo2_b64,
        "logo3_b64":    st.session_state.logo3_b64,
    })

# ══════════════════════════════════════════════════════════════════
#  ROUTING
# ══════════════════════════════════════════════════════════════════
qp   = st.query_params
page = qp.get("page", "admin")

# ══════════════════════════════════════════════════════════════════
#  STUDENT FORM PAGE
# ══════════════════════════════════════════════════════════════════
if page == "form":
    cfg      = load_config()
    event    = cfg.get("event_name","Certificate Event")
    cats_str = cfg.get("categories","Participant,Teacher,Speaker,Management")
    cats     = [c.strip() for c in cats_str.split(",") if c.strip()]
    s_cats   = [c.strip().lower() for c in cfg.get("student_cats","Participant").split(",")]
    l1b = base64.b64decode(cfg["logo1_b64"]) if cfg.get("logo1_b64") else None
    l2b = base64.b64decode(cfg["logo2_b64"]) if cfg.get("logo2_b64") else None
    l3b = base64.b64decode(cfg["logo3_b64"]) if cfg.get("logo3_b64") else None

    # Header
    venue_line = cfg.get("event_venue","")
    date_line  = cfg.get("event_date","")
    st.markdown(f"""
    <div style="text-align:center;padding:24px 0 8px;">
      <div style="font-size:3rem;">🎓</div>
      <h1 style="color:#ffd159;font-size:2rem;margin:8px 0;">{event}</h1>
      <p style="color:#7ecefd;margin:4px 0;font-size:1rem;">
        {"📍 "+venue_line if venue_line else ""}
        {"&nbsp;&nbsp;|&nbsp;&nbsp;📅 "+date_line if date_line else ""}
      </p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    # ── AFTER SUBMIT: Show invitation card instantly ──────────────
    if st.session_state.get("form_submitted") and st.session_state.get("invitation_png"):
        rec     = st.session_state.last_submission
        inv_png = st.session_state.invitation_png

        st.markdown("""
        <div style="text-align:center;">
          <h2 style="color:#2ecc71;">✅ Registration Kamiyab!</h2>
          <p style="color:#7ecefd;font-size:1.1rem;">
            Aapka Invitation Card tayar hai — download aur share karein!
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Card display
        _, mid, _ = st.columns([1,3,1])
        with mid:
            st.image(inv_png, use_container_width=True)

        st.markdown("---")

        # Download buttons
        d1, d2 = st.columns(2)
        with d1:
            fn = f"Invitation_{rec.get('name','').replace(' ','_')}_{rec.get('ref_no','')}.png"
            st.download_button(
                "⬇️  Download Invitation Card (PNG)",
                data=inv_png, file_name=fn,
                mime="image/png", use_container_width=True)
        with d2:
            ref       = rec.get("ref_no","")
            wa_text   = (f"🎓 I registered for: *{rec.get('event','')}*%0A"
                        f"👤 Name: *{rec.get('name','')}*%0A"
                        f"🏷️ Category: {rec.get('category','')}%0A"
                        f"🆔 Ref: {ref}%0A"
                        f"📅 {cfg.get('event_date','')}")
            st.markdown(
                f'<a href="https://api.whatsapp.com/send?text={wa_text}" target="_blank"'
                f' style="display:block;text-align:center;'
                f'background:linear-gradient(90deg,#25D366,#128C7E);'
                f'color:white;font-weight:bold;font-size:1rem;padding:.68rem;'
                f'border-radius:10px;text-decoration:none;">📲 WhatsApp Share</a>',
                unsafe_allow_html=True)

        # Social share row
        st.markdown("#### 🔗 Share on Social Media")
        s1, s2, s3 = st.columns(3)
        app_url = cfg.get("app_url","")
        with s1:
            st.markdown(
                f'<a href="https://www.facebook.com/sharer/sharer.php?u={app_url}" target="_blank"'
                f' style="display:block;text-align:center;background:#1877F2;color:white;'
                f'font-weight:bold;padding:.6rem;border-radius:10px;text-decoration:none;">'
                f'📘 Facebook</a>', unsafe_allow_html=True)
        with s2:
            st.markdown(
                f'<a href="https://www.linkedin.com/sharing/share-offsite/?url={app_url}" target="_blank"'
                f' style="display:block;text-align:center;background:#0A66C2;color:white;'
                f'font-weight:bold;padding:.6rem;border-radius:10px;text-decoration:none;">'
                f'💼 LinkedIn</a>', unsafe_allow_html=True)
        with s3:
            tw = wa_text.replace("%0A"," ")
            st.markdown(
                f'<a href="https://twitter.com/intent/tweet?text={tw}" target="_blank"'
                f' style="display:block;text-align:center;background:#1DA1F2;color:white;'
                f'font-weight:bold;padding:.6rem;border-radius:10px;text-decoration:none;">'
                f'🐦 Twitter / X</a>', unsafe_allow_html=True)

        # Details expander
        st.markdown("---")
        with st.expander("📋 Registration Details"):
            r = rec
            details_md = f"""
| Field | Value |
|-------|-------|
| 🆔 Ref No | `{r.get('ref_no','')}` |
| 👤 Name | {r.get('name','')} |
| 🏷️ Category | {r.get('category','')} |
| 🏫 Department | {r.get('department','—')} |
| 🔢 Roll No | {r.get('roll_no','—')} |
| 📅 Batch | {r.get('batch','—')} |
| 🗓️ Date | {r.get('date','')} |
| 🕐 Time | {r.get('time','')} |
"""
            st.markdown(details_md)

        if st.button("🔄 Nai Registration", use_container_width=True):
            st.session_state.form_submitted = False
            st.session_state.last_submission = {}
            st.session_state.invitation_png  = None
            st.rerun()

    # ── FORM ─────────────────────────────────────────────────────
    else:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("#### 📝 Apni Details Bharein")

        c1, c2 = st.columns(2)
        with c1:
            name     = st.text_input("👤 Poora Naam / Full Name ✱",
                                     placeholder="Muhammad Ali Khan")
            dept     = st.text_input("🏫 Department",
                                     placeholder="Computer Science")
        with c2:
            category = st.selectbox("🏷️ Category ✱", cats)
            is_stud  = category.lower() in s_cats
            rollno   = st.text_input(
                "🔢 Roll No" + (" ✱" if is_stud else " (Optional)"),
                placeholder="CS-2022-45" if is_stud else "N/A for non-students")
            if is_stud:
                batch = st.text_input("📅 Batch / Year ✱", placeholder="2022-2026")
            else:
                batch = ""

        st.markdown("---")
        if st.button("✅  Submit — Jama Karein", use_container_width=True):
            n=name.strip(); r=rollno.strip(); d=dept.strip(); b=batch.strip() if batch else ""
            missing=[]
            if not n: missing.append("Full Name")
            if is_stud and not r: missing.append("Roll No")
            if is_stud and not b: missing.append("Batch")
            if missing:
                st.error("❌ Zaroori fields: **" + "  |  ".join(missing) + "**")
            else:
                now    = datetime.now()
                ref_no = generate_ref_no(category)
                rec    = {
                    "ref_no":rec if False else ref_no,
                    "name":n,"roll_no":r,"department":d,
                    "batch":b,"category":category,"event":event,
                    "date":now.strftime("%Y-%m-%d"),"time":now.strftime("%H:%M:%S"),
                }
                rec["ref_no"] = ref_no   # fix shadowing
                save_registration(rec)

                # Generate invitation card INSTANTLY
                inv_png = generate_invitation_card(rec, cfg, l1b, l2b, l3b)

                st.session_state.form_submitted  = True
                st.session_state.last_submission = rec
                st.session_state.invitation_png  = inv_png
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<p style="text-align:center;color:#7ecefd33;font-size:.8rem;margin-top:20px;">'
        'Developed by Abdul Samad — SBBU Nawabshah</p>', unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════
#  ADMIN PAGE
# ══════════════════════════════════════════════════════════════════
st.markdown("# 🎓 QR Certificate System")
st.markdown('<p style="text-align:center;color:#7ecefd;">Abdul Samad | SBBU Nawabshah</p>',
            unsafe_allow_html=True)
st.markdown("---")

# ── Auth ─────────────────────────────────────────────────────────
if not st.session_state.admin_auth:
    _, col, _ = st.columns([1,2,1])
    with col:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🔐 Admin Login")

        # First-run notice
        if not os.path.exists(AUTH_FILE):
            st.markdown("""
            <div class="card-warn">
            🔑 <b>First Run!</b> Default password: <code>Admin@2025</code><br>
            Login ke baad <b>foran password change karein!</b>
            </div>
            """, unsafe_allow_html=True)

        pwd = st.text_input("Password", type="password")
        if st.button("🔓 Login", use_container_width=True):
            if check_password(pwd):
                st.session_state.admin_auth = True
                st.rerun()
            else:
                st.error("❌ Galat password!")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 Event Settings")
    st.session_state.event_name  = st.text_input("Event Name",          st.session_state.event_name)
    st.session_state.event_topic = st.text_input("Topic",               st.session_state.event_topic)
    st.session_state.event_date  = st.text_input("Date (YYYY-MM-DD)",   st.session_state.event_date)
    st.session_state.event_venue = st.text_input("Venue",               st.session_state.event_venue)
    st.session_state.organizer   = st.text_input("Organizer",           st.session_state.organizer)
    st.session_state.categories  = st.text_input("Categories (comma)",  st.session_state.categories)
    st.session_state.student_cats_input = st.text_input(
        "Student categories (Roll No required)", st.session_state.student_cats_input)
    st.markdown("---")
    st.markdown("## 🌐 App URL")
    st.session_state.app_url = st.text_input(
        "Deployed URL", value=st.session_state.app_url,
        placeholder="https://yourname-app.streamlit.app")
    if st.button("💾 Save All Settings", use_container_width=True):
        save_all_settings(); st.success("✅ Saved!")
    st.markdown("---")
    st.markdown("## 🎨 Certificate Text")
    st.session_state.font_size  = st.slider("Font Size",          20,250,st.session_state.font_size)
    st.session_state.text_x    = st.slider("Horizontal % (←→)",  0,100, st.session_state.text_x)
    st.session_state.text_y    = st.slider("Vertical %   (↑↓)",  0,100, st.session_state.text_y)
    st.session_state.text_color= st.color_picker("Text Color",   st.session_state.text_color)
    st.markdown("---")
    st.markdown("## 🎨 Invitation Theme")
    st.session_state.inv_theme = st.selectbox(
        "Card Theme", list(THEMES.keys()),
        format_func=lambda x: THEME_LABELS[x],
        index=list(THEMES.keys()).index(st.session_state.inv_theme))
    st.markdown("**Logos (1-3):**")
    for li, lkey in enumerate(["logo1_b64","logo2_b64","logo3_b64"],1):
        lupl = st.file_uploader(f"Logo {li}", type=["png","jpg","jpeg"],
                                key=f"logo_up_{li}")
        if lupl:
            st.session_state[lkey] = base64.b64encode(lupl.read()).decode()
            st.success(f"✅ Logo {li}!")
        elif st.session_state.get(lkey):
            try: st.image(base64.b64decode(st.session_state[lkey]), width=70)
            except: pass
            if st.button(f"🗑️ Remove {li}", key=f"rm_{li}"):
                st.session_state[lkey]=""; st.rerun()
    st.markdown("---")
    st.markdown("## 🔤 Font")
    sq = st.text_input("🔍 Font Search...", placeholder="bold, times, gothic")
    all_fonts = list(FONTS.keys())
    if sq.strip():
        matched=[f for f in all_fonts if sq.strip().lower() in f.lower()]
        if matched:
            st.caption(f"{len(matched)} fonts")
            idx = matched.index(st.session_state.selected_font) if st.session_state.selected_font in matched else 0
            st.session_state.selected_font = st.selectbox("Results:", matched, index=idx, key="fss")
        else: st.warning("No fonts found")
    else:
        for cl, cf in FONT_CATS.items():
            if not cf: continue
            with st.expander(cl, expanded="Sans" in cl):
                for fn in cf:
                    lbl=("✅ " if st.session_state.selected_font==fn else "")+fn
                    if st.button(lbl, key=f"fb_{fn}", use_container_width=True):
                        st.session_state.selected_font=fn; st.rerun()
    st.markdown(f"**Selected:** `{st.session_state.selected_font}`")
    st.markdown("---")

    # ── Secure Password Change ─────────────────────────────────
    with st.expander("🔑 Change Password (Secure)"):
        st.markdown("""
        <div style="font-size:.85rem;color:#f39c12;padding:6px 0;">
        ⚠️ Strong password use karein:<br>
        • 8+ characters<br>
        • Uppercase + Lowercase<br>
        • Numbers + Symbols (@#$!)
        </div>
        """, unsafe_allow_html=True)
        cur_p = st.text_input("Current Password", type="password", key="cur_pwd")
        new_p = st.text_input("New Password",     type="password", key="new_pwd")
        cnf_p = st.text_input("Confirm Password", type="password", key="cnf_pwd")
        if st.button("🔒 Update Password", use_container_width=True):
            if not check_password(cur_p):
                st.error("❌ Current password galat hai!")
            elif len(new_p) < 8:
                st.error("❌ Password 8+ characters ka hona chahiye!")
            elif new_p != cnf_p:
                st.error("❌ New passwords match nahi karte!")
            elif new_p == cur_p:
                st.warning("⚠️ New password purane se alag hona chahiye!")
            else:
                save_password(new_p)
                st.success("✅ Password secure tarike se update ho gaya!")

    if st.button("🚪 Logout"):
        st.session_state.admin_auth = False; st.rerun()

# ── Admin Tabs ────────────────────────────────────────────────────
tab1,tab2,tab3,tab4,tab5,tab6,tab7 = st.tabs([
    "🔳 QR Generate",
    "📊 Registered Data",
    "🃏 Invitation Card",
    "🖼️ Certificate Preview",
    "🚀 Generate Certificates",
    "💾 Backup & Security",
    "☁️ Deploy Guide",
])

# ══════════════════════════════════════════════
#  TAB 1 — QR Generate
# ══════════════════════════════════════════════
with tab1:
    cl, cr = st.columns(2)
    with cl:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🔳 Registration QR Code")
        saved_url = st.session_state.app_url
        if saved_url:
            st.markdown(f"""
            <div class="card-blue">
            ✅ <b>Saved URL:</b><br>
            <code style="color:#ffd159;">{saved_url}</code><br>
            <small>Bar bar likhne ki zaroorat nahi — config mein save hai!</small>
            </div>
            """, unsafe_allow_html=True)
            qr_url = f"{saved_url.rstrip('/')}/?page=form"
            if st.button("🔳 QR Refresh Karein", use_container_width=True):
                st.session_state.qr_data = make_qr(qr_url)
            if not st.session_state.qr_data:
                st.session_state.qr_data = make_qr(qr_url)
            if st.session_state.qr_data:
                st.image(st.session_state.qr_data, width=250)
                st.download_button("⬇️ QR Download", data=st.session_state.qr_data,
                    file_name="registration_qr.png", mime="image/png", use_container_width=True)
                st.code(qr_url, language=None)
        else:
            st.markdown("""
            <div class="card-warn">
            ⚠️ URL set nahi hai!<br>
            Sidebar mein <b>"App URL"</b> paste karein → <b>"Save All Settings"</b>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with cr:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 📱 Student Experience")
        st.markdown("""
**QR scan → Form fill → Submit → Invitation Card instantly!**

| Step | Action |
|------|--------|
| 1 | 📱 QR scan karo |
| 2 | 📝 Name, Dept, Roll No, Batch bharein |
| 3 | 🏷️ Category choose karo |
| 4 | ✅ Submit karein |
| 5 | 🎉 Invitation Card turant milta hai! |
| 6 | 📲 WhatsApp / Social Media pe share |
        """)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### ✏️ Manual Entry")
        with st.form("manual_form"):
            m1,m2=st.columns(2)
            with m1: mn=st.text_input("Name"); md=st.text_input("Department")
            with m2:
                mr=st.text_input("Roll No")
                mb=st.text_input("Batch")
            cl2=[c.strip() for c in st.session_state.categories.split(",") if c.strip()]
            mc=st.selectbox("Category",cl2)
            if st.form_submit_button("➕ Add", use_container_width=True):
                if mn.strip() and mr.strip():
                    now=datetime.now(); ref=generate_ref_no(mc)
                    save_registration({"ref_no":ref,"name":mn.strip(),"roll_no":mr.strip(),
                        "department":md.strip(),"batch":mb.strip(),"category":mc,
                        "event":st.session_state.event_name,
                        "date":now.strftime("%Y-%m-%d"),"time":now.strftime("%H:%M:%S")})
                    st.success(f"✅ {mn.strip()} added!")
                else: st.error("Name aur Roll No zaroori hain!")
        st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════
#  TAB 2 — Registered Data
# ══════════════════════════════════════════════
with tab2:
    regs=load_registrations()
    st.markdown("### 📊 Registered Data")
    if st.button("🔄 Refresh"): st.rerun()
    cat_list=[c.strip() for c in st.session_state.categories.split(",") if c.strip()]
    mc=[st.columns(len(cat_list)+1)][0]
    mc[0].metric("Total",len(regs))
    for i,cat in enumerate(cat_list):
        mc[i+1].metric(cat,sum(1 for r in regs if r.get("category","")==cat))
    st.markdown("---")
    if regs:
        df=pd.DataFrame(regs)
        rename={"ref_no":"Ref No","name":"Full Name","roll_no":"Roll No",
                "department":"Department","batch":"Batch","category":"Category",
                "event":"Event","date":"Date","time":"Time"}
        df=df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
        fc=st.selectbox("Filter:",["All"]+cat_list,key="flt")
        st.dataframe(df if fc=="All" else df[df["Category"]==fc],
                     use_container_width=True, height=380)
        st.markdown("---")
        e1,e2,e3=st.columns(3)
        with e1:
            st.download_button("📊 Excel",build_excel(regs),
                file_name=f"{st.session_state.event_name.replace(' ','_')}_Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        with e2:
            st.download_button("📄 TXT",
                "\n".join(f"{r['name']}|{r['roll_no']}|{r['department']}|{r['category']}" for r in regs).encode(),
                file_name="registrations.txt",mime="text/plain",use_container_width=True)
        with e3:
            if st.button("🗑️ Clear All",use_container_width=True):
                clear_registrations(); st.success("Cleared!"); st.rerun()
    else:
        st.info("📭 Koi registration nahi abhi.")

# ══════════════════════════════════════════════
#  TAB 3 — Invitation Card
# ══════════════════════════════════════════════
with tab3:
    st.markdown("### 🃏 Invitation Card — Preview & Batch Generate")
    cfg_now=load_config()
    cfg_now["inv_theme"]=st.session_state.inv_theme
    l1b=base64.b64decode(st.session_state.logo1_b64) if st.session_state.logo1_b64 else None
    l2b=base64.b64decode(st.session_state.logo2_b64) if st.session_state.logo2_b64 else None
    l3b=base64.b64decode(st.session_state.logo3_b64) if st.session_state.logo3_b64 else None

    st.info(f"💡 Current Theme: **{THEME_LABELS.get(st.session_state.inv_theme,'—')}** | "
            f"Logos: **{sum(1 for x in [l1b,l2b,l3b] if x)}** uploaded")

    pname=st.text_input("Preview naam:",value="Muhammad Ali Khan",key="inv_pn")
    pcat=st.selectbox("Preview category:",[c.strip() for c in st.session_state.categories.split(",") if c.strip()],key="inv_pc")
    proll=st.text_input("Roll No:",value="CS-2022-45",key="inv_pr")

    srec={"ref_no":"P-260120-0001","name":pname,"roll_no":proll,
           "department":"Computer Science","batch":"2022-2026","category":pcat,
           "event":st.session_state.event_name,"date":datetime.now().strftime("%Y-%m-%d")}
    iprev=generate_invitation_card(srec,cfg_now,l1b,l2b,l3b)
    _,mid,_=st.columns([1,3,1])
    with mid: st.image(iprev,use_container_width=True)

    pd1,pd2=st.columns(2)
    with pd1:
        st.download_button("⬇️ Preview Download",iprev,
            file_name=f"Invitation_Preview_{pname.replace(' ','_')}.png",
            mime="image/png",use_container_width=True)
    with pd2:
        if st.button("💾 Save Theme Settings",use_container_width=True):
            save_all_settings(); st.success("✅ Saved!")

    st.markdown("---")
    regs_inv=load_registrations()
    if regs_inv:
        if st.button(f"🚀 Generate All {len(regs_inv)} Invitation Cards (ZIP)",use_container_width=True):
            p=st.progress(0); s=st.empty(); bz=io.BytesIO()
            with zipfile.ZipFile(bz,"w",zipfile.ZIP_DEFLATED) as zf:
                for i,rec in enumerate(regs_inv):
                    s.markdown(f"⏳ **{rec.get('name','')}** ({i+1}/{len(regs_inv)})")
                    card=generate_invitation_card(rec,cfg_now,l1b,l2b,l3b)
                    zf.writestr(f"Cards/{rec.get('category','Other')}/{rec.get('name','')}.png",card)
                    p.progress((i+1)/len(regs_inv))
            s.success("✅ Done!")
            st.download_button("⬇️ All Cards ZIP",bz.getvalue(),
                file_name="All_Invitation_Cards.zip",mime="application/zip",use_container_width=True)
    else:
        st.info("Koi registration nahi abhi.")

# ══════════════════════════════════════════════
#  TAB 4 — Certificate Preview
# ══════════════════════════════════════════════
with tab4:
    cl,cr=st.columns(2)
    with cl:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🖼️ Template Upload")
        tpl=st.file_uploader("Template (.png/.jpg)",type=["png","jpg","jpeg"])
        if tpl:
            st.session_state.template_bytes=tpl.read()
            img_tmp=Image.open(io.BytesIO(st.session_state.template_bytes))
            st.success(f"✅ {tpl.name} — {img_tmp.width}×{img_tmp.height}px")
        if st.session_state.template_bytes:
            st.image(st.session_state.template_bytes,use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with cr:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 👁️ Live Preview")
        if st.session_state.template_bytes:
            st.markdown(f"**Font:** `{st.session_state.selected_font}` | **Size:** `{st.session_state.font_size}` | "
                        f"**Pos:** ({st.session_state.text_x}%,{st.session_state.text_y}%)")
            pn=st.text_input("Preview naam:",value="Muhammad Ali Khan",key="cert_pn")
            pp=generate_cert(pn,st.session_state.template_bytes,cur_cfg())
            st.image(pp,use_container_width=True)
            pa,pb=st.columns(2)
            with pa: st.download_button("⬇️ PNG",pp,file_name=f"Preview_{pn}.png",mime="image/png",use_container_width=True)
            with pb: st.download_button("⬇️ PDF",cert_to_pdf(pp,pn),file_name=f"Preview_{pn}.pdf",mime="application/pdf",use_container_width=True)
        else:
            st.warning("⚠️ Template upload karo (left side)")
        st.markdown('</div>', unsafe_allow_html=True)

    regs_p=load_registrations()
    if st.session_state.template_bytes and regs_p:
        st.markdown("---")
        st.markdown("### 👁️ Sabke Certificates Preview")
        names_all=[r["name"] for r in regs_p]
        sn=st.slider("Kitne?",1,min(len(names_all),30),min(6,len(names_all)))
        for i in range(0,sn,3):
            rn=names_all[i:i+3]; cs=st.columns(3)
            for ci,nm in enumerate(rn):
                with cs[ci]:
                    pv=generate_cert(nm,st.session_state.template_bytes,cur_cfg())
                    st.image(pv,caption=nm,use_container_width=True)
                    st.download_button(f"⬇️ {nm[:14]}",pv,file_name=f"{nm}.png",mime="image/png",key=f"pv_{nm}_{i}_{ci}")

# ══════════════════════════════════════════════
#  TAB 5 — Generate Certificates
# ══════════════════════════════════════════════
with tab5:
    st.markdown("### 🚀 Bulk Certificate Generation")
    regs=load_registrations()
    if not st.session_state.template_bytes:
        st.markdown('<div class="card-warn">⚠️ Pehle Tab 4 mein template upload karo!</div>',unsafe_allow_html=True)
    elif not regs:
        st.markdown('<div class="card-warn">⚠️ Koi registration nahi hai.</div>',unsafe_allow_html=True)
    else:
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Total",len(regs)); c2.metric("Font",st.session_state.selected_font[:14])
        c3.metric("Size",st.session_state.font_size); c4.metric("Pos",f"{st.session_state.text_x}%,{st.session_state.text_y}%")
        st.markdown("---")
        f1,f2=st.columns(2)
        with f1: do_png=st.checkbox("✅ PNG",value=True)
        with f2: do_pdf=st.checkbox("✅ PDF",value=True)
        if st.button(f"🚀 Generate All {len(regs)} Certificates",use_container_width=True):
            cn=cur_cfg(); p=st.progress(0); s=st.empty(); bz=io.BytesIO()
            with zipfile.ZipFile(bz,"w",zipfile.ZIP_DEFLATED) as zf:
                for i,rec in enumerate(regs):
                    nm=rec["name"]; cat=rec.get("category","Other")
                    s.markdown(f"⏳ **{nm}** [{cat}] ({i+1}/{len(regs)})")
                    png=generate_cert(nm,st.session_state.template_bytes,cn)
                    if do_png: zf.writestr(f"PNG/{cat}/{nm}.png",png)
                    if do_pdf: zf.writestr(f"PDF/{cat}/{nm}.pdf",cert_to_pdf(png,nm))
                    p.progress((i+1)/len(regs))
            s.success(f"✅ {len(regs)} certificates ready!"); st.balloons()
            st.download_button(f"⬇️ Download All ZIP",bz.getvalue(),
                file_name=f"{st.session_state.event_name.replace(' ','_')}_Certificates.zip",
                mime="application/zip",use_container_width=True)

# ══════════════════════════════════════════════
#  TAB 6 — Backup & Security
# ══════════════════════════════════════════════
with tab6:
    st.markdown("### 💾 Backup & Data Security")

    # ── Security Status ────────────────────────────────────────
    st.markdown("#### 🔒 Security Status")
    auth_info=load_auth()
    sc1,sc2,sc3=st.columns(3)
    sc1.metric("Password","🔒 Hashed","PBKDF2-SHA256")
    sc2.metric("Algorithm","310,000 iterations","OWASP 2024")
    sc3.metric("Salt","256-bit random","Per password")

    if "changed" in auth_info:
        st.success(f"✅ Password last changed: {auth_info['changed'][:10]}")
    else:
        st.markdown('<div class="card-warn">⚠️ Password abhi default hai — sidebar se change karein!</div>',unsafe_allow_html=True)

    st.markdown("---")
    # ── Manual Backup ─────────────────────────────────────────
    st.markdown("#### 💾 Manual Backup")
    regs_b=load_registrations()
    bc1,bc2=st.columns(2)
    with bc1:
        st.metric("Registrations", len(regs_b))
        backup_data=create_backup()
        ts=datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            "⬇️ Download Full Backup (ZIP)",
            data=backup_data,
            file_name=f"QRSystem_Backup_{ts}.zip",
            mime="application/zip",
            use_container_width=True)
        st.caption("Backup mein: registrations.csv + config.json")
    with bc2:
        st.markdown("**Auto-backup status:**")
        bfiles=sorted(os.listdir(BACKUP_DIR)) if os.path.exists(BACKUP_DIR) else []
        if bfiles:
            st.success(f"✅ {len(bfiles)} auto-backups on server")
            for bf in bfiles[-5:]:  # last 5
                st.caption(f"📁 {bf}")
        else:
            st.info("Pehla auto-backup kal hoga")

    st.markdown("---")
    # ── Restore ───────────────────────────────────────────────
    st.markdown("#### 🔄 Restore Data")
    st.markdown("""
    <div class="card-blue">
    <b>Restore karne ka tarika:</b><br>
    1. Backup ZIP download karo<br>
    2. ZIP mein se <code>registrations.csv</code> aur <code>config.json</code> nikalo<br>
    3. App folder mein paste karo (same directory as app.py)<br>
    4. App restart karo — data wapas aa jayega ✅
    </div>
    """, unsafe_allow_html=True)

    upl_restore=st.file_uploader("Restore CSV file:",type=["csv"])
    if upl_restore:
        try:
            restore_df=pd.read_csv(upl_restore)
            st.success(f"✅ {len(restore_df)} records found in file")
            st.dataframe(restore_df.head(5),use_container_width=True)
            if st.button("⚠️ Confirm Restore (overwrites current data)"):
                restore_df.to_csv(DATA_FILE,index=False)
                st.success("✅ Data restored!"); st.rerun()
        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.markdown("---")
    # ── Danger zone ───────────────────────────────────────────
    st.markdown("#### ⚠️ Danger Zone")
    with st.expander("🗑️ Delete All Data (Irreversible)"):
        confirm=st.text_input("Type DELETE to confirm:")
        if st.button("🗑️ Delete All Registrations") and confirm=="DELETE":
            backup_data=create_backup()  # auto backup before delete
            clear_registrations()
            st.warning("✅ Deleted! Backup automatically liya gaya.")
            st.download_button("⬇️ Pre-delete Backup",backup_data,
                file_name="pre_delete_backup.zip",mime="application/zip")
            st.rerun()

# ══════════════════════════════════════════════
#  TAB 7 — Deploy Guide
# ══════════════════════════════════════════════
with tab7:
    st.markdown("""
<div class="card">

## ☁️ GitHub + Streamlit Cloud — Free Hosting

### Sirf 2 files GitHub par upload karo:
```
app.py
requirements.txt
```

### Commands:
```bash
cd d:/Avalon.AI
git add app.py requirements.txt
git commit -m "v5 - secure passwords + backups"
git push
```

### Deploy steps:
1. [share.streamlit.io](https://share.streamlit.io) → GitHub login
2. New App → repo select → `app.py` → Deploy
3. URL copy karo → Sidebar → Save → QR generate ✅

### 🔒 Security Notes:
- Default password: `Admin@2025` — **foran change karein!**
- `auth.json` mein sirf hash stored hai — plain password kabhi nahi
- `registrations.csv` aur `config.json` server par persist hote hain
- **Daily auto-backup** `backups/` folder mein hoti hai

</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.markdown('<p style="text-align:center;color:#7ecefd44;font-size:.85rem;">'
            '© QR Certificate System v5.0 | Abdul Samad | SBBU Nawabshah</p>',
            unsafe_allow_html=True)
