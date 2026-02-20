import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime
import json
import os
import time
import re
import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import base64
import cv2
import numpy as np
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration, VideoProcessorBase
import av
import threading

# ============================================================================
# CONFIGURATION
# ============================================================================

GEMINI_API_KEY = "AIzaSyAeSOUPOB3JyVCqro_rXD5C5sgVo0ohC7Q"
USDA_API_KEY = "NwTn1c91fQ0I0fKE9rBw0vP48cnesEUWE19hImjX"
genai.configure(api_key=GEMINI_API_KEY)

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".product_analyzer_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


# Additives CSV path - try multiple locations
ADDITIVES_CSV_PATHS = [
    r"C:\Users\DELL\Downloads\master_global_additives_regulatory_complete (1).csv",
    os.path.join(os.path.dirname(__file__), "additives_database.csv"),
    os.path.join(os.path.expanduser("~"), "additives_database.csv"),
    "additives_database.csv"
]

def get_additives_csv_path():
    """Find the additives CSV file in available locations"""
    for path in ADDITIVES_CSV_PATHS:
        if os.path.exists(path):
            return path
    # Return first path as default (will create if needed)
    return ADDITIVES_CSV_PATHS[-1]

ADDITIVES_CSV_PATH = get_additives_csv_path()

st.set_page_config(
    page_title="AI Food Product Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

RTC_CONFIGURATION = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})



def load_css():
    st.markdown("""
    <style>
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .product-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    .metric-box {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        text-align: center;
        border-left: 5px solid #667eea;
        transition: transform 0.2s;
    }
    .metric-box:hover {
        transform: translateY(-5px);
    }
    .alert-danger {
        background: #fee;
        border-left: 5px solid #e53e3e;
        padding: 1.2rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .alert-success {
        background: #e8f5e9;
        border-left: 5px solid #38a169;
        padding: 1.2rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .alert-warning {
        background: #fff8e1;
        border-left: 5px solid #f59e0b;
        padding: 1.2rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .scanner-box {
        background: #f7fafc;
        padding: 2rem;
        border-radius: 15px;
        border: 3px dashed #667eea;
        text-align: center;
        margin: 1rem 0;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .user-message {
        background: #e3f2fd;
        margin-left: 2rem;
    }
    .ai-message {
        background: #f3e5f5;
        margin-right: 2rem;
    }
    .ingredient-chip {
        display: inline-block;
        padding: 0.5rem 1rem;
        margin: 0.25rem;
        border-radius: 20px;
        background: #e8f5e9;
        color: #2e7d32;
        font-size: 0.9rem;
    }
    .additive-danger {
        background: #ffebee !important;
        color: #c62828 !important;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# BARCODE SCANNER CLASS
# ============================================================================

class BarcodeScanner(VideoProcessorBase):
    def __init__(self):
        # Try different OpenCV barcode detector methods for compatibility
        try:
            # OpenCV 4.5.1+ uses barcode.BarcodeDetector
            self.detector = cv2.barcode.BarcodeDetector()
        except AttributeError:
            try:
                # Older versions might use barcode_BarcodeDetector
                self.detector = cv2.barcode_BarcodeDetector()
            except AttributeError:
                # Fallback: use pyzbar or other library
                try:
                    from pyzbar import pyzbar
                    self.detector = None
                    self.use_pyzbar = True
                except ImportError:
                    st.warning("Barcode detection libraries not available. Install opencv-contrib-python or pyzbar.")
                    self.detector = None
                    self.use_pyzbar = False
        self.lock = threading.Lock()
        self.detected_barcode = None
        self.use_pyzbar = False
    
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        
        try:
            if self.detector is not None:
                retval, decoded_info, decoded_type, points = self.detector.detectAndDecode(img)
                
                if retval and decoded_info:
                    with self.lock:
                        self.detected_barcode = decoded_info[0]
                    
                    if points is not None and len(points) > 0:
                        points = points.astype(int)
                        for i in range(len(points[0])):
                            pt1 = tuple(points[0][i])
                            pt2 = tuple(points[0][(i + 1) % len(points[0])])
                            cv2.line(img, pt1, pt2, (0, 255, 0), 3)
                        
                        cv2.putText(img, decoded_info[0], (50, 50), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            elif self.use_pyzbar:
                # Fallback to pyzbar if available
                try:
                    from pyzbar import pyzbar
                    import cv2
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    barcodes = pyzbar.decode(gray)
                    if barcodes:
                        barcode_data = barcodes[0].data.decode('utf-8')
                        with self.lock:
                            self.detected_barcode = barcode_data
                        cv2.putText(img, barcode_data, (50, 50), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                except:
                    pass
        except Exception as e:
            # Silently handle errors to avoid breaking the video stream
            pass
        
        return av.VideoFrame.from_ndarray(img, format="bgr24")



class OpenFoodFactsFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'AIFoodAnalyzer/1.0'})
        self.base_url = "https://world.openfoodfacts.org/api/v0"
    
    def _get_cache_key(self, barcode):
        return hashlib.md5(f"off_{barcode}".encode()).hexdigest()
    
    def _load_cache(self, barcode):
        cache_file = os.path.join(CACHE_DIR, f"{self._get_cache_key(barcode)}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                if time.time() - data.get('timestamp', 0) < 86400:
                    return data.get('product')
            except:
                pass
        return None
    
    def _save_cache(self, barcode, product):
        cache_file = os.path.join(CACHE_DIR, f"{self._get_cache_key(barcode)}.json")
        try:
            with open(cache_file, 'w') as f:
                json.dump({'product': product, 'timestamp': time.time()}, f)
        except:
            pass
    
    @st.cache_data(ttl=86400)
    def fetch_product(_self, barcode):
        cached = _self._load_cache(barcode)
        if cached:
            return cached
        
        try:
            url = f"{_self.base_url}/product/{barcode}.json"
            response = _self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == 1:
                product_data = data["product"]
                
                result = {
                    "barcode": barcode,
                    "name": product_data.get("product_name", "Unknown Product"),
                    "brand": product_data.get("brands", "Unknown Brand"),
                    "category": product_data.get("categories", "Unknown"),
                    "image": product_data.get("image_url"),
                    "ingredients": product_data.get("ingredients_text", "Not available"),
                    "ingredients_list": [i.get("text", "") for i in product_data.get("ingredients", [])],
                    "nutrients": product_data.get("nutriments", {}),
                    "nutri_score": product_data.get("nutrition_grades", "").upper(),
                    "nova_group": product_data.get("nova_group"),
                    "ecoscore": product_data.get("ecoscore_grade", "").upper(),
                    "allergens": [a.replace("en:", "").replace("-", " ").title() 
                                 for a in product_data.get("allergens_tags", [])],
                    "additives": [a.replace("en:", "").upper() 
                                 for a in product_data.get("additives_tags", [])],
                    "labels": product_data.get("labels", ""),
                    "packaging": product_data.get("packaging", ""),
                    "origin": product_data.get("countries", "Unknown")
                }
                
                _self._save_cache(barcode, result)
                return result
        except Exception as e:
            st.error(f"OpenFoodFacts Error: {str(e)}")
        
        return None
    
    @st.cache_data(ttl=86400)
    def search_by_name(_self, name):
        try:
            url = f"{_self.base_url}/../cgi/search.pl"
            params = {"search_terms": name, "json": 1, "page_size": 10}
            response = _self.session.get(url, params=params, timeout=10)
            data = response.json()
            return data.get("products", [])[:5]
        except:
            return []



class USDAFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://api.nal.usda.gov/fdc/v1"
    
    @st.cache_data(ttl=86400)
    def fetch_nutrition(_self, product_name):
        try:
            url = f"{_self.base_url}/foods/search"
            params = {
                "api_key": USDA_API_KEY,
                "query": product_name,
                "pageSize": 1
            }
            response = _self.session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("foods"):
                food = data["foods"][0]
                nutrients = {}
                
                for nutrient in food.get("foodNutrients", []):
                    name = nutrient.get("nutrientName", "")
                    value = nutrient.get("value", 0)
                    unit = nutrient.get("unitName", "")
                    
                    if "Energy" in name and "KCAL" in unit.upper():
                        nutrients["energy-kcal_100g"] = value
                    elif "Protein" in name:
                        nutrients["proteins_100g"] = value
                    elif "Carbohydrate" in name:
                        nutrients["carbohydrates_100g"] = value
                    elif "Total lipid" in name or "Fat" in name:
                        nutrients["fat_100g"] = value
                    elif "Sugars" in name:
                        nutrients["sugars_100g"] = value
                    elif "Fiber" in name:
                        nutrients["fiber_100g"] = value
                    elif "Sodium" in name:
                        nutrients["salt_100g"] = value / 1000 * 2.5
                
                return nutrients
        except Exception as e:
            st.warning(f"USDA API unavailable: {str(e)}")
        
        return {}

# ============================================================================
# ADDITIVE ANALYZER
# ============================================================================

class AdditiveAnalyzer:
    def __init__(self):
        self.additives_db = self._load_additives_database()
    
    def _load_additives_database(self):
        if os.path.exists(ADDITIVES_CSV_PATH):
            try:
                df = pd.read_csv(ADDITIVES_CSV_PATH)
                return df
            except:
                pass
        
        sample_data = {
            'E_number': ['E102', 'E110', 'E120', 'E124', 'E127', 'E129', 'E951', 'E621', 'E320', 'E321'],
            'Additive_name': ['Tartrazine', 'Sunset Yellow', 'Cochineal', 'Ponceau 4R', 'Erythrosine', 
                             'Allura Red', 'Aspartame', 'MSG', 'BHA', 'BHT'],
            'Risk_Level': ['High', 'High', 'Medium', 'High', 'High', 'High', 'Medium', 'Medium', 'High', 'High'],
            'Banned_In_Countries': [
                'Norway,Austria', 'Norway', 'USA', 'Norway,USA', 'USA', 'EU(restricted)', 
                'None', 'None', 'Japan', 'Japan,EU(restricted)'
            ],
            'Scientific_Concern': [
                'Hyperactivity,Allergies', 'Hyperactivity,Allergies', 'Allergic reactions',
                'Hyperactivity,Cancer concerns', 'Thyroid issues', 'Hyperactivity',
                'Headaches,Allergies', 'Headaches,Allergies', 'Carcinogen potential', 'Carcinogen potential'
            ]
        }
        
        df = pd.DataFrame(sample_data)
        try:
            df.to_csv(ADDITIVES_CSV_PATH, index=False)
        except:
            pass
        
        return df
    
    def analyze(self, additives_list):
        if not additives_list or self.additives_db is None:
            return []
        
        results = []
        
        for additive in additives_list:
            additive_clean = additive.strip().upper()
            
            match = self.additives_db[
                self.additives_db['E_number'].str.upper() == additive_clean
            ]
            
            if not match.empty:
                row = match.iloc[0]
                results.append({
                    'code': row['E_number'],
                    'name': row['Additive_name'],
                    'risk_level': row['Risk_Level'],
                    'banned_countries': str(row['Banned_In_Countries']).split(',') if pd.notna(row['Banned_In_Countries']) else [],
                    'health_effects': [row['Scientific_Concern']] if pd.notna(row['Scientific_Concern']) else []
                })
            else:
                results.append({
                    'code': additive_clean,
                    'name': 'Unknown',
                    'risk_level': 'Unknown',
                    'banned_countries': [],
                    'health_effects': []
                })
        
        return results

# ============================================================================
# HEALTH SCORER
# ============================================================================

class HealthScorer:
    def calculate_score(self, nutrients):
        if not nutrients:
            return 50
        
        score = 100
        
        sugar = nutrients.get('sugars_100g', 0)
        if sugar > 15:
            score -= min(30, (sugar - 15) * 2)
        
        fat = nutrients.get('fat_100g', 0)
        if fat > 20:
            score -= min(20, (fat - 20) * 1.5)
        
        saturated_fat = nutrients.get('saturated-fat_100g', 0)
        if saturated_fat > 5:
            score -= min(15, (saturated_fat - 5) * 2)
        
        salt = nutrients.get('salt_100g', 0)
        if salt > 1.5:
            score -= min(20, (salt - 1.5) * 10)
        
        protein = nutrients.get('proteins_100g', 0)
        score += min(15, protein * 0.5)
        
        fiber = nutrients.get('fiber_100g', 0)
        score += min(10, fiber * 1.5)
        
        return max(0, min(100, score))
    
    def get_grade(self, score):
        if score >= 80:
            return "A", "#38a169"
        elif score >= 60:
            return "B", "#85bb2f"
        elif score >= 40:
            return "C", "#f59e0b"
        elif score >= 20:
            return "D", "#ee8100"
        else:
            return "E", "#e53e3e"

# ============================================================================
# AI ANALYZER
# ============================================================================

class AIAnalyzer:
    def __init__(self):
        # Try to use the configured API key
        api_key = get_api_key("GEMINI_API_KEY", "AIzaSyB5gEnTHs8PgFcE5HDfuEhAnC9GJ7ofdHs")
        if api_key:
            try:
                genai.configure(api_key=api_key)
            except:
                pass
        
        # Try different model names for compatibility
        model_names = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-pro"]
        self.model = None
        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                break
            except:
                continue
        
        if self.model is None:
            st.error("Failed to initialize Gemini model. Please check your API key.")
    
    @st.cache_data(ttl=3600)
    def analyze_health(_self, product_name, ingredients, nutrients, additives):
        if _self.model is None:
            return "AI analysis unavailable: Model not initialized. Please check your API key."
        
        prompt = f"""As a food safety expert, analyze this product:

Product: {product_name}
Ingredients: {ingredients}
Nutrients per 100g: {nutrients}
Additives: {additives}

Provide a comprehensive health analysis covering:
1. Overall safety assessment (Safe/Caution/Avoid)
2. Main health benefits (if any)
3. Main health concerns (if any)
4. Specific recommendations for:
   - Children
   - Pregnant women
   - People with diabetes
   - People with heart conditions
5. Suggested healthier alternatives

Be specific, evidence-based, and balanced."""

        try:
            response = _self.model.generate_content(prompt)
            if response and hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'parts') and response.parts:
                return ''.join([part.text for part in response.parts if hasattr(part, 'text')])
            else:
                return "AI analysis unavailable: Unexpected response format."
        except Exception as e:
            return f"AI analysis unavailable: {str(e)}"
    
    def chat(_self, question, product_context):
        if _self.model is None:
            return "Chat unavailable: Model not initialized. Please check your API key."
        
        prompt = f"""You are a food safety expert. Answer this question about the product:

Product Context:
{json.dumps(product_context, indent=2)}

User Question: {question}

Provide a clear, helpful, and evidence-based answer."""

        try:
            response = _self.model.generate_content(prompt)
            if response and hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'parts') and response.parts:
                return ''.join([part.text for part in response.parts if hasattr(part, 'text')])
            else:
                return "Unable to generate response: Unexpected response format."
        except Exception as e:
            return f"Unable to answer: {str(e)}"

# ============================================================================
# UI RENDERER
# ============================================================================

class UIRenderer:
    @staticmethod
    def render_scanner():
        st.markdown("<div class='scanner-box'>", unsafe_allow_html=True)
        st.markdown("### 📷 Real-Time Barcode Scanner")
        st.markdown("Position barcode in front of camera")
        
        ctx = webrtc_streamer(
            key="barcode_scanner",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=RTC_CONFIGURATION,
            video_processor_factory=BarcodeScanner,
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
        )
        
        if ctx.video_processor:
            with ctx.video_processor.lock:
                detected = ctx.video_processor.detected_barcode
                if detected:
                    st.session_state.scanned_barcode = detected
                    ctx.video_processor.detected_barcode = None  # Reset after reading
                    st.success(f"✅ Detected: {detected}")
                    st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def render_product_header(product):
        st.markdown("<div class='product-card'>", unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            if product.get("image"):
                st.image(product["image"], width=200)
            else:
                st.image("https://via.placeholder.com/200x200?text=No+Image", width=200)
        
        with col2:
            st.markdown(f"## {product.get('name', 'Unknown Product')}")
            st.markdown(f"**Brand:** {product.get('brand', 'Unknown')}")
            st.markdown(f"**Category:** {product.get('category', 'Unknown')}")
            st.markdown(f"**Barcode:** {product.get('barcode', 'N/A')}")
            
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                nutri = product.get('nutri_score', '')
                if nutri:
                    colors = {'A': '#038141', 'B': '#85bb2f', 'C': '#fecb02', 'D': '#ee8100', 'E': '#e63e11'}
                    color = colors.get(nutri, '#999')
                    st.markdown(f"<div style='background:{color};color:white;padding:8px;border-radius:8px;text-align:center;font-weight:bold;'>Nutri-Score: {nutri}</div>", unsafe_allow_html=True)
            
            with col_b:
                nova = product.get('nova_group')
                if nova:
                    colors = {1: '#038141', 2: '#85bb2f', 3: '#ee8100', 4: '#e63e11'}
                    color = colors.get(nova, '#999')
                    st.markdown(f"<div style='background:{color};color:white;padding:8px;border-radius:8px;text-align:center;font-weight:bold;'>NOVA: {nova}</div>", unsafe_allow_html=True)
            
            with col_c:
                eco = product.get('ecoscore', '')
                if eco:
                    colors = {'A': '#038141', 'B': '#85bb2f', 'C': '#fecb02', 'D': '#ee8100', 'E': '#e63e11'}
                    color = colors.get(eco, '#999')
                    st.markdown(f"<div style='background:{color};color:white;padding:8px;border-radius:8px;text-align:center;font-weight:bold;'>Eco-Score: {eco}</div>", unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def render_ingredients(product):
        st.markdown("### 📋 Ingredients Analysis")
        
        ingredients = product.get("ingredients", "Not available")
        
        if ingredients != "Not available":
            st.markdown("<div class='alert-success'>", unsafe_allow_html=True)
            st.markdown(f"**Full Ingredient List:**")
            st.write(ingredients)
            st.markdown("</div>", unsafe_allow_html=True)
            
            ingredients_list = product.get("ingredients_list", [])
            if ingredients_list:
                st.markdown("**Individual Ingredients:**")
                for ing in ingredients_list[:10]:
                    st.markdown(f"<span class='ingredient-chip'>{ing}</span>", unsafe_allow_html=True)
        else:
            st.info("Ingredients information not available")
    
    @staticmethod
    def render_nutrient_table(nutrients):
        st.markdown("### 🥗 Nutritional Information (per 100g)")
        
        if not nutrients:
            st.info("Nutritional data not available")
            return
        
        nutrient_data = []
        
        nutrient_mapping = {
            'energy-kcal_100g': ('Energy', 'kcal'),
            'proteins_100g': ('Protein', 'g'),
            'carbohydrates_100g': ('Carbohydrates', 'g'),
            'sugars_100g': ('Sugars', 'g'),
            'fat_100g': ('Fat', 'g'),
            'saturated-fat_100g': ('Saturated Fat', 'g'),
            'fiber_100g': ('Fiber', 'g'),
            'salt_100g': ('Salt', 'g'),
            'sodium_100g': ('Sodium', 'g')
        }
        
        for key, (label, unit) in nutrient_mapping.items():
            if key in nutrients and nutrients[key] is not None:
                nutrient_data.append({
                    'Nutrient': label,
                    'Amount': f"{nutrients[key]:.2f}",
                    'Unit': unit
                })
        
        if nutrient_data:
            df = pd.DataFrame(nutrient_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            fig = px.bar(df, x='Nutrient', y='Amount', 
                        title='Nutritional Profile',
                        color='Amount',
                        color_continuous_scale='viridis')
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No detailed nutritional data available")
    
    @staticmethod
    def render_health_score(nutrients, scorer):
        st.markdown("### ❤️ Health Score Engine")
        
        score = scorer.calculate_score(nutrients)
        grade, color = scorer.get_grade(score)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown(f"""
            <div style='text-align:center;padding:3rem;background:{color}20;
                       border-radius:20px;border:4px solid {color};'>
                <h1 style='color:{color};margin:0;font-size:4rem;'>{score:.0f}</h1>
                <p style='color:#666;margin:0.5rem 0;font-size:1.2rem;'>Health Score</p>
                <h2 style='color:{color};margin:0;'>Grade {grade}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Sugar", f"{nutrients.get('sugars_100g', 0):.1f}g", 
                     delta="Low" if nutrients.get('sugars_100g', 0) < 5 else "High",
                     delta_color="normal" if nutrients.get('sugars_100g', 0) < 5 else "inverse")
        
        with col2:
            st.metric("Fat", f"{nutrients.get('fat_100g', 0):.1f}g",
                     delta="Low" if nutrients.get('fat_100g', 0) < 10 else "High",
                     delta_color="normal" if nutrients.get('fat_100g', 0) < 10 else "inverse")
        
        with col3:
            st.metric("Salt", f"{nutrients.get('salt_100g', 0):.2f}g",
                     delta="Low" if nutrients.get('salt_100g', 0) < 0.3 else "High",
                     delta_color="normal" if nutrients.get('salt_100g', 0) < 0.3 else "inverse")
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Health Score", 'font': {'size': 24}},
            gauge={
                'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': color},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 20], 'color': '#fee'},
                    {'range': [20, 40], 'color': '#fffbeb'},
                    {'range': [40, 60], 'color': '#fffdf0'},
                    {'range': [60, 80], 'color': '#f0fdf4'},
                    {'range': [80, 100], 'color': '#e8f5e9'}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ))
        
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    @staticmethod
    def render_additive_analysis(additives_list, analyzer):
        st.markdown("### 🔬 Additive Risk Analysis")
        
        if not additives_list:
            st.markdown("<div class='alert-success'>", unsafe_allow_html=True)
            st.markdown("✅ **No additives detected**")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        
        results = analyzer.analyze(additives_list)
        
        high_risk = [r for r in results if r['risk_level'] == 'High']
        
        if high_risk:
            st.markdown("<div class='alert-danger'>", unsafe_allow_html=True)
            st.markdown(f"⚠️ **{len(high_risk)} High Risk Additives Found**")
            st.markdown("</div>", unsafe_allow_html=True)
        
        for result in results:
            if result['risk_level'] == 'High':
                box_class = 'alert-danger'
                emoji = '🔴'
            elif result['risk_level'] == 'Medium':
                box_class = 'alert-warning'
                emoji = '🟡'
            else:
                box_class = 'alert-success'
                emoji = '🟢'
            
            st.markdown(f"<div class='{box_class}'>", unsafe_allow_html=True)
            st.markdown(f"{emoji} **{result['code']} - {result['name']}**")
            st.markdown(f"**Risk Level:** {result['risk_level']}")
            
            if result['banned_countries']:
                st.markdown(f"**Banned in:** {', '.join(result['banned_countries'])}")
            
            if result['health_effects']:
                st.markdown(f"**Health Effects:** {', '.join(result['health_effects'])}")
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def render_ai_analysis(product, analyzer):
        st.markdown("### 🤖 AI Health Analysis")
        
        with st.spinner("🔬 Analyzing product with AI..."):
            analysis = analyzer.analyze_health(
                product.get('name', ''),
                product.get('ingredients', ''),
                str(product.get('nutrients', {})),
                product.get('additives', [])
            )
        
        st.markdown("<div class='alert-success'>", unsafe_allow_html=True)
        st.markdown(analysis)
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def render_chatbot(product, analyzer):
        st.markdown("### 💬 Ask AI About This Product")
        
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        
        st.markdown("**Quick Questions:**")
        
        col1, col2 = st.columns(2)
        
        questions = [
            "Is this product safe for daily consumption?",
            "Is it suitable for children?",
            "Can diabetics consume this?",
            "Are there healthier alternatives?"
        ]
        
        for i, q in enumerate(questions):
            with col1 if i % 2 == 0 else col2:
                if st.button(q, key=f"quick_{i}"):
                    with st.spinner("🤔 Thinking..."):
                        answer = analyzer.chat(q, product)
                    st.session_state.chat_history.append({"question": q, "answer": answer})
                    st.rerun()
        
        st.markdown("---")
        
        for chat in st.session_state.chat_history[-5:]:
            st.markdown(f"<div class='chat-message user-message'>", unsafe_allow_html=True)
            st.markdown(f"**You:** {chat['question']}")
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown(f"<div class='chat-message ai-message'>", unsafe_allow_html=True)
            st.markdown(f"**AI:** {chat['answer']}")
            st.markdown("</div>", unsafe_allow_html=True)
        
        user_question = st.text_input("Ask your own question:", key="custom_question")
        
        if st.button("Send Question", type="primary"):
            if user_question:
                with st.spinner("🤔 Thinking..."):
                    answer = analyzer.chat(user_question, product)
                st.session_state.chat_history.append({"question": user_question, "answer": answer})
                st.rerun()

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    load_css()
    
    if 'product' not in st.session_state:
        st.session_state.product = None
    if 'history' not in st.session_state:
        st.session_state.history = []
    if 'scanned_barcode' not in st.session_state:
        st.session_state.scanned_barcode = None
    
    # If barcode came from the front-end scanner via query params, capture it
    query_params = st.experimental_get_query_params()
    if 'barcode' in query_params and query_params['barcode']:
        scanned_code = query_params['barcode'][0]
        if scanned_code:
            st.session_state.scanned_barcode = scanned_code
            # Clear query params so we don't re-trigger on every rerun
            st.experimental_set_query_params()
    
    off_fetcher = OpenFoodFactsFetcher()
    usda_fetcher = USDAFetcher()
    additive_analyzer = AdditiveAnalyzer()
    health_scorer = HealthScorer()
    ai_analyzer = AIAnalyzer()
    ui_renderer = UIRenderer()
    
    st.markdown("<h1 class='main-title'>🔍 AI Food Product Analyzer</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Real-time barcode scanning • AI health analysis • Additive risk detection</p>", unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown("### 📜 Scan History")
        
        if st.session_state.history:
            for idx, item in enumerate(st.session_state.history[:5]):
                if st.button(f"{item.get('name', 'Unknown')[:25]}...", key=f"hist_{idx}", use_container_width=True):
                    st.session_state.product = item
                    st.rerun()
            
            if st.button("🗑️ Clear History", type="secondary", use_container_width=True):
                st.session_state.history = []
                st.rerun()
        else:
            st.info("No scans yet")
        
        st.markdown("---")
        st.markdown("### ℹ️ About")
        st.caption("This app uses OpenFoodFacts API, USDA FoodData Central, and Google Gemini AI for comprehensive food analysis.")
    
    tab1, tab2 = st.tabs(["📷 Camera Scanner", "🔎 Manual Search"])
    
    with tab1:
        ui_renderer.render_scanner()
        
        if st.session_state.scanned_barcode:
            barcode = st.session_state.scanned_barcode
            st.session_state.scanned_barcode = None
            
            with st.spinner(f"Fetching product data for {barcode}..."):
                product = off_fetcher.fetch_product(barcode)
                
                if product:
                    if not product.get('nutrients') or len(product.get('nutrients', {})) < 3:
                        usda_nutrients = usda_fetcher.fetch_nutrition(product.get('name', ''))
                        if usda_nutrients:
                            product['nutrients'].update(usda_nutrients)
                    
                    st.session_state.product = product
                    
                    if product not in st.session_state.history:
                        st.session_state.history.insert(0, product)
                    
                    st.rerun()
                else:
                    st.error("Product not found in database")
    
    with tab2:
        col1, col2 = st.columns([4, 1])
        
        with col1:
            search_input = st.text_input("Enter barcode or product name", 
                                        placeholder="e.g., 737628064502 or 'Coca Cola'",
                                        key="search_input")
        
        with col2:
            search_btn = st.button("Search", type="primary", use_container_width=True)
        
        st.caption("💡 Try: 737628064502 (Kettle Chips) | 041196910759 (Cheerios) | 3017620422003 (Nutella)")
        
        if search_btn and search_input:
            with st.spinner("Searching..."):
                if search_input.isdigit():
                    product = off_fetcher.fetch_product(search_input)
                    
                    if product:
                        if not product.get('nutrients') or len(product.get('nutrients', {})) < 3:
                            usda_nutrients = usda_fetcher.fetch_nutrition(product.get('name', ''))
                            if usda_nutrients:
                                product['nutrients'].update(usda_nutrients)
                        
                        st.session_state.product = product
                        
                        if product not in st.session_state.history:
                            st.session_state.history.insert(0, product)
                        
                        st.rerun()
                    else:
                        st.error("Product not found")
                else:
                    results = off_fetcher.search_by_name(search_input)
                    
                    if results:
                        st.success(f"Found {len(results)} products")
                        
                        for idx, item in enumerate(results):
                            col1, col2, col3 = st.columns([1, 5, 1])
                            
                            with col1:
                                if item.get("image_url"):
                                    st.image(item["image_url"], width=60)
                                else:
                                    st.markdown("📦")
                            
                            with col2:
                                st.markdown(f"**{item.get('product_name', 'Unknown')}**")
                                st.caption(f"{item.get('brands', 'Unknown')} • {item.get('code', 'N/A')}")
                            
                            with col3:
                                if st.button("Select", key=f"sel_{idx}"):
                                    product = off_fetcher.fetch_product(item.get('code', ''))
                                    
                                    if product:
                                        if not product.get('nutrients') or len(product.get('nutrients', {})) < 3:
                                            usda_nutrients = usda_fetcher.fetch_nutrition(product.get('name', ''))
                                            if usda_nutrients:
                                                product['nutrients'].update(usda_nutrients)
                                        
                                        st.session_state.product = product
                                        
                                        if product not in st.session_state.history:
                                            st.session_state.history.insert(0, product)
                                        
                                        st.rerun()
                    else:
                        st.error("No products found")
    
    if st.session_state.product:
        st.markdown("---")
        
        product = st.session_state.product
        
        ui_renderer.render_product_header(product)
        
        allergens = product.get('allergens', [])
        if allergens:
            st.markdown("<div class='alert-warning'>", unsafe_allow_html=True)
            st.markdown(f"⚠️ **Contains Allergens:** {', '.join(allergens)}")
            st.markdown("</div>", unsafe_allow_html=True)
        
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 Ingredients",
            "🥗 Nutrition",
            "❤️ Health Score",
            "🔬 Additives",
            "🤖 AI Analysis",
            "💬 Chatbot"
        ])
        
        with tab1:
            ui_renderer.render_ingredients(product)
        
        with tab2:
            ui_renderer.render_nutrient_table(product.get('nutrients', {}))
        
        with tab3:
            ui_renderer.render_health_score(product.get('nutrients', {}), health_scorer)
        
        with tab4:
            ui_renderer.render_additive_analysis(product.get('additives', []), additive_analyzer)
        
        with tab5:
            ui_renderer.render_ai_analysis(product, ai_analyzer)
        
        with tab6:
            ui_renderer.render_chatbot(product, ai_analyzer)

if __name__ == "__main__":
    main()