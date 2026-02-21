import os
import json
import requests
import streamlit as st
from bs4 import BeautifulSoup
import re
import google.generativeai as genai

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


# Function to extract data from a URL
def extract_data_from_url(url):
    """
    Extract product information from a given URL
    Returns a dictionary with product name, ingredients, and description
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Initialize data with empty values
        product_data = {
            'product_name': '',
            'ingredients': '',
            'description': '',
            'brand': '',
            'extraction_success': False,
            'message': ''
        }

        # Try to extract product name (common patterns)
        product_name_elements = soup.select(
            'h1.product-name, h1.product-title, h1.product, div.product-title h1, span.product-title')
        if product_name_elements:
            product_data['product_name'] = product_name_elements[0].get_text().strip()

        # Try to extract ingredients (common patterns)
        ingredients_elements = soup.select('div.ingredients, div.product-ingredients, div.ingredients-list, section.ingredients, div[data-ingredients]')
        for element in ingredients_elements:
            text = element.get_text().strip()
            if "ingredient" in text.lower():
                # Extract ingredients from the text content
                ingredients_match = re.search(r'ingredients:?\s*(.*)', text, re.IGNORECASE)
                if ingredients_match:
                    product_data['ingredients'] = ingredients_match.group(1).strip()
                else:
                    product_data['ingredients'] = text
                break

        # Try to extract product description
        description_elements = soup.select('div.product-description, div.description, p.product-description, div.product-details')
        if description_elements:
            product_data['description'] = description_elements[0].get_text().strip()

        # Try to extract brand information
        brand_elements = soup.select('div.brand, span.brand, a.brand')
        if brand_elements:
            product_data['brand'] = brand_elements[0].get_text().strip()

        # Check if we extracted any useful information
        if product_data['product_name'] or product_data['ingredients']:
            product_data['extraction_success'] = True
        product_data['message'] = "Successfully extracted product information"
        else:
        product_data['message'] = "Could not extract product information from this URL"

        return product_data

    except requests.exceptions.RequestException as e:
        return {
            'product_name': '',
            'ingredients': '',
            'description': '',
            'brand': '',
            'extraction_success': False,
            'message': f"Error accessing URL: {str(e)}"
        }
    except Exception as e:
        return {
            'product_name': '',
            'ingredients': '',
            'description': '',
            'brand': '',
            'extraction_success': False,
            'message': f"An error occurred: {str(e)}"
        }


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

    def load_banned_products(self):
        with open(self.banned_products_file, 'r') as f:
            return json.load(f)

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


# Example usage in a Streamlit interface
def url_extraction_interface():
    st.header("Extract Product Data from URL")

    url = st.text_input("Enter product URL", placeholder="https://example.com/product")

    if st.button("Extract Data"):
        with st.spinner("Extracting data from URL..."):
            product_data = extract_data_from_url(url)

            if product_data['extraction_success']:
                st.success(product_data['message'])

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Product Details")
                    st.write(f"**Product Name:** {product_data['product_name']}")
                    if product_data['brand']:
                        st.write(f"**Brand:** {product_data['brand']}")
                    if product_data['description']:
                        st.write("**Description:**")
                        st.write(product_data['description'])

                with col2:
                    st.subheader("Ingredients")
                    if product_data['ingredients']:
                        st.write(product_data['ingredients'])
                    else:
                        st.info("No ingredients information found")

                # Now you can use the extracted data with your existing functions
                reg_db = RegulationDatabase()
                if product_data['ingredients']:
                    st.subheader("Regulatory Compliance")
                    compliance = reg_db.check_compliance(product_data['ingredients'], "United States")
                    if compliance["compliant"]:
                        st.markdown('<div class="success-box">✅ No compliance issues found</div>',
                                    unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="danger-box">⚠️ Compliance issues detected</div>',
                                    unsafe_allow_html=True)
                        for issue in compliance["issues"]:
                            st.write(f"- {issue}")
            else:
                st.error(product_data['message'])
                st.info("Try entering product information manually instead.")


# You can integrate this function into your main app flow
def main():
    load_css()
    st.title("Product Health & Safety Analyzer")

    # Add tabs for different functionalities
    tabs = st.tabs(["URL Analysis", "Manual Entry", "Database Search"])

    with tabs[0]:
        url_extraction_interface()

    with tabs[1]:
        st.header("Manual Product Analysis")
        # Your existing manual entry code here

    with tabs[2]:
        st.header("Database Search")
        # Your existing database search code here


if __name__ == "__main__":
    main()