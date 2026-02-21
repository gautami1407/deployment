import streamlit as st
from PIL import Image
import time
import google.generativeai as genai
import io
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json
from pathlib import Path
import os
import random
import matplotlib.pyplot as plt


class NutriChatConfig:
    """Configuration settings for the NutriChat application"""

    # 👉 Replace these with your actual keys (or use st.secrets / env vars)
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    USDA_API_KEY = os.environ.get("USDA_API_KEY")

    # AI Model Settings
    GEMINI_MODEL = "gemini-2.5-flash"
    GEMINI_VISION_MODEL = "gemini-2.5-flash"
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds

    # Image Settings
    SUPPORTED_IMAGE_TYPES = ["jpg", "jpeg", "png"]
    MAX_IMAGE_SIZE = (800, 800)

    # Categories for Suggested Questions
    QUESTION_CATEGORIES = {
        "Nutrition Basics": [
            "What are essential nutrients for a balanced diet?",
            "How can I improve my daily nutrition?",
            "What's the importance of meal timing?"
        ],
        "Diet-Specific": [
            "Best protein sources for vegetarians?",
            "How to follow a keto diet safely?",
            "Mediterranean diet meal plan suggestions?"
        ],
        "Health & Fitness": [
            "Pre and post workout nutrition tips?",
            "Foods for muscle recovery",
            "Best foods for weight management"
        ],
        "Practical Tips": [
            "Healthy meal prep ideas",
            "Budget-friendly healthy eating",
            "Quick and nutritious breakfast ideas"
        ]
    }

    # User Preference Options
    DIETARY_OPTIONS = [
        "Vegetarian", "Vegan", "Keto", "Paleo",
        "Mediterranean", "Gluten-Free", "Low-Carb", "High-Protein", "None"
    ]

    ALLERGY_OPTIONS = [
        "Nuts", "Dairy", "Gluten", "Shellfish",
        "Eggs", "Soy", "Fish", "Peanuts", "None"
    ]

    HEALTH_GOALS = [
        "Weight Loss", "Muscle Gain", "Maintenance",
        "Better Nutrition", "Sports Performance", "Heart Health", "None"
    ]

    # Inspirational nutrition quotes
    NUTRITION_QUOTES = [
        "\"Let food be thy medicine and medicine be thy food.\" — Hippocrates",
        "\"Take care of your body. It's the only place you have to live.\" — Jim Rohn",
        "\"The food you eat can be either the safest and most powerful form of medicine or the slowest form of poison.\" — Ann Wigmore",
        "\"Health is a relationship between you and your body.\" — Unknown",
        "\"Eat for nourishment, not for comfort.\" — Unknown",
        "\"Your diet is a bank account. Good food choices are good investments.\" — Bethenny Frankel",
        "\"If you keep good food in your fridge, you will eat good food.\" — Errick McAdams",
        "\"The greatest wealth is health.\" — Virgil",
        "\"You are what you eat, so don't be fast, cheap, easy, or fake.\" — Unknown",
        "\"Our bodies are our gardens, our wills are our gardeners.\" — William Shakespeare",
        "\"Don't eat less, eat right.\" — Unknown",
        "\"Healthy eating is a way of life, not a diet.\" — Unknown"
    ]


class NutriChatApp:
    def __init__(self):
        self.logger = self._setup_logging()
        self.config = NutriChatConfig()
        self._configure_gemini()
        self._setup_page_config()
        self._initialize_session_state()
        self._apply_custom_styles()

    def _initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        defaults = {
            'chat_history': [],
            'analysis_cache': {},
            'user_input': "",
            'current_image': None,
            'dietary_preferences': [],
            'allergies': [],
            'health_goals': None,
            'last_activity': None,
            'session_stats': {
                'chats': 0,
                'images_analyzed': 0,
                'streak_days': 0,
                'health_score': 0
            },
            'daily_quote': random.choice(self.config.NUTRITION_QUOTES),
            'show_clear_confirm': False
        }

        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('nutrichat.log')
            ]
        )
        return logging.getLogger(__name__)

    def _configure_gemini(self):
        """Configure the Gemini AI API"""
        try:
            if not self.config.GEMINI_API_KEY or "YOUR_GEMINI_API_KEY" in self.config.GEMINI_API_KEY:
                st.error("⚠ Please set your GEMINI_API_KEY in the config.")
                st.stop()

            genai.configure(api_key=self.config.GEMINI_API_KEY)
            self.logger.info("Gemini API configured successfully")
        except Exception as e:
            self.logger.error(f"Failed to configure Gemini API: {e}")
            st.error("Failed to initialize AI services. Please check your configuration.")
            st.stop()

    # 🧠 Helper to get the Gemini model (as you requested)
    def get_gemini_model(self, model_name: Optional[str] = None) -> "genai.GenerativeModel":
        if model_name is None:
            model_name = self.config.GEMINI_MODEL
        try:
            return genai.GenerativeModel(model_name)
        except Exception as e:
            self.logger.error(f"Failed to load Gemini model '{model_name}': {e}")
            raise

    def _setup_page_config(self):
        """Configure Streamlit page settings"""
        st.set_page_config(
            page_title="NutriChat Advisor",
            page_icon="🥗",
            layout="wide",
            initial_sidebar_state="expanded"
        )

    def _apply_custom_styles(self):
        """Apply custom CSS styles to the application"""
        st.markdown("""
            <style>
            .main {
                background-color: #f9f9f9;
                color: #333;
            }

            .header {
                background: linear-gradient(135deg, #4CAF50, #45a049);
                color: white;
                padding: 2rem;
                border-radius: 15px;
                margin-bottom: 2rem;
                text-align: center;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }

            .chat-container {
                max-height: 600px;
                overflow-y: auto;
                padding: 1rem;
                border-radius: 10px;
                background: rgba(255,255,255,0.05);
                backdrop-filter: blur(10px);
            }

            .chat-message {
                padding: 1rem;
                margin: 1rem 0;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                animation: fadeIn 0.3s ease-in;
            }

            .user-message {
                background: linear-gradient(135deg, #E8F5E9, #C8E6C9);
                margin-left: 2rem;
            }

            .assistant-message {
                background: linear-gradient(135deg, #F1F8E9, #DCEDC8);
                margin-right: 2rem;
            }

            .stat-card {
                background: rgba(255,255,255,0.1);
                padding: 1.5rem;
                border-radius: 15px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
                transition: transform 0.2s ease;
            }

            .stat-card:hover {
                transform: translateY(-5px);
            }

            .quote-box {
                background: linear-gradient(135deg, rgba(76, 175, 80, 0.1), rgba(69, 160, 73, 0.2));
                padding: 1.5rem;
                border-radius: 15px;
                border-left: 5px solid #4CAF50;
                margin: 1.5rem 0;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                text-align: center;
                font-style: italic;
            }

            .stats-dashboard {
                margin-top: 2rem;
                padding: 1.5rem;
                border-radius: 15px;
                background: rgba(255,255,255,0.1);
                backdrop-filter: blur(10px);
            }

            .question-category {
                background: white;
                padding: 1rem;
                border-radius: 10px;
                margin-bottom: 1rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }

            .question-button {
                width: 100%;
                margin: 0.5rem 0;
                padding: 0.5rem;
                border-radius: 5px;
                border: 1px solid #4CAF50;
                background: transparent;
                transition: all 0.2s ease;
            }

            .question-button:hover {
                background: #4CAF50;
                color: white;
            }

            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            </style>
        """, unsafe_allow_html=True)

    def get_ai_response(self, prompt: str, context: Optional[Dict] = None) -> str:
        """Get response from Gemini AI with retry logic (synchronous version)"""
        base_prompt = self._construct_prompt(prompt, context)
        self.logger.info(f"Sending prompt to Gemini AI: {prompt[:50]}...")

        for attempt in range(self.config.MAX_RETRIES):
            try:
                model = self.get_gemini_model()
                response = model.generate_content(base_prompt)

                if response and hasattr(response, 'text') and response.text:
                    st.session_state.session_stats['chats'] += 1
                    self._update_session_stats()
                    return response.text
                else:
                    self.logger.warning(f"Empty response from Gemini on attempt {attempt + 1}")

            except Exception as e:
                self.logger.error(f"AI response attempt {attempt + 1} failed: {str(e)}")
                time.sleep(self.config.RETRY_DELAY)

        return "I apologize, but I'm having trouble processing your request. Please try again later."

    def _construct_prompt(self, user_query: str, context: Optional[Dict] = None) -> str:
        """Constructs a detailed prompt with user preferences and query context"""
        system_prompt = """You are NutriChat, a specialized nutrition advisor with expertise in:
        - Dietary science and balanced nutrition
        - Different diets and eating patterns
        - Food ingredients and allergens
        - Nutritional needs for various health goals

        Provide accurate, personalized nutrition advice based on the user's preferences and goals.
        Use evidence-based information and stay within your nutritional expertise.
        You do not provide medical diagnoses or emergency instructions.
        """

        if context and "preferences" in context:
            prefs = context["preferences"]
            system_prompt += "\nUser Preferences:"

            if prefs.get("dietary"):
                system_prompt += f"\n- Dietary: {', '.join(prefs['dietary'])}"
            if prefs.get("allergies"):
                system_prompt += f"\n- Allergies: {', '.join(prefs['allergies'])}"
            if prefs.get("goal"):
                system_prompt += f"\n- Health Goal: {prefs['goal']}"

        complete_prompt = (
            f"{system_prompt}\n\nUser Query: {user_query}\n\n"
            "Provide a helpful, accurate response:"
        )
        return complete_prompt

    def render_chat_interface(self):
        """Render the chat interface section"""
        st.markdown("""
            <div class="chat-container">
                <h3>💬 Chat with NutriChat</h3>
            </div>
        """, unsafe_allow_html=True)

        if len(st.session_state.chat_history) > 0:
            for message in st.session_state.chat_history:
                role_class = "user-message" if message["role"] == "user" else "assistant-message"
                st.markdown(
                    f"""<div class="chat-message {role_class}">
                        <strong>{message["role"].title()}:</strong> {message["content"]}
                    </div>""",
                    unsafe_allow_html=True
                )
        else:
            st.info("Start a conversation by typing a message or selecting a suggested question.")

        col1, col2 = st.columns([4, 1])
        with col1:
            st.text_input("Type your message:", key="user_input")
        with col2:
            if st.button("Send", key="send_message"):
                self._handle_chat_input()

    def _handle_chat_input(self):
        """Process user input from the chat interface"""
        user_input = st.session_state.user_input
        if not user_input or user_input.strip() == "":
            st.warning("Please enter a message")
            return

        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.spinner("Thinking..."):
            context = {
                "preferences": {
                    "dietary": st.session_state.dietary_preferences,
                    "allergies": st.session_state.allergies,
                    "goal": st.session_state.health_goals
                }
            }
            try:
                response = self.get_ai_response(user_input, context)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.session_state.user_input = ""
                st.experimental_rerun()
            except Exception as e:
                self.logger.error(f"Failed to get AI response: {e}")
                st.error("Failed to get response. Please try again.")

    def render_image_analysis(self):
        """Render the food image analysis section"""
        st.markdown("### 📷 Food Image Analysis")
        uploaded_file = st.file_uploader(
            "Upload food image for analysis",
            type=self.config.SUPPORTED_IMAGE_TYPES,
            key="food_image_uploader"
        )

        if uploaded_file is not None:
            try:
                image = Image.open(uploaded_file)
                st.image(image, caption="Uploaded Food Image", use_column_width=True)

                if st.button("Analyze Food", key="analyze_food_btn"):
                    with st.spinner("Analyzing your food..."):
                        analysis_result = self._analyze_food_image(image)
                        st.session_state.session_stats['images_analyzed'] += 1
                        self._update_session_stats()
                        st.success("Analysis Complete!")
                        st.markdown(f"### Analysis Results\n{analysis_result}")
            except Exception as e:
                self.logger.error(f"Image processing error: {e}")
                st.error("Failed to process image. Please try a different file.")

    def _analyze_food_image(self, image: Image.Image) -> str:
        """Analyze food image using Gemini Vision API"""
        try:
            image.thumbnail(self.config.MAX_IMAGE_SIZE)

            img_byte_arr = io.BytesIO()
            image_format = image.format if image.format else 'JPEG'
            image.save(img_byte_arr, format=image_format)
            img_bytes = img_byte_arr.getvalue()

            model = self.get_gemini_model(self.config.GEMINI_VISION_MODEL)
            prompt = [
                """Analyze this food image and provide:
                1. Food identification
                2. Estimated calories
                3. Macronutrients breakdown (proteins, carbs, fats)
                4. Nutritional benefits
                5. Considerations for special diets
                """,
                {"mime_type": f"image/{image_format.lower()}", "data": img_bytes}
            ]

            response = model.generate_content(prompt)

            if response and hasattr(response, 'text') and response.text:
                image_hash = hash(img_bytes)
                st.session_state.analysis_cache[image_hash] = response.text
                return response.text
            else:
                return "Unable to analyze image. The AI model did not return a valid response."

        except Exception as e:
            self.logger.error(f"Image analysis error: {str(e)}")
            return f"Error analyzing image: {str(e)}. Please try again with a clearer image of food."

    def _handle_suggested_question(self, question: str):
        """Handle clicked suggested question (sync version)"""
        st.session_state.chat_history.append({"role": "user", "content": question})

        context = {
            "preferences": {
                "dietary": st.session_state.dietary_preferences,
                "allergies": st.session_state.allergies,
                "goal": st.session_state.health_goals
            }
        }

        response = self.get_ai_response(question, context)
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.experimental_rerun()

    def render_user_dashboard(self):
        """Render user statistics dashboard"""
        st.markdown("### 📊 Your Nutrition Journey")

        cols = st.columns(4)
        stats = [
            {"icon": "💬", "label": "Chats", "value": st.session_state.session_stats['chats']},
            {"icon": "📸", "label": "Foods Analyzed",
             "value": st.session_state.session_stats['images_analyzed']},
            {"icon": "🎯", "label": "Health Score",
             "value": f"{st.session_state.session_stats['health_score']:.1f}/10"},
            {"icon": "🔥", "label": "Day Streak",
             "value": f"{st.session_state.session_stats['streak_days']} days"}
        ]

        for col, stat in zip(cols, stats):
            col.markdown(
                f"""<div class="stat-card">
                    <h1>{stat['icon']}</h1>
                    <h4>{stat['label']}</h4>
                    <h2>{stat['value']}</h2>
                </div>""",
                unsafe_allow_html=True
            )

        self.render_interactive_charts()

    def render_quote_section(self):
        """Render nutrition inspiration quote box"""
        st.markdown(
            f"""<div class="quote-box">
                <h4>✨ Daily Inspiration</h4>
                <p>{st.session_state.daily_quote}</p>
            </div>""",
            unsafe_allow_html=True
        )

    def render_interactive_charts(self):
        """Render interactive charts for user statistics"""
        st.markdown("### 📈 Progress Charts")

        days = list(range(1, 31))
        chats = [random.randint(0, 10) for _ in days]
        images_analyzed = [random.randint(0, 5) for _ in days]
        health_scores = [random.uniform(5.0, 10.0) for _ in days]

        fig, ax = plt.subplots(3, 1, figsize=(10, 15))

        ax[0].plot(days, chats, marker='o', linestyle='-')
        ax[0].set_title("Chats per Day")
        ax[0].set_xlabel("Day")
        ax[0].set_ylabel("Number of Chats")

        ax[1].plot(days, images_analyzed, marker='s', linestyle='-')
        ax[1].set_title("Images Analyzed per Day")
        ax[1].set_xlabel("Day")
        ax[1].set_ylabel("Number of Images")

        ax[2].plot(days, health_scores, marker='^', linestyle='-')
        ax[2].set_title("Health Score Progression")
        ax[2].set_xlabel("Day")
        ax[2].set_ylabel("Health Score")

        st.pyplot(fig)

    def _update_session_stats(self):
        """Updates user session statistics and health score"""
        current_time = datetime.now()

        if st.session_state.last_activity:
            try:
                last_date = datetime.strptime(st.session_state.last_activity, "%Y-%m-%d")
                today = current_time.date()
                delta_days = (today - last_date.date()).days

                if delta_days == 1:
                    st.session_state.session_stats['streak_days'] += 1
                elif delta_days > 1:
                    st.session_state.session_stats['streak_days'] = 1
            except Exception as e:
                self.logger.error(f"Error calculating streak: {e}")
                st.session_state.session_stats['streak_days'] = 1
        else:
            st.session_state.session_stats['streak_days'] = 1

        st.session_state.last_activity = current_time.strftime("%Y-%m-%d")

        engagement_score = min(st.session_state.session_stats['chats'] / 10, 5)
        analysis_score = min(st.session_state.session_stats['images_analyzed'] / 5, 3)
        streak_score = min(st.session_state.session_stats['streak_days'] / 7, 2)

        health_score = engagement_score + analysis_score + streak_score
        st.session_state.session_stats['health_score'] = min(health_score, 10)

    def _render_user_preferences(self):
        """Render user preferences section in sidebar"""
        st.markdown("### 🍽 Dietary Preferences")
        preferences = st.multiselect(
            "Select your diet:",
            self.config.DIETARY_OPTIONS,
            default=st.session_state.dietary_preferences,
            key="sidebar_dietary_preferences"
        )
        st.session_state.dietary_preferences = preferences

        st.markdown("### ⚠ Allergies")
        allergies = st.multiselect(
            "Select allergies:",
            self.config.ALLERGY_OPTIONS,
            default=st.session_state.allergies,
            key="sidebar_allergies"
        )
        st.session_state.allergies = allergies

        st.markdown("### 🎯 Health Goals")
        goal = st.selectbox(
            "Select your goal:",
            self.config.HEALTH_GOALS,
            index=0 if st.session_state.health_goals is None
            else self.config.HEALTH_GOALS.index(st.session_state.health_goals),
            key="sidebar_health_goals"
        )
        st.session_state.health_goals = goal

    def _render_settings(self):
        """Render application settings in sidebar"""
        st.markdown("### ⚙ Settings")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Export Data", key="export_btn"):
                self._export_chat_history()

        with col2:
            if st.button("Clear History", key="clear_btn"):
                self._clear_history_confirmation()

    def _clear_history_confirmation(self):
        """Show confirmation dialog for clearing history"""
        st.session_state.show_clear_confirm = True
        st.info("Are you sure you want to clear all chat history and analysis data?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, Clear", key="confirm_clear"):
                self._clear_history()
        with col2:
            if st.button("Cancel", key="cancel_clear"):
                st.session_state.show_clear_confirm = False
                st.experimental_rerun()

    def _clear_history(self):
        """Clears chat history and analysis cache"""
        st.session_state.chat_history = []
        st.session_state.analysis_cache = {}
        st.session_state.show_clear_confirm = False
        st.success("History cleared successfully")
        time.sleep(1)
        st.experimental_rerun()

    def _export_chat_history(self):
        """Exports the chat history to a JSON file"""
        try:
            export_data = {
                "chat_history": st.session_state.chat_history,
                "user_preferences": {
                    "dietary": st.session_state.dietary_preferences,
                    "allergies": st.session_state.allergies,
                    "health_goal": st.session_state.health_goals
                },
                "stats": st.session_state.session_stats,
                "exported_at": datetime.now().isoformat()
            }

            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)

            filename = f"nutrichat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            export_path = export_dir / filename

            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2)

            st.sidebar.success(f"Exported data to {filename}")
            self.logger.info(f"Successfully exported data to {filename}")
        except Exception as e:
            self.logger.error(f"Export error: {e}")
            st.sidebar.error("Failed to export data")

    def _render_help_section(self):
        """Render help and tips section in sidebar"""
        with st.expander("❓ Help & Tips"):
            st.markdown("""
                Quick Start Guide:
                1. Set your preferences in the sidebar
                2. Ask nutrition questions in the chat
                3. Upload food photos for analysis
                4. Explore suggested topics

                Pro Tips:
                - Be specific with questions
                - Regular check-ins improve your score
                - Track your progress with stats
                - Export data to monitor long-term progress
            """)

            st.markdown("---")
            st.markdown("Need help? If you encounter any issues, email support@nutrichat.example.com")

    def render_suggested_questions(self):
        """Render suggested questions based on categories"""
        st.markdown("### 💡 Suggested Questions")
        for category, questions in self.config.QUESTION_CATEGORIES.items():
            with st.expander(category):
                for question in questions:
                    if st.button(question, key=f"suggested_{question}"):
                        self._handle_suggested_question(question)

    def run(self):
        """Main application entry point"""
        try:
            self._initialize_session_state()

            st.markdown("""
                <div class="header">
                    <h1>🥗 NutriChat Advisor</h1>
                    <p>Your AI-powered nutrition and healthy eating guide!</p>
                </div>
            """, unsafe_allow_html=True)

            left_col, right_col = st.columns([2, 1])

            with left_col:
                self.render_chat_interface()
                self.render_image_analysis()

            with right_col:
                self.render_suggested_questions()

            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown("""
                <div class="stats-dashboard">
                    <h3>📊 Your Nutrition Journey</h3>
                </div>
            """, unsafe_allow_html=True)

            st.markdown("<div style='margin-top: -15px;'>", unsafe_allow_html=True)
            stats_cols = st.columns(4)
            stats = [
                {"icon": "💬", "label": "Chats", "value": st.session_state.session_stats['chats']},
                {"icon": "📸", "label": "Foods Analyzed",
                 "value": st.session_state.session_stats['images_analyzed']},
                {"icon": "🎯", "label": "Health Score",
                 "value": f"{st.session_state.session_stats['health_score']:.1f}/10"},
                {"icon": "🔥", "label": "Day Streak",
                 "value": f"{st.session_state.session_stats['streak_days']} days"}
            ]

            for col, stat in zip(stats_cols, stats):
                col.markdown(
                    f"""<div class="stat-card">
                        <h1>{stat['icon']}</h1>
                        <h4>{stat['label']}</h4>
                        <h2>{stat['value']}</h2>
                    </div>""",
                    unsafe_allow_html=True
                )
            st.markdown("</div>", unsafe_allow_html=True)

            self.render_quote_section()

            with st.sidebar:
                st.image("https://via.placeholder.com/150x150.png?text=NutriChat", width=150)
                st.markdown("## User Settings")

                self._render_user_preferences()
                self._render_settings()
                self._render_help_section()

                st.markdown("---")
                st.markdown("© 2025 NutriChat | v1.0.4")

        except Exception as e:
            self.logger.error(f"Application error: {e}")
            st.error(f"An unexpected error occurred: {str(e)}")
            st.info("Please refresh the page and try again. If the issue persists, contact support.")


if __name__ == "__main__":
    app = NutriChatApp()
    app.run()
