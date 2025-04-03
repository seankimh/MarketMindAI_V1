from flask import Flask, render_template, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import requests
import os
from dotenv import load_dotenv  # Fixed typo: load_potenv → load_dotenv

load_dotenv()

app = Flask(__name__)

# Google Sheets Setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = "service_account.json"
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

# OpenRouter Setup
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEEPSEEK_MODEL = "deepseek/deepseek-r1:free"  # Corrected model name (was DeepSeek_R1_key)
SHEET_URL = os.getenv("SHEET_URL")

def clean_numeric(value):
    """Convert currency/percentage strings to floats safely"""
    try:
        if isinstance(value, str):
            cleaned = value.replace('$', '').replace(',', '').replace('%', '').strip()
            return float(cleaned) if cleaned else 0.0
        return float(value) if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        # Fetch and prepare data
        sheet = client.open_by_url(SHEET_URL).sheet1
        records = sheet.get_all_records()
        
        analysis_data = []
        for row in records:
            analysis_data.append({
                "Ticker": str(row.get("Ticker", "N/A")),
                "Price": clean_numeric(row.get("Price")),
                "PE_Ratio": clean_numeric(row.get("P/E Ratio")),
                "EPS": clean_numeric(row.get("EPS")),
                "52W_High": clean_numeric(row.get("50-Watch High")),
                "From_High": f"{clean_numeric(row.get('%', 0))}%",
                "Volume": int(clean_numeric(row.get("Volume(Today)", 0))),
                "Beta": clean_numeric(row.get("Beta (Volatility)"))
            })

        # Generate analysis prompt
        data_str = "\n".join([
            f"{d['Ticker']}: ${d['Price']:.2f} | P/E {d['PE_Ratio']:.1f} | "
            f"EPS {d['EPS']:.2f} | {d['From_High']} from 52W High | "
            f"Vol {d['Volume']:,.0f} | Beta {d['Beta']:.2f}"
            for d in analysis_data
        ])

        prompt = f"""
        Analyze these stocks based on:
        {data_str}

        Focus on:
        1. Valuation (P/E ratios vs sector averages)
        2. Momentum (% from 52-week highs)
        3. Risk (Beta volatility)
        4. Growth (EPS trends)

        Provide:
        - Top 3 buys with price targets
        - 3 stocks to avoid
        - Market sentiment summary
        """

        # Call DeepSeek with proper headers
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:5000",  # Required by OpenRouter
            "X-Title": "Stock Analysis Tool",         # Required by OpenRouter
            "Content-Type": "application/json"
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            },
            timeout=30
        )

        if response.status_code == 200:
            prediction = response.json()["choices"][0]["message"]["content"]
            return jsonify({
                "success": True,
                "prediction": prediction,
                "raw_data": analysis_data
            })
        return jsonify({
            "success": False,
            "error": f"API request failed: {response.text}",
            "status_code": response.status_code
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

if __name__ == "__main__":
    app.run(debug=True)