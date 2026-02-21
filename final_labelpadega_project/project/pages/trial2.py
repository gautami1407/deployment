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

# ─── API Keys ─────────────────────────────────────────────────────────────────
# FIX: Load from st.secrets first (Streamlit Cloud), then .env, then env vars
def load_api_keys():
    gemini_key = None
    usda_key = None

    # 1) Try Streamlit secrets (works on Streamlit Cloud & local secrets.toml)
    try:
        gemini_key = st.secrets.get("GEMINI_API_KEY")
        usda_key = st.secrets.get("USDA_API_KEY")
    except Exception:
        pass

    # 2) Fall back to .env file search
    if not gemini_key:
        try:
            from dotenv import load_dotenv
            script_dir = os.path.dirname(os.path.abspath(__file__))
            dotenv_path = None
            curr_path = script_dir
            while curr_path != os.path.dirname(curr_path):
                potential = os.path.join(curr_path, ".env")
                if os.path.exists(potential):
                    dotenv_path = potential
                    break
                curr_path = os.path.dirname(curr_path)
            if dotenv_path:
                load_dotenv(dotenv_path)
            else:
                load_dotenv()
        except ImportError:
            pass  # python-dotenv not installed, skip

    # 3) Fall back to environment variables
    if not gemini_key:
        gemini_key = os.environ.get("GEMINI_API_KEY")
    if not usda_key:
        usda_key = os.environ.get("USDA_API_KEY")

    return gemini_key, usda_key


GEMINI_API_KEY, USDA_API_KEY = load_api_keys()

# Validate API Keys
if not GEMINI_API_KEY:
    st.error("❌ `GEMINI_API_KEY` not found!")
    st.markdown("""
    **How to fix:**
    - **Streamlit Cloud:** Add `GEMINI_API_KEY` in *App Settings → Secrets*
    - **Local:** Create a `.env` file with `GEMINI_API_KEY=your_key_here`  
      OR create `.streamlit/secrets.toml` with `GEMINI_API_KEY = "your_key_here"`
    """)
    st.stop()

if not USDA_API_KEY:
    st.warning("⚠️ `USDA_API_KEY` not found. USDA fallback search will be disabled.")

try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"❌ Failed to configure Gemini API: {e}")
    st.stop()

# ─── Cache Directory ───────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".product_checker_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Product Health & Safety Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS ───────────────────────────────────────────────────────────────────────
def load_css():
    st.markdown("""
    <style>
    .product-title { font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }
    .metric-card { background: #f8fafc; border-radius: 12px; padding: 1rem; text-align: center; border: 1px solid #e2e8f0; }
    .metric-value { font-size: 1.8rem; font-weight: 700; }
    .metric-label { font-size: 0.8rem; color: #64748b; margin-top: 0.2rem; }
    .success-box { background: #dcfce7; border-left: 4px solid #16a34a; padding: 0.75rem 1rem; border-radius: 6px; margin: 0.5rem 0; }
    .warning-box { background: #fef9c3; border-left: 4px solid #ca8a04; padding: 0.75rem 1rem; border-radius: 6px; margin: 0.5rem 0; }
    .danger-box  { background: #fee2e2; border-left: 4px solid #dc2626; padding: 0.75rem 1rem; border-radius: 6px; margin: 0.5rem 0; }
    .highlight-box { background: #eff6ff; border-left: 4px solid #2563eb; padding: 0.75rem 1rem; border-radius: 6px; margin: 0.5rem 0; }
    .ingredient-box { background: #f1f5f9; border-radius: 8px; padding: 1rem; font-size: 0.9rem; line-height: 1.6; }
    .additive-box { background: #fff7ed; border-radius: 8px; padding: 1rem; font-size: 0.9rem; }
    .sidebar-title { font-size: 1.4rem; font-weight: 700; text-align: center; margin-bottom: 0.5rem; }
    .main-title { font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 0.2rem; }
    </style>
    """, unsafe_allow_html=True)

# ─── Barcode Scanner HTML Component ───────────────────────────────────────────
SCANNER_HTML = """
<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/@zxing/library@latest/umd/index.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #f1f5f9; padding: 16px; }
  .scanner-card { background: #1e293b; border-radius: 16px; padding: 20px; max-width: 500px; margin: 0 auto; box-shadow: 0 4px 24px rgba(0,0,0,0.4); }
  .scanner-title { font-size: 1.1rem; font-weight: 700; text-align: center; margin-bottom: 4px; color: #38bdf8; }
  .scanner-subtitle { font-size: 0.75rem; text-align: center; color: #94a3b8; margin-bottom: 16px; }
  #video-container { position: relative; width: 100%; aspect-ratio: 4/3; background: #000; border-radius: 12px; overflow: hidden; }
  #video { width: 100%; height: 100%; object-fit: cover; }
  .scanner-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .scan-frame { width: 60%; height: 50%; border: 3px solid #38bdf8; border-radius: 8px; box-shadow: 0 0 0 9999px rgba(0,0,0,0.4); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { border-color: #38bdf8; } 50% { border-color: #818cf8; } }
  .no-cam { display: none; color: #94a3b8; font-size: 0.85rem; text-align: center; padding: 2rem; }
  .status-bar { margin: 12px 0; padding: 8px 12px; background: #0f172a; border-radius: 8px; font-size: 0.8rem; color: #94a3b8; text-align: center; min-height: 36px; }
  .status-bar.success { color: #4ade80; background: #052e16; }
  .status-bar.error { color: #f87171; background: #450a0a; }
  .btn-row { display: flex; gap: 8px; margin-top: 12px; }
  .btn { flex: 1; padding: 10px; border: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
  .btn-start { background: #0284c7; color: #fff; }
  .btn-start:hover { background: #0369a1; }
  .btn-stop  { background: #dc2626; color: #fff; display: none; }
  .btn-stop:hover  { background: #b91c1c; }
  .divider { text-align: center; color: #475569; font-size: 0.75rem; margin: 14px 0 10px; }
  .manual-row { display: flex; gap: 8px; }
  .manual-input { flex: 1; padding: 10px 12px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; color: #f1f5f9; font-size: 0.9rem; }
  .manual-input:focus { outline: none; border-color: #38bdf8; }
  .btn-search { background: #7c3aed; color: #fff; padding: 10px 16px; border: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
  .btn-search:hover { background: #6d28d9; }
  #result-box { display: none; margin-top: 14px; padding: 12px; background: #052e16; border: 1px solid #16a34a; border-radius: 10px; }
  #result-barcode { font-family: monospace; font-size: 1.1rem; font-weight: 700; color: #4ade80; }
  #result-label { font-size: 0.75rem; color: #86efac; margin-top: 4px; }
</style>
</head>
<body>
<div class="scanner-card">
  <div class="scanner-title">🔍 Barcode Scanner</div>
  <div class="scanner-subtitle">Point camera at barcode — it auto-detects instantly</div>
  <div id="video-container">
    <video id="video" muted playsinline></video>
    <div class="scanner-overlay"><div class="scan-frame"></div></div>
    <div class="no-cam" id="no-cam">📷<br>Camera not available. Use manual entry below.</div>
  </div>
  <div class="status-bar" id="status">Ready</div>
  <div class="btn-row">
    <button class="btn btn-start" id="btn-start" onclick="startScan()">▶ Start Scanning</button>
    <button class="btn btn-stop"  id="btn-stop"  onclick="stopScan()">⏹ Stop</button>
  </div>
  <div class="divider">— or enter barcode manually —</div>
  <div class="manual-row">
    <input class="manual-input" id="manual-input" type="text" placeholder="e.g. 737628064502" />
    <button class="btn-search" onclick="submitManual()">Search</button>
  </div>
  <div id="result-box">
    <div id="result-barcode"></div>
    <div id="result-label">✅ Barcode detected — sending to app…</div>
  </div>
</div>
<script>
let codeReader = null;
let scanning = false;

function setStatus(msg, cls) {
  const s = document.getElementById('status');
  s.textContent = msg;
  s.className = 'status-bar' + (cls ? ' ' + cls : '');
}

function showResult(barcode) {
  const box = document.getElementById('result-box');
  document.getElementById('result-barcode').textContent = barcode;
  box.style.display = 'block';
  setTimeout(() => { box.style.display = 'none'; }, 4000);
}

function sendBarcode(barcode) {
  showResult(barcode);
  const url = new URL(window.location.href);
  url.searchParams.set('barcode', barcode);
  window.parent.postMessage({ type: 'streamlit:setComponentValue', value: barcode }, '*');
  // Also update the parent page URL for st.query_params
  try {
    window.parent.history.replaceState(null, '', '?barcode=' + encodeURIComponent(barcode));
  } catch(e) {}
}

async function startScan() {
  if (scanning) return;
  try {
    codeReader = new ZXing.BrowserMultiFormatReader();
    const devices = await ZXing.BrowserCodeReader.listVideoInputDevices();
    if (!devices.length) throw new Error('No camera found');
    const deviceId = devices[devices.length - 1].deviceId;
    scanning = true;
    document.getElementById('btn-start').style.display = 'none';
    document.getElementById('btn-stop').style.display = 'flex';
    setStatus('📡 Scanning… point at a barcode');
    let lastBarcode = null;
    let lastTime = 0;
    await codeReader.decodeFromVideoDevice(deviceId, 'video', (result, err) => {
      if (result) {
        const bc = result.getText();
        const now = Date.now();
        if (bc !== lastBarcode || now - lastTime > 3000) {
          lastBarcode = bc;
          lastTime = now;
          setStatus('✅ Found: ' + bc, 'success');
          sendBarcode(bc);
        }
      }
    });
  } catch(e) {
    setStatus('❌ ' + e.message, 'error');
    document.getElementById('no-cam').style.display = 'block';
    scanning = false;
    document.getElementById('btn-start').style.display = 'flex';
    document.getElementById('btn-stop').style.display = 'none';
  }
}

function stopScan() {
  if (codeReader) { codeReader.reset(); codeReader = null; }
  scanning = false;
  document.getElementById('btn-start').style.display = 'flex';
  document.getElementById('btn-stop').style.display = 'none';
  setStatus('Stopped');
}

function submitManual() {
  const val = document.getElementById('manual-input').value.trim();
  if (val) { setStatus('Submitting: ' + val, 'success'); sendBarcode(val); }
}

document.getElementById('manual-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitManual();
});
</script>
</body>
</html>
"""

# ─── RegulationDatabase ────────────────────────────────────────────────────────
class RegulationDatabase:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        self.banned_products_file = os.path.join(cache_dir, "banned_products.json")
        self.recalls_file = os.path.join(cache_dir, "product_recalls.json")
        self.initialize_database()

    def initialize_database(self):
        if not os.path.exists(self.banned_products_file):
            data = {
                "ingredients": {
                    "Potassium Bromate": {"banned_in": ["European Union","United Kingdom","Canada","Brazil","China","India"], "reason": "Potential carcinogen", "alternatives": ["Ascorbic acid","Enzymes"]},
                    "Brominated Vegetable Oil (BVO)": {"banned_in": ["European Union","Japan","India"], "reason": "Thyroid problems", "alternatives": ["Natural emulsifiers"]},
                    "Azodicarbonamide": {"banned_in": ["European Union","Australia","United Kingdom","Singapore"], "reason": "Respiratory issues", "alternatives": ["Ascorbic acid"]},
                    "BHA/BHT": {"banned_in": ["Japan","European Union"], "reason": "Potential endocrine disruptors", "alternatives": ["Vitamin E","Rosemary extract"]},
                    "Tartrazine (Yellow #5)": {"banned_in": ["Norway","Austria"], "reason": "Hyperactivity in children", "alternatives": ["Natural food colors"]},
                    "Sodium Cyclamate": {"banned_in": ["United States"], "reason": "Cancer in animal studies", "alternatives": ["Stevia"]},
                    "Titanium Dioxide (E171)": {"banned_in": ["European Union"], "reason": "Potential genotoxicity", "alternatives": ["Natural whitening agents"]}
                },
                "products": {
                    "Unpasteurized dairy products": {"banned_in": ["Australia","Canada","Scotland"], "reason": "Harmful bacteria risk", "alternatives": "Pasteurized dairy"},
                    "Kinder Surprise Eggs (original)": {"banned_in": ["United States"], "reason": "Choking hazard", "alternatives": "Kinder Joy"}
                }
            }
            with open(self.banned_products_file, 'w') as f:
                json.dump(data, f, indent=2)

        if not os.path.exists(self.recalls_file):
            data = {"recent_recalls": [
                {"product_name": "XYZ Organic Peanut Butter", "date": "2024-02-15", "reason": "Potential Salmonella", "regions_affected": ["United States","Canada"], "batch_numbers": ["PB202401"]},
                {"product_name": "ABC Infant Formula", "date": "2024-01-22", "reason": "Possible Cronobacter", "regions_affected": ["United States"], "batch_numbers": ["IF24A123"]},
            ]}
            with open(self.recalls_file, 'w') as f:
                json.dump(data, f, indent=2)

    def load_banned_products(self):
        try:
            with open(self.banned_products_file) as f:
                return json.load(f)
        except:
            return {"ingredients": {}, "products": {}}

    def load_product_recalls(self):
        try:
            with open(self.recalls_file) as f:
                return json.load(f)
        except:
            return {"recent_recalls": []}

    def check_against_banned_ingredients(self, ingredients_text):
        if not ingredients_text or ingredients_text == "Not available":
            return []
        banned_data = self.load_banned_products()
        found = []
        txt = ingredients_text.lower()
        for ing, data in banned_data["ingredients"].items():
            if ing.lower() in txt:
                found.append({"ingredient": ing, **data})
        return found

    def check_product_recalls(self, product_name, brand_name):
        recalls = self.load_product_recalls()
        terms = [product_name.lower(), brand_name.lower()]
        return [r for r in recalls["recent_recalls"] if any(t in r["product_name"].lower() for t in terms)]

    def check_banned_products(self, product_name):
        data = self.load_banned_products()
        out = []
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


# ─── DataFetcher ───────────────────────────────────────────────────────────────
class DataFetcher:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'ProductHealthSafetyAnalyzer/2.0'})

    def _cache_path(self, key, src):
        h = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{src}_{h}.json")

    def _load_cache(self, key, src, max_age=86400):
        p = self._cache_path(key, src)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    c = json.load(f)
                if time.time() - c.get('cache_time', 0) <= max_age:
                    return c.get('data')
            except:
                pass
        return None

    def _save_cache(self, key, src, data):
        p = self._cache_path(key, src)
        try:
            with open(p, 'w') as f:
                json.dump({'data': data, 'cache_time': time.time()}, f)
        except:
            pass

    def _get(self, url, params=None):
        for i in range(3):
            try:
                r = self.session.get(url, params=params, timeout=12)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if i == 2:
                    raise e
                time.sleep(1 * (i + 1))

    def fetch_from_open_food_facts(self, barcode):
        cached = self._load_cache(barcode, 'off')
        if cached:
            return self._extract_off(cached)
        try:
            data = self._get(f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json")
            if data.get("status") == 1:
                self._save_cache(barcode, 'off', data)
                return self._extract_off(data)
            return (None,) * 7
        except Exception as e:
            st.error(f"Error fetching from Open Food Facts: {e}")
            return (None,) * 7

    def _extract_off(self, data):
        if data.get("status") != 1:
            return (None,) * 7
        p = data["product"]
        name = p.get("product_name", "Unknown Product")
        brand = p.get("brands", "Unknown Brand")
        category = (p.get("categories_tags", ["unknown"])[0]).replace("en:", "").capitalize() if p.get("categories_tags") else "Unknown"
        origin = p.get("countries", "Unknown")
        img = p.get("image_url")
        allergens = [a.replace("en:", "") for a in p.get("allergens_tags", [])]
        details = {
            "ingredients": p.get("ingredients_text", "Not available"),
            "ingredients_list": [i.get("text", "") for i in p.get("ingredients", [])],
            "nutriments": p.get("nutriments", {}),
            "nutrition_grades": p.get("nutrition_grades", ""),
            "nova_group": p.get("nova_group", ""),
            "ecoscore_grade": p.get("ecoscore_grade", ""),
            "packaging": p.get("packaging", "Not specified"),
            "manufacturing_places": p.get("manufacturing_places", "Not specified"),
            "additives_tags": [a.replace("en:", "") for a in p.get("additives_tags", [])],
            "labels": p.get("labels", ""),
            "allergens": allergens,
            "serving_size": p.get("serving_size", "Not specified"),
            "stores": p.get("stores", "Not specified"),
            "image_url": img,
            "traces": p.get("traces", "")
        }
        return name, brand, category, origin, details, img, allergens

    def fetch_from_usda(self, barcode):
        if not USDA_API_KEY:
            return (None,) * 7
        cached = self._load_cache(barcode, 'usda')
        if cached:
            return self._extract_usda(cached)
        try:
            search = self._get("https://api.nal.usda.gov/fdc/v1/foods/search",
                               {"api_key": USDA_API_KEY, "query": barcode, "pageSize": 1})
            if not search.get("foods"):
                return (None,) * 7
            fid = search["foods"][0]["fdcId"]
            detail = self._get(f"https://api.nal.usda.gov/fdc/v1/food/{fid}", {"api_key": USDA_API_KEY})
            combined = {"search_result": search, "detail": detail}
            self._save_cache(barcode, 'usda', combined)
            return self._extract_usda(combined)
        except Exception as e:
            st.error(f"Error fetching from USDA: {e}")
            return (None,) * 7

    def _extract_usda(self, combined):
        try:
            search = combined.get("search_result", {})
            detail = combined.get("detail", {})
            if not search.get("foods"):
                return (None,) * 7
            food = search["foods"][0]
            name = food.get("description", "Unknown")
            brand = food.get("brandOwner", "Unknown Brand")
            cat = food.get("foodCategory", "Unknown")
            orig = detail.get("marketCountry", "Unknown")
            ings = detail.get("ingredients", "Not available")
            allergens = []
            ndisp = {}
            for n in detail.get("foodNutrients", []):
                if "nutrientName" in n and "value" in n:
                    ndisp[n["nutrientName"]] = {"value": n["value"], "unit": n.get("unitName", "")}
            details = {
                "ingredients": ings,
                "foodNutrients": detail.get("foodNutrients", []),
                "nutrients_display": ndisp,
                "ingredients_list": [],
                "serving_size": detail.get("servingSize", "Not specified"),
                "serving_unit": detail.get("servingSizeUnit", ""),
                "additives_tags": [],
                "labels": "",
                "packaging": "Not specified",
                "ecoscore_grade": "",
                "nutrition_grades": "",
                "nova_group": "",
                "nutriments": {},
                "allergens": [],
                "traces": "",
                "image_url": None
            }
            return name, brand, cat, orig, details, None, allergens
        except Exception as e:
            st.error(f"Error processing USDA data: {e}")
            return (None,) * 7

    def search_products_by_name(self, name):
        cached = self._load_cache(f"search_{name}", 'off')
        if cached:
            return cached
        try:
            data = self._get("https://world.openfoodfacts.org/cgi/search.pl",
                             {"search_terms": name, "search_simple": 1, "action": "process", "json": 1, "page_size": 10})
            prods = data.get("products", []) if data else []
            self._save_cache(f"search_{name}", 'off', prods)
            return prods
        except:
            return []


# ─── AIAnalyzer ────────────────────────────────────────────────────────────────
class AIAnalyzer:
    def __init__(self):
        pass

    def _cache_path(self, atype, pname, bname):
        h = hashlib.md5(f"{pname}_{bname}".encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{atype}_{h}.json")

    def _load_cache(self, atype, pname, bname, max_age=604800):
        p = self._cache_path(atype, pname, bname)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    c = json.load(f)
                if time.time() - c.get('cache_time', 0) <= max_age:
                    return c.get('data')
            except:
                pass
        return None

    def _save_cache(self, atype, pname, bname, data):
        p = self._cache_path(atype, pname, bname)
        try:
            with open(p, 'w') as f:
                json.dump({'data': data, 'cache_time': time.time()}, f)
        except:
            pass

    def _model(self):
        return genai.GenerativeModel("gemini-2.0-flash")

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
            if 0 <= v <= 10:
                return v
        return 5.0

    def _extract_nutrition_metrics(self, text, details):
        metrics = {k: None for k in ["calories_per_serving","sugar_content_g","saturated_fat_g","sodium_mg","protein_g","fiber_g","additive_count"]}
        patterns = {
            "calories_per_serving": r"calories[^:]*:?\s*(\d+(?:\.\d+)?)",
            "sugar_content_g": r"sugar[^:]*:?\s*(\d+(?:\.\d+)?)",
            "saturated_fat_g": r"saturated[^:]*:?\s*(\d+(?:\.\d+)?)",
            "sodium_mg": r"sodium[^:]*:?\s*(\d+(?:\.\d+)?)",
            "protein_g": r"protein[^:]*:?\s*(\d+(?:\.\d+)?)",
            "fiber_g": r"fiber[^:]*:?\s*(\d+(?:\.\d+)?)",
            "additive_count": r"additive[^:]*:?\s*(\d+)"
        }
        for k, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    metrics[k] = float(m.group(1))
                except:
                    pass
        if details and "nutriments" in details:
            n = details["nutriments"]
            if metrics["calories_per_serving"] is None and "energy-kcal_serving" in n:
                metrics["calories_per_serving"] = n["energy-kcal_serving"]
            if metrics["sugar_content_g"] is None and "sugars_100g" in n:
                metrics["sugar_content_g"] = n["sugars_100g"]
            if metrics["saturated_fat_g"] is None and "saturated-fat_100g" in n:
                metrics["saturated_fat_g"] = n["saturated-fat_100g"]
            if metrics["sodium_mg"] is None and "sodium_100g" in n:
                metrics["sodium_mg"] = n["sodium_100g"] * 1000
            if metrics["protein_g"] is None and "proteins_100g" in n:
                metrics["protein_g"] = n["proteins_100g"]
            if metrics["fiber_g"] is None and "fiber_100g" in n:
                metrics["fiber_g"] = n["fiber_100g"]
            if metrics["additive_count"] is None and "additives_tags" in details:
                metrics["additive_count"] = len(details["additives_tags"])
        return metrics

    def _ctx(self, details):
        ctx = ""
        if not details:
            return ctx
        if details.get("ingredients") and details["ingredients"] != "Not available":
            ctx += f"Ingredients: {details['ingredients']}\n\n"
        if details.get("nutriments"):
            ctx += "Nutritional Info:\n"
            for k, v in details["nutriments"].items():
                if isinstance(v, (int, float)) and ("_100g" in k or "_serving" in k):
                    ctx += f"  {k}: {v}\n"
        if details.get("nutrition_grades"):
            ctx += f"\nNutri-Score: {details['nutrition_grades'].upper()}\n"
        if details.get("nova_group"):
            ctx += f"NOVA Group: {details['nova_group']}\n"
        if details.get("additives_tags"):
            ctx += f"Additives: {', '.join(details['additives_tags'])}\n"
        return ctx

    def analyze_product_health(self, pname, bname, cat, details):
        cached = self._load_cache("health", pname, bname)
        if cached:
            return cached.get("analysis", ""), cached.get("rating", 0), cached.get("metrics", {})
        ctx = self._ctx(details)
        prompt = f"Analyze health of '{pname}' by '{bname}' in '{cat}'.\n\n{ctx}\n\n1. Top 5 health factors\n2. Rate 1-10 with explanation\n3. Health concerns for specific groups\n4. Healthier alternatives\n5. Numeric estimates: calories_per_serving, sugar_content_g, saturated_fat_g, sodium_mg, protein_g, fiber_g, additive_count\n\nUse clear headings."
        text = self._gen(prompt)
        rating = self._extract_rating(text)
        metrics = self._extract_nutrition_metrics(text, details)
        self._save_cache("health", pname, bname, {"analysis": text, "rating": rating, "metrics": metrics})
        return text, rating, metrics

    def analyze_environmental_impact(self, pname, bname, details):
        cached = self._load_cache("env", pname, bname)
        if cached:
            return cached.get("analysis", ""), cached.get("rating", 0)
        prompt = f"Analyze environmental impact of '{pname}' by '{bname}'.\nPackaging: {details.get('packaging','?')}\nEcoscore: {details.get('ecoscore_grade','?')}\nManufacturing: {details.get('manufacturing_places','?')}\n\n1. Rate 1-10 environmental friendliness\n2. Packaging sustainability\n3. Carbon footprint\n4. Sustainable alternatives"
        text = self._gen(prompt)
        rating = self._extract_rating(text)
        self._save_cache("env", pname, bname, {"analysis": text, "rating": rating})
        return text, rating

    def analyze_allergen_risks(self, pname, bname, allergens, ingredients):
        cached = self._load_cache("allergen", pname, bname)
        if cached:
            return cached
        alist = ", ".join(allergens) if allergens else "None listed"
        prompt = f"Analyze allergen risks for '{pname}' by '{bname}'.\nListed allergens: {alist}\nIngredients: {ingredients}\n\n1. Explicit allergens\n2. Hidden allergens from ingredients\n3. Cross-contamination risks\n4. Recommendations"
        text = self._gen(prompt)
        self._save_cache("allergen", pname, bname, text)
        return text

    def generate_healthier_recipes(self, pname, cat, ingredients):
        cached = self._load_cache("recipes", pname, cat)
        if cached:
            return cached
        prompt = f"Give 3 healthier homemade alternatives to '{pname}' (category: {cat}).\nOriginal ingredients: {ingredients}\n\nFor each: name, wholesome ingredients, instructions, health benefits vs original."
        text = self._gen(prompt)
        self._save_cache("recipes", pname, cat, text)
        return text

    def check_certification(self, bname, pname, cert_type, details=None):
        cached = self._load_cache(f"cert_{cert_type}", pname, bname)
        if cached:
            return cached
        ctx = ""
        if details:
            if details.get("ingredients", "") != "Not available":
                ctx += f"Ingredients: {details['ingredients']}\n"
            if details.get("labels"):
                ctx += f"Labels: {details['labels']}\n"
        prompt = f"Assess '{pname}' by '{bname}' for {cert_type} compliance.\n{ctx}\n1. Likely meets requirements?\n2. Common compliance issues\n3. What consumers should know\n4. Recommendations"
        text = self._gen(prompt)
        self._save_cache(f"cert_{cert_type}", pname, bname, text)
        return text


# ─── Chat Helpers ──────────────────────────────────────────────────────────────
def _format_product_context(product_data):
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
    context = "\n".join(parts)
    if len(context) > 3000:
        context = context[:3000] + "\n[...truncated]"
    return context


def get_gemini_response(question, product_name, product_context):
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
        elif "api_key" in error_msg.lower() or "invalid" in error_msg.lower() or "401" in error_msg:
            return "⚠️ Invalid API key. Please check your GEMINI_API_KEY in secrets/environment."
        return f"⚠️ Error getting response: {error_msg}"


# ─── Display full product info ─────────────────────────────────────────────────
def display_product_information(product_data, regulation_db, ai_analyzer):
    product_name = product_data["product_name"]
    brand_name = product_data["brand_name"]
    category = product_data["category"]
    origin = product_data["origin"]
    details = product_data["details"]
    image_url = product_data["image_url"]
    allergens = product_data["allergens"]
    barcode = product_data.get("barcode", "Unknown")
    ingredients = details.get("ingredients", "Not available")

    # Header
    col1, col2 = st.columns([1, 3])
    with col1:
        if image_url:
            st.image(image_url, width=200)
        else:
            st.image("https://cdn-icons-png.flaticon.com/512/1046/1046857.png", width=200)
    with col2:
        st.markdown(f"<div class='product-title'>{product_name}</div>", unsafe_allow_html=True)
        st.markdown(f"**Brand:** {brand_name} | **Category:** {category} | **Origin:** {origin} | **Barcode:** {barcode}")

    # Safety Summary
    st.header("Safety & Certification Summary")
    banned_ings = regulation_db.check_against_banned_ingredients(ingredients)
    recalls = regulation_db.check_product_recalls(product_name, brand_name)
    fssai_cert = "Yes" if "FSSAI" in details.get("labels", "") else "No"
    eco_score = details.get("ecoscore_grade", "N/A")
    nutri_score = details.get("nutrition_grades", "N/A")
    additives_cnt = len(details.get("additives_tags", []))
    serving_size = details.get("serving_size", "Not specified")
    banned_text = ", ".join(i["ingredient"] for i in banned_ings) if banned_ings else "None"

    rows = {
        "Is it safe for children?": ("Yes (check full analysis)", "✅"),
        "FSSAI Certified": (fssai_cert, "✅" if fssai_cert == "Yes" else "❌"),
        "Other Certifications": (details.get("labels", "None") or "None", "📜"),
        "Contains Allergens": (", ".join(allergens) if allergens else "No allergens declared", "⚠️" if allergens else "✅"),
        "Banned Ingredients Found": (banned_text, "🚫" if banned_ings else "✅"),
        "Recent Recalls": ("Yes" if recalls else "No", "🚨" if recalls else "✅"),
        "Eco-Score": (eco_score.upper() if eco_score and eco_score != "N/A" else "N/A", "🌱"),
        "Nutri-Score": (nutri_score.upper() if nutri_score and nutri_score != "N/A" else "N/A", "🍏"),
        "Additives Count": (str(additives_cnt), "⚗️"),
        "Serving Size": (serving_size, "🍽️")
    }
    cols = st.columns(2)
    for i, (k, (v, icon)) in enumerate(rows.items()):
        with cols[i % 2]:
            st.write(f"{icon} **{k}:** {v}")

    banned_prods = regulation_db.check_banned_products(product_name)
    if banned_prods:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.write("❌ This product is banned/seized in some countries:")
        for bp in banned_prods:
            st.write(f"- **{bp['product']}** — Banned in: {', '.join(bp['banned_in'])} — Reason: {bp['reason']}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='success-box'>✅ This product is not banned in any known database entry.</div>", unsafe_allow_html=True)

    compliance = regulation_db.check_food_packaging_compliance(ingredients, st.session_state.region)
    if compliance["compliant"]:
        st.markdown(f"<div class='success-box'>✅ Appears compliant with food regulations in {st.session_state.region}.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='danger-box'>❌ Possible compliance issues: " + " ".join(f"• {i}" for i in compliance["issues"]) + "</div>", unsafe_allow_html=True)

    if banned_ings:
        st.markdown("<div class='warning-box'>", unsafe_allow_html=True)
        st.markdown("## ⚠️ Regulatory Alerts")
        for item in banned_ings:
            st.markdown(f"**{item['ingredient']}** — Banned in: {', '.join(item['banned_in'])} — Reason: {item['reason']} — Alt: {', '.join(item['alternatives'])}")
        st.markdown("</div>", unsafe_allow_html=True)

    if recalls:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.markdown("## 🚨 Recall Alerts")
        for r in recalls:
            st.markdown(f"**Date:** {r['date']} | **Reason:** {r['reason']} | **Regions:** {', '.join(r['regions_affected'])} | **Batches:** {', '.join(r['batch_numbers'])}")
        st.markdown("</div>", unsafe_allow_html=True)

    # TABS
    tabs = st.tabs(["📋 Product Details", "❤️ Health Analysis", "🌿 Environmental", "🚫 Allergens", "🔬 Certifications", "🥗 Healthier Alternatives"])

    with tabs[0]:
        st.header("Product Details")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Ingredients")
            if ingredients != "Not available":
                st.markdown(f"<div class='ingredient-box'>{ingredients}</div>", unsafe_allow_html=True)
            else:
                st.info("Ingredients not available")
        with c2:
            st.subheader("Nutritional Information (per 100g)")
            nut = details.get("nutriments", {})
            if nut:
                if "energy-kcal_100g" in nut:
                    st.metric("Calories", f"{nut['energy-kcal_100g']:.1f} kcal")
                for label, key, unit, mult in [
                    ("Fat", "fat_100g", "g", 1), ("Sat. Fat", "saturated-fat_100g", "g", 1),
                    ("Carbs", "carbohydrates_100g", "g", 1), ("Sugars", "sugars_100g", "g", 1),
                    ("Fiber", "fiber_100g", "g", 1), ("Protein", "proteins_100g", "g", 1),
                    ("Salt", "salt_100g", "g", 1), ("Sodium", "sodium_100g", "mg", 1000)
                ]:
                    if key in nut and nut[key] is not None:
                        st.write(f"**{label}:** {nut[key] * mult:.1f} {unit}")
            else:
                st.info("Nutritional information not available")

        c1, c2, c3 = st.columns(3)
        with c1:
            ns = details.get("nutrition_grades", "")
            if ns:
                cls = {"A": "success-box", "B": "success-box", "C": "warning-box", "D": "warning-box", "E": "danger-box"}.get(ns.upper(), "highlight-box")
                st.markdown(f"<div class='{cls}'><div style='font-size:2rem;font-weight:700'>{ns.upper()}</div>Nutri-Score</div>", unsafe_allow_html=True)
        with c2:
            nova = details.get("nova_group", "")
            if nova:
                cls = {1: "success-box", 2: "success-box", 3: "warning-box", 4: "danger-box"}.get(nova, "highlight-box")
                st.markdown(f"<div class='{cls}'><div style='font-size:2rem;font-weight:700'>{nova}</div>NOVA Group</div>", unsafe_allow_html=True)
        with c3:
            eco = details.get("ecoscore_grade", "")
            if eco:
                cls = {"A": "success-box", "B": "success-box", "C": "warning-box", "D": "warning-box", "E": "danger-box"}.get(eco.upper(), "highlight-box")
                st.markdown(f"<div class='{cls}'><div style='font-size:2rem;font-weight:700'>{eco.upper()}</div>Eco-Score</div>", unsafe_allow_html=True)

        if details.get("additives_tags"):
            st.subheader("Additives")
            st.markdown(f"<div class='additive-box'>{', '.join(details['additives_tags'])}</div>", unsafe_allow_html=True)
            if len(details["additives_tags"]) > 5:
                st.warning(f"This product contains {len(details['additives_tags'])} additives — considered high.")

    with tabs[1]:
        st.header("Health Analysis")
        with st.spinner("Analyzing health factors…"):
            health_text, health_rating, nutrition_metrics = ai_analyzer.analyze_product_health(product_name, brand_name, category, details)
        hcls = "success-box" if health_rating >= 7 else ("warning-box" if health_rating >= 4 else "danger-box")
        st.markdown(f"<div class='{hcls}'><div class='metric-value'>{health_rating:.1f}/10</div><div class='metric-label'>Health Rating</div></div>", unsafe_allow_html=True)
        if nutrition_metrics:
            mcols = st.columns(4)
            for i, (label, key, unit) in enumerate([("Calories/Serving", "calories_per_serving", "kcal"), ("Sugar", "sugar_content_g", "g"), ("Sat. Fat", "saturated_fat_g", "g"), ("Protein", "protein_g", "g")]):
                with mcols[i]:
                    v = nutrition_metrics.get(key)
                    if v is not None:
                        st.markdown(f"<div class='metric-card'><div class='metric-value'>{v:.1f} {unit}</div><div class='metric-label'>{label}</div></div>", unsafe_allow_html=True)
        st.markdown(health_text)
        if nutrition_metrics:
            valid = {k: v for k, v in nutrition_metrics.items() if v is not None}
            if len(valid) >= 3:
                refs = {"calories_per_serving": 250, "sugar_content_g": 25, "saturated_fat_g": 20, "sodium_mg": 2300, "protein_g": 50, "fiber_g": 25}
                avail = [m for m in refs if nutrition_metrics.get(m) is not None]
                if len(avail) >= 3:
                    pcts, labels = [], []
                    for m in avail:
                        v = nutrition_metrics[m]
                        r = refs[m]
                        pct = min(100, (v / r) * 100) if m in ["protein_g", "fiber_g"] else max(0, 100 - ((v / r) * 100))
                        pcts.append(pct)
                        labels.append(" ".join(w.capitalize() for w in m.replace("_", " ").split()))
                    fig = go.Figure(go.Scatterpolar(r=pcts, theta=labels, fill='toself', line_color='#059669'))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, title="Nutritional Quality (Higher = Better)")
                    st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        st.header("Environmental Impact")
        with st.spinner("Analyzing environmental impact…"):
            env_text, env_rating = ai_analyzer.analyze_environmental_impact(product_name, brand_name, details)
        ecls = "success-box" if env_rating >= 7 else ("warning-box" if env_rating >= 4 else "danger-box")
        st.markdown(f"<div class='{ecls}'><div class='metric-value'>{env_rating:.1f}/10</div><div class='metric-label'>Environmental Score</div></div>", unsafe_allow_html=True)
        if details.get("packaging", "Not specified") != "Not specified":
            st.info(f"📦 Packaging: {details['packaging']}")
        st.markdown(env_text)

    with tabs[3]:
        st.header("Allergens & Sensitivities")
        if allergens:
            st.markdown("<div class='warning-box'>⚠️ Contains: " + " ".join(f"• {a.capitalize()}" for a in allergens) + "</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='success-box'>✅ No allergens declared. Always verify packaging.</div>", unsafe_allow_html=True)
        with st.spinner("Analyzing allergen risks…"):
            allergen_text = ai_analyzer.analyze_allergen_risks(product_name, brand_name, allergens, ingredients)
        st.markdown(allergen_text)
        if details.get("traces"):
            st.markdown(f"<div class='warning-box'>⚠️ May contain traces of: {details['traces']}</div>", unsafe_allow_html=True)

    with tabs[4]:
        st.header("Certifications & Standards")
        certs = [c.strip() for c in details.get("labels", "").split(",") if c.strip()]
        if certs:
            st.subheader("Declared Certifications")
            for c in certs:
                st.write(f"• {c}")
        else:
            st.info("No certification info available.")
        st.subheader(f"Regulatory Compliance — {st.session_state.region}")
        comp = regulation_db.check_compliance(ingredients, st.session_state.region)
        if comp["compliant"]:
            st.markdown("<div class='success-box'>✅ Appears to comply with local regulations.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='danger-box'>❌ Possible issues: " + " ".join(f"• {i}" for i in comp["issues"]) + "</div>", unsafe_allow_html=True)

    with tabs[5]:
        st.header("Healthier Alternatives")
        with st.spinner("Generating healthier alternatives…"):
            recipes = ai_analyzer.generate_healthier_recipes(product_name, category, ingredients)
        st.markdown(recipes)
        st.info("🔜 Commercial healthier alternatives feature coming soon.")


# ─── Chat Section ─────────────────────────────────────────────────────────────
def render_chat_section(product_data):
    st.divider()
    st.header("💬 Chat with Product Analyzer")
    product_name = product_data["product_name"]
    product_context = _format_product_context(product_data)

    if st.session_state.get("pending_suggestion"):
        sug = st.session_state.pending_suggestion
        st.session_state.pending_suggestion = None
        with st.spinner(f"Answering: {sug}"):
            resp = get_gemini_response(sug, product_name, product_context)
        st.session_state.chat_history.append({"user": sug, "ai": resp})

    for chat in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(chat["user"])
        with st.chat_message("assistant"):
            st.write(chat["ai"])

    user_q = st.chat_input("Ask anything about this product…")
    if user_q:
        with st.chat_message("user"):
            st.write(user_q)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                resp = get_gemini_response(user_q, product_name, product_context)
            st.write(resp)
        st.session_state.chat_history.append({"user": user_q, "ai": resp})

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


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    load_css()
    regulation_db = RegulationDatabase()
    data_fetcher = DataFetcher()
    ai_analyzer = AIAnalyzer()

    defaults = {
        "product_data": None,
        "scan_history": [],
        "region": "United States",
        "pending_barcode": None,
        "chat_history": [],
        "pending_suggestion": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Sidebar
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2921/2921788.png", width=90)
        st.markdown("<div class='sidebar-title'>Product Analyzer</div>", unsafe_allow_html=True)
        countries = sorted([c.name for c in pycountry.countries])
        default_region = "United States"
        st.session_state.region = st.selectbox(
            "Your region:",
            countries,
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
                    if item.get("image_url"):
                        st.image(item["image_url"], width=45)
                    else:
                        st.write("📦")
                with c2:
                    st.write(item["product_name"])
                if st.button("View", key=f"hist_{idx}"):
                    st.session_state.product_data = item
                    st.session_state.chat_history = []
                    st.rerun()
        if st.session_state.scan_history:
            if st.button("Clear History"):
                st.session_state.scan_history = []
                st.rerun()

    # Main Header
    st.markdown("<div class='main-title'>🔍 Product Health & Safety Analyzer</div>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#64748b;'>Scan barcodes or search products for detailed health, safety, and environmental insights.</p>", unsafe_allow_html=True)

    # ── Process barcode helper ──
    def process_barcode(bc, source="barcode"):
        with st.spinner(f"Fetching product for barcode {bc}…"):
            pname, bname, cat, orig, det, img, alg = data_fetcher.fetch_from_open_food_facts(bc)
            if not pname:
                with st.spinner("Not found in Open Food Facts — trying USDA…"):
                    pname, bname, cat, orig, det, img, alg = data_fetcher.fetch_from_usda(bc)
        if pname:
            product_obj = {
                "product_name": pname,
                "brand_name": bname,
                "category": cat,
                "origin": orig,
                "details": det,
                "image_url": img,
                "allergens": alg,
                "barcode": bc
            }
            st.session_state.product_data = product_obj
            st.session_state.chat_history = []
            if product_obj not in st.session_state.scan_history:
                st.session_state.scan_history.append(product_obj)
        else:
            st.error(f"No product found for barcode: {bc}")

    # ── TWO TABS: Barcode Scanner vs Manual Search ──
    search_tab1, search_tab2 = st.tabs(["📷 Barcode Scanner", "🔎 Manual Search"])

    with search_tab1:
        st.markdown("### Live Barcode Scanner")
        st.markdown("Use your camera to scan a barcode — it auto-detects and fetches product info instantly.")
        components.html(SCANNER_HTML, height=620, scrolling=False)

        barcode_from_scan = st.query_params.get("barcode", None)
        if barcode_from_scan and st.session_state.get("pending_barcode") != barcode_from_scan:
            st.session_state.pending_barcode = barcode_from_scan
            process_barcode(barcode_from_scan)

    with search_tab2:
        st.markdown("### Manual Barcode or Product Name Search")
        st.caption("Sample barcodes: `737628064502` (Kettle Chips) · `041196910759` (Cheerios) · `076840100744` (Nature Valley)")

        col1, col2 = st.columns([4, 1])
        with col1:
            query = st.text_input("Enter barcode or product name:", key="manual_search", placeholder="e.g. 737628064502 or Cheerios")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            search_btn = st.button("Search", use_container_width=True, type="primary")

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
                            if prod.get("image_url"):
                                st.image(prod["image_url"], width=70)
                            else:
                                st.write("📦")
                        with c2:
                            st.write(f"**{prod.get('product_name', 'Unknown')}**")
                            st.write(f"Brand: {prod.get('brands', 'N/A')} | Barcode: {prod.get('code', 'N/A')}")
                        with c3:
                            if st.button("Select", key=f"sel_{idx}"):
                                bc = prod.get("code", "")
                                if bc:
                                    process_barcode(bc)
                                    st.rerun()
                else:
                    st.error(f"No products found for '{query}'")

    # Display product + chat
    if st.session_state.product_data:
        st.divider()
        display_product_information(st.session_state.product_data, regulation_db, ai_analyzer)
        render_chat_section(st.session_state.product_data)


if __name__ == "__main__":
    main()