import streamlit as st
import streamlit.components.v1 as components
import requests
import google.generativeai as genai
from datetime import datetime
import json
import os
import time
import re
from PIL import Image
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import base64
import uuid
import pycountry
import hashlib

# ─── API Keys ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv

# Try to find .env in current and parent directories more explicitly
script_dir = os.path.dirname(os.path.abspath(__file__))
# Check for .env in current dir, project root or any parent
dotenv_path = None
curr_path = script_dir
while curr_path != os.path.dirname(curr_path): # Stop at root
    potential_dotenv = os.path.join(curr_path, ".env")
    if os.path.exists(potential_dotenv):
        dotenv_path = potential_dotenv
        break
    # Also check parent of 'project' or 'pages'
    curr_path = os.path.dirname(curr_path)

if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv() # Fallback to standard behavior

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USDA_API_KEY   = os.environ.get("USDA_API_KEY")

# Validate API Keys
if not GEMINI_API_KEY:
    st.error("❌ `GEMINI_API_KEY` not found! Please add it to your `.env` file.")
    st.info("The `.env` file should be in the project root or the same directory as this script.")
    st.stop()

if not USDA_API_KEY:
    st.warning("⚠️ `USDA_API_KEY` not found! USDA search functionality will be limited.")

try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"❌ Failed to configure Gemini API: {e}")
    st.stop()

# ─── Cache Directory ─────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".product_checker_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Product Health & Safety Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
def load_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap');

    * { font-family: 'DM Sans', sans-serif; }
    h1, h2, h3 { font-family: 'Syne', sans-serif; }

    .main-header { color: #059669; font-weight: 800; }
    .sub-header  { color: #424242; font-weight: 400; }

    .highlight-box {
        background: linear-gradient(135deg, #f0fdf4, #ecfdf5);
        padding: 14px; border-radius: 10px;
        border-left: 4px solid #059669; margin-bottom: 12px;
    }
    .success-box {
        background: #E8F5E9; padding: 14px; border-radius: 10px;
        border-left: 5px solid #4CAF50; margin-bottom: 12px;
    }
    .warning-box {
        background: #FFF8E1; padding: 14px; border-radius: 10px;
        border-left: 5px solid #FFC107; margin-bottom: 12px;
    }
    .danger-box {
        background: #FFEBEE; padding: 14px; border-radius: 10px;
        border-left: 5px solid #F44336; margin-bottom: 12px;
    }
    .metric-card {
        background: white; padding: 14px; border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08); text-align: center;
        margin-bottom: 10px;
    }
    .metric-value { font-size: 26px; font-weight: 700; color: #1E88E5; }
    .metric-label { font-size: 13px; color: #616161; margin-top: 4px; }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: #E8F5E9; border-radius: 6px 6px 0 0;
        padding: 10px 16px; font-weight: 500;
    }
    .stTabs [aria-selected="true"] { background: #059669; color: white; }

    .scanner-wrapper {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 20px; padding: 24px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        margin-bottom: 24px;
    }

    /* Chat styles */
    .chat-container {
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-height: 500px;
        overflow-y: auto;
        padding: 16px;
        background: #f8fafc;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        margin-bottom: 16px;
    }
    </style>
    """, unsafe_allow_html=True)

# ─── Barcode Scanner HTML Component ─────────────────────────────────────────
SCANNER_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'DM Sans', 'Segoe UI', sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
    color: white;
  }

  .title {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 6px;
    background: linear-gradient(90deg, #34d399, #059669);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .subtitle {
    font-size: 13px;
    color: #94a3b8;
    margin-bottom: 20px;
    text-align: center;
  }

  .camera-container {
    position: relative;
    width: 100%;
    max-width: 380px;
    border-radius: 20px;
    overflow: hidden;
    border: 3px solid #1e3a2f;
    box-shadow: 0 0 40px rgba(52, 211, 153, 0.25), 0 0 0 1px rgba(52,211,153,0.1);
    background: #000;
    aspect-ratio: 4/3;
  }

  video {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .scan-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }

  .scan-frame {
    width: 220px;
    height: 140px;
    position: relative;
  }

  .corner {
    position: absolute;
    width: 22px;
    height: 22px;
    border-color: #34d399;
    border-style: solid;
  }
  .corner.tl { top:0; left:0;  border-width: 3px 0 0 3px; border-radius: 4px 0 0 0; }
  .corner.tr { top:0; right:0; border-width: 3px 3px 0 0; border-radius: 0 4px 0 0; }
  .corner.bl { bottom:0; left:0;  border-width: 0 0 3px 3px; border-radius: 0 0 0 4px; }
  .corner.br { bottom:0; right:0; border-width: 0 3px 3px 0; border-radius: 0 0 4px 0; }

  .scan-line {
    position: absolute;
    left: 10px; right: 10px;
    height: 2px;
    background: linear-gradient(90deg, transparent, #34d399, transparent);
    animation: scanMove 2s linear infinite;
    box-shadow: 0 0 8px #34d399;
    top: 10px;
  }

  @keyframes scanMove {
    0%   { top: 10px; opacity: 1; }
    90%  { top: calc(100% - 12px); opacity: 1; }
    100% { top: 10px; opacity: 0; }
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 14px;
    padding: 8px 18px;
    border-radius: 100px;
    font-size: 13px;
    font-weight: 600;
    transition: all 0.3s ease;
  }
  .status-badge.idle    { background: rgba(255,255,255,0.08); color: #94a3b8; }
  .status-badge.scanning{ background: rgba(52,211,153,0.15); color: #34d399; border: 1px solid rgba(52,211,153,0.3); }
  .status-badge.found   { background: rgba(52,211,153,0.25); color: #34d399; border: 1px solid rgba(52,211,153,0.5); }
  .status-badge.error   { background: rgba(239,68,68,0.15);  color: #f87171; border: 1px solid rgba(239,68,68,0.3); }

  .dot {
    width: 8px; height: 8px; border-radius: 50%; background: currentColor;
  }
  .dot.pulse { animation: pulse 1.2s infinite; }
  @keyframes pulse {
    0%,100%{ opacity:1; transform:scale(1); }
    50%    { opacity:0.4; transform:scale(0.7); }
  }

  .controls {
    display: flex;
    gap: 10px;
    margin-top: 16px;
    width: 100%;
    max-width: 380px;
  }

  button {
    flex: 1;
    padding: 12px 16px;
    border: none;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    letter-spacing: 0.3px;
  }
  #scanBtn {
    background: linear-gradient(135deg, #059669, #34d399);
    color: white;
    box-shadow: 0 4px 20px rgba(52,211,153,0.3);
  }
  #scanBtn:hover  { transform: translateY(-1px); box-shadow: 0 6px 24px rgba(52,211,153,0.4); }
  #scanBtn:active { transform: translateY(0); }
  #scanBtn:disabled { background: #374151; color: #6b7280; box-shadow: none; cursor: not-allowed; transform: none; }

  #stopBtn {
    background: rgba(239,68,68,0.15);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.3);
    display: none;
  }
  #stopBtn:hover { background: rgba(239,68,68,0.25); }

  .manual-section {
    width: 100%;
    max-width: 380px;
    margin-top: 14px;
  }
  .manual-label {
    font-size: 12px;
    color: #64748b;
    margin-bottom: 8px;
    text-align: center;
  }
  .manual-row {
    display: flex;
    gap: 8px;
  }
  .manual-row input {
    flex: 1;
    padding: 10px 14px;
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    color: white;
    font-size: 14px;
    outline: none;
    transition: border 0.2s;
  }
  .manual-row input:focus { border-color: #34d399; }
  .manual-row input::placeholder { color: #475569; }
  .manual-row button {
    flex: 0 0 auto;
    width: auto;
    padding: 10px 18px;
    background: rgba(52,211,153,0.15);
    color: #34d399;
    border: 1px solid rgba(52,211,153,0.3);
    border-radius: 10px;
    font-size: 13px;
  }
  .manual-row button:hover { background: rgba(52,211,153,0.25); }

  .product-result {
    width: 100%;
    max-width: 380px;
    margin-top: 16px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 16px;
    display: none;
    animation: fadeIn 0.4s ease;
  }
  @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }

  .product-result.visible { display: block; }
  .product-img {
    width: 80px; height: 80px;
    object-fit: contain;
    border-radius: 10px;
    background: white;
    padding: 6px;
    float: left;
    margin-right: 12px;
  }
  .product-name { font-size: 15px; font-weight: 700; color: #f1f5f9; margin-bottom: 3px; }
  .product-brand { font-size: 12px; color: #94a3b8; margin-bottom: 6px; }
  .product-tags { display: flex; flex-wrap: wrap; gap: 5px; }
  .tag {
    font-size: 11px; font-weight: 600;
    padding: 2px 9px; border-radius: 100px;
  }
  .tag.ns-a,.tag.ns-b { background:rgba(52,211,153,0.2); color:#34d399; }
  .tag.ns-c           { background:rgba(234,179,8,0.2);   color:#eab308; }
  .tag.ns-d,.tag.ns-e { background:rgba(239,68,68,0.2);   color:#f87171; }
  .tag.default        { background:rgba(148,163,184,0.15); color:#94a3b8; }

  .clearfix::after { content:''; display:table; clear:both; }

  .camera-error {
    position: absolute; inset: 0;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: rgba(15,23,42,0.95);
    color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;
    gap: 8px; display: none;
  }
  .camera-error.show { display: flex; }
  .camera-error-icon { font-size: 36px; }
</style>
</head>
<body>

<div class="title">🔍 Barcode Scanner</div>
<div class="subtitle">Point camera at barcode — it auto-detects instantly</div>

<div class="camera-container">
  <video id="video" autoplay playsinline muted></video>
  <div class="scan-overlay">
    <div class="scan-frame">
      <div class="corner tl"></div>
      <div class="corner tr"></div>
      <div class="corner bl"></div>
      <div class="corner br"></div>
      <div class="scan-line" id="scanLine" style="display:none"></div>
    </div>
  </div>
  <div class="camera-error" id="cameraError">
    <div class="camera-error-icon">📷</div>
    <div>Camera not available.<br>Use manual entry below.</div>
  </div>
</div>

<div id="statusBadge" class="status-badge idle">
  <div class="dot"></div>
  <span id="statusText">Ready</span>
</div>

<div class="controls">
  <button id="scanBtn">▶ Start Scanning</button>
  <button id="stopBtn">⏹ Stop</button>
</div>

<div class="manual-section">
  <div class="manual-label">— or enter barcode manually —</div>
  <div class="manual-row">
    <input id="manualInput" type="number" placeholder="Enter barcode number..." />
    <button id="manualBtn">Search</button>
  </div>
</div>

<div class="product-result" id="productResult">
  <div class="clearfix">
    <img class="product-img" id="productImg" src="" alt="" />
    <div class="product-name" id="productName"></div>
    <div class="product-brand" id="productBrand"></div>
    <div class="product-tags" id="productTags"></div>
  </div>
</div>

<script>
const video      = document.getElementById("video");
const scanBtn    = document.getElementById("scanBtn");
const stopBtn    = document.getElementById("stopBtn");
const statusBadge= document.getElementById("statusBadge");
const statusText = document.getElementById("statusText");
const scanLine   = document.getElementById("scanLine");
const cameraError= document.getElementById("cameraError");
const manualInput= document.getElementById("manualInput");
const manualBtn  = document.getElementById("manualBtn");
const productResult = document.getElementById("productResult");

let scanning   = false;
let detector   = null;
let lastCode   = null;
let cooldown   = false;
let streamRef  = null;

function setStatus(type, text) {
  statusBadge.className = "status-badge " + type;
  statusText.textContent = text;
  const dot = statusBadge.querySelector(".dot");
  dot.className = "dot" + (type === "scanning" ? " pulse" : "");
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
      audio: false
    });
    streamRef = stream;
    video.srcObject = stream;
    return true;
  } catch(e) {
    cameraError.classList.add("show");
    return false;
  }
}

function stopCamera() {
  if (streamRef) {
    streamRef.getTracks().forEach(t => t.stop());
    streamRef = null;
  }
}

function isBarcodeSupported() {
  return "BarcodeDetector" in window;
}

async function fetchProduct(code) {
  setStatus("scanning", "Fetching product…");
  try {
    const res  = await fetch(`https://world.openfoodfacts.org/api/v0/product/${code}.json`);
    const data = await res.json();

    if (data.status === 1) {
      const p = data.product;
      showProductCard(
        p.product_name || "Unknown Product",
        p.brands       || "",
        p.image_url    || "",
        p.nutriscore_grade || "",
        p.nova_group   || "",
        p.ecoscore_grade || "",
        code
      );
      setStatus("found", "Product found!");
      sendToStreamlit(code);
    } else {
      setStatus("error", "Product not found — try USDA");
      sendToStreamlit(code);
    }
  } catch(e) {
    setStatus("error", "Network error");
  }
  cooldown = false;
}

function showProductCard(name, brand, img, ns, nova, eco, code) {
  document.getElementById("productName").textContent  = name;
  document.getElementById("productBrand").textContent = brand ? "Brand: " + brand : "Barcode: " + code;
  const imgEl = document.getElementById("productImg");
  if (img) { imgEl.src = img; imgEl.style.display = "block"; }
  else      { imgEl.style.display = "none"; }

  const tags = document.getElementById("productTags");
  tags.innerHTML = "";
  if (ns)   tags.innerHTML += `<span class="tag ns-${ns}">NutriScore: ${ns.toUpperCase()}</span>`;
  if (nova) tags.innerHTML += `<span class="tag default">NOVA: ${nova}</span>`;
  if (eco)  tags.innerHTML += `<span class="tag ns-${eco}">Eco: ${eco.toUpperCase()}</span>`;
  if (code) tags.innerHTML += `<span class="tag default">📦 ${code}</span>`;

  productResult.classList.add("visible");
}

function sendToStreamlit(code) {
  window.parent.postMessage({ type: "barcode", code: code }, "*");
}

async function scanLoop() {
  if (!isBarcodeSupported()) {
    setStatus("error", "BarcodeDetector not supported — use manual entry");
    return;
  }

  if (!detector) {
    try {
      detector = new BarcodeDetector({ formats: ["ean_13","ean_8","upc_a","upc_e","code_128","code_39","qr_code","data_matrix"] });
    } catch(e) {
      setStatus("error", "Detector init failed");
      return;
    }
  }

  scanning = true;
  scanLine.style.display = "block";
  scanBtn.disabled = true;
  stopBtn.style.display = "block";
  setStatus("scanning", "Scanning…");

  while (scanning) {
    if (video.readyState >= 2 && !cooldown) {
      try {
        const codes = await detector.detect(video);
        if (codes.length > 0) {
          const code = codes[0].rawValue;
          if (code !== lastCode) {
            lastCode = code;
            cooldown = true;
            setStatus("found", "Barcode: " + code);
            fetchProduct(code);
          }
        }
      } catch(e) { /* ignore frame errors */ }
    }
    await new Promise(r => setTimeout(r, 200));
  }
}

function stopScanning() {
  scanning  = false;
  cooldown  = false;
  scanLine.style.display  = "none";
  scanBtn.disabled        = false;
  stopBtn.style.display   = "none";
  setStatus("idle", "Stopped");
}

scanBtn.addEventListener("click", async () => {
  if (!streamRef) {
    const ok = await startCamera();
    if (!ok) return;
  }
  lastCode = null;
  scanLoop();
});

stopBtn.addEventListener("click", stopScanning);

manualBtn.addEventListener("click", () => {
  const code = manualInput.value.trim();
  if (code) fetchProduct(code);
});

manualInput.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    const code = manualInput.value.trim();
    if (code) fetchProduct(code);
  }
});

startCamera();
</script>
</body>
</html>
"""

# ─── RegulationDatabase ──────────────────────────────────────────────────────
class RegulationDatabase:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        self.banned_products_file = os.path.join(cache_dir, "banned_products.json")
        self.recalls_file         = os.path.join(cache_dir, "product_recalls.json")
        self.initialize_database()

    def initialize_database(self):
        if not os.path.exists(self.banned_products_file):
            data = {
                "ingredients": {
                    "Potassium Bromate": {"banned_in":["European Union","United Kingdom","Canada","Brazil","China","India"],"reason":"Potential carcinogen","alternatives":["Ascorbic acid","Enzymes"]},
                    "Brominated Vegetable Oil (BVO)": {"banned_in":["European Union","Japan","India"],"reason":"Thyroid problems","alternatives":["Natural emulsifiers"]},
                    "Azodicarbonamide": {"banned_in":["European Union","Australia","United Kingdom","Singapore"],"reason":"Respiratory issues","alternatives":["Ascorbic acid"]},
                    "BHA/BHT": {"banned_in":["Japan","European Union"],"reason":"Potential endocrine disruptors","alternatives":["Vitamin E","Rosemary extract"]},
                    "Tartrazine (Yellow #5)": {"banned_in":["Norway","Austria"],"reason":"Hyperactivity in children","alternatives":["Natural food colors"]},
                    "Sodium Cyclamate": {"banned_in":["United States"],"reason":"Cancer in animal studies","alternatives":["Stevia"]},
                    "Titanium Dioxide (E171)": {"banned_in":["European Union"],"reason":"Potential genotoxicity","alternatives":["Natural whitening agents"]}
                },
                "products": {
                    "Unpasteurized dairy products": {"banned_in":["Australia","Canada","Scotland"],"reason":"Harmful bacteria risk","alternatives":"Pasteurized dairy"},
                    "Kinder Surprise Eggs (original)": {"banned_in":["United States"],"reason":"Choking hazard","alternatives":"Kinder Joy"}
                }
            }
            with open(self.banned_products_file, 'w') as f:
                json.dump(data, f, indent=2)

        if not os.path.exists(self.recalls_file):
            data = {"recent_recalls":[
                {"product_name":"XYZ Organic Peanut Butter","date":"2024-02-15","reason":"Potential Salmonella","regions_affected":["United States","Canada"],"batch_numbers":["PB202401"]},
                {"product_name":"ABC Infant Formula","date":"2024-01-22","reason":"Possible Cronobacter","regions_affected":["United States"],"batch_numbers":["IF24A123"]},
            ]}
            with open(self.recalls_file, 'w') as f:
                json.dump(data, f, indent=2)

    def load_banned_products(self):
        try:
            with open(self.banned_products_file) as f: return json.load(f)
        except: return {"ingredients":{}, "products":{}}

    def load_product_recalls(self):
        try:
            with open(self.recalls_file) as f: return json.load(f)
        except: return {"recent_recalls":[]}

    def check_against_banned_ingredients(self, ingredients_text):
        if not ingredients_text or ingredients_text == "Not available": return []
        banned_data = self.load_banned_products()
        found = []
        txt = ingredients_text.lower()
        for ing, data in banned_data["ingredients"].items():
            if ing.lower() in txt:
                found.append({"ingredient": ing, **data})
        return found

    def check_product_recalls(self, product_name, brand_name):
        recalls = self.load_product_recalls()
        terms   = [product_name.lower(), brand_name.lower()]
        return [r for r in recalls["recent_recalls"] if any(t in r["product_name"].lower() for t in terms)]

    def check_banned_products(self, product_name):
        data = self.load_banned_products()
        out  = []
        for bp, d in data["products"].items():
            if product_name.lower() == bp.lower():
                out.append({"product": bp, **d})
        return out

    def check_compliance(self, ingredients, region):
        banned_data = self.load_banned_products()
        issues = []
        for ing in ingredients.split(","):
            ing = ing.strip().lower()
            for banned_ing in banned_data["ingredients"]:
                if ing and ing in banned_ing.lower():
                    issues.append(f"{ing} is restricted in {region}.")
        return {"compliant": len(issues) == 0, "issues": issues}

    def check_food_packaging_compliance(self, ingredients, region):
        return self.check_compliance(ingredients, region)


# ─── DataFetcher ─────────────────────────────────────────────────────────────
class DataFetcher:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        self.session   = requests.Session()
        self.session.headers.update({'User-Agent': 'ProductHealthSafetyAnalyzer/2.0'})

    def _cache_path(self, key, src):
        h = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{src}_{h}.json")

    def _load_cache(self, key, src, max_age=86400):
        p = self._cache_path(key, src)
        if os.path.exists(p):
            try:
                with open(p) as f: c = json.load(f)
                if time.time() - c.get('cache_time', 0) <= max_age:
                    return c.get('data')
            except: pass
        return None

    def _save_cache(self, key, src, data):
        p = self._cache_path(key, src)
        try:
            with open(p,'w') as f: json.dump({'data': data, 'cache_time': time.time()}, f)
        except: pass

    def _get(self, url, params=None):
        for i in range(3):
            try:
                r = self.session.get(url, params=params, timeout=12)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if i == 2: raise e
                time.sleep(1*(i+1))

    def fetch_from_open_food_facts(self, barcode):
        cached = self._load_cache(barcode, 'off')
        if cached: return self._extract_off(cached)
        try:
            data = self._get(f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json")
            if data.get("status") == 1:
                self._save_cache(barcode, 'off', data)
                return self._extract_off(data)
            return (None,)*7
        except Exception as e:
            st.error(f"Error fetching from Open Food Facts: {e}")
            return (None,)*7

    def _extract_off(self, data):
        if data.get("status") != 1: return (None,)*7
        p = data["product"]
        name      = p.get("product_name","Unknown Product")
        brand     = p.get("brands","Unknown Brand")
        category  = (p.get("categories_tags",["unknown"])[0]).replace("en:","").capitalize() if p.get("categories_tags") else "Unknown"
        origin    = p.get("countries","Unknown")
        img       = p.get("image_url")
        allergens = [a.replace("en:","") for a in p.get("allergens_tags",[])]
        details = {
            "ingredients":         p.get("ingredients_text","Not available"),
            "ingredients_list":    [i.get("text","") for i in p.get("ingredients",[])],
            "nutriments":          p.get("nutriments",{}),
            "nutrition_grades":    p.get("nutrition_grades",""),
            "nova_group":          p.get("nova_group",""),
            "ecoscore_grade":      p.get("ecoscore_grade",""),
            "packaging":           p.get("packaging","Not specified"),
            "manufacturing_places":p.get("manufacturing_places","Not specified"),
            "additives_tags":      [a.replace("en:","") for a in p.get("additives_tags",[])],
            "labels":              p.get("labels",""),
            "allergens":           allergens,
            "serving_size":        p.get("serving_size","Not specified"),
            "stores":              p.get("stores","Not specified"),
            "image_url":           img,
            "traces":              p.get("traces","")
        }
        return name, brand, category, origin, details, img, allergens

    def fetch_from_usda(self, barcode):
        cached = self._load_cache(barcode, 'usda')
        if cached: return self._extract_usda(cached)
        try:
            search = self._get("https://api.nal.usda.gov/fdc/v1/foods/search",
                               {"api_key": USDA_API_KEY, "query": barcode, "pageSize": 1})
            if not search.get("foods"): return (None,)*7
            fid    = search["foods"][0]["fdcId"]
            detail = self._get(f"https://api.nal.usda.gov/fdc/v1/food/{fid}", {"api_key": USDA_API_KEY})
            combined = {"search_result": search, "detail": detail}
            self._save_cache(barcode, 'usda', combined)
            return self._extract_usda(combined)
        except Exception as e:
            st.error(f"Error fetching from USDA: {e}")
            return (None,)*7

    def _extract_usda(self, combined):
        try:
            search = combined.get("search_result",{})
            detail = combined.get("detail",{})
            if not search.get("foods"): return (None,)*7
            food  = search["foods"][0]
            name  = food.get("description","Unknown")
            brand = food.get("brandOwner","Unknown Brand")
            cat   = food.get("foodCategory","Unknown")
            orig  = detail.get("marketCountry","Unknown")
            ings  = detail.get("ingredients","Not available")
            allergens = []
            ndisp = {}
            for n in detail.get("foodNutrients",[]):
                if "nutrientName" in n and "value" in n:
                    ndisp[n["nutrientName"]] = {"value":n["value"],"unit":n.get("unitName","")}
            details = {
                "ingredients": ings, "foodNutrients": detail.get("foodNutrients",[]),
                "nutrients_display": ndisp, "ingredients_list": [],
                "serving_size": detail.get("servingSize","Not specified"),
                "serving_unit": detail.get("servingSizeUnit",""),
                "additives_tags": [], "labels": "", "packaging": "Not specified",
                "ecoscore_grade": "", "nutrition_grades": "", "nova_group": "",
                "nutriments": {}, "allergens": [], "traces": "", "image_url": None
            }
            return name, brand, cat, orig, details, None, allergens
        except Exception as e:
            st.error(f"Error processing USDA data: {e}")
            return (None,)*7

    def search_products_by_name(self, name):
        cached = self._load_cache(f"search_{name}", 'off')
        if cached: return cached
        try:
            data = self._get("https://world.openfoodfacts.org/cgi/search.pl",
                             {"search_terms": name, "search_simple":1, "action":"process","json":1,"page_size":10})
            prods = data.get("products",[]) if data else []
            self._save_cache(f"search_{name}", 'off', prods)
            return prods
        except: return []


# ─── AIAnalyzer ──────────────────────────────────────────────────────────────
class AIAnalyzer:
    def __init__(self):
        pass  # genai already configured at module level

    def _cache_path(self, atype, pname, bname):
        h = hashlib.md5(f"{pname}_{bname}".encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{atype}_{h}.json")

    def _load_cache(self, atype, pname, bname, max_age=604800):
        p = self._cache_path(atype, pname, bname)
        if os.path.exists(p):
            try:
                with open(p) as f: c = json.load(f)
                if time.time() - c.get('cache_time',0) <= max_age: return c.get('data')
            except: pass
        return None

    def _save_cache(self, atype, pname, bname, data):
        p = self._cache_path(atype, pname, bname)
        try:
            with open(p,'w') as f: json.dump({'data':data,'cache_time':time.time()},f)
        except: pass

    def _model(self): return genai.GenerativeModel("gemini-2.0-flash")

    def _gen(self, prompt):
        try:
            r = self._model().generate_content(prompt)
            return r.text if r else ""
        except Exception as e:
            return f"Error: {e}"

    def _extract_rating(self, text):
        m = re.search(r'(?:rate|rating|score)[^\d]*(\d+(?:\.\d+)?)\s*(?:\/|of|out of)?\s*10', text, re.IGNORECASE)
        if m:
            v = float(m.group(1))
            if 0 <= v <= 10: return v
        return 5.0

    def _extract_nutrition_metrics(self, text, details):
        metrics = {k:None for k in ["calories_per_serving","sugar_content_g","saturated_fat_g","sodium_mg","protein_g","fiber_g","additive_count"]}
        patterns = {
            "calories_per_serving": r"calories[^:]*:?\s*(\d+(?:\.\d+)?)",
            "sugar_content_g":      r"sugar[^:]*:?\s*(\d+(?:\.\d+)?)",
            "saturated_fat_g":      r"saturated[^:]*:?\s*(\d+(?:\.\d+)?)",
            "sodium_mg":            r"sodium[^:]*:?\s*(\d+(?:\.\d+)?)",
            "protein_g":            r"protein[^:]*:?\s*(\d+(?:\.\d+)?)",
            "fiber_g":              r"fiber[^:]*:?\s*(\d+(?:\.\d+)?)",
            "additive_count":       r"additive[^:]*:?\s*(\d+)"
        }
        for k, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try: metrics[k] = float(m.group(1))
                except: pass

        if details and "nutriments" in details:
            n = details["nutriments"]
            if metrics["calories_per_serving"] is None and "energy-kcal_serving" in n: metrics["calories_per_serving"] = n["energy-kcal_serving"]
            if metrics["sugar_content_g"]      is None and "sugars_100g"          in n: metrics["sugar_content_g"]      = n["sugars_100g"]
            if metrics["saturated_fat_g"]      is None and "saturated-fat_100g"   in n: metrics["saturated_fat_g"]      = n["saturated-fat_100g"]
            if metrics["sodium_mg"]            is None and "sodium_100g"           in n: metrics["sodium_mg"]            = n["sodium_100g"] * 1000
            if metrics["protein_g"]            is None and "proteins_100g"         in n: metrics["protein_g"]            = n["proteins_100g"]
            if metrics["fiber_g"]              is None and "fiber_100g"            in n: metrics["fiber_g"]              = n["fiber_100g"]
        if metrics["additive_count"] is None and "additives_tags" in details:
            metrics["additive_count"] = len(details["additives_tags"])
        return metrics

    def _ctx(self, details):
        ctx = ""
        if not details: return ctx
        if details.get("ingredients") and details["ingredients"] != "Not available":
            ctx += f"Ingredients: {details['ingredients']}\n\n"
        if details.get("nutriments"):
            ctx += "Nutritional Info:\n"
            for k,v in details["nutriments"].items():
                if isinstance(v,(int,float)) and ("_100g" in k or "_serving" in k):
                    ctx += f"  {k}: {v}\n"
        if details.get("nutrition_grades"): ctx += f"\nNutri-Score: {details['nutrition_grades'].upper()}\n"
        if details.get("nova_group"):       ctx += f"NOVA Group: {details['nova_group']}\n"
        if details.get("additives_tags"):   ctx += f"Additives: {', '.join(details['additives_tags'])}\n"
        return ctx

    def analyze_product_health(self, pname, bname, cat, details):
        cached = self._load_cache("health", pname, bname)
        if cached: return cached.get("analysis",""), cached.get("rating",0), cached.get("metrics",{})
        ctx = self._ctx(details)
        prompt = f"Analyze health of '{pname}' by '{bname}' in '{cat}'.\n\n{ctx}\n\n1. Top 5 health factors\n2. Rate 1-10 with explanation\n3. Health concerns for specific groups\n4. Healthier alternatives\n5. Numeric estimates: calories_per_serving, sugar_content_g, saturated_fat_g, sodium_mg, protein_g, fiber_g, additive_count\n\nUse clear headings."
        text = self._gen(prompt)
        rating  = self._extract_rating(text)
        metrics = self._extract_nutrition_metrics(text, details)
        self._save_cache("health", pname, bname, {"analysis":text,"rating":rating,"metrics":metrics})
        return text, rating, metrics

    def analyze_environmental_impact(self, pname, bname, details):
        cached = self._load_cache("env", pname, bname)
        if cached: return cached.get("analysis",""), cached.get("rating",0)
        prompt = f"Analyze environmental impact of '{pname}' by '{bname}'.\nPackaging: {details.get('packaging','?')}\nEcoscore: {details.get('ecoscore_grade','?')}\nManufacturing: {details.get('manufacturing_places','?')}\n\n1. Rate 1-10 environmental friendliness\n2. Packaging sustainability\n3. Carbon footprint\n4. Sustainable alternatives"
        text   = self._gen(prompt)
        rating = self._extract_rating(text)
        self._save_cache("env", pname, bname, {"analysis":text,"rating":rating})
        return text, rating

    def analyze_allergen_risks(self, pname, bname, allergens, ingredients):
        cached = self._load_cache("allergen", pname, bname)
        if cached: return cached
        alist  = ", ".join(allergens) if allergens else "None listed"
        prompt = f"Analyze allergen risks for '{pname}' by '{bname}'.\nListed allergens: {alist}\nIngredients: {ingredients}\n\n1. Explicit allergens\n2. Hidden allergens from ingredients\n3. Cross-contamination risks\n4. Recommendations"
        text   = self._gen(prompt)
        self._save_cache("allergen", pname, bname, text)
        return text

    def generate_healthier_recipes(self, pname, cat, ingredients):
        cached = self._load_cache("recipes", pname, cat)
        if cached: return cached
        prompt = f"Give 3 healthier homemade alternatives to '{pname}' (category: {cat}).\nOriginal ingredients: {ingredients}\n\nFor each: name, wholesome ingredients, instructions, health benefits vs original."
        text   = self._gen(prompt)
        self._save_cache("recipes", pname, cat, text)
        return text

    def check_certification(self, bname, pname, cert_type, details=None):
        cached = self._load_cache(f"cert_{cert_type}", pname, bname)
        if cached: return cached
        ctx = ""
        if details:
            if details.get("ingredients","") != "Not available": ctx += f"Ingredients: {details['ingredients']}\n"
            if details.get("labels"):                            ctx += f"Labels: {details['labels']}\n"
        prompt = f"Assess '{pname}' by '{bname}' for {cert_type} compliance.\n{ctx}\n1. Likely meets requirements?\n2. Common compliance issues\n3. What consumers should know\n4. Recommendations"
        text   = self._gen(prompt)
        self._save_cache(f"cert_{cert_type}", pname, bname, text)
        return text


# ─── Chat Helpers ────────────────────────────────────────────────────────────
def _format_product_context(product_data):
    """Build a readable context string from product data for the AI prompt."""
    details = product_data.get("details", {})
    parts = []
    parts.append(f"Product Name: {product_data.get('product_name', 'Unknown')}")
    parts.append(f"Brand: {product_data.get('brand_name', 'Unknown')}")
    parts.append(f"Category: {product_data.get('category', 'Unknown')}")
    parts.append(f"Origin: {product_data.get('origin', 'Unknown')}")

    ingredients = details.get("ingredients", "Not available")
    if ingredients and ingredients != "Not available":
        parts.append(f"Ingredients: {ingredients}")

    allergens = product_data.get("allergens", [])
    if allergens:
        parts.append(f"Declared Allergens: {', '.join(allergens)}")

    ns = details.get("nutrition_grades", "")
    if ns:
        parts.append(f"Nutri-Score: {ns.upper()}")

    nova = details.get("nova_group", "")
    if nova:
        parts.append(f"NOVA Group: {nova}")

    eco = details.get("ecoscore_grade", "")
    if eco:
        parts.append(f"Eco-Score: {eco.upper()}")

    additives = details.get("additives_tags", [])
    if additives:
        parts.append(f"Additives ({len(additives)}): {', '.join(additives[:15])}")

    nutriments = details.get("nutriments", {})
    if nutriments:
        nut_parts = []
        for label, key, unit, mult in [
            ("Calories", "energy-kcal_100g", "kcal", 1),
            ("Fat", "fat_100g", "g", 1),
            ("Sat. Fat", "saturated-fat_100g", "g", 1),
            ("Carbs", "carbohydrates_100g", "g", 1),
            ("Sugars", "sugars_100g", "g", 1),
            ("Fiber", "fiber_100g", "g", 1),
            ("Protein", "proteins_100g", "g", 1),
            ("Sodium", "sodium_100g", "mg", 1000),
        ]:
            v = nutriments.get(key)
            if v is not None:
                nut_parts.append(f"{label}: {v * mult:.1f} {unit}")
        if nut_parts:
            parts.append("Nutrition per 100g: " + ", ".join(nut_parts))

    labels = details.get("labels", "")
    if labels:
        parts.append(f"Labels/Certifications: {labels}")

    packaging = details.get("packaging", "Not specified")
    if packaging and packaging != "Not specified":
        parts.append(f"Packaging: {packaging}")

    traces = details.get("traces", "")
    if traces:
        parts.append(f"May contain traces of: {traces}")

    # Limit total context size to avoid exceeding token limits
    context = "\n".join(parts)
    if len(context) > 3000:
        context = context[:3000] + "\n[...truncated]"
    return context


def get_gemini_response(question, product_name, product_context):
    """Get AI response for a product-related question."""
    system_instruction = (
        "You are a knowledgeable product health and safety expert. "
        "You answer questions about food products based on the product information provided. "
        "Give clear, accurate, well-structured answers. "
        "When discussing health, safety, allergens, nutrition, or environmental impact, "
        "be specific and cite the product's actual data. "
        "If the information is not available in the product data, say so honestly. "
        "Keep answers concise but thorough."
    )
    prompt = (
        f"{system_instruction}\n\n"
        f"--- Product Information ---\n"
        f"{product_context}\n\n"
        f"--- User Question ---\n"
        f"{question}\n\n"
        f"Please provide a helpful, accurate answer:"
    )
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        r = model.generate_content(prompt)
        if r and r.text:
            return r.text.strip()
        return "I wasn't able to generate a response. Please try rephrasing your question."
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "rate" in error_msg.lower():
            return "⚠️ API rate limit reached. Please wait a moment and try again."
        elif "block" in error_msg.lower() or "safety" in error_msg.lower():
            return "⚠️ The response was blocked by content safety filters. Please rephrase your question."
        return f"⚠️ Error getting response: {error_msg}"


# ─── Display full product info ────────────────────────────────────────────────
def display_product_information(product_data, regulation_db, ai_analyzer):
    product_name = product_data["product_name"]
    brand_name   = product_data["brand_name"]
    category     = product_data["category"]
    origin       = product_data["origin"]
    details      = product_data["details"]
    image_url    = product_data["image_url"]
    allergens    = product_data["allergens"]
    barcode      = product_data.get("barcode","Unknown")
    ingredients  = details.get("ingredients","Not available")

    # ── Header ──
    col1, col2 = st.columns([1, 3])
    with col1:
        if image_url: st.image(image_url, width=200)
        else:         st.image("https://cdn-icons-png.flaticon.com/512/1046/1046857.png", width=200)
    with col2:
        st.markdown(f"<h2 class='main-header'>{product_name}</h2>", unsafe_allow_html=True)
        st.markdown(f"**Brand:** {brand_name}  |  **Category:** {category}  |  **Origin:** {origin}  |  **Barcode:** {barcode}")

    # ── Safety Summary ──
    st.header("Safety & Certification Summary")
    banned_ings   = regulation_db.check_against_banned_ingredients(ingredients)
    recalls       = regulation_db.check_product_recalls(product_name, brand_name)
    fssai_cert    = "Yes" if "FSSAI" in details.get("labels","") else "No"
    eco_score     = details.get("ecoscore_grade","N/A")
    nutri_score   = details.get("nutrition_grades","N/A")
    additives_cnt = len(details.get("additives_tags",[]))
    serving_size  = details.get("serving_size","Not specified")
    banned_text   = ", ".join(i["ingredient"] for i in banned_ings) if banned_ings else "None"

    rows = {
        "Is it safe for children?":  ("Yes (check full analysis)", "✅"),
        "FSSAI Certified":           (fssai_cert, "✅" if fssai_cert=="Yes" else "❌"),
        "Other Certifications":      (details.get("labels","None") or "None", "📜"),
        "Contains Allergens":        (", ".join(allergens) if allergens else "No allergens declared", "⚠️" if allergens else "✅"),
        "Banned Ingredients Found":  (banned_text, "🚫" if banned_ings else "✅"),
        "Recent Recalls":            ("Yes" if recalls else "No", "🚨" if recalls else "✅"),
        "Eco-Score":                 (eco_score.upper() if eco_score else "N/A", "🌱"),
        "Nutri-Score":               (nutri_score.upper() if nutri_score else "N/A", "🍏"),
        "Additives Count":           (str(additives_cnt), "⚗️"),
        "Serving Size":              (serving_size, "🍽️")
    }
    cols = st.columns(2)
    for i, (k,(v,icon)) in enumerate(rows.items()):
        with cols[i%2]:
            st.write(f"{icon} **{k}:** {v}")

    # ── Banned Products Check ──
    banned_prods = regulation_db.check_banned_products(product_name)
    if banned_prods:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.write("❌ This product is banned/seized in some countries:")
        for bp in banned_prods:
            st.write(f"- **{bp['product']}** — Banned in: {', '.join(bp['banned_in'])} — Reason: {bp['reason']}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='success-box'>✅ This product is not banned in any known database entry.</div>", unsafe_allow_html=True)

    # ── Compliance ──
    compliance = regulation_db.check_food_packaging_compliance(ingredients, st.session_state.region)
    if compliance["compliant"]:
        st.markdown(f"<div class='success-box'>✅ Appears compliant with food regulations in {st.session_state.region}.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='danger-box'>❌ Possible compliance issues:<br>" + "<br>".join(f"• {i}" for i in compliance["issues"]) + "</div>", unsafe_allow_html=True)

    # ── Banned Ingredient Detail ──
    if banned_ings:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.markdown("## ⚠️ Regulatory Alerts")
        for item in banned_ings:
            st.markdown(f"**{item['ingredient']}** — Banned in: {', '.join(item['banned_in'])} — Reason: {item['reason']} — Alt: {', '.join(item['alternatives'])}")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Recall Detail ──
    if recalls:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.markdown("## 🚨 Recall Alerts")
        for r in recalls:
            st.markdown(f"**Date:** {r['date']} | **Reason:** {r['reason']} | **Regions:** {', '.join(r['regions_affected'])} | **Batches:** {', '.join(r['batch_numbers'])}")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── TABS ──
    tabs = st.tabs(["📋 Product Details","❤️ Health Analysis","🌿 Environmental","🚫 Allergens","🔬 Certifications","🥗 Healthier Alternatives"])

    # Tab 0 – Product Details
    with tabs[0]:
        st.header("Product Details")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Ingredients")
            if ingredients != "Not available":
                st.markdown(f"<div class='highlight-box'>{ingredients}</div>", unsafe_allow_html=True)
            else:
                st.info("Ingredients not available")
        with c2:
            st.subheader("Nutritional Information (per 100g)")
            nut = details.get("nutriments",{})
            if nut:
                if "energy-kcal_100g" in nut: st.metric("Calories", f"{nut['energy-kcal_100g']:.1f} kcal")
                for label,key,unit,mult in [("Fat","fat_100g","g",1),("Sat. Fat","saturated-fat_100g","g",1),
                                            ("Carbs","carbohydrates_100g","g",1),("Sugars","sugars_100g","g",1),
                                            ("Fiber","fiber_100g","g",1),("Protein","proteins_100g","g",1),
                                            ("Salt","salt_100g","g",1),("Sodium","sodium_100g","mg",1000)]:
                    if key in nut and nut[key] is not None:
                        st.write(f"**{label}:** {nut[key]*mult:.1f} {unit}")
            else:
                st.info("Nutritional information not available")

        c1,c2,c3 = st.columns(3)
        with c1:
            ns = details.get("nutrition_grades","")
            if ns:
                cls = {"A":"success-box","B":"success-box","C":"warning-box","D":"warning-box","E":"danger-box"}.get(ns.upper(),"highlight-box")
                st.markdown(f"<div class='{cls}'><div class='metric-value'>{ns.upper()}</div><div class='metric-label'>Nutri-Score</div></div>", unsafe_allow_html=True)
        with c2:
            nova = details.get("nova_group","")
            if nova:
                cls = {1:"success-box",2:"success-box",3:"warning-box",4:"danger-box"}.get(nova,"highlight-box")
                st.markdown(f"<div class='{cls}'><div class='metric-value'>{nova}</div><div class='metric-label'>NOVA Group</div></div>", unsafe_allow_html=True)
        with c3:
            eco = details.get("ecoscore_grade","")
            if eco:
                cls = {"A":"success-box","B":"success-box","C":"warning-box","D":"warning-box","E":"danger-box"}.get(eco.upper(),"highlight-box")
                st.markdown(f"<div class='{cls}'><div class='metric-value'>{eco.upper()}</div><div class='metric-label'>Eco-Score</div></div>", unsafe_allow_html=True)

        if details.get("additives_tags"):
            st.subheader("Additives")
            st.markdown(f"<div class='highlight-box'>{', '.join(details['additives_tags'])}</div>", unsafe_allow_html=True)
            if len(details["additives_tags"]) > 5:
                st.warning(f"This product contains {len(details['additives_tags'])} additives — considered high.")

    # Tab 1 – Health Analysis
    with tabs[1]:
        st.header("Health Analysis")
        with st.spinner("Analyzing health factors…"):
            health_text, health_rating, nutrition_metrics = ai_analyzer.analyze_product_health(product_name, brand_name, category, details)

        hcls = "success-box" if health_rating >= 7 else ("warning-box" if health_rating >= 4 else "danger-box")
        st.markdown(f"<div class='{hcls}'><div class='metric-value'>{health_rating:.1f}/10</div><div class='metric-label'>Health Rating</div></div>", unsafe_allow_html=True)

        if nutrition_metrics:
            mcols = st.columns(4)
            for i,(label,key,unit) in enumerate([("Calories/Serving","calories_per_serving","kcal"),("Sugar","sugar_content_g","g"),("Sat. Fat","saturated_fat_g","g"),("Protein","protein_g","g")]):
                with mcols[i]:
                    v = nutrition_metrics.get(key)
                    if v is not None:
                        st.markdown(f"<div class='metric-card'><div class='metric-value'>{v:.1f} {unit}</div><div class='metric-label'>{label}</div></div>", unsafe_allow_html=True)

        st.markdown(health_text)

        if nutrition_metrics:
            valid = {k:v for k,v in nutrition_metrics.items() if v is not None}
            if len(valid) >= 3:
                refs = {"calories_per_serving":250,"sugar_content_g":25,"saturated_fat_g":20,"sodium_mg":2300,"protein_g":50,"fiber_g":25}
                avail = [m for m in refs if nutrition_metrics.get(m) is not None]
                if len(avail) >= 3:
                    pcts, labels = [], []
                    for m in avail:
                        v = nutrition_metrics[m]
                        r = refs[m]
                        pct = min(100,(v/r)*100) if m in ["protein_g","fiber_g"] else max(0,100-((v/r)*100))
                        pcts.append(pct)
                        labels.append(" ".join(w.capitalize() for w in m.replace("_"," ").split()))
                    fig = go.Figure(go.Scatterpolar(r=pcts, theta=labels, fill='toself', line_color='#059669'))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,100])), showlegend=False, title="Nutritional Quality (Higher = Better)")
                    st.plotly_chart(fig, use_container_width=True)

    # Tab 2 – Environmental
    with tabs[2]:
        st.header("Environmental Impact")
        with st.spinner("Analyzing environmental impact…"):
            env_text, env_rating = ai_analyzer.analyze_environmental_impact(product_name, brand_name, details)
        ecls = "success-box" if env_rating >= 7 else ("warning-box" if env_rating >= 4 else "danger-box")
        st.markdown(f"<div class='{ecls}'><div class='metric-value'>{env_rating:.1f}/10</div><div class='metric-label'>Environmental Score</div></div>", unsafe_allow_html=True)
        if details.get("packaging","Not specified") != "Not specified":
            st.info(f"📦 Packaging: {details['packaging']}")
        st.markdown(env_text)

    # Tab 3 – Allergens
    with tabs[3]:
        st.header("Allergens & Sensitivities")
        if allergens:
            st.markdown("<div class='danger-box'><b>⚠️ Contains:</b><br>" + "<br>".join(f"• {a.capitalize()}" for a in allergens) + "</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='success-box'>✅ No allergens declared. Always verify packaging.</div>", unsafe_allow_html=True)
        with st.spinner("Analyzing allergen risks…"):
            allergen_text = ai_analyzer.analyze_allergen_risks(product_name, brand_name, allergens, ingredients)
        st.markdown(allergen_text)
        if details.get("traces"):
            st.markdown(f"<div class='warning-box'>⚠️ May contain traces of: {details['traces']}</div>", unsafe_allow_html=True)

    # Tab 4 – Certifications
    with tabs[4]:
        st.header("Certifications & Standards")
        certs = [c.strip() for c in details.get("labels","").split(",") if c.strip()]
        if certs:
            st.subheader("Declared Certifications")
            for c in certs: st.write(f"• {c}")
        else:
            st.info("No certification info available.")
        st.subheader(f"Regulatory Compliance — {st.session_state.region}")
        comp = regulation_db.check_compliance(ingredients, st.session_state.region)
        if comp["compliant"]:
            st.markdown("<div class='success-box'>✅ Appears to comply with local regulations.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='danger-box'>❌ Possible issues:<br>" + "<br>".join(f"• {i}" for i in comp["issues"]) + "</div>", unsafe_allow_html=True)

    # Tab 5 – Healthier Alternatives
    with tabs[5]:
        st.header("Healthier Alternatives")
        with st.spinner("Generating healthier alternatives…"):
            recipes = ai_analyzer.generate_healthier_recipes(product_name, category, ingredients)
        st.markdown(recipes)
        st.info("🔜 Commercial healthier alternatives feature coming soon.")


# ─── Chat Section (standalone, outside display_product_information) ───────────
def render_chat_section(product_data):
    """
    Renders the chat UI. Must be called OUTSIDE display_product_information
    so session_state['chat_history'] persists across reruns.
    """
    st.divider()
    st.header("💬 Chat with Product Analyzer")

    product_name = product_data["product_name"]
    # Build clean, structured context instead of raw dict dump
    product_context = _format_product_context(product_data)

    # ── Handle pending suggestion FIRST (before rendering chat history) ──
    # This ensures the response is generated and added to history before display
    if st.session_state.get("pending_suggestion"):
        sug = st.session_state.pending_suggestion
        st.session_state.pending_suggestion = None  # Clear immediately to prevent loop

        with st.spinner(f"Answering: {sug}"):
            resp = get_gemini_response(sug, product_name, product_context)

        st.session_state.chat_history.append({"user": sug, "ai": resp})
        # No st.rerun() needed — we just appended to history and it will render below

    # ── Display existing messages ──
    chat_history = st.session_state.chat_history
    for chat in chat_history:
        with st.chat_message("user"):
            st.write(chat["user"])
        with st.chat_message("assistant"):
            st.write(chat["ai"])

    # ── Handle chat input ──
    user_q = st.chat_input("Ask anything about this product…")
    if user_q:
        # Immediately show the user message
        with st.chat_message("user"):
            st.write(user_q)

        # Get AI response with spinner
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                resp = get_gemini_response(user_q, product_name, product_context)
            st.write(resp)

        # Save to history — st.chat_input already triggers a rerun on next submit
        st.session_state.chat_history.append({"user": user_q, "ai": resp})

    # ── Suggested questions ──
    with st.expander("💡 Suggested questions"):
        suggestions = [
            "Are there any known side effects of this product?",
            "Is this product suitable for diabetics?",
            "What certifications does this product have?",
            "How sustainable is the packaging?",
            "Can you suggest healthier alternatives?",
            "Is this product safe for children?",
        ]
        for sug in suggestions:
            btn_key = f"sug_{hashlib.md5((sug + product_name).encode()).hexdigest()[:8]}"
            if st.button(sug, key=btn_key):
                st.session_state.pending_suggestion = sug
                st.rerun()


# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    load_css()
    regulation_db = RegulationDatabase()
    data_fetcher  = DataFetcher()
    ai_analyzer   = AIAnalyzer()

    # ── IMPORTANT FIX #4: Initialize ALL session state keys at the top, unconditionally ──
    # This ensures chat_history persists across reruns and is never reset
    defaults = {
        "product_data": None,
        "scan_history": [],
        "region": "United States",
        "pending_barcode": None,
        "chat_history": [],        # Must be here, not inside product block
        "pending_suggestion": None, # For suggestion button handling
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Sidebar ──
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2921/2921788.png", width=90)
        st.markdown("<h2 class='main-header'>Product Analyzer</h2>", unsafe_allow_html=True)
        countries      = sorted([c.name for c in pycountry.countries])
        default_region = "United States"
        st.session_state.region = st.selectbox(
            "Your region:", countries,
            index=countries.index(default_region) if default_region in countries else 0
        )
        st.divider()
        st.subheader("Scan History")
        if not st.session_state.scan_history:
            st.info("No products scanned yet.")
        else:
            for idx, item in enumerate(reversed(st.session_state.scan_history[-5:])):
                c1, c2 = st.columns([1, 3])
                with c1:
                    if item.get("image_url"): st.image(item["image_url"], width=45)
                    else: st.write("📦")
                with c2:
                    st.write(item["product_name"])
                    if st.button("View", key=f"hist_{idx}"):
                        st.session_state.product_data = item
                        # ── IMPORTANT FIX #5: Clear chat history when switching products ──
                        st.session_state.chat_history = []
                        st.rerun()
        if st.session_state.scan_history:
            if st.button("Clear History"):
                st.session_state.scan_history = []
                st.rerun()

    # ── Main Header ──
    st.markdown("<h1 class='main-header'>🔍 Product Health & Safety Analyzer</h1>", unsafe_allow_html=True)
    st.markdown("Scan barcodes or search products for detailed health, safety, and environmental insights.")

    # ── SCANNER SECTION ──
    st.markdown("### 📷 Barcode Scanner")
    st.markdown("Use the live scanner below — it auto-detects barcodes and fetches product info instantly.")
    components.html(SCANNER_HTML, height=700, scrolling=False)

    barcode_from_scan = st.query_params.get("barcode", None)

    # ── Manual / Text Search ──
    st.markdown("### 🔎 Manual Search")
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input("Enter barcode or product name:", key="manual_search",
                              placeholder="e.g. 737628064502 or Cheerios")
    with col2:
        search_btn = st.button("Search", use_container_width=True, type="primary")

    st.caption("Sample barcodes: `737628064502` (Kettle Chips) · `041196910759` (Cheerios) · `076840100744` (Nature Valley)")

    # ── Process barcode ──
    def process_barcode(bc, source="barcode"):
        with st.spinner(f"Fetching product for barcode {bc}…"):
            pname, bname, cat, orig, det, img, alg = data_fetcher.fetch_from_open_food_facts(bc)
            if not pname:
                with st.spinner("Not found in Open Food Facts — trying USDA…"):
                    pname, bname, cat, orig, det, img, alg = data_fetcher.fetch_from_usda(bc)
            if pname:
                # ── IMPORTANT FIX #6: Use product_obj (not pd_obj) to avoid shadowing pandas 'pd' ──
                product_obj = {
                    "product_name": pname, "brand_name": bname, "category": cat,
                    "origin": orig, "details": det, "image_url": img,
                    "allergens": alg, "barcode": bc
                }
                st.session_state.product_data = product_obj
                # Clear chat history when a new product is loaded
                st.session_state.chat_history = []
                if product_obj not in st.session_state.scan_history:
                    st.session_state.scan_history.append(product_obj)
            else:
                st.error(f"No product found for barcode: {bc}")

    if barcode_from_scan and st.session_state.get("pending_barcode") != barcode_from_scan:
        st.session_state.pending_barcode = barcode_from_scan
        process_barcode(barcode_from_scan)

    # ── Process manual search ──
    if search_btn and query:
        if query.isdigit():
            process_barcode(query)
        else:
            with st.spinner(f"Searching for '{query}'…"):
                products = data_fetcher.search_products_by_name(query)
            if products:
                st.success(f"Found {len(products)} results for '{query}'")
                for idx, prod in enumerate(products[:5]):
                    c1, c2, c3 = st.columns([1, 3, 1])
                    with c1:
                        if prod.get("image_url"): st.image(prod["image_url"], width=70)
                        else: st.write("📦")
                    with c2:
                        st.write(f"**{prod.get('product_name','Unknown')}**")
                        st.write(f"Brand: {prod.get('brands','N/A')} | Barcode: {prod.get('code','N/A')}")
                    with c3:
                        if st.button("Select", key=f"sel_{idx}"):
                            bc = prod.get("code","")
                            if bc: process_barcode(bc)
                            st.rerun()
            else:
                st.error(f"No products found for '{query}'")

    # ── Display product + chat ──
    if st.session_state.product_data:
        st.divider()
        display_product_information(
            st.session_state.product_data, regulation_db, ai_analyzer
        )
        # ── IMPORTANT FIX #7: Call chat OUTSIDE display_product_information ──
        render_chat_section(st.session_state.product_data)


if __name__ == "__main__":
    main()