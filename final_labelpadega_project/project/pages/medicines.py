import streamlit as st
from typing import List, Dict, Optional, Tuple
from PIL import Image
from datetime import datetime
from dataclasses import dataclass
import os

# ====================================
# IMPORTS & THIRD-PARTY LIBRARIES
# ====================================

# Google Gemini AI
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    st.error("❌ google-generativeai not installed. Run: `pip install google-generativeai`")

# OCR with pytesseract
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ====================================
# CONFIGURATION & CONSTANTS
# ====================================

# Your API key (OK for local dev, don’t commit this to GitHub)
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CONFIG = {
    "max_image_size": (1920, 1920),
    "supported_formats": ["jpg", "jpeg", "png", "webp"],
    "chat_history_limit": 40,
    "analysis_timeout": 45,
    "scan_history_limit": 10,
}

MEDICAL_CONDITIONS = {
    "Cardiovascular": ["high blood pressure", "heart disease", "high cholesterol"],
    "Metabolic": ["diabetes", "thyroid disorder", "obesity"],
    "Kidney & Liver": ["kidney disease", "liver disease"],
    "Respiratory": ["asthma", "COPD"],
    "Gastrointestinal": ["acid reflux", "IBS", "ulcer"],
    "Other": ["arthritis", "migraine", "anxiety", "depression", "none"],
}

ALL_CONDITIONS = []
for category, conditions in MEDICAL_CONDITIONS.items():
    ALL_CONDITIONS.extend(conditions)

SUPPORTED_LANG_CODES = {
    "English (en)": "en",
    "Hindi (hi)": "hi",
    "Telugu (te)": "te",
    "Tamil (ta)": "ta",
    "Spanish (es)": "es",
}

# ====================================
# DATA CLASSES
# ====================================

@dataclass
class AnalysisResult:
    full_analysis: str
    success: bool
    risk_level: str = "⚠️ USE WITH CAUTION"
    timestamp: str = ""
    source_text: str = ""
    analysis_type: str = "short"
    brand_name: str = ""
    generic_name: str = ""

# ====================================
# UTILITY FUNCTIONS
# ====================================

@st.cache_resource(show_spinner=False)
def setup_gemini_api() -> bool:
    """Setup Gemini API with error handling (cached)."""
    if not GEMINI_AVAILABLE:
        return False

    if not GEMINI_API_KEY:
        st.error("❌ Gemini API key is empty. Please set GEMINI_API_KEY in the code.")
        return False

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        return True
    except Exception as e:
        st.error(f"❌ API Configuration Error: {str(e)}")
        return False


def optimize_image(image: Image.Image) -> Image.Image:
    """Optimize image for better OCR and API efficiency."""
    try:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        if image.size[0] > CONFIG["max_image_size"][0] or image.size[1] > CONFIG["max_image_size"][1]:
            image.thumbnail(CONFIG["max_image_size"], Image.Resampling.LANCZOS)

        return image
    except Exception as e:
        st.warning(f"Image optimization failed: {str(e)}")
        return image


def validate_medicine_text(text: str) -> Tuple[bool, str]:
    """Validate if text looks like medicine-related information."""
    if not text or len(text.strip()) < 5:
        return False, "Text too short. Please provide more details."

    medicine_keywords = [
        "mg", "ml", "tablet", "capsule", "syrup", "injection",
        "exp", "mfg", "batch", "dose", "strength", "ip", "usp"
    ]

    text_lower = text.lower()
    has_keyword = any(keyword in text_lower for keyword in medicine_keywords)

    if not has_keyword and len(text) < 20:
        return False, "Please provide more medicine details (name, strength, etc.)."

    return True, "Valid"


def detect_emergency_keywords(text: str) -> bool:
    """Basic emergency keyword detector to gently redirect user."""
    emergency_terms = [
        "chest pain", "severe pain", "difficulty breathing", "can't breathe",
        "cant breathe", "unconscious", "seizure", "suicidal", "overdose", "poisoned",
        "bleeding heavily", "heart attack", "stroke"
    ]
    t = text.lower()
    return any(term in t for term in emergency_terms)

# ====================================
# GEMINI HELPERS
# ====================================

@st.cache_resource(show_spinner=False)
def get_gemini_model(model_name: str = "gemini-2.5-flash") -> "genai.GenerativeModel":
    """Return a cached Gemini model instance."""
    return genai.GenerativeModel(model_name)


def extract_text_from_image_gemini(image: Image.Image, model_choice: str) -> Dict[str, any]:
    """Enhanced text extraction with better error handling and structure."""
    try:
        model = get_gemini_model(model_choice)

        optimized_image = optimize_image(image)

        prompt = """You are an expert OCR system for medical packaging. Extract ALL text from this medicine package/label.

FOCUS ON:
1. Medicine Name (Brand Name in LARGE letters)
2. Generic/Active Ingredient Name
3. Strength/Dosage (e.g., 500mg, 10ml)
4. Form (tablet/capsule/syrup/injection)
5. Manufacturing Date (Mfg/Mfd)
6. Expiry Date (Exp)
7. Batch/Lot Number
8. Manufacturer Name
9. Any warnings or special instructions
10. Storage instructions

FORMAT your response as:
**Brand Name:** [name]
**Generic Name:** [ingredient]
**Strength:** [dose]
**Form:** [type]
**Mfg Date:** [date]
**Exp Date:** [date]
**Batch:** [number]
**Manufacturer:** [company]
**Additional Info:** [any warnings, storage, etc.]

If you cannot read certain fields clearly, write "Not visible" for that field.
If the image quality is poor, mention specific issues (blur, glare, angle, etc.)."""

        response = model.generate_content([prompt, optimized_image])

        if response and hasattr(response, "text") and response.text:
            extracted_text = response.text.strip()

            if len(extracted_text) < 20 or "cannot read" in extracted_text.lower():
                return {
                    "success": False,
                    "text": extracted_text,
                    "error": "Low quality extraction. Image may be unclear.",
                }

            return {
                "success": True,
                "text": extracted_text,
                "error": None,
            }
        else:
            return {
                "success": False,
                "text": "",
                "error": "No response from Gemini Vision API.",
            }

    except Exception as e:
        return {
            "success": False,
            "text": "",
            "error": f"Extraction error: {str(e)}",
        }


def analyze_medicine_with_gemini(
    medicine_text: str,
    user_profile: Dict,
    analysis_type: str = "long",
    model_choice: str = "gemini-2.5-flash",
) -> AnalysisResult:
    """Enhanced medicine analysis with structured output - supports short and long formats."""
    try:
        model = get_gemini_model(model_choice)

        conditions_list = [c for c in user_profile.get("conditions", []) if c != "none"]

        profile_context = f"""
USER PROFILE:
- Age Group: {user_profile.get('age_group', 'adult').title()}
- Medical Conditions: {', '.join(conditions_list) if conditions_list else 'None reported'}
- Known Allergies: {user_profile.get('allergies', 'None') or 'None reported'}
- Language Preference: {user_profile.get('language', 'English (en)')}
"""

        if analysis_type == "short":
            prompt = f"""You are an expert medical education assistant. Analyze this medicine and provide a CONCISE educational summary.

MEDICINE INFORMATION:
{medicine_text}

{profile_context}

CRITICAL GUIDELINES:
✅ Keep response brief and focused (max ~400 words)
✅ Provide accurate, evidence-based information
✅ Highlight key safety concerns based on user profile
❌ DO NOT provide personal medical advice or prescriptions
❌ DO NOT suggest dosages

Provide analysis in this EXACT CONCISE format:

---

## 🏷️ MEDICINE IDENTIFICATION

**Brand Name:** [name]
**Generic Name:** [ingredient]
**Drug Class:** [class]
**Form & Strength:** [e.g., 500mg Tablet]

---

## 💊 WHAT IT DOES

[2-3 sentences explaining primary use and how it works]

---

## ⚠️ KEY SAFETY INFO

**Common Side Effects:** [List 3-4 most common]

**Serious Warning Signs:** [List 3 critical symptoms to watch]

**Who Should Avoid:** [2-3 key contraindications]

---

## 👤 FOR YOUR PROFILE

[Give brief notes using the user profile above. Do NOT give specific medical advice.]

**Risk Level:** [Choose ONE: ✅ GENERALLY SAFE | ⚠️ USE WITH CAUTION | 🛑 REQUIRES MONITORING]

---

## 💡 QUICK TIPS

- [Storage tip]
- [Timing tip]
- [Key interaction to avoid]

---

**⚠️ EDUCATIONAL ONLY** - Always consult your healthcare provider for personalized medical advice.

---"""
        else:  # long analysis
            prompt = f"""You are an expert medical education assistant. Analyze this medicine information and provide comprehensive educational content.

MEDICINE INFORMATION:
{medicine_text}

{profile_context}

CRITICAL GUIDELINES:
✅ This is STRICTLY for educational purposes
✅ Provide accurate, evidence-based information
✅ Be clear and accessible to non-medical professionals
✅ Highlight safety concerns based on user profile
✅ Use simple language
❌ DO NOT provide personal medical advice or prescriptions
❌ DO NOT recommend dosages
❌ DO NOT diagnose conditions

Provide analysis in this EXACT format:

---

## 🏷️ MEDICINE IDENTIFICATION

**Brand Name:** [Extract exact brand name]
**Generic Name (Active Ingredient):** [Scientific/generic name]
**Drug Class:** [e.g., Analgesic, Antibiotic, Antacid]
**Form:** [Tablet/Capsule/Syrup/Injection/Cream]
**Strength:** [e.g., 500mg, 10ml]
**Expiry Date:** [If found, otherwise "Check packaging"]

---

## 💊 WHAT IS THIS MEDICINE?

[2-3 clear sentences explaining what this medicine is and its primary medical use.]

---

## 🎯 COMMON USES

This medicine is commonly prescribed for:
- [Use 1]
- [Use 2]
- [Use 3]
- [Use 4]

---

## ⚠️ COMMON SIDE EFFECTS

Most people tolerate this medicine well, but some may experience:
- [Side effect 1]
- [Side effect 2]
- [Side effect 3]
- [Side effect 4]
- [Side effect 5]

*Note: Most side effects are mild and temporary.*

---

## 🚨 WHEN TO SEEK IMMEDIATE HELP

⚠️ Stop taking and contact a doctor immediately if you experience:
- [Serious symptom 1]
- [Serious symptom 2]
- [Serious symptom 3]
- [Serious symptom 4]
- [Serious symptom 5]

---

## 🚫 WHO SHOULD AVOID THIS MEDICINE

This medicine may not be suitable for:
- [Contraindication 1]
- [Contraindication 2]
- [Contraindication 3]
- [Contraindication 4]

**Special Groups:**
- Pregnancy: [Safety advice]
- Breastfeeding: [Advice]
- Children: [Age restrictions if any]
- Elderly: [Special precautions]

---

## 👤 PERSONALIZED SAFETY NOTES

Based on your profile above, provide 2-3 sentences of general, educational advice.
Do NOT give specific instructions or dosages.

---

## 📊 SAFETY RISK ASSESSMENT

**Overall Risk Level:** [Choose ONE: ✅ GENERALLY SAFE | ⚠️ USE WITH CAUTION | 🛑 REQUIRES CLOSE MONITORING]

**Assessment Reasoning:**
[2-3 sentences explaining this risk level]

---

## 💡 IMPORTANT USAGE NOTES

**Storage:**
[Storage conditions]

**Timing:**
[Before/after meals, time of day, spacing between doses]

**Drug Interactions:**
[Common medicines to avoid or be cautious with]

**Lifestyle Considerations:**
[Alcohol, driving, operating machinery, sun exposure]

**What to Do if You Miss a Dose:**
[General guidance only]

---

## ⚕️ ALWAYS REMEMBER

✅ Follow your doctor's prescription exactly  
✅ Never share medicines with others  
✅ Check expiry date before use  
✅ Report any unusual symptoms to your doctor

---

**⚠️ MEDICAL DISCLAIMER**

This information is for educational purposes only and does not replace professional medical advice.

---"""

        response = model.generate_content(prompt)

        if response and hasattr(response, "text") and response.text:
            analysis_text = response.text.strip()

            # Basic extraction of risk level
            risk_level = "⚠️ USE WITH CAUTION"
            if "✅ GENERALLY SAFE" in analysis_text:
                risk_level = "✅ GENERALLY SAFE"
            elif "🛑" in analysis_text:
                risk_level = "🛑 REQUIRES CLOSE MONITORING"

            # Try to sniff brand/generic
            brand_name = ""
            generic_name = ""
            for line in analysis_text.splitlines():
                if "Brand Name:" in line:
                    brand_name = line.split(":", 1)[-1].strip().strip("*")
                if "Generic Name" in line:
                    generic_name = line.split(":", 1)[-1].strip().strip("*")

            return AnalysisResult(
                full_analysis=analysis_text,
                success=True,
                risk_level=risk_level,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source_text=medicine_text,
                analysis_type=analysis_type,
                brand_name=brand_name,
                generic_name=generic_name,
            )
        else:
            return AnalysisResult(
                full_analysis="⚠️ No response received from AI. Please try again.",
                success=False,
            )

    except Exception as e:
        return AnalysisResult(
            full_analysis=f"❌ Analysis Error: {str(e)}\n\nPlease try again or contact support.",
            success=False,
        )


def translate_analysis_if_needed(analysis: AnalysisResult, user_profile: Dict, model_choice: str) -> str:
    """Translate analysis into user's preferred language (optional)."""
    lang_label = user_profile.get("language", "English (en)")
    lang_code = SUPPORTED_LANG_CODES.get(lang_label, "en")

    if lang_code == "en":
        return ""  # No translation needed

    try:
        model = get_gemini_model(model_choice)
        prompt = f"""Translate the following medicine educational explanation into {lang_label}.

Keep the meaning accurate, keep emojis and headings if possible.
DO NOT add extra medical advice.

Text to translate:
{analysis.full_analysis}
"""
        response = model.generate_content(prompt)
        if response and hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception:
        return ""

    return ""


def chatbot_reply_gemini(
    question: str,
    user_profile: Dict,
    chat_history: List[Dict],
    model_choice: str,
) -> str:
    """Enhanced chatbot with better context awareness.

    ❗ Emergency detection is now handled *outside* this function on the raw user question.
    """
    try:
        model = get_gemini_model(model_choice)

        # Detect strongly prescriptive / dosing questions
        prescriptive_patterns = [
            "should i take", "should i use", "can i take", "can i use",
            "how many", "how much should", "what should i take",
            "is this safe for me", "can you prescribe", "recommend a medicine",
            "what medicine", "which medicine", "dose for me", "dosage for",
        ]

        question_lower = question.lower()
        if any(pattern in question_lower for pattern in prescriptive_patterns):
            # Still educational, but clearly explain limitation
            return """I understand you're looking for medical guidance, but I **cannot** provide personal medical advice, prescribe medicines, or suggest exact dosages.

**Why:**
- Safe treatment needs your full medical history and physical examination  
- Dosing and medicine choice depend on many personal factors  
- Drug interactions must be checked carefully by a doctor or pharmacist  

**What you can do:**
- 📞 Talk to your doctor or a licensed healthcare provider  
- 💊 Ask a registered pharmacist about your medicines  
- 📱 Use a trusted telemedicine service for a proper consultation  

**What I *can* help with:**
- Explaining how a type of medicine generally works  
- Describing common side effects and warnings (in a general way)  
- Clarifying medical terms or drug classes  

---

🔔 *This chatbot is for educational information only and does not replace professional medical advice.*"""

        # Build short conversation context (last few messages)
        context = ""
        if len(chat_history) > 1:
            context = "\n**PREVIOUS CONVERSATION (last few messages):**\n"
            for msg in chat_history[-6:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                content = msg["content"][:300]
                context += f"{role}: {content}\n\n"

        conditions_list = [c for c in user_profile.get("conditions", []) if c != "none"]

        profile_context = f"""
**USER PROFILE (for general education only):**
- Age Group: {user_profile.get('age_group', 'adult').title()}
- Medical Conditions: {', '.join(conditions_list) if conditions_list else 'None'}
- Allergies: {user_profile.get('allergies', 'None') or 'None'}
"""

        prompt = f"""You are a friendly, knowledgeable medical education chatbot. Your role is to provide clear, accurate educational information about medicines and health topics.

{profile_context}

{context}

**CURRENT USER QUESTION (may also contain context):** {question}

**RESPONSE GUIDELINES:**

✅ DO:
- Provide clear, evidence-based educational information
- Explain in simple language
- Use bullet points for lists when helpful
- Add context if useful, but keep the answer focused
- Encourage consulting healthcare professionals for personal advice

❌ DO NOT:
- Give personal medical advice or diagnoses
- Recommend specific medicines or dosages for the user
- Create treatment plans
- Claim certainty about an individual’s health situation

**FORMAT:**
- 2–4 short, clear paragraphs
- Bullet points if they make things clearer
- End with a one-line safety reminder

Provide your helpful, educational response:"""

        response = model.generate_content(prompt)

        if response and hasattr(response, "text") and response.text:
            reply = response.text.strip()

            disclaimer_keywords = ["educational", "not medical advice"]
            has_disclaimer = any(keyword in reply.lower() for keyword in disclaimer_keywords)

            if not has_disclaimer:
                reply += "\n\n---\n🔔 *This information is for educational purposes only and does not replace professional medical advice from a doctor or pharmacist.*"

            return reply
        else:
            return """I'm having trouble generating a response right now. Please try rephrasing your question or try again.

---

🔔 *This chatbot provides educational information only and does not replace professional medical advice.*"""

    except Exception as e:
        return f"""❌ I encountered an error while processing your question: {str(e)}

Please try again. If the problem persists, try rephrasing your question.

---

🔔 *This chatbot provides educational information only and does not replace professional medical advice.*"""


def extract_text_pytesseract(image: Image.Image) -> Dict[str, any]:
    """Fallback OCR with enhanced processing."""
    if not OCR_AVAILABLE:
        return {
            "success": False,
            "text": "",
            "error": "Tesseract OCR not installed.",
        }

    try:
        optimized_image = optimize_image(image)

        configs = [
            "--psm 6",
            "--psm 3",
            "--psm 11",
        ]

        best_text = ""
        for config in configs:
            text = pytesseract.image_to_string(optimized_image, config=config)
            if len(text) > len(best_text):
                best_text = text

        if best_text.strip():
            return {
                "success": True,
                "text": best_text.strip(),
                "error": None,
            }
        else:
            return {
                "success": False,
                "text": "",
                "error": "No text detected in image.",
            }

    except Exception as e:
        return {
            "success": False,
            "text": "",
            "error": f"OCR Error: {str(e)}",
        }

# ====================================
# UI COMPONENTS
# ====================================

def render_sidebar(model_choice_key: str = "model_choice"):
    """Render enhanced sidebar with user profile & controls."""
    with st.sidebar:
        st.title("👤 User Profile")
        st.caption("Your health info helps personalize safety warnings (education only).")

        with st.form("profile_form"):
            age_group = st.selectbox(
                "Age Group",
                ["child (0-12)", "teen (13-17)", "adult (18-64)", "senior (65+)"],
                index=2,  # default "adult (18-64)"
                help="Age affects medicine metabolism and safety.",
            )

            st.subheader("Medical Conditions")
            conditions = st.multiselect(
                "Known Medical Conditions",
                ALL_CONDITIONS,
                default=st.session_state.user_profile.get("conditions", []),
                help="Helps highlight potential medicine interactions.",
            )

            allergies = st.text_input(
                "Known Allergies",
                value=st.session_state.user_profile.get("allergies", ""),
                placeholder="e.g., penicillin, sulfa drugs, ibuprofen",
            )

            language = st.selectbox(
                "Preferred Language (for explanations)",
                list(SUPPORTED_LANG_CODES.keys()),
                index=list(SUPPORTED_LANG_CODES.keys()).index(
                    st.session_state.user_profile.get("language", "English (en)")
                ),
                help="English is the primary language. Others are translated.",
            )

            # Model choice (Streamlit manages st.session_state['model_choice'])
            st.radio(
                "AI Model",
                ["gemini-2.5-flash", "gemini-2.5-pro"],
                index=0,
                help="Flash is faster & cheaper; Pro is more powerful.",
                key=model_choice_key,
            )

            submitted = st.form_submit_button("💾 Save Profile")
            if submitted:
                age_simple = age_group.split()[0]
                st.session_state.user_profile = {
                    "age_group": age_simple,
                    "conditions": conditions,
                    "allergies": allergies,
                    "language": language,
                }
                st.success("✅ Profile saved successfully!")
                st.rerun()

        st.divider()

        if st.session_state.user_profile.get("conditions") or st.session_state.user_profile.get("allergies"):
            with st.expander("📋 Profile Summary", expanded=False):
                st.write(f"**Age:** {st.session_state.user_profile.get('age_group', 'adult').title()}")
                conditions = st.session_state.user_profile.get("conditions", [])
                if conditions and conditions != ["none"]:
                    st.write(f"**Conditions:** {', '.join(conditions)}")
                else:
                    st.write("**Conditions:** None")
                allergies = st.session_state.user_profile.get("allergies", "")
                st.write(f"**Allergies:** {allergies if allergies else 'None'}")

        st.divider()

        # API / System status
        st.subheader("System Status")
        col1, col2 = st.columns(2)
        with col1:
            st.caption("🤖 Gemini AI")
            st.caption("🔗 ✅ Ready" if GEMINI_AVAILABLE and GEMINI_API_KEY else "🔗 ⚠️ Check API key")
        with col2:
            st.caption("📝 Tesseract OCR")
            st.caption("🔗 ✅ Ready" if OCR_AVAILABLE else "🔗 ⚠️ Not installed")

        st.divider()

        st.error(
            """
**⚠️ IMPORTANT DISCLAIMER**

This app is **STRICTLY EDUCATIONAL**.

**❌ This app does NOT:**
- Provide medical advice
- Diagnose conditions
- Prescribe medicines
- Replace healthcare professionals

**✅ Always consult:**
- Your doctor for prescriptions
- Pharmacist for medicine questions
- Emergency services for urgent care

🚨 In an emergency: Call emergency services immediately.
        """
        )


def render_scan_history():
    """Show list of recent scans and bookmarks."""
    st.subheader("🕘 Recent Scans")
    history: List[Dict] = st.session_state.scan_history
    bookmarks: List[int] = st.session_state.bookmarks

    if not history:
        st.caption("No scans yet. Your recent analyses will appear here.")
        return

    for idx, item in enumerate(reversed(history)):
        real_idx = len(history) - 1 - idx
        ar = item["analysis"]
        with st.expander(
            f"{'⭐ ' if real_idx in bookmarks else ''}{ar.brand_name or 'Unknown Brand'} "
            f"({ar.generic_name or 'Generic name not detected'}) · {ar.timestamp}",
            expanded=False,
        ):
            st.markdown(ar.full_analysis)
            cols = st.columns(3)
            with cols[0]:
                if st.button("📥 Download This", key=f"dl_{real_idx}"):
                    st.download_button(
                        label="Download Text",
                        data=ar.full_analysis,
                        file_name=f"medicine_analysis_{real_idx}_{ar.timestamp.replace(':', '').replace(' ', '_')}.txt",
                        mime="text/plain",
                        key=f"dl_btn_{real_idx}",
                    )
            with cols[1]:
                if real_idx in bookmarks:
                    if st.button("⭐ Remove Bookmark", key=f"bm_remove_{real_idx}"):
                        st.session_state.bookmarks.remove(real_idx)
                        st.experimental_rerun()
                else:
                    if st.button("⭐ Bookmark", key=f"bm_add_{real_idx}"):
                        st.session_state.bookmarks.append(real_idx)
                        st.experimental_rerun()
            with cols[2]:
                if st.button("Use for Follow-up", key=f"use_{real_idx}"):
                    st.session_state.last_analysis = ar
                    st.success("This analysis is now set as the active one below.")
                    st.experimental_rerun()


def render_scanner_tab():
    """Render enhanced medicine scanner tab."""
    st.header("📸 Medicine Scanner & Analysis")
    st.markdown(
        """
Upload a medicine image **or** enter the label manually to get AI-powered **educational** analysis.
"""
    )

    # Quick start tips
    with st.expander("🧭 Quick Start Guide", expanded=False):
        st.markdown(
            """
1. Fill your **User Profile** in the left sidebar.  
2. Upload a clear photo of the **medicine strip / box / bottle**, or use the **Camera** below.  
3. (Optional) Type the label text manually if OCR is unclear.  
4. Click **“Analyze Medicine with AI”**.  
5. Scroll down to read the analysis and ask follow-up questions.
"""
        )

    col1, col2 = st.columns([1.2, 1])

    # LEFT: image & camera
    with col1:
        st.subheader("📷 Upload or Capture Image")

        img_source = st.radio(
            "Image Source",
            ["Upload from device", "Use camera"],
            horizontal=True,
        )

        uploaded_file = None
        camera_image = None

        if img_source == "Upload from device":
            uploaded_file = st.file_uploader(
                "Choose an image file",
                type=CONFIG["supported_formats"],
                help="Supported formats: JPG, JPEG, PNG, WEBP.",
            )
        else:
            camera_image = st.camera_input("Take a photo of the medicine label")

        image = None
        if uploaded_file:
            try:
                image = Image.open(uploaded_file)
            except Exception as e:
                st.error(f"❌ Error opening uploaded image: {e}")
        elif camera_image:
            try:
                image = Image.open(camera_image)
            except Exception as e:
                st.error(f"❌ Error opening captured image: {e}")

        ocr_method = None
        if image:
            st.image(image, caption="Selected Medicine Image", use_column_width=True)

            with st.expander("📸 Tips for Better Results"):
                st.markdown(
                    """
- Use good lighting, avoid shadows and glare  
- Keep camera steady and text in focus  
- Capture the label straight (not at an extreme angle)  
- Fill the frame with the text as much as possible
"""
                )

            ocr_method = st.radio(
                "Text Extraction Method:",
                ["🤖 Gemini Vision AI (Recommended)", "📝 Tesseract OCR"],
                help="Gemini Vision AI usually gives best results for medicine labels.",
            )

    # RIGHT: manual entry
    with col2:
        st.subheader("⌨️ Manual Text Entry")
        st.caption("Use this if image text is unclear or you want full control.")

        manual_text = st.text_area(
            "Medicine Label Information",
            placeholder="""Example:

Dolo 650
Paracetamol Tablets IP
Strength: 650 mg
Mfg: January 2024
Exp: December 2026
Batch: DL123456
Manufacturer: Micro Labs Ltd""",
            height=260,
        )

        st.info(
            "💡 **Tip:** Include medicine name, strength, Mfg/Exp date, batch no., and manufacturer for best analysis."
        )

    st.divider()

    # Analysis options
    st.subheader("🧪 Analysis Options")
    cols = st.columns(2)
    with cols[0]:
        analysis_length_choice = st.radio(
            "Detail Level",
            ["Short overview (Recommended)", "Detailed report"],
            index=0,
            help="Short overview gives key points. Detailed report explains everything in depth.",
        )
    with cols[1]:
        # Show currently selected model from sidebar
        st.markdown("**AI Model in use:**")
        st.code(st.session_state.model_choice, language="text")

    analysis_type = "short" if "Short" in analysis_length_choice else "long"

    analyze_button = st.button(
        "🔬 Analyze Medicine with AI",
        type="primary",
        help="Click to start AI-powered medicine analysis.",
    )

    if analyze_button:
        model_choice = st.session_state.model_choice
        extracted_text = ""
        extraction_result = None
        has_image = image is not None

        # Step 1: image OCR
        if has_image and ocr_method:
            with st.spinner("🔍 Extracting text from image..."):
                if "Gemini" in ocr_method:
                    extraction_result = extract_text_from_image_gemini(image, model_choice=model_choice)
                else:
                    extraction_result = extract_text_pytesseract(image)

                if extraction_result["success"]:
                    extracted_text = extraction_result["text"]
                    st.success("✅ Text extracted successfully!")

                    with st.expander("📝 View Extracted Text", expanded=True):
                        st.text_area(
                            "Extracted Information:",
                            extracted_text,
                            height=200,
                            key="extracted_display",
                        )
                else:
                    st.warning(f"⚠️ {extraction_result['error']}")
                    st.info("💡 You can edit or retype the label in the manual text box on the right.")

        # Step 2: Decide final text to analyze
        text_to_analyze = manual_text.strip() if manual_text.strip() else extracted_text.strip()

        if text_to_analyze:
            is_valid, validation_msg = validate_medicine_text(text_to_analyze)
            if not is_valid:
                st.warning(f"⚠️ {validation_msg}")
            else:
                with st.spinner("🤖 Analyzing medicine with Gemini AI..."):
                    analysis = analyze_medicine_with_gemini(
                        text_to_analyze,
                        st.session_state.user_profile,
                        analysis_type=analysis_type,
                        model_choice=model_choice,
                    )

                if analysis.success:
                    st.balloons()
                    st.success("✅ Analysis Complete!")

                    # Save to session
                    st.session_state.last_analysis = analysis
                    st.session_state.scan_history.append({"analysis": analysis})
                    if len(st.session_state.scan_history) > CONFIG["scan_history_limit"]:
                        st.session_state.scan_history = st.session_state.scan_history[-CONFIG["scan_history_limit"] :]

                else:
                    st.error("❌ Analysis failed. Please try again or check your input.")
                    with st.expander("Error Details"):
                        st.text(analysis.full_analysis)
                    st.session_state.last_analysis = None
        else:
            if not has_image and not manual_text.strip():
                st.warning("⚠️ Please upload/capture an image OR enter medicine text to analyze.")
            elif has_image and not manual_text.strip() and not extracted_text:
                st.info("💡 OCR could not extract text. Please enter the medicine details manually.")

    # Show latest analysis + follow-up chatbot
    if st.session_state.last_analysis and st.session_state.last_analysis.success:
        last: AnalysisResult = st.session_state.last_analysis

        st.markdown("---")
        st.subheader("🧾 Latest Analysis")

        risk = last.risk_level or "⚠️ USE WITH CAUTION"
        if "✅" in risk:
            st.success(f"**Safety Assessment (Educational):** {risk}")
        elif "🛑" in risk:
            st.error(f"**Safety Assessment (Educational):** {risk}")
        else:
            st.warning(f"**Safety Assessment (Educational):** {risk}")

        st.caption(f"🕒 Generated at: {last.timestamp}")

        st.markdown(last.full_analysis)

        # Translation (if needed)
        translated = translate_analysis_if_needed(last, st.session_state.user_profile, st.session_state.model_choice)
        if translated:
            with st.expander("🌐 View Translated Version"):
                st.markdown(translated)

        st.download_button(
            label="📥 Download Analysis Report",
            data=last.full_analysis,
            file_name=f"medicine_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
        )

        st.markdown("---")
        st.subheader("💬 Ask More About This Medicine")
        st.caption("Ask follow-up questions about **this same medicine** (education only).")

        col_q1, col_q2 = st.columns([5, 1])
        with col_q1:
            followup_question = st.text_input(
                "Your follow-up question",
                placeholder="e.g., Is this medicine an antibiotic?",
                key="scanner_followup_input",
                label_visibility="collapsed",
            )
        with col_q2:
            followup_ask = st.button("🚀 Ask", key="scanner_followup_ask")

        st.markdown("**Suggested questions:**")
        sq_col1, sq_col2, sq_col3 = st.columns(3)
        sugg1 = sq_col1.button("What is this used for?", key="scanner_sugg1")
        sugg2 = sq_col2.button("Common side effects?", key="scanner_sugg2")
        sugg3 = sq_col3.button("Any precautions?", key="scanner_sugg3")

        trigger_followup = False
        question_to_send = ""

        if followup_ask and followup_question.strip():
            trigger_followup = True
            question_to_send = followup_question.strip()
        elif sugg1:
            trigger_followup = True
            question_to_send = "What is this medicine mainly used for?"
        elif sugg2:
            trigger_followup = True
            question_to_send = "What are the common side effects of this medicine?"
        elif sugg3:
            trigger_followup = True
            question_to_send = "What precautions should I know before using this medicine?"

        if trigger_followup:
            # Emergency check only on the RAW user question
            if detect_emergency_keywords(question_to_send):
                bot_response = """🚨 Your question sounds potentially urgent.

I am **not** an emergency service and cannot safely guide you in emergencies.

**Please immediately:**
- Contact your local emergency number, or  
- Go to the nearest hospital / emergency room.

---

🔔 This chatbot is for educational information only and cannot handle emergencies."""
            else:
                compound_question = f"""Context: The user scanned a medicine with this label:

{last.source_text or '[no source text stored]'}

You generated this educational analysis earlier:

{last.full_analysis}

Now the user has this follow-up question about **the same medicine**:
"{question_to_send}"

Using ONLY this educational context, answer clearly without giving personal medical advice or dosages.
"""

                with st.spinner("🤖 Thinking about your follow-up question..."):
                    st.session_state.chat_history.append(
                        {
                            "role": "user",
                            "content": question_to_send,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

                    bot_response = chatbot_reply_gemini(
                        compound_question,
                        st.session_state.user_profile,
                        st.session_state.chat_history,
                        model_choice=st.session_state.model_choice,
                    )

                    st.session_state.chat_history.append(
                        {
                            "role": "assistant",
                            "content": bot_response,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                    )

            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(bot_response)

    st.markdown("---")
    render_scan_history()


def render_chatbot_tab():
    """Render enhanced chatbot tab."""
    st.header("💬 Medicine Education Chatbot")
    st.markdown(
        """
Ask questions about medicines, their uses, side effects, and more.  
You’ll get **clear, educational explanations** (no prescriptions or dosages).
"""
    )

    # If there is a last scanned medicine, show a small summary + option to link question
    link_to_last = False
    if st.session_state.last_analysis and st.session_state.last_analysis.success:
        last: AnalysisResult = st.session_state.last_analysis
        with st.expander("📦 Last scanned medicine context (optional)", expanded=True):
            st.write(f"**Brand (detected):** {last.brand_name or 'Unknown'}")
            st.write(f"**Generic (detected):** {last.generic_name or 'Unknown'}")
            st.caption("You can choose to link your question to this medicine.")
            link_to_last = st.checkbox(
                "Relate my question to the last scanned medicine",
                value=True,
                help="If enabled, the chatbot will use the last analysis as context.",
            )

    col1, col2 = st.columns([5, 1])
    with col1:
        user_question = st.text_input(
            "💭 Your Question",
            placeholder="e.g., What are antibiotics? How does Paracetamol work?",
            key="chat_input",
            label_visibility="collapsed",
        )
    with col2:
        ask_button = st.button("🚀 Ask", type="primary")

    st.markdown("**Suggested questions:**")
    s_col1, s_col2, s_col3 = st.columns(3)
    s1 = s_col1.button("What is Paracetamol used for?", key="main_sugg1")
    s2 = s_col2.button("Side effects of Ibuprofen?", key="main_sugg2")
    s3 = s_col3.button("What are antibiotics?", key="main_sugg3")

    trigger_ask = False
    question_to_send = ""

    if ask_button and user_question.strip():
        trigger_ask = True
        question_to_send = user_question.strip()
    elif s1:
        trigger_ask = True
        question_to_send = "What is Paracetamol used for?"
    elif s2:
        trigger_ask = True
        question_to_send = "What are the common side effects of Ibuprofen?"
    elif s3:
        trigger_ask = True
        question_to_send = "What are antibiotics and how do they work?"

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear Chat History"):
            st.session_state.chat_history = []
            st.success("Chat cleared!")
            st.rerun()

    with col2:
        if st.session_state.chat_history:
            chat_export = "\n\n".join(
                [
                    f"{'User' if msg['role']=='user' else 'Bot'} ({msg.get('timestamp','')}): {msg['content']}"
                    for msg in st.session_state.chat_history
                ]
            )
            st.download_button(
                label="📥 Export Chat",
                data=chat_export,
                file_name=f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
            )

    if trigger_ask:
        # Always show what the user actually typed in history
        st.session_state.chat_history.append(
            {
                "role": "user",
                "content": question_to_send,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
        )

        # Emergency check ONLY on the raw question
        if detect_emergency_keywords(question_to_send):
            bot_response = """🚨 Your question sounds potentially urgent.

I am **not** an emergency service and cannot safely guide you in emergencies.

**Please immediately:**
- Contact your local emergency number, or  
- Go to the nearest hospital / emergency room.

---

🔔 This chatbot is for educational information only and cannot handle emergencies."""
        else:
            # Build effective prompt, optionally including context of last scanned medicine
            effective_prompt = question_to_send
            if link_to_last and st.session_state.last_analysis and st.session_state.last_analysis.success:
                last: AnalysisResult = st.session_state.last_analysis
                effective_prompt = f"""Context: The user previously scanned this medicine:

Label information:
{last.source_text or '[no label text stored]'}

You generated this educational analysis earlier:
{last.full_analysis}

Now the user asks this question about medicines:
"{question_to_send}"

If it clearly refers to the above medicine, answer with that context in mind.
Otherwise, answer in general. 
Do NOT give personal medical advice or dosages."""

            with st.spinner("🤖 AI is thinking..."):
                bot_response = chatbot_reply_gemini(
                    effective_prompt,
                    st.session_state.user_profile,
                    st.session_state.chat_history,
                    model_choice=st.session_state.model_choice,
                )

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": bot_response,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
        )

        if len(st.session_state.chat_history) > CONFIG["chat_history_limit"]:
            st.session_state.chat_history = st.session_state.chat_history[-CONFIG["chat_history_limit"] :]

        st.rerun()

    st.divider()

    if st.session_state.chat_history:
        for message in st.session_state.chat_history:
            timestamp = message.get("timestamp", "")
            if message["role"] == "user":
                with st.chat_message("user", avatar="👤"):
                    st.write(message["content"])
                    if timestamp:
                        st.caption(f"🕒 {timestamp}")
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(message["content"])
                    if timestamp:
                        st.caption(f"🕒 {timestamp}")
    else:
        st.info(
            """
👋 **Welcome to the Medicine Education Chatbot!**

Example questions:

- What is Paracetamol used for?  
- How do antibiotics work?  
- What are the side effects of Ibuprofen?  
- What is the difference between generic and brand name medicines?

---

🔔 **Reminder:** This chatbot is for **educational information only** and cannot give personal medical advice or prescriptions.
"""
        )


def render_about_tab():
    """About & Help tab."""
    st.header("ℹ️ About & Help")

    st.markdown(
        """
### 💊 Medicine Scanner & Education System

This app helps you:

- 🔍 Scan medicine labels from images or camera  
- ✏️ Enter label text manually  
- 🤖 Get AI-powered **educational explanations** about medicines  
- 💬 Ask follow-up questions through a chatbot  

### 🧠 What this app is **for**

- Learning how medicines are commonly used  
- Understanding common side effects & warnings (in a general way)  
- Getting simplified explanations of drug classes and terms  

### 🚫 What this app is **NOT** for

- Diagnosing any medical condition  
- Replacing doctors, pharmacists, or emergency services  
- Giving you doses, prescriptions, or personalized treatment plans  

### 🔐 Privacy

- All data stays in your current session in this browser tab  
- Nothing is stored permanently by this app itself  

---

If you’re building this project:

- Backend: **Streamlit + Gemini**  
- You can host it on platforms like **Streamlit Community Cloud**  
- Set secrets (API keys) via Streamlit’s **Secrets Manager**
"""
    )


# ====================================
# MAIN APPLICATION
# ====================================

def main():
    st.set_page_config(
        page_title="Medicine Scanner & Education System",
        page_icon="💊",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": "Medicine Scanner & Education System (Educational use only)",
        },
    )

    # Session state init
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = {
            "age_group": "adult",
            "conditions": [],
            "allergies": "",
            "language": "English (en)",
        }
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "last_analysis" not in st.session_state:
        st.session_state.last_analysis = None
    if "scan_history" not in st.session_state:
        st.session_state.scan_history = []
    if "bookmarks" not in st.session_state:
        st.session_state.bookmarks = []
    if "model_choice" not in st.session_state:
        st.session_state.model_choice = "gemini-2.5-flash"

    # Setup API
    if not GEMINI_AVAILABLE:
        st.error("❌ **Critical Error: `google-generativeai` library not found!**")
        st.code("pip install google-generativeai", language="bash")
        st.stop()

    if not setup_gemini_api():
        st.error("❌ **Failed to configure Gemini API**")
        st.info("Please check your API key.")
        st.stop()

    # Sidebar (creates model_choice widget)
    render_sidebar()

    # Main header
    st.title("💊 Medicine Scanner & Education System")
    st.caption("🤖 AI-Powered Educational Platform | Not a substitute for professional medical care")

    tab1, tab2, tab3 = st.tabs(
        [
            "🔍 Medicine Scanner",
            "💬 Medicine Chatbot",
            "ℹ️ About & Help",
        ]
    )

    with tab1:
        render_scanner_tab()
    with tab2:
        render_chatbot_tab()
    with tab3:
        render_about_tab()

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("📅 Last Updated: Nov 30, 2025")
    with col2:
        st.caption("🔧 Version 3.2 (Emergency Fix)")
    with col3:
        st.caption("💡 Educational Use Only · Always consult a doctor")


if __name__ == "__main__":
    main()
