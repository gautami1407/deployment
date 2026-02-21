from flask import Flask, render_template, redirect
import subprocess
import webbrowser
import time

app = Flask(__name__)

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LABEL_ANALYZER_PATH = os.path.join(BASE_DIR, "pages", "finalanalyzerbot.py")
BARCODE_ANALYZER_PATH = os.path.join(BASE_DIR, "pages", "barcode.py")
CHATBOT_PATH = os.path.join(BASE_DIR, "pages", "chatbot.py")
MEDICINE_ANALYZER_PATH = os.path.join(BASE_DIR, "pages", "medicines.py")
def start_streamlit(script_path):
    """Runs a Streamlit app and opens it in a browser."""
    subprocess.Popen(["streamlit", "run", script_path], shell=True)
    time.sleep(3)  # Give Streamlit some time to start
    webbrowser.open("http://localhost:8501")  # Open Streamlit default port

@app.route('/')
def home():
    return render_template('frontpage.html')

@app.route('/about')
def about():
    return render_template('aboutpage.html')

@app.route('/guidelines')
def guidelines():
    return render_template('guidelines.html')

@app.route('/helplines')
def helplines():
    return render_template('helplines.html')

@app.route('/start-scanning')
def start_scanning():
    start_streamlit(LABEL_ANALYZER_PATH)
    return redirect("http://localhost:8501")

@app.route('/start-barcode')
def start_barcode():
    start_streamlit(BARCODE_ANALYZER_PATH)
    return redirect("http://localhost:8501")

@app.route('/start-chatbot')
def start_chatbot():
    start_streamlit(CHATBOT_PATH)
    return redirect("http://localhost:8501")

@app.route('/start-medicine')
def start_medicine():
    start_streamlit(MEDICINE_ANALYZER_PATH)
    return redirect("http://localhost:8501")

if __name__ == "__main__":
    app.run(debug=True)
