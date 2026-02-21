import streamlit as st
from PIL import Image
import google.generativeai as genai
import io
import logging
from datetime import datetime
import pandas as pd
import plotly.express as px

class AppConfig:
    # Default/fallback model; _configure_gemini will try a fallback if unavailable
    GEMINI_MODEL = "gemini-2.5-flash"
    SUPPORTED_IMAGE_TYPES = ["jpg", "jpeg", "png"]
    MAX_IMAGE_SIZE = (800, 800)

    @staticmethod
    def get_api_key():
        """
        Get Gemini API key from (in order):
        1. Streamlit secrets
        2. Environment variable GEMINI_API_KEY
        3. Hardcoded fallback (local/dev only – replace/remove for production)
        """
        # 1) Streamlit secrets (if configured)
        try:
            if hasattr(st, "secrets") and st.secrets:
                key = st.secrets.get("GEMINI_API_KEY", None)
                if key:
                    return key
        except Exception:
            pass

        # 2) Environment variable
        import os
        from dotenv import load_dotenv
        load_dotenv()

        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            return env_key

        # 3) No key found
        return None

    # Enhanced configuration
    NUTRITION_THRESHOLDS = {
        "calories": {"low": 100, "medium": 300, "high": 500},
        "sugar": {"low": 5, "medium": 15, "high": 25},
        "protein": {"low": 5, "medium": 15, "high": 25},
        "sodium": {"low": 140, "medium": 400, "high": 700},  # Added sodium thresholds
        "saturated_fat": {"low": 2, "medium": 5, "high": 10},  # Added saturated fat thresholds
        "fiber": {"low": 2, "medium": 5, "high": 10},  # Added fiber thresholds
    }

    # Added food processing levels with descriptions
    PROCESSING_LEVELS = {
        "Unprocessed": "Natural foods with no processing",
        "Minimally processed": "Basic processes like washing, cutting, drying",
        "Processed": "Manufactured with salt, sugar, oil or other additives",
        "Highly processed": "Ultra-processed foods with numerous industrial ingredients"
    }

    # Added health impact scale
    HEALTH_IMPACT = {
        "Very Beneficial": "Substantial positive health effects",
        "Beneficial": "Moderate positive health effects",
        "Neutral": "Neither beneficial nor harmful",
        "Concerning": "Some potentially negative health effects",
        "Harmful": "Significant potentially negative health effects"
    }


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('app.log')
        ]
    )
    return logging.getLogger(__name__)


class FoodLabelAnalyzerApp:
    def __init__(self):
        self.config = AppConfig()
        self.logger = setup_logging()
        self._initialize_session_state()
        self._configure_gemini()

    def _configure_gemini(self):
        # Get API key from session state if user entered it, otherwise try config sources
        api_key = st.session_state.get('user_api_key', None) or self.config.get_api_key()
        
        if not api_key:
            # Show API key input in sidebar
            with st.sidebar:
                st.error("⚠️ Gemini API Key Required")
                st.markdown("""
                **To use this app, you need a Gemini API key:**
                1. Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
                2. Enter it below or set it as environment variable `GEMINI_API_KEY`
                """)
                user_key = st.text_input(
                    "Enter your Gemini API Key:",
                    type="password",
                    key="api_key_input",
                    help="Your API key will be stored in session only"
                )
                if user_key:
                    st.session_state.user_api_key = user_key
                    api_key = user_key
                    st.success("✅ API key saved for this session!")
                    st.rerun()
                else:
                    st.stop()
        
        try:
            genai.configure(api_key=api_key)
            # Test if model is available
            try:
                test_model = genai.GenerativeModel(self.config.GEMINI_MODEL)
                self.logger.info(f"Gemini API configured successfully with model: {self.config.GEMINI_MODEL}")
            except Exception as model_error:
                self.logger.warning(f"Model {self.config.GEMINI_MODEL} may not be available: {model_error}")
                # Try fallback model
                self.config.GEMINI_MODEL = "gemini-1.5-flash"
                try:
                    test_model = genai.GenerativeModel(self.config.GEMINI_MODEL)
                    self.logger.info(f"Using fallback model: {self.config.GEMINI_MODEL}")
                except Exception as fallback_error:
                    self.logger.error(f"Fallback model also failed: {fallback_error}")
                    st.error(f"Failed to initialize model. Error: {str(fallback_error)}")
                    st.info("Please check your API key is valid and has access to Gemini models.")
                    st.stop()
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Failed to configure Gemini API: {e}")
            if "API_KEY" in error_msg or "invalid" in error_msg.lower():
                st.error("❌ Invalid API Key. Please check your Gemini API key.")
                st.info("Get your API key from: https://makersuite.google.com/app/apikey")
                # Clear invalid key from session
                if 'user_api_key' in st.session_state:
                    del st.session_state.user_api_key
            else:
                st.error(f"Failed to initialize AI services: {error_msg}")
            st.stop()

    def _initialize_session_state(self):
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'analysis_results' not in st.session_state:
            st.session_state.analysis_results = None
        if 'analysis_data' not in st.session_state:
            st.session_state.analysis_data = {}
        if 'user_preferences' not in st.session_state:
            st.session_state.user_preferences = {
                'dietary': [],
                'allergies': [],
                'health_goals': [],
                'health_conditions': []  # Added health conditions preference
            }
        if 'last_analysis_time' not in st.session_state:
            st.session_state.last_analysis_time = None
        if 'question_response' not in st.session_state:
            st.session_state.question_response = ""
        if 'current_question' not in st.session_state:
            st.session_state.current_question = ""
        if 'trends' not in st.session_state:
            st.session_state.trends = []  # Add tracking for historical analyses
        if 'warnings' not in st.session_state:
            st.session_state.warnings = []  # Add warnings about food

    def render_sidebar(self):
        with st.sidebar:
            # API Key management section
            if not self.config.get_api_key() and not st.session_state.get('user_api_key'):
                st.warning("⚠️ API Key Required")
                api_key = st.text_input(
                    "Enter Gemini API Key:",
                    type="password",
                    key="sidebar_api_key",
                    help="Get your key from https://makersuite.google.com/app/apikey"
                )
                if api_key:
                    st.session_state.user_api_key = api_key
                    st.success("✅ API key saved!")
                    st.rerun()
                st.markdown("---")
            
            st.header("👤 User Preferences")

            # User profile
            with st.expander("📋 Profile Information", expanded=False):
                st.text_input("Name (optional)", key="user_name")
                st.selectbox("Age Group",
                             ["", "Child (<12)", "Teen (13-19)", "Adult (20-40)",
                              "Middle Age (41-65)", "Senior (65+)"])
                st.radio("Gender", ["", "Male", "Female", "Other"])
                st.number_input("Weight (kg)", min_value=0, max_value=300, step=1)
                st.number_input("Height (cm)", min_value=0, max_value=250, step=1)

            # Dietary Preferences
            st.subheader("🥗 Dietary Preferences")
            dietary = st.multiselect(
                "Select your diet:",
                ["Vegetarian", "Vegan", "Keto", "Paleo", "Gluten-free", "Dairy-free",
                 "Low Carb", "Low Fat", "Mediterranean", "DASH", "Pescatarian", "Flexitarian"],
                default=st.session_state.user_preferences['dietary']
            )

            # Allergies
            st.subheader("⚠ Allergies")
            allergies = st.multiselect(
                "Select allergies:",
                ["Nuts", "Peanuts", "Tree Nuts", "Dairy", "Lactose", "Gluten",
                 "Shellfish", "Eggs", "Soy", "Fish", "Wheat", "Sesame", "Sulfites"],
                default=st.session_state.user_preferences['allergies']
            )

            # Health Goals
            st.subheader("🎯 Health Goals")
            health_goals = st.multiselect(
                "Select your health goals:",
                ["Weight Loss", "Weight Maintenance", "Muscle Gain", "Heart Health",
                 "Blood Sugar Control", "Reduce Cholesterol", "Energy Boost",
                 "Better Sleep", "Gut Health", "Brain Health", "Hydration"],
                default=st.session_state.user_preferences['health_goals']
            )

            # Health Conditions
            st.subheader("🏥 Health Conditions")
            health_conditions = st.multiselect(
                "Select any health conditions:",
                ["Diabetes", "Hypertension", "Heart Disease", "Kidney Disease",
                 "GERD/Acid Reflux", "IBS", "Celiac Disease", "Inflammatory Conditions",
                 "Hypercholesterolemia", "Thyroid Issues"],
                default=st.session_state.user_preferences.get('health_conditions', [])
            )

            st.session_state.user_preferences = {
                'dietary': dietary,
                'allergies': allergies,
                'health_goals': health_goals,
                'health_conditions': health_conditions
            }

            # Export data option
            if st.button("Export My Data"):
                self._export_user_data()

    def _export_user_data(self):
        # Function to allow users to export their data and analysis history
        try:
            data = {
                "preferences": st.session_state.user_preferences,
                "analysis_history": st.session_state.trends
            }

            # Create CSV for download
            df = pd.DataFrame(st.session_state.trends)
            if not df.empty:
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download Analysis History",
                    data=csv,
                    file_name=f"food_analysis_history_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No analysis history to export yet.")
        except Exception as e:
            self.logger.error(f"Export error: {e}")
            st.error("Failed to export data.")

    def analyze_food_image(self, image):
        try:
            # Convert RGBA to RGB if necessary (JPEG doesn't support alpha channel)
            if image.mode == 'RGBA':
                # Create a white background
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
                image = rgb_image
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if image is too large
            max_size = self.config.MAX_IMAGE_SIZE
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=85)
            img_bytes = img_byte_arr.getvalue()

            # Get API key from session state if available
            api_key = st.session_state.get('user_api_key', None) or self.config.get_api_key()
            if api_key:
                genai.configure(api_key=api_key)
            
            model = genai.GenerativeModel(self.config.GEMINI_MODEL)

            # Enhanced prompt incorporating user preferences and structured output
            preferences = st.session_state.user_preferences
            
            # Build dietary compliance section
            dietary_items = []
            for diet in preferences.get('dietary', []):
                dietary_items.append(f'    "{diet}": "Compatible/Incompatible with reasons"')
            dietary_section = ',\n'.join(dietary_items) if dietary_items else ''
            if dietary_section:
                dietary_section += ',\n'
            
            # Build allergy risks section
            allergy_items = []
            for allergy in preferences.get('allergies', []):
                allergy_items.append(f'    "{allergy}": "Safe/Unsafe with explanation"')
            allergy_section = ',\n'.join(allergy_items) if allergy_items else ''
            if allergy_section:
                allergy_section += ',\n'
            
            # Build health impact section
            health_goal_items = []
            for goal in preferences.get('health_goals', []):
                health_goal_items.append(f'    "{goal}": "Positive/Neutral/Negative with explanation"')
            
            health_condition_items = []
            for condition in preferences.get('health_conditions', []):
                health_condition_items.append(f'    "{condition}": "Safe/Caution/Avoid with explanation"')
            
            health_items = health_goal_items + health_condition_items
            health_section = ',\n'.join(health_items) if health_items else ''
            if health_section:
                health_section += ',\n'
            
            prompt = (
                "Analyze this food image and provide detailed information in the following JSON format structure. "
                "The values should be as accurate as possible for numerical data, include units when appropriate. "
                "Please structure your response like this (with your actual analysis values):\n\n"
                "```json\n"
                "{\n"
                "  \"name\": \"Food Name\",\n"
                "  \"nutrition\": {\n"
                "    \"calories\": \"X kcal\",\n"
                "    \"protein\": \"X g\",\n"
                "    \"carbs\": \"X g\",\n"
                "    \"sugars\": \"X g\",\n"
                "    \"fats\": {\n"
                "      \"total\": \"X g\",\n"
                "      \"saturated\": \"X g\",\n"
                "      \"trans\": \"X g\",\n"
                "      \"unsaturated\": \"X g\"\n"
                "    },\n"
                "    \"fiber\": \"X g\",\n"
                "    \"sodium\": \"X mg\",\n"
                "    \"cholesterol\": \"X mg\",\n"
                "    \"vitamins\": [\"list significant vitamins\"],\n"
                "    \"minerals\": [\"list significant minerals\"]\n"
                "  },\n"
                "  \"ingredients\": [\"main ingredients\"],\n"
                "  \"additives\": [\"food additives or E-numbers if present\"],\n"
                "  \"allergens\": [\"potential allergens\"],\n"
                "  \"servingSize\": \"X g/ml\",\n"
                "  \"processingLevel\": \"one of: Unprocessed, Minimally processed, Processed, Highly processed\",\n"
                "  \"nutritionalScore\": \"A to E (Nutri-Score rating if applicable)\",\n"
                "  \"dietaryCompliance\": {\n"
                f"{dietary_section}"
                "    \"generalAssessment\": \"Overall dietary assessment\"\n"
                "  },\n"
                "  \"allergyRisks\": {\n"
                f"{allergy_section}"
                "    \"crossContamination\": \"Possible cross-contamination risks\"\n"
                "  },\n"
                "  \"healthImpact\": {\n"
                f"{health_section}"
                "    \"overallImpact\": \"Very Beneficial/Beneficial/Neutral/Concerning/Harmful\"\n"
                "  },\n"
                "  \"sustainability\": {\n"
                "    \"packaging\": \"Sustainability of packaging\",\n"
                "    \"carbonFootprint\": \"Estimated impact\",\n"
                "    \"waterUsage\": \"Estimated impact\"\n"
                "  },\n"
                "  \"storageAndPreparation\": {\n"
                "    \"storage\": \"Storage recommendations\",\n"
                "    \"shelfLife\": \"Expected shelf life\",\n"
                "    \"preparation\": \"Preparation suggestions\"\n"
                "  },\n"
                "  \"warnings\": [\"list any important warnings\"],\n"
                "  \"recommendations\": [\"personalized recommendations\"]\n"
                "}\n"
                "```\n\n"
                "If you cannot determine an exact value for any field, provide your best estimate and indicate this. "
                "Focus on accuracy rather than completeness if information is limited."
            )

            # Generate content with proper error handling
            try:
                response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
            except Exception as api_error:
                self.logger.error(f"Gemini API error: {api_error}")
                return f"API Error: {str(api_error)}. Please check your API key and try again."

            # Check response
            if not response:
                self.logger.error("No response from Gemini API")
                return "No response received from the AI service. Please try again."
            
            # Handle different response formats
            if hasattr(response, 'text') and response.text:
                response_text = response.text
            elif hasattr(response, 'parts') and response.parts:
                # Try to extract text from parts
                response_text = ""
                for part in response.parts:
                    if hasattr(part, 'text'):
                        response_text += part.text
                if not response_text:
                    self.logger.error("Response has parts but no text content")
                    return "Received response but could not extract text. Please try again."
            else:
                self.logger.error(f"Unexpected response format: {type(response)}")
                return "Unexpected response format from AI service. Please try again."

            if response_text:
                try:
                    # Extract JSON data (looking for JSON within ```json ``` blocks if present)
                    analysis_text = response_text
                    import json
                    import re

                    # Try to find JSON block
                    json_match = re.search(r'```json\s*(.*?)\s*```', analysis_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        # If no JSON code block found, assume the entire response might be JSON
                        json_str = analysis_text

                    # Clean up the string by removing any non-JSON elements (but preserve essential JSON characters)
                    # Remove markdown code block markers if present
                    cleaned_json_str = json_str.strip()
                    # Remove any leading/trailing markdown code block syntax
                    cleaned_json_str = re.sub(r'^```json\s*', '', cleaned_json_str, flags=re.IGNORECASE)
                    cleaned_json_str = re.sub(r'\s*```$', '', cleaned_json_str)
                    cleaned_json_str = cleaned_json_str.strip()
                    
                    # Try to parse JSON
                    try:
                        analysis_data = json.loads(cleaned_json_str)
                    except json.JSONDecodeError as json_err:
                        # If JSON parsing fails, try to extract JSON object more carefully
                        self.logger.warning(f"Initial JSON parse failed: {json_err}, attempting recovery...")
                        # Try to find the first { and last } to extract JSON object
                        first_brace = cleaned_json_str.find('{')
                        last_brace = cleaned_json_str.rfind('}')
                        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                            json_candidate = cleaned_json_str[first_brace:last_brace + 1]
                            try:
                                analysis_data = json.loads(json_candidate)
                            except json.JSONDecodeError:
                                raise json_err
                        else:
                            raise json_err

                    # Store structured data
                    st.session_state.analysis_data = analysis_data

                    # Store full text
                    st.session_state.analysis_results = analysis_text

                    # Create markdown for display
                    markdown_result = self._create_markdown_from_json(analysis_data)

                    # Add to trends
                    self._add_to_trends(analysis_data)

                    # Extract warnings
                    if "warnings" in analysis_data and analysis_data["warnings"]:
                        st.session_state.warnings = analysis_data["warnings"]

                    st.session_state.last_analysis_time = datetime.now()
                    return markdown_result
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON parsing error: {e}")
                    self.logger.error(f"Failed to parse JSON. Raw response: {analysis_text[:500]}...")
                    # Fallback to text display if JSON parsing fails
                    st.session_state.analysis_results = analysis_text
                    st.session_state.last_analysis_time = datetime.now()
                    # Try to create a basic markdown display from the text
                    return f"## Food Analysis Results\n\n{analysis_text}\n\n*Note: Full structured analysis could not be parsed, but here's the raw response.*"
            else:
                self.logger.error("No response text available")
                return "No analysis result received from the AI service."

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Image analysis error: {error_msg}")
            self.logger.exception("Full error traceback:")
            # Provide more helpful error messages
            if "RGBA" in error_msg or "JPEG" in error_msg:
                return f"Image format error: {error_msg}. Please try uploading a different image."
            elif "API" in error_msg or "key" in error_msg.lower():
                return f"API configuration error: {error_msg}. Please check your API key."
            else:
                return f"Error analyzing image: {error_msg}. Please try again with a clearer image."

    def _create_markdown_from_json(self, data):
        """Convert the structured analysis data to a formatted markdown display"""
        try:
            md = f"# {data.get('name', 'Food Analysis Results')}\n\n"

            # Create nutritional table
            md += "## 📊 Nutritional Information\n\n"
            md += "| Nutrient | Amount | % Daily Value* |\n"
            md += "|----------|--------|---------------|\n"

            nutrition = data.get('nutrition', {})
            md += f"| Calories | {nutrition.get('calories', 'N/A')} | |\n"
            md += f"| Protein | {nutrition.get('protein', 'N/A')} | |\n"
            md += f"| Carbohydrates | {nutrition.get('carbs', 'N/A')} | |\n"
            md += f"| Sugars | {nutrition.get('sugars', 'N/A')} | |\n"

            fats = nutrition.get('fats', {})
            md += f"| Total Fat | {fats.get('total', 'N/A')} | |\n"
            md += f"| Saturated Fat | {fats.get('saturated', 'N/A')} | |\n"
            md += f"| Trans Fat | {fats.get('trans', 'N/A')} | |\n"
            md += f"| Unsaturated Fat | {fats.get('unsaturated', 'N/A')} | |\n"

            md += f"| Fiber | {nutrition.get('fiber', 'N/A')} | |\n"
            md += f"| Sodium | {nutrition.get('sodium', 'N/A')} | |\n"
            md += f"| Cholesterol | {nutrition.get('cholesterol', 'N/A')} | |\n"
            md += "\n*Percent Daily Values based on a 2,000 calorie diet\n\n"

            # Ingredients and additives
            md += "## 🍲 Ingredients & Additives\n\n"
            ingredients = data.get('ingredients', [])
            if ingredients:
                md += "### Ingredients\n"
                for ingredient in ingredients:
                    md += f"- {ingredient}\n"
                md += "\n"

            additives = data.get('additives', [])
            if additives:
                md += "### Additives\n"
                for additive in additives:
                    md += f"- {additive}\n"
                md += "\n"

            # Allergen information
            md += "## ⚠️ Allergen Information\n\n"
            allergens = data.get('allergens', [])
            if allergens:
                md += "### Identified Allergens\n"
                for allergen in allergens:
                    md += f"- {allergen}\n"
                md += "\n"

            allergy_risks = data.get('allergyRisks', {})
            if allergy_risks:
                md += "### Allergy Assessment\n"
                md += "| Allergen | Status | Notes |\n"
                md += "|----------|--------|-------|\n"
                for allergen, status in allergy_risks.items():
                    if allergen != "crossContamination":
                        md += f"| {allergen} | {status} |\n"
                if "crossContamination" in allergy_risks:
                    md += f"\n**Cross-contamination risk**: {allergy_risks['crossContamination']}\n\n"

            # Dietary compliance
            md += "## 🥗 Dietary Compliance\n\n"
            dietary = data.get('dietaryCompliance', {})
            if dietary:
                md += "| Diet | Compatibility | \n"
                md += "|------|---------------|\n"
                for diet, compliance in dietary.items():
                    if diet != "generalAssessment":
                        md += f"| {diet} | {compliance} |\n"
                if "generalAssessment" in dietary:
                    md += f"\n**Overall assessment**: {dietary['generalAssessment']}\n\n"

            # Health impact
            md += "## 💚 Health Impact\n\n"
            health = data.get('healthImpact', {})
            if health:
                if "overallImpact" in health:
                    overall = health["overallImpact"]
                    color = {
                        "Very Beneficial": "🟢",
                        "Beneficial": "🟢",
                        "Neutral": "🟡",
                        "Concerning": "🟠",
                        "Harmful": "🔴"
                    }.get(overall, "⚪")
                    md += f"**Overall health impact**: {color} {overall}\n\n"

                md += "| Health Factor | Impact |\n"
                md += "|--------------|--------|\n"
                for factor, impact in health.items():
                    if factor not in ["overallImpact"]:
                        md += f"| {factor} | {impact} |\n"
                md += "\n"

            # Serving and processing
            md += "## ℹ️ Additional Information\n\n"
            md += f"**Serving size**: {data.get('servingSize', 'Not specified')}\n"
            md += f"**Processing level**: {data.get('processingLevel', 'Not specified')}\n"
            md += f"**Nutritional score**: {data.get('nutritionalScore', 'Not available')}\n\n"

            # Storage and preparation
            storage = data.get('storageAndPreparation', {})
            if storage:
                md += "### Storage & Preparation\n"
                md += f"- **Storage**: {storage.get('storage', 'Not specified')}\n"
                md += f"- **Shelf life**: {storage.get('shelfLife', 'Not specified')}\n"
                md += f"- **Preparation**: {storage.get('preparation', 'Not specified')}\n\n"

            # Sustainability
            sustainability = data.get('sustainability', {})
            if sustainability:
                md += "### Sustainability\n"
                md += f"- **Packaging**: {sustainability.get('packaging', 'Not evaluated')}\n"
                md += f"- **Carbon footprint**: {sustainability.get('carbonFootprint', 'Not evaluated')}\n"
                md += f"- **Water usage**: {sustainability.get('waterUsage', 'Not evaluated')}\n\n"

            # Warnings (highlighted)
            warnings = data.get('warnings', [])
            if warnings:
                md += "## ⛔ Important Warnings\n\n"
                for warning in warnings:
                    md += f"- ⚠️ **{warning}**\n"
                md += "\n"

            # Recommendations
            recommendations = data.get('recommendations', [])
            if recommendations:
                md += "## 💡 Personalized Recommendations\n\n"
                for rec in recommendations:
                    md += f"- {rec}\n"

            return md

        except Exception as e:
            self.logger.error(f"Markdown creation error: {e}")
            return "Error formatting analysis results."

    def _add_to_trends(self, analysis_data):
        """Add the current analysis to the user's trends history"""
        try:
            if not analysis_data:
                return

            # Extract key metrics for trending
            trend_item = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "food": analysis_data.get("name", "Unknown"),
                "calories": self._extract_numeric_value(analysis_data.get("nutrition", {}).get("calories", "0")),
                "protein": self._extract_numeric_value(analysis_data.get("nutrition", {}).get("protein", "0")),
                "carbs": self._extract_numeric_value(analysis_data.get("nutrition", {}).get("carbs", "0")),
                "fat": self._extract_numeric_value(
                    analysis_data.get("nutrition", {}).get("fats", {}).get("total", "0")),
                "processing_level": analysis_data.get("processingLevel", "Unknown"),
                "health_impact": analysis_data.get("healthImpact", {}).get("overallImpact", "Unknown")
            }

            st.session_state.trends.append(trend_item)

            # Keep only the last 20 items
            if len(st.session_state.trends) > 20:
                st.session_state.trends = st.session_state.trends[-20:]

        except Exception as e:
            self.logger.error(f"Trend tracking error: {e}")

    def _extract_numeric_value(self, value_str):
        """Extract numeric value from strings like '150 kcal' or '20 g'"""
        try:
            import re
            match = re.search(r'(\d+\.?\d*)', str(value_str))
            if match:
                return float(match.group(1))
            return 0
        except:
            return 0

    def render_analysis_section(self):
        st.header("📸 Food Image Analysis")

        col1, col2 = st.columns([2, 1])

        with col1:
            uploaded_file = st.file_uploader(
                "Upload food image for analysis",
                type=self.config.SUPPORTED_IMAGE_TYPES,
                help="Upload a clear image of your food item or its label"
            )

            if uploaded_file:
                image = Image.open(uploaded_file)
                st.image(image, caption="Uploaded Food Image", use_container_width=True)

                if st.button("🔍 Analyze Food", type="primary"):
                    with st.spinner("Analyzing your food..."):
                        analysis_result = self.analyze_food_image(image)
                        st.success("Analysis Complete!")

                        # Show immediate warnings if any
                        if st.session_state.warnings:
                            with st.expander("⚠️ IMPORTANT WARNINGS", expanded=True):
                                for warning in st.session_state.warnings:
                                    st.warning(warning)

                        # Display analysis table
                        st.markdown(analysis_result)

        with col2:
            if st.session_state.last_analysis_time:
                st.info(f"Last analysis: {st.session_state.last_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")

            if st.session_state.analysis_data:
                # Quick summary card
                with st.container():
                    st.subheader("🔔 Quick Summary")

                    # Get data for summary
                    name = st.session_state.analysis_data.get('name', 'This food')
                    health_impact = st.session_state.analysis_data.get('healthImpact', {}).get('overallImpact',
                                                                                               'Neutral')
                    processing = st.session_state.analysis_data.get('processingLevel', 'Unknown')

                    # Health impact color coding
                    impact_color = {
                        "Very Beneficial": "green",
                        "Beneficial": "green",
                        "Neutral": "gray",
                        "Concerning": "orange",
                        "Harmful": "red"
                    }.get(health_impact, "gray")

                    # Display summary
                    st.markdown(f"**Food:** {name}")
                    # Use proper Streamlit markdown for colored text
                    health_emoji = {
                        "Very Beneficial": "🟢",
                        "Beneficial": "🟢",
                        "Neutral": "🟡",
                        "Concerning": "🟠",
                        "Harmful": "🔴"
                    }.get(health_impact, "⚪")
                    st.markdown(f"**Health Impact:** {health_emoji} {health_impact}")
                    st.markdown(f"**Processing Level:** {processing}")

                    # Display allergen warnings if applicable
                    user_allergies = st.session_state.user_preferences.get('allergies', [])
                    if user_allergies:
                        food_allergens = st.session_state.analysis_data.get('allergens', [])
                        matching_allergens = [a for a in user_allergies if
                                              any(a.lower() in allergen.lower() for allergen in food_allergens)]

                        if matching_allergens:
                            st.error(f"⚠️ Contains allergens you're sensitive to: {', '.join(matching_allergens)}")

                # Health score visualization
                health_scores = {}
                health_impact = st.session_state.analysis_data.get('healthImpact', {})
                for goal in st.session_state.user_preferences.get('health_goals', []):
                    if goal in health_impact:
                        impact = health_impact[goal]
                        if "Positive" in impact or "Beneficial" in impact:
                            health_scores[goal] = 5
                        elif "Neutral" in impact:
                            health_scores[goal] = 3
                        else:
                            health_scores[goal] = 1

                if health_scores:
                    score_df = pd.DataFrame({"Goal": list(health_scores.keys()), "Score": list(health_scores.values())})
                    fig = px.bar(score_df, x="Score", y="Goal", orientation='h',
                                 color="Score", color_continuous_scale=["red", "yellow", "green"],
                                 title="Alignment with Your Health Goals",
                                 range_color=[1, 5])
                    st.plotly_chart(fig, use_container_width=True)

            # Show relevant questions based on analysis
            if st.session_state.analysis_results:
                self.render_follow_up_questions()

                # Add chat interface directly on analysis page
                self.render_inline_chat()

    def render_trends_section(self):
        st.header("📈 Your Food Trends")

        if not st.session_state.trends:
            st.info("No food analysis history yet. Start by analyzing a food image!")
            return

        # Display recent food items analyzed
        st.subheader("Recent Foods Analyzed")
        trends_df = pd.DataFrame(st.session_state.trends)
        if not trends_df.empty:
            # Select only columns that exist
            available_cols = ["timestamp", "food", "calories", "protein", "carbs", "fat", "processing_level"]
            display_cols = [col for col in available_cols if col in trends_df.columns]
            if display_cols:
                st.dataframe(trends_df[display_cols])
            else:
                st.dataframe(trends_df)
        else:
            st.info("No data to display yet.")

        # Calories trend over time
        if not trends_df.empty and "calories" in trends_df.columns and "timestamp" in trends_df.columns:
            st.subheader("Caloric Intake Trend")
            fig = px.line(trends_df, x="timestamp", y="calories", markers=True,
                          title="Calories per Food Item")
            st.plotly_chart(fig, use_container_width=True)

        # Processing level distribution
        if not trends_df.empty and "processing_level" in trends_df.columns:
            st.subheader("Processing Level Distribution")
            processing_counts = trends_df["processing_level"].value_counts().reset_index()
            processing_counts.columns = ["Processing Level", "Count"]
            fig = px.pie(processing_counts, values="Count", names="Processing Level",
                         title="Distribution of Processing Levels in Your Diet")
            st.plotly_chart(fig, use_container_width=True)

        # Macronutrient breakdown
        if not trends_df.empty and all(col in trends_df.columns for col in ["protein", "carbs", "fat"]):
            st.subheader("Average Macronutrient Distribution")
            macros_df = pd.DataFrame({
                "Nutrient": ["Protein", "Carbs", "Fat"],
                "Grams": [
                    trends_df["protein"].mean(),
                    trends_df["carbs"].mean(),
                    trends_df["fat"].mean()
                ]
            })
            fig = px.bar(macros_df, x="Nutrient", y="Grams", title="Average Macronutrient Content")
            st.plotly_chart(fig, use_container_width=True)

        # Food health impact distribution
        if not trends_df.empty and "health_impact" in trends_df.columns:
            st.subheader("Health Impact Distribution")
            impact_counts = trends_df["health_impact"].value_counts().reset_index()
            impact_counts.columns = ["Health Impact", "Count"]
            fig = px.bar(impact_counts, x="Health Impact", y="Count",
                         color="Health Impact",
                         color_discrete_map={
                             "Very Beneficial": "green",
                             "Beneficial": "lightgreen",
                             "Neutral": "gray",
                             "Concerning": "orange",
                             "Harmful": "red"
                         },
                         title="Distribution of Food Health Impact")
            st.plotly_chart(fig, use_container_width=True)

    def render_follow_up_questions(self):
        if st.session_state.analysis_results:
            st.subheader("❓ Ask More About Your Food")

            # Enhanced questions based on food type and user preferences
            questions = {
                "nutrition": "Tell me more about the nutritional value",
                "allergies": "Is this safe for my allergies?",
                "diet": "Does this fit my diet?",
                "health": "How does this align with my health goals?",
                "alternatives": "What are healthier alternatives?",
                "preparation": "How should I prepare this food?",
                "compare": "How does this compare to similar foods?",
                "science": "What's the science behind this food?",
                "portion": "What's an appropriate portion size?",
                "meal": "What can I pair this with for a balanced meal?"
            }

            # Create two rows of buttons with improved layout
            rows = [st.columns(3) for _ in range(4)]  # 4 rows of 3 buttons
            buttons = [col for row in rows for col in row]  # Flatten the list

            response_container = st.container()

            # Create buttons with improved styling
            for i, (key, question) in enumerate(questions.items()):
                if i < len(buttons):
                    with buttons[i]:
                        if st.button(question, key=f"btn_{key}", use_container_width=True):
                            with st.spinner("Generating response..."):
                                st.session_state.current_question = question
                                st.session_state.question_response = self.get_specific_analysis(question)

                                # Add to chat history for context
                                st.session_state.chat_history.append({"role": "user", "content": question})
                                st.session_state.chat_history.append(
                                    {"role": "assistant", "content": st.session_state.question_response})

            # Display response
            with response_container:
                if st.session_state.question_response:
                    st.subheader(f"Response: {st.session_state.current_question}")
                    st.markdown(st.session_state.question_response)

    def render_inline_chat(self):
        st.subheader("💬 Chat about your food")

        # Display recent chat history (last 4 messages)
        if st.session_state.chat_history:
            with st.expander("Recent conversation:", expanded=True):
                for message in st.session_state.chat_history[-4:]:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

        # Quick suggestion chips
        st.markdown("**Quick questions:**")
        suggestion_cols = st.columns(4)
        suggestions = [
            "Is this processed?",
            "Nutritional benefits?",
            "Good for weight loss?",
            "Any side effects?"
        ]

        prompt = None
        for i, suggestion in enumerate(suggestions):
            with suggestion_cols[i]:
                if st.button(suggestion, key=f"suggestion_{i}"):
                    prompt = suggestion
                    st.session_state.chat_history.append({"role": "user", "content": prompt})
                    with st.spinner("Generating response..."):
                        response = self.get_ai_response(prompt)
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.rerun()

        # Chat input
        if user_input := st.chat_input("Ask about your food..."):
            prompt = user_input
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.spinner("Generating response..."):
                response = self.get_ai_response(prompt)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()

    def render_chat_interface(self):
        st.header("💬 Full Chat History")

        # Display chat history
        if not st.session_state.chat_history:
            st.info("No chat history yet. Start a conversation on the Analysis tab!")
        else:
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        # Chat input with a unique key
        if prompt := st.chat_input("Ask about your food...", key="chat_input"):  # Added a unique key
            st.session_state.chat_history.append({"role": "user", "content": prompt})

            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                response = self.get_ai_response(prompt)
                st.markdown(response)
                st.session_state.chat_history.append({"role": "assistant", "content": response})

    def render_education_section(self):
        """New section for educational content about nutrition and food labels"""
        st.header("📚 Learn About Nutrition & Food Labels")

        # Educational tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "Reading Food Labels",
            "Nutrition Basics",
            "Food Additives",
            "Health Claims"
        ])

        with tab1:
            st.subheader("How to Read Food Labels")
            st.markdown("""
            ### Understanding Nutrition Facts Panels

            Food labels provide crucial information about what you're eating. Here's how to decode them:

            1. **Serving Size**: All nutritional information is based on this amount
            2. **Calories**: Energy provided by one serving
            3. **% Daily Value**: Shows how much a nutrient contributes to a 2,000 calorie daily diet
            4. **Macronutrients**: Fat, carbohydrates, and protein
            5. **Vitamins and Minerals**: Essential micronutrients

            ### Key Areas to Check

            - **Ingredient List**: Ingredients are listed in descending order by weight
            - **Allergen Information**: Required to be clearly stated
            - **Health Claims**: Regulated statements about health benefits

            ### Red Flags on Labels

            - Long ingredient lists with chemical names
            - High amounts of added sugars (look for names ending in "-ose")
            - High sodium content (over 20% DV per serving)
            - Partially hydrogenated oils (trans fats)
            """)

            try:
                st.image("https://www.fda.gov/files/styles/main_image_medium/public/NFLS-v5-sample.png",
                         caption="Sample Nutrition Facts Label (FDA)", use_container_width=True)
            except Exception as e:
                self.logger.warning(f"Could not load external image: {e}")
                st.info("Sample nutrition label image would appear here. Check your internet connection.")

        with tab2:
            st.subheader("Nutrition Basics")
            st.markdown("""
            ### Macronutrients

            - **Proteins**: Building blocks for muscles and tissues (4 calories/gram)
            - **Carbohydrates**: Primary energy source (4 calories/gram)
            - **Fats**: Essential for hormone production and nutrient absorption (9 calories/gram)

            ### Micronutrients

            - **Vitamins**: Organic compounds needed in small amounts
            - **Minerals**: Inorganic elements needed for various bodily functions

            ### Understanding Processed Foods

            The NOVA classification system categorizes foods by processing level:

            1. **Unprocessed/Minimally Processed**: Whole foods, minimal changes
            2. **Processed Culinary Ingredients**: Oils, flours, sugars
            3. **Processed Foods**: Canned vegetables, cheese, bread
            4. **Ultra-Processed Foods**: Industrial formulations with many ingredients
            """)

            # Food processing chart
            processing_data = {
                "Category": ["Unprocessed", "Minimally Processed", "Processed", "Ultra-Processed"],
                "Health Impact": [5, 4, 3, 1],
                "Examples": [
                    "Fresh fruits, vegetables, eggs",
                    "Frozen vegetables, roasted nuts",
                    "Canned foods, cheese, bread",
                    "Chips, soda, frozen meals"
                ]
            }
            processing_df = pd.DataFrame(processing_data)
            st.dataframe(processing_df, use_container_width=True)

        with tab3:
            st.subheader("Common Food Additives")
            st.markdown("""
            ### Understanding E-Numbers and Additives

            Food additives serve various purposes from preservation to enhancing flavor or appearance.

            ### Common Additive Categories:

            - **Colors (E100-E199)**: Add or restore color
            - **Preservatives (E200-E299)**: Prevent spoilage
            - **Antioxidants (E300-E399)**: Prevent oxidation/rancidity
            - **Thickeners/Stabilizers (E400-E499)**: Modify texture
            - **Emulsifiers (E500-E599)**: Help mix ingredients that normally separate

            ### Controversial Additives

            Some additives have sparked health concerns:

            - **Artificial Colors (E102, E104, E110)**: Linked to hyperactivity in children
            - **BHA/BHT (E320, E321)**: Possible endocrine disruptors
            - **MSG (E621)**: May cause sensitivity reactions in some individuals
            - **Sodium Nitrite (E250)**: Forms potentially carcinogenic compounds

            ### Natural vs. Artificial

            "Natural" doesn't always mean healthier. Evaluate additives based on:

            1. Purpose in the food
            2. Research on safety
            3. Your individual sensitivities
            """)

            # Additives table
            st.markdown("#### Common Food Additives and Their Functions")
            additives_data = {
                "Additive": ["Citric Acid (E330)", "Lecithin (E322)", "Xanthan Gum (E415)", "Ascorbic Acid (E300)",
                             "Sodium Benzoate (E211)"],
                "Function": ["Acidifier, preservative", "Emulsifier", "Thickener, stabilizer", "Antioxidant",
                             "Preservative"],
                "Common In": ["Soft drinks, jams", "Chocolate, margarine", "Sauces, dressings", "Fruit products",
                              "Acidic foods, soft drinks"],
                "Origin": ["Natural/Synthetic", "Natural", "Natural (fermented)", "Natural/Synthetic", "Synthetic"]
            }
            additives_df = pd.DataFrame(additives_data)
            st.dataframe(additives_df, use_container_width=True)

        with tab4:
            st.subheader("Understanding Health Claims")
            st.markdown("""
            ### Regulated Health Claims

            Food packages often display claims about health benefits. These are regulated but can be misleading:

            ### Types of Claims:

            1. **Nutrient Content Claims**: "Low fat," "High in fiber"
            2. **Health Claims**: Link a food to reduced disease risk
            3. **Structure/Function Claims**: Describe how a nutrient affects body structure/function

            ### Common Misleading Terms:

            - **"Natural"**: No clear definition; doesn't mean unprocessed or healthy
            - **"Made with whole grains"**: May contain minimal whole grains
            - **"No added sugar"**: May still be high in natural sugars
            - **"Low-fat"**: Often has added sugar to compensate for taste
            - **"Organic"**: Refers to production methods, not nutritional quality

            ### How to Evaluate Claims:

            - Check the ingredients list
            - Review the nutrition facts panel
            - Look beyond front-of-package marketing
            - Consider the whole food in context of your diet
            """)

            # Health claims vs reality
            st.markdown("#### Common Claims vs. Reality")
            claims_data = {
                "Claim": ["Low Fat", "All Natural", "Made with Whole Grains", "No Added Sugar", "Organic"],
                "What it Means": ["Less than 3g fat per serving", "No standard definition",
                                  "Contains some whole grains", "No sugar added during processing",
                                  "Meets USDA organic standards"],
                "Reality Check": ["May be high in sugar", "Can include processed ingredients",
                                  "May be mostly refined flour", "May be naturally high in sugar",
                                  "Not necessarily more nutritious"]
            }
            claims_df = pd.DataFrame(claims_data)
            st.dataframe(claims_df, use_container_width=True)

    def get_specific_analysis(self, question):
        try:
            # Ensure API key is configured
            api_key = st.session_state.get('user_api_key', None) or self.config.get_api_key()
            if api_key:
                genai.configure(api_key=api_key)
            model = genai.GenerativeModel(self.config.GEMINI_MODEL)

            # Create context-aware prompt with structured data
            analysis_json = st.session_state.analysis_data
            prompt = (
                f"Based on the previous food analysis data:\n{str(analysis_json)}\n\n"
                f"And considering user preferences:\n"
                f"Dietary: {st.session_state.user_preferences['dietary']}\n"
                f"Allergies: {st.session_state.user_preferences['allergies']}\n"
                f"Health Goals: {st.session_state.user_preferences['health_goals']}\n"
                f"Health Conditions: {st.session_state.user_preferences['health_conditions']}\n\n"
                f"Please answer this question: {question}\n"
                "Provide a detailed but concise response with actionable information."
                "Format your response using markdown for readability."
            )

            response = model.generate_content(prompt)
            return response.text if response and hasattr(response, 'text') else "Unable to generate response."

        except Exception as e:
            self.logger.error(f"Question analysis error: {e}")
            return "Error generating response."

    def get_ai_response(self, user_query):
        try:
            # Ensure API key is configured
            api_key = st.session_state.get('user_api_key', None) or self.config.get_api_key()
            if api_key:
                genai.configure(api_key=api_key)
            model = genai.GenerativeModel(self.config.GEMINI_MODEL)

            # Create context-aware prompt for chat with more detailed structure
            analysis_json = st.session_state.analysis_data

            # Include chat history for context
            chat_history_text = ""
            if st.session_state.chat_history:
                recent_messages = st.session_state.chat_history[-6:]  # Include 6 most recent messages for context
                for msg in recent_messages:
                    chat_history_text += f"{msg['role'].upper()}: {msg['content']}\n"

            context = (
                f"CONTEXT:\n"
                f"User Preferences:\n"
                f"- Diet: {', '.join(st.session_state.user_preferences['dietary']) if st.session_state.user_preferences['dietary'] else 'None specified'}\n"
                f"- Allergies: {', '.join(st.session_state.user_preferences['allergies']) if st.session_state.user_preferences['allergies'] else 'None specified'}\n"
                f"- Health Goals: {', '.join(st.session_state.user_preferences['health_goals']) if st.session_state.user_preferences['health_goals'] else 'None specified'}\n"
                f"- Health Conditions: {', '.join(st.session_state.user_preferences['health_conditions']) if st.session_state.user_preferences['health_conditions'] else 'None specified'}\n"
                f"\nAnalyzed Food Data: {str(analysis_json) if analysis_json else 'No food currently analyzed'}\n"
                f"\nRecent Conversation:\n{chat_history_text}\n"
                f"\nCURRENT USER QUESTION: {user_query}\n\n"
                f"Instructions:\n"
                f"1. Answer the user's question specifically about the food.\n"
                f"2. If the question is unrelated to food analysis, nutrition, or health, politely redirect to food topics.\n"
                f"3. Format your response with markdown for clarity.\n"
                f"4. Keep responses concise but informative.\n"
                f"5. Include specific numbers and facts when available.\n"
                f"6. If appropriate, add a brief research citation or evidence for claims made."
            )

            response = model.generate_content(context)
            return response.text if response and hasattr(response, 'text') else "I couldn't generate a response."

        except Exception as e:
            self.logger.error(f"Chat response error: {e}")
            return "I encountered an error while processing your question."

    def render_report_section(self):
        """New section for generating comprehensive health reports"""
        st.header("📊 Generate Nutrition Report")

        if not st.session_state.analysis_data:
            st.warning("Please analyze a food item first to generate a report.")
            return

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("Report Options")

            report_type = st.selectbox(
                "Report Type",
                ["Basic Nutritional Analysis", "Comprehensive Health Assessment",
                 "Diet Compatibility Check", "Allergen Safety Report"]
            )

            include_recommendations = st.checkbox("Include Personalized Recommendations", value=True)
            include_alternatives = st.checkbox("Include Healthier Alternatives", value=True)
            include_scientific_evidence = st.checkbox("Include Scientific References", value=False)

            if st.button("Generate Report", type="primary"):
                with st.spinner("Generating your custom nutrition report..."):
                    report = self.generate_custom_report(
                        report_type,
                        include_recommendations,
                        include_alternatives,
                        include_scientific_evidence
                    )

                    # Store report for download
                    st.session_state.current_report = report

        with col2:
            st.subheader("Previous Reports")
            st.info("Your recent reports will appear here")

        # Display current report if available
        if hasattr(st.session_state, 'current_report') and st.session_state.current_report:
            st.subheader("Your Generated Report")
            st.markdown(st.session_state.current_report)

            # Provide download option
            report_text = st.session_state.current_report
            st.download_button(
                label="Download Report as Text",
                data=report_text,
                file_name=f"nutrition_report_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )

    def generate_custom_report(self, report_type, include_recommendations, include_alternatives,
                               include_scientific_evidence):
        """Generate a custom report based on user preferences"""
        try:
            # Ensure API key is configured
            api_key = st.session_state.get('user_api_key', None) or self.config.get_api_key()
            if api_key:
                genai.configure(api_key=api_key)
            model = genai.GenerativeModel(self.config.GEMINI_MODEL)

            # Get data for report
            analysis_data = st.session_state.analysis_data
            user_prefs = st.session_state.user_preferences

            # Create prompt for report generation
            prompt = (
                f"Generate a {report_type} for the food: {analysis_data.get('name', 'analyzed food')}.\n\n"
                f"Food analysis data:\n{str(analysis_data)}\n\n"
                f"User profile:\n"
                f"- Dietary preferences: {user_prefs['dietary']}\n"
                f"- Allergies: {user_prefs['allergies']}\n"
                f"- Health goals: {user_prefs['health_goals']}\n"
                f"- Health conditions: {user_prefs['health_conditions']}\n\n"
                f"Include personalized recommendations: {include_recommendations}\n"
                f"Include healthier alternatives: {include_alternatives}\n"
                f"Include scientific evidence: {include_scientific_evidence}\n\n"
                f"Format the report using detailed markdown with proper headers, sections, and formatting.\n"
                f"Create a well-structured, professional-looking report with clear sections and visual hierarchy.\n"
                f"Include a summary at the beginning and a conclusion at the end.\n"
            )

            response = model.generate_content(prompt)
            if response and hasattr(response, 'text'):
                return response.text
            return "Failed to generate report."

        except Exception as e:
            self.logger.error(f"Report generation error: {e}")
            return "Error generating nutrition report."

    def run(self):
        st.set_page_config(
            page_title="Smart Food Label Analyzer Pro",
            page_icon="🥗",
            layout="wide",
            initial_sidebar_state="expanded"
        )

        st.title("🥗 Smart Food Label Analyzer Pro")
        st.markdown("### Decode your food's true nutritional story with AI")

        self.render_sidebar()

        # Create tabs for different sections
        tabs = st.tabs([
            "📸 Analyze Food",
            "📊 Track Trends",
            "📚 Learn",
            "💬 Chat History",
            "📋 Reports"
        ])

        with tabs[0]:
            self.render_analysis_section()

        with tabs[1]:
            self.render_trends_section()

        with tabs[2]:
            self.render_education_section()

        with tabs[3]:
            self.render_chat_interface()

        with tabs[4]:
            self.render_report_section()

        # Footer with app information
        st.markdown("---")
        cols = st.columns([1, 1, 1])
        with cols[0]:
            st.markdown("**Smart Food Label Analyzer Pro** • v2.0")
        with cols[1]:
            st.markdown("Powered by Gemini AI")
        with cols[2]:
            st.markdown("© 2025 • [Privacy Policy](#)")


if __name__ == "__main__":
    app = FoodLabelAnalyzerApp()
    app.run()