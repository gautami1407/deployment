import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
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
from streamlit_lottie import st_lottie
import uuid
import pycountry
import hashlib

# API Keys
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USDA_API_KEY = os.environ.get("USDA_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Cache directory setup
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".product_checker_cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Global settings
st.set_page_config(
    page_title="Product Health & Safety Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)


def load_css():
    st.markdown("""
    <style>
    .main-header {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        color: #2E7D32; /* Dark Green */
    }
    .sub-header {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        color: #e8f5e9;
    }
    .highlight-box {
        background-color: #f0f8ff;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #388E3C; /* Green */
        margin-bottom: 20px;
    }
    .danger-box {
        background-color: #ffebee;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #e53935;
        margin-bottom: 20px;
    }
    .success-box {
        background-color: #e8f5e9;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #43a047;
        margin-bottom: 20px;
    }
    .warning-box {
        background-color: #fff8e1;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #ffb300;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: white;
        padding: 15px;
        border-radius: 5px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
    }
    .metric-label {
        font-size: 14px;
        color: #666;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #E8F5E9; /* Light Green */
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #388E3C; /* Green */
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)



# Load a Lottie animation for the loading state
def load_lottie(url: str):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()


# Database class for product regulations
class RegulationDatabase:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        self.banned_products_file = os.path.join(cache_dir, "banned_products.json")
        self.recalls_file = os.path.join(cache_dir, "product_recalls.json")
        self.initialize_database()

    def check_banned_products(self, product_name):
        banned_data = self.load_banned_products()
        banned_products = []

        for banned_product, data in banned_data["products"].items():
            if product_name.lower() == banned_product.lower():
                banned_products.append({
                    "product": banned_product,
                    "banned_in": data["banned_in"],
                    "reason": data["reason"],
                    "alternatives": data["alternatives"]
                })

        return banned_products

    def check_food_packaging_compliance(self, ingredients, region):
        compliance_issues = []

        # Example logic: Check against banned ingredients
        banned_data = self.load_banned_products()
        for ingredient in ingredients.split(","):
            ingredient = ingredient.strip().lower()
            if ingredient in banned_data["ingredients"]:
                compliance_issues.append(f"{ingredient} is banned in {region}.")

        # Add more checks based on your specific regulations
        # For example, you could check for specific packaging materials or labeling requirements

        return {
            "compliant": len(compliance_issues) == 0,
            "issues": compliance_issues
        }

    def check_compliance(self, ingredients, region):
        # Example implementation
        # This method should check if the ingredients comply with regulations in the specified region
        compliance_issues = []

        # Example logic: Check against banned ingredients
        banned_data = self.load_banned_products()
        for ingredient in ingredients.split(","):
            ingredient = ingredient.strip().lower()
            if ingredient in banned_data["ingredients"]:
                compliance_issues.append(f"{ingredient} is banned in {region}.")

        return {
            "compliant": len(compliance_issues) == 0,
            "issues": compliance_issues
        }

    def initialize_database(self):
        # Create sample banned products database if it doesn't exist
        if not os.path.exists(self.banned_products_file):
            sample_banned_products = {
                "ingredients": {
                    "Potassium Bromate": {
                        "banned_in": ["European Union", "United Kingdom", "Canada", "Brazil", "China", "India"],
                        "reason": "Potential carcinogen, linked to kidney and nervous system damage",
                        "alternatives": ["Ascorbic acid", "Enzymes"]
                    },
                    "Brominated Vegetable Oil (BVO)": {
                        "banned_in": ["European Union", "Japan", "India"],
                        "reason": "Linked to thyroid problems and neurological development issues",
                        "alternatives": ["Natural emulsifiers", "Hydrocolloids"]
                    },
                    "Azodicarbonamide": {
                        "banned_in": ["European Union", "Australia", "United Kingdom", "Singapore"],
                        "reason": "Linked to respiratory issues and allergies",
                        "alternatives": ["Ascorbic acid", "Enzymes"]
                    },
                    "rBGH/rBST": {
                        "banned_in": ["European Union", "Canada", "Australia", "New Zealand", "Japan", "Israel"],
                        "reason": "Concerns about impacts on human health and animal welfare",
                        "alternatives": ["Organic dairy products"]
                    },
                    "BHA/BHT": {
                        "banned_in": ["Japan", "European Union (restricted)"],
                        "reason": "Potential endocrine disruptors, possible carcinogens",
                        "alternatives": ["Vitamin E", "Rosemary extract"]
                    },
                    "Tartrazine (Yellow #5)": {
                        "banned_in": ["Norway", "Austria"],
                        "reason": "Linked to hyperactivity in children, allergic reactions",
                        "alternatives": ["Natural food colors", "Turmeric", "Saffron"]
                    },
                    "Olestra/Olean": {
                        "banned_in": ["United Kingdom", "Canada"],
                        "reason": "Causes digestive issues, inhibits nutrient absorption",
                        "alternatives": ["Natural oils in moderation"]
                    },
                    "Sodium Cyclamate": {
                        "banned_in": ["United States"],
                        "reason": "Linked to cancer in animal studies",
                        "alternatives": ["Stevia", "Monk fruit extract"]
                    },
                    "Formaldehyde": {
                        "banned_in": ["European Union (in cosmetics)"],
                        "reason": "Known carcinogen",
                        "alternatives": ["Natural preservatives"]
                    },
                    "Paraben preservatives": {
                        "banned_in": ["European Union (some types)"],
                        "reason": "Hormone disruption concerns",
                        "alternatives": ["Essential oils", "Grapefruit seed extract"]
                    },
                    "Titanium Dioxide (E171)": {
                        "banned_in": ["European Union (as food additive)"],
                        "reason": "Potential genotoxicity concerns",
                        "alternatives": ["Natural whitening agents"]
                    }
                },
                "products": {
                    "Unpasteurized dairy products": {
                        "banned_in": ["Australia", "Canada (for sale)", "Scotland"],
                        "reason": "Risk of harmful bacteria including E. coli, Salmonella, and Listeria",
                        "alternatives": "Pasteurized dairy products"
                    },
                    "Kinder Surprise Eggs (original)": {
                        "banned_in": ["United States"],
                        "reason": "Choking hazard due to non-food items inside food products",
                        "alternatives": "Kinder Joy (compartmentalized version)"
                    },
                    "Sassafras oil": {
                        "banned_in": ["United States", "European Union"],
                        "reason": "Contains safrole, a carcinogen",
                        "alternatives": "Artificial sassafras flavoring (safrole-free)"
                    },
                    "Shark fins": {
                        "banned_in": ["Canada", "Taiwan", "United Arab Emirates"],
                        "reason": "Unethical harvesting practices and species conservation",
                        "alternatives": "Plant-based alternatives, cultivated seafood"
                    }
                }
            }
            with open(self.banned_products_file, 'w') as f:
                json.dump(sample_banned_products, f, indent=4)

        # Create sample product recalls database if it doesn't exist
        if not os.path.exists(self.recalls_file):
            sample_recalls = {
                "recent_recalls": [
                    {
                        "product_name": "XYZ Organic Peanut Butter",
                        "date": "2024-02-15",
                        "reason": "Potential Salmonella contamination",
                        "regions_affected": ["United States", "Canada"],
                        "batch_numbers": ["PB202401", "PB202402", "PB202403"]
                    },
                    {
                        "product_name": "ABC Infant Formula",
                        "date": "2024-01-22",
                        "reason": "Possible Cronobacter contamination",
                        "regions_affected": ["United States"],
                        "batch_numbers": ["IF24A123", "IF24A124"]
                    },
                    {
                        "product_name": "Green Fields Spinach",
                        "date": "2024-02-28",
                        "reason": "Potential E. coli contamination",
                        "regions_affected": ["United States", "Mexico"],
                        "batch_numbers": ["GFS-2402-A", "GFS-2402-B"]
                    }
                ]
            }
            with open(self.recalls_file, 'w') as f:
                json.dump(sample_recalls, f, indent=4)


    def load_banned_products(self):
        try:
            with open(self.banned_products_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"ingredients": {}, "products": {}}

    def load_product_recalls(self):
        try:
            with open(self.recalls_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"recent_recalls": []}

    def check_against_banned_ingredients(self, ingredients_text):
        if not ingredients_text or ingredients_text == "Not available":
            return []

        banned_data = self.load_banned_products()
        found_issues = []

        ingredients_text = ingredients_text.lower()
        for ingredient, data in banned_data["ingredients"].items():
            if ingredient.lower() in ingredients_text:
                found_issues.append({
                    "ingredient": ingredient,
                    "banned_in": data["banned_in"],
                    "reason": data["reason"],
                    "alternatives": data["alternatives"]
                })

        return found_issues

    def check_product_recalls(self, product_name, brand_name):
        recalls = self.load_product_recalls()
        matching_recalls = []

        search_terms = [product_name.lower(), brand_name.lower()]

        for recall in recalls["recent_recalls"]:
            recall_name = recall["product_name"].lower()
            if any(term in recall_name for term in search_terms):
                matching_recalls.append(recall)

        return matching_recalls


class DataFetcher:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ProductHealthSafetyAnalyzer/2.0',
        })
        self.retry_count = 3
        self.retry_delay = 1  # seconds

    def _get_cache_path(self, key, source):
        # Use a hash of the key for filename safety
        hashed_key = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{source}_{hashed_key}.json")

    def _load_from_cache(self, key, source, max_age=86400):
        cache_path = self._get_cache_path(key, source)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                cache_time = cached_data.get('cache_time', 0)
                current_time = time.time()
                if current_time - cache_time <= max_age:
                    return cached_data.get('data')
            except (json.JSONDecodeError, IOError):
                pass
        return None

    def _save_to_cache(self, key, source, data):
        cache_path = self._get_cache_path(key, source)
        try:
            with open(cache_path, 'w') as f:
                json.dump({
                    'data': data,
                    'cache_time': time.time()
                }, f)
        except IOError:
            pass

    def fetch_with_retries(self, url, params=None, headers=None):
        for attempt in range(self.retry_count):
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    raise e

    def fetch_from_open_food_facts(self, barcode):
        cached_data = self._load_from_cache(barcode, 'off')
        if cached_data:
            return self._extract_off_data(cached_data)

        try:
            url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
            data = self.fetch_with_retries(url)
            if data.get("status") == 1:
                self._save_to_cache(barcode, 'off', data)
                return self._extract_off_data(data)
            else:
                return None, None, None, None, None, None, None
        except Exception as e:
            st.error(f"Error fetching from Open Food Facts: {str(e)}")
            return None, None, None, None, None, None, None

    def _extract_off_data(self, data):
        if data.get("status") == 1:
            product = data.get("product", {})
            product_name = product.get("product_name", "Unknown Product")
            brand_name = product.get("brands", "Unknown Brand")
            category = product.get("categories_tags", ["unknown"])[0].replace("en:", "") if product.get(
                "categories_tags") else "Unknown"
            origin = product.get("countries", "Unknown")
            image_url = product.get("image_url")

            # Extract allergens
            allergens = product.get("allergens_tags", [])
            allergens = [a.replace("en:", "") for a in allergens]

            details = {
                "ingredients": product.get("ingredients_text", "Not available"),
                "ingredients_list": [i.get("text", "") for i in product.get("ingredients", [])],
                "nutriments": product.get("nutriments", {}),
                "nutrition_grades": product.get("nutrition_grades", ""),
                "nova_group": product.get("nova_group", ""),
                "ecoscore_grade": product.get("ecoscore_grade", ""),
                "packaging": product.get("packaging", "Not specified"),
                "manufacturing_places": product.get("manufacturing_places", "Not specified"),
                "additives_tags": [a.replace("en:", "") for a in product.get("additives_tags", [])],
                "labels": product.get("labels", ""),
                "exp_date": product.get("expiration_date", ""),
                "image_url": image_url,
                "allergens": allergens,
                "serving_size": product.get("serving_size", "Not specified"),
                "stores": product.get("stores", "Not specified")
            }
            return product_name, brand_name, category.capitalize(), origin, details, image_url, allergens
        return None, None, None, None, None, None, None

    def fetch_from_usda(self, barcode):
        cached_data = self._load_from_cache(barcode, 'usda')
        if cached_data:
            return self._extract_usda_data(cached_data)

        try:
            search_url = f"https://api.nal.usda.gov/fdc/v1/foods/search"
            params = {
                "api_key": USDA_API_KEY,
                "query": barcode,
                "pageSize": 1
            }
            search_data = self.fetch_with_retries(search_url, params)
            if not search_data.get("foods"):
                return None, None, None, None, None, None, None
            food = search_data["foods"][0]
            food_id = food.get("fdcId")
            detail_url = f"https://api.nal.usda.gov/fdc/v1/food/{food_id}"
            params = {"api_key": USDA_API_KEY}
            detail_data = self.fetch_with_retries(detail_url, params)
            combined_data = {
                "search_result": search_data,
                "detail": detail_data
            }
            self._save_to_cache(barcode, 'usda', combined_data)
            return self._extract_usda_data(combined_data)
        except Exception as e:
            st.error(f"Error fetching from USDA: {str(e)}")
            return None, None, None, None, None, None, None

    def _extract_usda_data(self, combined_data):
        try:
            search_data = combined_data.get("search_result", {})
            detail_data = combined_data.get("detail", {})
            if not search_data.get("foods"):
                return None, None, None, None, None, None, None
            food = search_data["foods"][0]
            product_name = food.get("description", "Unknown Product")
            brand_name = food.get("brandOwner", "Unknown Brand")
            category = food.get("foodCategory", "Unknown Category")
            origin = detail_data.get("marketCountry", "Unknown")
            allergens = []
            if "allergens" in detail_data:
                allergens = detail_data["allergens"].split(",")
                allergens = [a.strip() for a in allergens]

            # Extract ingredients
            ingredients = detail_data.get("ingredients", "Not available")

            # Process nutrients into a more digestible format
            nutrients_display = {}
            if "foodNutrients" in detail_data:
                for nutrient in detail_data["foodNutrients"]:
                    if "nutrientName" in nutrient and "value" in nutrient:
                        nutrients_display[nutrient["nutrientName"]] = {
                            "value": nutrient["value"],
                            "unit": nutrient.get("unitName", "")
                        }

            details = {
                "ingredients": ingredients,
                "foodNutrients": detail_data.get("foodNutrients", []),
                "nutrients_display": nutrients_display,
                "ingredients_list": [],  # USDA doesn't provide a clean list like OFF
                "serving_size": detail_data.get("servingSize", "Not specified"),
                "serving_unit": detail_data.get("servingSizeUnit", ""),
                "household_serving": detail_data.get("householdServingFullText", "Not specified"),
                "data_type": detail_data.get("dataType", ""),
                "publication_date": detail_data.get("publicationDate", "")
            }

            image_url = None  # USDA doesn't provide images
            return product_name, brand_name, category, origin, details, image_url, allergens
        except Exception as e:
            st.error(f"Error processing USDA data: {str(e)}")
            return None, None, None, None, None, None, None

    def search_products_by_name(self, name):
        """Search for products by name in Open Food Facts database"""
        cached_data = self._load_from_cache(f"search_{name}", 'off')
        if cached_data:
            return cached_data

        try:
            url = "https://world.openfoodfacts.org/cgi/search.pl"
            params = {
                "search_terms": name,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 10
            }
            response = self.fetch_with_retries(url, params)
            if response and "products" in response:
                self._save_to_cache(f"search_{name}", 'off', response["products"])
                return response["products"]
            return []
        except Exception as e:
            st.error(f"Error searching products: {str(e)}")
            return []


class AIAnalyzer:
    def __init__(self, api_key=GEMINI_API_KEY, cache_dir=CACHE_DIR):
        self.api_key = api_key
        self.cache_dir = cache_dir
        genai.configure(api_key=self.api_key)

    def _get_cache_path(self, analysis_type, product_name, brand_name):
        safe_name = re.sub(r'[^\w]', '_', f"{product_name}_{brand_name}")
        safe_name = hashlib.md5(safe_name.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{analysis_type}_{safe_name}.json")

    def _load_from_cache(self, analysis_type, product_name, brand_name, max_age=604800):
        cache_path = self._get_cache_path(analysis_type, product_name, brand_name)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                cache_time = cached_data.get('cache_time', 0)
                current_time = time.time()
                if current_time - cache_time <= max_age:
                    return cached_data.get('data')
            except (json.JSONDecodeError, IOError):
                pass
        return None

    def _save_to_cache(self, analysis_type, product_name, brand_name, data):
        cache_path = self._get_cache_path(analysis_type, product_name, brand_name)
        try:
            with open(cache_path, 'w') as f:
                json.dump({
                    'data': data,
                    'cache_time': time.time()
                }, f)
        except IOError:
            pass

    def check_certification(self, brand_name, product_name, certification_type, product_details=None):
        cached_result = self._load_from_cache(f"{certification_type.lower()}_cert", product_name, brand_name)
        if cached_result:
            return cached_result

        context = ""
        if product_details:
            if "ingredients" in product_details and product_details["ingredients"] != "Not available":
                context += f"Product ingredients: {product_details['ingredients']}\n\n"

            if "labels" in product_details and product_details["labels"]:
                context += f"Product labels: {product_details['labels']}\n\n"

        prompt = f"""
            As a food safety expert, analyze the compliance of product "{product_name}" 
            from brand "{brand_name}" with {certification_type} standards.

            {context}

            Consider:
            1. If the product likely meets {certification_type} requirements
            2. Common compliance issues with similar products
            3. What consumers should know about {certification_type} certification
            4. Recommendations for consumers concerned about {certification_type} compliance

            Provide a detailed assessment with bullet points. Be honest about limitations in your analysis.
        """
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            result = response.text if response else f"Unable to check {certification_type} certification."

            self._save_to_cache(f"{certification_type.lower()}_cert", product_name, brand_name, result)
            return result
        except Exception as e:
            return f"Error checking {certification_type} certification: {str(e)}"

    def analyze_product_health(self, product_name, brand_name, category, product_details):
        cached_result = self._load_from_cache("health_analysis", product_name, brand_name)
        if cached_result:
            analysis = cached_result.get("analysis", "")
            rating = cached_result.get("rating", 0)
            nutrition_metrics = cached_result.get("nutrition_metrics", {})
            return analysis, rating, nutrition_metrics

        context = self._prepare_analysis_context(product_details)
        prompt = (
            f"Analyze the health aspects of product '{product_name}' from brand '{brand_name}' in category '{category}'.\n\n"
            f"{context}\n\n"
            f"Please provide:\n"
            f"1. List the top 5 health factors about this product (good or concerning)\n"
            f"2. Rate the product on a scale of 1-10 based on health considerations (where 10 is healthiest)\n"
            f"3. Provide a detailed explanation of the rating\n"
            f"4. List any potential health concerns for specific groups (children, elderly, pregnant women, people with health conditions)\n"
            f"5. Suggest healthier alternatives if the product has nutrition concerns\n\n"
            f"Also extract specific numeric values (as best you can estimate) for: calories_per_serving, sugar_content_g, saturated_fat_g, sodium_mg, protein_g, fiber_g, and additive_count.\n\n"
            f"Format your response with clear headings and bullet points."
        )
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            response_text = response.text if response else "Unable to generate health analysis."
            rating = self._extract_rating(response_text)

            # Extract nutrition metrics
            nutrition_metrics = self._extract_nutrition_metrics(response_text, product_details)

            result = {
                "analysis": response_text,
                "rating": rating,
                "nutrition_metrics": nutrition_metrics
            }
            self._save_to_cache("health_analysis", product_name, brand_name, result)
            return response_text, rating, nutrition_metrics
        except Exception as e:
            return f"Error analyzing product health: {str(e)}", 0, {}

    def analyze_environmental_impact(self, product_name, brand_name, product_details):
        cached_result = self._load_from_cache("environmental_analysis", product_name, brand_name)
        if cached_result:
            return cached_result.get("analysis", ""), cached_result.get("rating", 0)

        # Extract relevant environmental information
        packaging = product_details.get("packaging", "Not specified")
        ecoscore = product_details.get("ecoscore_grade", "")
        manufacturing_places = product_details.get("manufacturing_places", "Not specified")
        origin = product_details.get("origin", "Unknown")

        prompt = (
            f"Analyze the environmental impact of product '{product_name}' from brand '{brand_name}'.\n\n"
            f"Product packaging: {packaging}\n"
            f"Ecoscore grade: {ecoscore}\n"
            f"Manufacturing places: {manufacturing_places}\n"
            f"Origin: {origin}\n\n"
            f"Please provide:\n"
            f"1. Rate the product's environmental impact on a scale of 1-10 (where 10 is most environmentally friendly)\n"
            f"2. Analyze packaging sustainability\n"
            f"3. Consider carbon footprint from manufacturing and transportation\n"
            f"4. Suggest more sustainable alternatives if applicable\n"
            f"Format your response with clear headings and bullet points."
        )

        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            response_text = response.text if response else "Unable to generate environmental analysis."
            rating = self._extract_rating(response_text)

            result = {
                "analysis": response_text,
                "rating": rating
            }
            self._save_to_cache("environmental_analysis", product_name, brand_name, result)
            return response_text, rating
        except Exception as e:
            return f"Error analyzing environmental impact: {str(e)}", 0

    def analyze_allergen_risks(self, product_name, brand_name, allergens, ingredients):
        cached_result = self._load_from_cache("allergen_analysis", product_name, brand_name)
        if cached_result:
            return cached_result

        allergen_list = ", ".join(allergens) if allergens else "None listed"

        prompt = (
            f"Analyze the allergen risks for product '{product_name}' from brand '{brand_name}'.\n\n"
            f"Listed allergens: {allergen_list}\n"
            f"Ingredients: {ingredients}\n\n"
            f"Please provide:\n"
            f"1. Identify explicit allergens in the product\n"
            f"2. Identify potential hidden allergens based on ingredients\n"
            f"3. Assess cross-contamination risks that are common with this type of product\n"
            f"4. Provide recommendations for consumers with specific allergies or sensitivities\n"
            f"Format your response with clear headings and bullet points."
        )

        try:
            model = genai.GenerativeModel()
            response = model.generate_content(prompt)
            response_text = response.text if response else "Unable to generate allergen analysis."

            self._save_to_cache("allergen_analysis", product_name, brand_name, response_text)
            return response_text
        except Exception as e:
            return f"Error analyzing allergen risks: {str(e)}"

    def generate_healthier_recipes(self, product_name, category, ingredients):
        cached_result = self._load_from_cache("healthier_recipes", product_name, category)
        if cached_result:
            return cached_result

        prompt = (
            f"Generate three healthier homemade alternatives or recipes related to '{product_name}' in the category '{category}'.\n\n"
            f"Original ingredients: {ingredients}\n\n"
            f"For each alternative, please provide:\n"
            f"1. A name for the healthier alternative\n"
            f"2. List of wholesome ingredients\n"
            f"3. Brief preparation instructions\n"
            f"4. Health benefits compared to the original product\n"
            f"Format your response with clear headings and numbered recipes."
        )

        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            response_text = response.text if response else "Unable to generate healthier recipes."

            self._save_to_cache("healthier_recipes", product_name, category, response_text)
            return response_text
        except Exception as e:
            return f"Error generating healthier recipes: {str(e)}"

    def _prepare_analysis_context(self, product_details):
        context = ""
        if product_details:
            if "ingredients" in product_details and product_details["ingredients"] != "Not available":
                context += f"Ingredients: {product_details['ingredients']}\n\n"

            if "nutriments" in product_details and product_details["nutriments"]:
                context += "Nutritional Information:\n"
                nutrients = product_details["nutriments"]
                for key, value in nutrients.items():
                    if not key.endswith("_100g") and not key.endswith("_serving") and not key.endswith("_unit"):
                        continue
                    if isinstance(value, (int, float)):
                        context += f"- {key}: {value}\n"

            if "nutrition_grades" in product_details and product_details["nutrition_grades"]:
                context += f"\nNutri-Score: {product_details['nutrition_grades'].upper()}\n"

            if "nova_group" in product_details and product_details["nova_group"]:
                context += f"NOVA Group (food processing): {product_details['nova_group']}\n"

            if "additives_tags" in product_details and product_details["additives_tags"]:
                context += f"\nAdditives: {', '.join(product_details['additives_tags'])}\n"

        return context

    def _extract_rating(self, text):
        try:
            rating_pattern = r'(?:rate|rating|score)[^\d]*(\d+(?:\.\d+)?)\s*(?:\/|\bof\b|\bout of\b)?\s*10'
            matches = re.search(rating_pattern, text, re.IGNORECASE)
            if matches:
                rating = float(matches.group(1))
                if 0 <= rating <= 10:
                    return rating
            return 5.0  # Default middle rating
        except:
            return 5.0

    def _extract_nutrition_metrics(self, text, product_details):
        metrics = {
            "calories_per_serving": None,
            "sugar_content_g": None,
            "saturated_fat_g": None,
            "sodium_mg": None,
            "protein_g": None,
            "fiber_g": None,
            "additive_count": None
        }

        # Try to extract from AI response
        patterns = {
            "calories_per_serving": r"calories[^:]*:?\s*(\d+(?:\.\d+)?)",
            "sugar_content_g": r"sugar[^:]*:?\s*(\d+(?:\.\d+)?)",
            "saturated_fat_g": r"saturated[^:]*:?\s*(\d+(?:\.\d+)?)",
            "sodium_mg": r"sodium[^:]*:?\s*(\d+(?:\.\d+)?)",
            "protein_g": r"protein[^:]*:?\s*(\d+(?:\.\d+)?)",
            "fiber_g": r"fiber[^:]*:?\s*(\d+(?:\.\d+)?)",
            "additive_count": r"additive[^:]*:?\s*(\d+)"
        }

        for metric, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    metrics[metric] = float(match.group(1))
                except:
                    pass

        # Try to fill missing values from product details
        if product_details and "nutriments" in product_details:
            nutrients = product_details["nutriments"]

            if metrics["calories_per_serving"] is None and "energy-kcal_serving" in nutrients:
                metrics["calories_per_serving"] = nutrients["energy-kcal_serving"]

            if metrics["sugar_content_g"] is None and "sugars_100g" in nutrients:
                metrics["sugar_content_g"] = nutrients["sugars_100g"]

            if metrics["saturated_fat_g"] is None and "saturated-fat_100g" in nutrients:
                metrics["saturated_fat_g"] = nutrients["saturated-fat_100g"]

            if metrics["sodium_mg"] is None and "sodium_100g" in nutrients:
                metrics["sodium_mg"] = nutrients["sodium_100g"] * 1000  # Convert g to mg

            if metrics["protein_g"] is None and "proteins_100g" in nutrients:
                metrics["protein_g"] = nutrients["proteins_100g"]

            if metrics["fiber_g"] is None and "fiber_100g" in nutrients:
                metrics["fiber_g"] = nutrients["fiber_100g"]

        if metrics["additive_count"] is None and "additives_tags" in product_details:
            metrics["additive_count"] = len(product_details["additives_tags"])

        return metrics


def get_gemini_response(question, product_name, product_details):
    context = f"Product Name: {product_name}\n"
    if product_details:
        context += f"Product Details: {product_details}\n"

    prompt = f"{context}: User: {question}\nAI:"

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip() if response else "I'm sorry, I couldn't generate a response."
    except Exception as e:
        return f"Error: {str(e)}"

    # Add this function to handle chat interactions
def chat_session(product_data):
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    product_name = product_data["product_name"]
    product_details = product_data["details"]

    st.header("Chat with Product Analyzer")

    # Display chat history
    for chat in st.session_state.chat_history:
        st.write(f"**User   :** {chat['user']}")
        st.write(f"**AI:** {chat['ai']}")

    # User input for questions
    user_question = st.text_input("Ask a question about the product:", key="user_input")

    if st.button("Send"):
        if user_question:
            # Get response from Gemini API
            ai_response = get_gemini_response(user_question, product_name, product_details)

            # Store the chat in session state
            st.session_state.chat_history.append({"user": user_question, "ai": ai_response})

            # Clear the input field by resetting the text input widget
            user_question = ""  # This line can be removed

    # Suggested questions
    st.subheader("Suggested Questions")
    suggested_questions = [
        "Are there any known side effects of this product?",
        "Is this product compliant with local regulations?",
        "What certifications does this product have (e.g., organic, non-GMO)?",
        "How sustainable is the packaging of this product?",
        "Are there any common complaints about this product?",
        "Can you suggest healthier alternatives to this product?"
    ]

    for question in suggested_questions:
        if st.button(question):
            # Automatically send the suggested question
            ai_response = get_gemini_response(question, product_name, product_details)
            st.session_state.chat_history.append({"user": question, "ai": ai_response})


# Main app layout and functions
def main():
    load_css()
    regulation_db = RegulationDatabase()
    data_fetcher = DataFetcher()
    ai_analyzer = AIAnalyzer()

    # Initialize session state
    if 'product_data' not in st.session_state:
        st.session_state.product_data = None
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = 0
    if 'scan_history' not in st.session_state:
        st.session_state.scan_history = []
    if 'region' not in st.session_state:
        st.session_state.region = None

    # Sidebar for settings and history
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2921/2921788.png", width=100)
        st.markdown("<h2 class='main-header'>Product Health & Safety Analyzer</h2>", unsafe_allow_html=True)

        # Region selection
        countries = sorted([country.name for country in pycountry.countries])
        default_region = "United States"
        region = st.selectbox("Select your region:", countries,
                              index=countries.index(default_region) if default_region in countries else 0)
        st.session_state.region = region

        st.divider()

        # Scan history
        st.subheader("Scan History")
        if not st.session_state.scan_history:
            st.info("You haven't scanned any products yet.")
        else:
            for idx, item in enumerate(st.session_state.scan_history[-5:]):  # Show last 5
                col1, col2 = st.columns([1, 3])
                with col1:
                    if item["image_url"]:
                        st.image(item["image_url"], width=50)
                    else:
                        st.markdown("📦")
                with col2:
                    st.write(f"{item['product_name']}")
                    if st.button(f"View Details", key=f"history_{idx}"):
                        st.session_state.product_data = item
                        st.experimental_rerun()

        # Clear history button
        if st.session_state.scan_history:
            if st.button("Clear History"):
                st.session_state.scan_history = []
                st.success("History cleared!")

    # Main content
    st.markdown("<h1 class='main-header'>Product Health & Safety Analyzer</h1>", unsafe_allow_html=True)
    st.markdown("Scan barcodes or search for products to get detailed health, safety, and environmental information")

    # Search tab
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        barcode = st.text_input("Enter barcode or product name:", key="barcode_input")
    with search_col2:
        search_button = st.button("Search", use_container_width=True)

    # Demo barcodes
    st.markdown(
        "<small>Try sample barcodes: 737628064502 (Kettle Chips), 041196910759 (Cheerios), or 076840100744 (Nature Valley)</small>",
        unsafe_allow_html=True)

    # Process search
    if search_button and barcode:
        with st.spinner("Searching for product..."):
            # Check if input is a barcode (numeric)
            if barcode.isdigit():
                st.info(f"Searching for barcode: {barcode}")
                product_name, brand_name, category, origin, details, image_url, allergens = data_fetcher.fetch_from_open_food_facts(
                    barcode)

                # If not found in OFF, try USDA
                if not product_name:
                    st.info("Not found in Open Food Facts, trying USDA database...")
                    product_name, brand_name, category, origin, details, image_url, allergens = data_fetcher.fetch_from_usda(
                        barcode)
            else:
                # Search by name
                st.info(f"Searching for product name: {barcode}")
                products = data_fetcher.search_products_by_name(barcode)

                if products:
                    # Display search results
                    st.success(f"Found {len(products)} products matching '{barcode}'")

                    for idx, product in enumerate(products[:5]):  # Limit to 5 results
                        col1, col2, col3 = st.columns([1, 3, 1])
                        with col1:
                            if "image_url" in product and product["image_url"]:
                                st.image(product["image_url"], width=80)
                            else:
                                st.markdown("📦")
                        with col2:
                            st.write(f"**{product.get('product_name', 'Unknown')}**")
                            st.write(f"Brand: {product.get('brands', 'Unknown')}")
                            st.write(f"Barcode: {product.get('code', 'Unknown')}")
                        with col3:
                            if st.button(f"Select", key=f"select_{idx}"):
                                # Fetch full details with the barcode
                                barcode = product.get('code', '')
                                product_name, brand_name, category, origin, details, image_url, allergens = data_fetcher.fetch_from_open_food_facts(
                                    barcode)
                                if product_name:
                                    # Create product data
                                    product_data = {
                                        "product_name": product_name,
                                        "brand_name": brand_name,
                                        "category": category,
                                        "origin": origin,
                                        "details": details,
                                        "image_url": image_url,
                                        "allergens": allergens,
                                        "barcode": barcode
                                    }
                                    st.session_state.product_data = product_data

                                    # Add to scan history
                                    if product_data not in st.session_state.scan_history:
                                        st.session_state.scan_history.append(product_data)

                                    st.experimental_rerun()
                    return
                else:
                    st.error(f"No products found matching '{barcode}'")
                    return

            if product_name:
                # Create product data
                product_data = {
                    "product_name": product_name,
                    "brand_name": brand_name,
                    "category": category,
                    "origin": origin,
                    "details": details,
                    "image_url": image_url,
                    "allergens": allergens,
                    "barcode": barcode
                }
                st.session_state.product_data = product_data

                # Add to scan history
                if product_data not in st.session_state.scan_history:
                    st.session_state.scan_history.append(product_data)
            else:
                st.error(f"No product found with barcode {barcode}")
                return

    # Display product information if available
    if st.session_state.product_data:
        display_product_information(st.session_state.product_data, regulation_db, ai_analyzer)

        chat_session(st.session_state.product_data)


def display_product_information(product_data, regulation_db, ai_analyzer):
    product_name = product_data["product_name"]
    brand_name = product_data["brand_name"]
    category = product_data["category"]
    origin = product_data["origin"]
    details = product_data["details"]
    image_url = product_data["image_url"]
    allergens = product_data["allergens"]
    barcode = product_data.get("barcode", "Unknown")

    # Check if ingredients are available
    ingredients = details.get("ingredients", "Not available")

    # Product header section
    col1, col2 = st.columns([1, 3])
    with col1:
        if image_url:
            st.image(image_url, width=200)
        else:
            st.image("https://cdn-icons-png.flaticon.com/512/1046/1046857.png", width=200)
    with col2:
        st.markdown(f"<h2 class='main-header'>{product_name}</h2>", unsafe_allow_html=True)
        st.markdown(f"<h3 class='sub-header'>Brand: {brand_name}</h3>", unsafe_allow_html=True)
        st.write(f"**Category:** {category}")
        st.write(f"**Origin:** {origin}")
        st.write(f"**Barcode:** {barcode}")

    st.header("Safety & Certification Summary")


    # Logic to determine safety and certification status
    is_safe_for_children = "Yes"  # Placeholder logic; implement actual checks
    fssai_certified = "Yes" if "FSSAI" in details.get("labels", "") else "No"
    contains_allergens = "Yes" if allergens else "No"
    banned_ingredients = regulation_db.check_against_banned_ingredients(ingredients)
    recent_recalls = regulation_db.check_product_recalls(product_name, brand_name)
    eco_score = details.get("ecoscore_grade", "Not available")
    nutri_score = details.get("nutrition_grades", "Not available")
    additives_count = len(details.get("additives_tags", []))
    serving_size = details.get("serving_size", "Not specified")

    # Check if the product contains banned ingredients
    banned_ingredients_list = [item['ingredient'] for item in banned_ingredients]
    banned_ingredients_text = ", ".join(banned_ingredients_list) if banned_ingredients_list else "None"

    # Check if there are any recent recalls
    has_recent_recalls = "Yes" if recent_recalls else "No"

    # Prepare the summary data
    safety_certifications = {
        "Is it safe for children?": ("Yes", "✅"),
        "FSSAI Certified": (fssai_certified, "✅" if fssai_certified == "Yes" else "❌"),
        "Other Certifications": (details.get("labels", "None"), "📜"),
        "Contains Allergens": (
            ", ".join(allergens) if allergens else "No allergens declared", "⚠️" if allergens else "✅"),
        "Banned Ingredients": (banned_ingredients_text, "🚫" if banned_ingredients_list else "✅"),
        "Recent Recalls": (has_recent_recalls, "🚨" if has_recent_recalls == "Yes" else "✅"),
        "Eco-Score": (eco_score, "🌱"),
        "Nutri-Score": (nutri_score, "🍏"),
        "Additives Count": (additives_count, "⚗️"),
        "Serving Size": (serving_size, "🍽️")
    }

    for key, (value, icon) in safety_certifications.items():
        st.write(f"{icon} **{key}:** {value}")
    # Display the table

    banned_products = regulation_db.check_banned_products(product_name)

    if banned_products:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.write("❌ This product has been banned or seized in the following countries:")
        for banned_product in banned_products:
            st.write(f"- **Product:** {banned_product['product']}")
            st.write(f"  - **Banned in:** {', '.join(banned_product['banned_in'])}")
            st.write(f"  - **Reason:** {banned_product['reason']}")
            st.write(f"  - **Alternatives:** {', '.join(banned_product['alternatives'])}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='success-box'>", unsafe_allow_html=True)
        st.write("✅ This product is not banned or seized in any countries.")
        st.markdown("</div>", unsafe_allow_html=True)

        # Check compliance with food packaging laws
    compliance_status = regulation_db.check_food_packaging_compliance(ingredients, st.session_state.region)

    if compliance_status["compliant"]:
        st.markdown("<div class='success-box'>", unsafe_allow_html=True)
        st.write("✅ This product complies with food packaging laws and regulations in your region.")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.write("❌ This product may not comply with food packaging laws and regulations.")
        st.write("Issues:")
        for issue in compliance_status["issues"]:
            st.write(f"- {issue}")
        st.markdown("</div>", unsafe_allow_html=True)

    # Banned ingredient check
    banned_ingredients = regulation_db.check_against_banned_ingredients(ingredients)

    if banned_ingredients:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.markdown("## ⚠️ Regulatory Alerts")
        st.markdown("This product contains ingredients banned or restricted in some regions:")
        for item in banned_ingredients:
            st.markdown(f"**{item['ingredient']}**")
            st.markdown(f"* Banned in: {', '.join(item['banned_in'])}")
            st.markdown(f"* Reason: {item['reason']}")
            st.markdown(f"* Alternatives: {', '.join(item['alternatives'])}")
        st.markdown("</div>", unsafe_allow_html=True)

    # Product recall check
    recalls = regulation_db.check_product_recalls(product_name, brand_name)
    if recalls:
        st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
        st.markdown("## 🚨 Recall Alerts")
        st.markdown("This product may be affected by recent recalls:")
        for recall in recalls:
            st.markdown(f"**Date:** {recall['date']}")
            st.markdown(f"**Reason:** {recall['reason']}")
            st.markdown(f"**Regions affected:** {', '.join(recall['regions_affected'])}")
            st.markdown(f"**Batch numbers:** {', '.join(recall['batch_numbers'])}")
        st.markdown("</div>", unsafe_allow_html=True)

    # Create tabs
    tabs = st.tabs([
        "📋 Product Details",
        "❤️ Health Analysis",
        "🌿 Environmental Impact",
        "🚫 Allergens & Sensitivities",
        "🔬 Certifications",
        "🥗 Healthier Alternatives"
    ])

    # Product Details tab
    with tabs[0]:
        st.header("Product Details")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Ingredients")
            if ingredients != "Not available":
                st.markdown(f"<div class='highlight-box'>{ingredients}</div>", unsafe_allow_html=True)
            else:
                st.info("Ingredients information not available")

        with col2:
            st.subheader("Nutritional Information")
            if "nutriments" in details and details["nutriments"]:
                nutriments = details["nutriments"]
                if "energy-kcal_100g" in nutriments:
                    st.metric("Calories (per 100g)", f"{nutriments['energy-kcal_100g']:.1f} kcal")

                metrics_to_display = [
                    ("Fat", "fat_100g", "g"),
                    ("Saturated Fat", "saturated-fat_100g", "g"),
                    ("Carbohydrates", "carbohydrates_100g", "g"),
                    ("Sugars", "sugars_100g", "g"),
                    ("Fiber", "fiber_100g", "g"),
                    ("Proteins", "proteins_100g", "g"),
                    ("Salt", "salt_100g", "g"),
                    ("Sodium", "sodium_100g", "mg", 1000)  # Convert to mg
                ]

                for label, key, unit, multiplier in [(*m, 1) if len(m) == 3 else m for m in metrics_to_display]:
                    if key in nutriments and nutriments[key] is not None:
                        value = nutriments[key] * multiplier
                        st.write(f"**{label}:** {value:.1f} {unit}")
            else:
                st.info("Nutritional information not available")

        # Additional product details
        st.subheader("Additional Information")
        col1, col2, col3 = st.columns(3)

        with col1:
            if "nutrition_grades" in details and details["nutrition_grades"]:
                nutri_score = details["nutrition_grades"].upper()
                score_color = {
                    'A': 'success-box',
                    'B': 'success-box',
                    'C': 'warning-box',
                    'D': 'warning-box',
                    'E': 'danger-box'
                }.get(nutri_score, 'highlight-box')

                st.markdown(f"<div class='{score_color}'>", unsafe_allow_html=True)
                st.metric("Nutri-Score", nutri_score)
                st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            if "nova_group" in details and details["nova_group"]:
                nova_group = details["nova_group"]
                nova_color = {
                    1: 'success-box',
                    2: 'success-box',
                    3: 'warning-box',
                    4: 'danger-box'
                }.get(nova_group, 'highlight-box')

                st.markdown(f"<div class='{nova_color}'>", unsafe_allow_html=True)
                st.metric("NOVA Group", nova_group,
                          help="NOVA classification of food processing (1: Unprocessed, 4: Ultra-processed)")
                st.markdown("</div>", unsafe_allow_html=True)

        with col3:
            if "ecoscore_grade" in details and details["ecoscore_grade"]:
                ecoscore = details["ecoscore_grade"].upper()
                eco_color = {
                    'A': 'success-box',
                    'B': 'success-box',
                    'C': 'warning-box',
                    'D': 'warning-box',
                    'E': 'danger-box'
                }.get(ecoscore, 'highlight-box')

                st.markdown(f"<div class='{eco_color}'>", unsafe_allow_html=True)
                st.metric("Eco-Score", ecoscore)
                st.markdown("</div>", unsafe_allow_html=True)

        # Additives
        if "additives_tags" in details and details["additives_tags"]:
            st.subheader("Additives")
            st.markdown(f"<div class='highlight-box'>", unsafe_allow_html=True)
            st.write(", ".join(details["additives_tags"]))
            st.markdown("</div>", unsafe_allow_html=True)

            additives_count = len(details["additives_tags"])
            if additives_count > 5:
                st.warning(f"This product contains {additives_count} additives, which is considered high.")

    # Health Analysis tab
    with tabs[1]:
        st.header("Health Analysis")

        # Display loading animation while analyzing
        with st.spinner("Analyzing health factors..."):
            health_analysis, health_rating, nutrition_metrics = ai_analyzer.analyze_product_health(
                product_name, brand_name, category, details
            )

        # Display health rating and analysis
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            health_color = ""
            if health_rating >= 7:
                health_color = "success-box"
            elif health_rating >= 4:
                health_color = "warning-box"
            else:
                health_color = "danger-box"

            st.markdown(f"<div class='{health_color}'>", unsafe_allow_html=True)
            st.metric("Health Rating", f"{health_rating:.1f}/10")
            st.markdown("</div>", unsafe_allow_html=True)

        # Display nutrition metrics
        if nutrition_metrics:
            metrics_to_display = [
                ("Calories/Serving", "calories_per_serving", "kcal"),
                ("Sugar", "sugar_content_g", "g"),
                ("Sat. Fat", "saturated_fat_g", "g"),
                ("Protein", "protein_g", "g")
            ]

            metric_cols = st.columns(len(metrics_to_display))
            for i, (label, key, unit) in enumerate(metrics_to_display):
                with metric_cols[i]:
                    if nutrition_metrics.get(key) is not None:
                        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
                        st.markdown(f"<div class='metric-value'>{nutrition_metrics[key]:.1f} {unit}</div>",
                                    unsafe_allow_html=True)
                        st.markdown(f"<div class='metric-label'>{label}</div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

        # Display full analysis
        st.markdown(health_analysis)

        # Health visualization
        if nutrition_metrics:
            st.subheader("Nutrition Analysis")

            # Create a nutrition radar chart if we have enough metrics
            valid_metrics = {k: v for k, v in nutrition_metrics.items() if v is not None}
            if len(valid_metrics) >= 3:
                # Define reference values for comparison
                reference = {
                    "calories_per_serving": 250,  # Moderate calorie content
                    "sugar_content_g": 25,  # WHO recommendation (max)
                    "saturated_fat_g": 20,  # Recommended daily limit
                    "sodium_mg": 2300,  # Recommended daily limit
                    "protein_g": 50,  # Recommended daily intake
                    "fiber_g": 25,  # Recommended daily intake
                    "additive_count": 5  # Moderate number of additives
                }

                # Prepare data for radar chart
                radar_metrics = ["calories_per_serving", "sugar_content_g", "saturated_fat_g",
                                 "sodium_mg", "protein_g", "fiber_g"]

                # Filter metrics that are available
                available_metrics = [m for m in radar_metrics if nutrition_metrics.get(m) is not None]

                if len(available_metrics) >= 3:  # Need at least 3 metrics for a meaningful radar chart
                    # Calculate percentages relative to reference values
                    percentages = []
                    labels = []

                    for metric in available_metrics:
                        value = nutrition_metrics[metric]
                        ref = reference[metric]

                        # For nutrients where higher is better
                        if metric in ["protein_g", "fiber_g"]:
                            percentage = min(100, (value / ref) * 100)  # Cap at 100%
                        else:  # For nutrients where lower is better
                            percentage = max(0, 100 - ((value / ref) * 100))  # Min 0%, lower is worse

                        percentages.append(percentage)
                        # Format label
                        label = metric.replace("_", " ").replace("content", "").replace("per serving", "")
                        label = " ".join(word.capitalize() for word in label.split())
                        labels.append(label)

                    # Create radar chart
                    fig = go.Figure()

                    fig.add_trace(go.Scatterpolar(
                        r=percentages,
                        theta=labels,
                        fill='toself',
                        name='Product',
                        line_color='#1E88E5'
                    ))

                    fig.update_layout(
                        polar=dict(
                            radialaxis=dict(
                                visible=True,
                                range=[0, 100]
                            )
                        ),
                        showlegend=False,
                        title="Nutritional Quality (Higher % is Better)"
                    )

                    st.plotly_chart(fig, use_container_width=True)

            # Create a horizontal bar chart for additives count
            if nutrition_metrics.get("additive_count") is not None:
                additive_count = nutrition_metrics["additive_count"]
                fig = go.Figure()

                # Define thresholds
                thresholds = [
                    {"value": 0, "color": "#4CAF50", "label": "None (Best)"},
                    {"value": 3, "color": "#8BC34A", "label": "Low"},
                    {"value": 5, "color": "#FFEB3B", "label": "Moderate"},
                    {"value": 8, "color": "#FF9800", "label": "High"},
                    {"value": 10, "color": "#F44336", "label": "Very High (Concern)"}
                ]

                # Find the right color based on the count
                color = "#F44336"  # Default to red (worst)
                for threshold in reversed(thresholds):
                    if additive_count >= threshold["value"]:
                        color = threshold["color"]
                        break

                fig.add_trace(go.Bar(
                    x=[additive_count],
                    y=["Additives"],
                    orientation='h',
                    marker_color=color,
                    text=[f"{additive_count}"],
                    textposition='outside'
                ))

                # Add reference lines and zones
                for i in range(len(thresholds) - 1):
                    fig.add_shape(
                        type="line",
                        x0=thresholds[i + 1]["value"],
                        y0=-0.4,
                        x1=thresholds[i + 1]["value"],
                        y1=0.4,
                        line=dict(color="gray", width=1, dash="dot")
                    )

                fig.update_layout(
                    title="Additives Count",
                    xaxis=dict(
                        title="Number of Additives",
                        range=[0, max(15, additive_count + 2)]
                    ),
                    yaxis=dict(showticklabels=False),
                    height=200,
                    margin=dict(l=20, r=20, t=40, b=20)
                )

                # Add annotations for thresholds
                annotations = []
                for threshold in thresholds:
                    annotations.append(dict(
                        x=threshold["value"],
                        y=0.5,
                        xref="x",
                        yref="y",
                        text=threshold["label"],
                        showarrow=False,
                        font=dict(size=10),
                        textangle=-90,
                        xanchor="center",
                        yanchor="bottom"
                    ))

                fig.update_layout(annotations=annotations)
                st.plotly_chart(fig, use_container_width=True)

    # Environmental Impact tab
    with tabs[2]:
        st.header("Environmental Impact Analysis")

        with st.spinner("Analyzing environmental impact..."):
            env_analysis, env_rating = ai_analyzer.analyze_environmental_impact(
                product_name, brand_name, details
            )

        # Display environmental rating
        col1, col2 = st.columns([1, 3])
        with col1:
            env_color = ""
            if env_rating >= 7:
                env_color = "success-box"
            elif env_rating >= 4:
                env_color = "warning-box"
            else:
                env_color = "danger-box"

            st.markdown(f"<div class='{env_color}'>", unsafe_allow_html=True)
            st.metric("Environmental Impact Score", f"{env_rating:.1f}/10")
            st.markdown("</div>", unsafe_allow_html=True)

        # Display packaging info if available
        if "packaging" in details and details["packaging"] != "Not specified":
            st.subheader("Packaging")
            st.info(details["packaging"])

        # Display full environmental analysis
        st.markdown(env_analysis)

    # Allergens tab
    # Allergens tab
    with tabs[3]:
        st.header("Allergens & Sensitivities")

        # List known allergens
        if allergens:
            st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
            st.subheader("⚠️ Contains the following allergens:")
            for allergen in allergens:
                st.write(f"- {allergen.capitalize()}")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='success-box'>", unsafe_allow_html=True)
            st.subheader("✅ No allergens declared")
            st.write("However, always check the packaging for the most up-to-date information.")
            st.markdown("</div>", unsafe_allow_html=True)

        # AI allergen analysis
        with st.spinner("Analyzing potential allergen risks..."):
            allergen_analysis = ai_allergen_analysis = ai_analyzer.analyze_allergen_risks(
                product_name, ingredients, allergens, ingredients
            )

        st.markdown(allergen_analysis)

    # Display potential cross-contamination warnings
    if "traces" in details and details["traces"]:
        st.markdown("<div class='warning-box'>", unsafe_allow_html=True)
        st.subheader("⚠️ May contain traces of:")
        traces = details["traces"].split(",")
        for trace in traces:
            st.write(f"- {trace.strip().capitalize()}")
        st.markdown("</div>", unsafe_allow_html=True)

    # Certifications tab
    with tabs[4]:
        st.header("Certifications & Standards")

        # Extract certifications from the product details
        certifications = []
        if "labels" in details and details["labels"]:
            certifications = details["labels"].split(",")

        if certifications:
            st.subheader("Product Certifications")
            for cert in certifications:
                st.write(f"- {cert.strip()}")
        else:
            st.info("No certification information available for this product.")

        # Display regulatory compliance based on region
        st.subheader(f"Regulatory Compliance ({st.session_state.region})")

        # Check compliance status
        compliance_status = regulation_db.check_compliance(ingredients, st.session_state.region)

        if compliance_status["compliant"]:
            st.markdown("<div class='success-box'>", unsafe_allow_html=True)
            st.write("✅ This product appears to comply with local regulations")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='danger-box'>", unsafe_allow_html=True)
            st.write("❌ This product may not comply with local regulations")
            st.write("Issues:")
            for issue in compliance_status["issues"]:
                st.write(f"- {issue}")
            st.markdown("</div>", unsafe_allow_html=True)

    # Healthier Alternatives tab
    with tabs[5]:
        st.header("Healthier Alternatives")

        with st.spinner("Generating healthier alternatives..."):
            healthier_alternatives = ai_analyzer.generate_healthier_recipes(
                product_name, category, ingredients
            )

        st.markdown(healthier_alternatives)

        # Additional recommendations based on category
        st.subheader("Similar Products (Higher Health Rating)")
        st.info("This feature is coming soon. We'll recommend healthier commercial alternatives to this product.")


def load_css():
    st.markdown("""
    <style>
    .main-header {
        color: #059669;
        font-weight: 600;
    }

    .sub-header {
        color: #424242;
        font-weight: 400;
    }

    .highlight-box {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }

    .success-box {
        background-color: #E8F5E9;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #4CAF50;
        margin-bottom: 10px;
    }

    .warning-box {
        background-color: #FFF8E1;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #FFC107;
        margin-bottom: 10px;
    }

    .danger-box {
        background-color: #FFEBEE;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #F44336;
        margin-bottom: 10px;
    }

    .metric-card {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
        text-align: center;
        margin-bottom: 10px;
    }

    .metric-value {
        font-size: 24px;
        font-weight: 600;
        color: #1E88E5;
    }

    .metric-label {
        font-size: 14px;
        color: #616161;
    }
    </style>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()