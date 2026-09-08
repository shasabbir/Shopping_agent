# 🇧🇩 Bangladesh AI Shopping Decision Agent

An agentic AI shopping assistant specialized in Bangladesh's e-commerce ecosystem. Unlike traditional search engines, it doesn't just return product links—it acts as an **expert buyer's assistant**, evaluating trade-offs, calculating value scores, highlighting official vs. gray-market warranty warnings, and explaining **"Why Buy"** and **"Why NOT to Buy"**.

Built using **LangGraph**, **Google Gemini**, **DuckDuckGo**, and **Jina AI Reader**.

---

## 🌟 Key Features
- **4-Node Agentic Pipeline (LangGraph):**
  1. **Requirement Analyzer:** Extracts structured constraints (category, budget in BDT, priorities) and supports multilingual inputs (English, Bangla, Banglish).
  2. **Search Coordinator:** Executes targeted DuckDuckGo searches across top Bangladeshi tech stores (Star Tech, Ryans Computers, Daraz BD, Pickaboo).
  3. **Product Extractor & Normalizer:** Uses Jina AI Reader (`r.jina.ai`) to strip HTML/scripts and extract clean product specs, prices, and warranties.
  4. **Recommendation & Decision Agent:** Scores products, ranks top picks, generates trade-offs, and issues Bangladesh market buying guidance.
- **$0 Free-Tier Stack:** Runs with zero mandatory API costs.
- **Offline & Mock Mode:** Graceful fallback support for offline development, rate limits, or environments without API keys.

---

## 🚀 Quickstart

### 1. Prerequisites
- Python 3.11+ (Python 3.13 tested)

### 2. Setup Virtual Environment
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure Environment Variables (Optional)
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Add your free Google Gemini API key from [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-flash
```
*(Note: If `GEMINI_API_KEY` is omitted, the agent seamlessly operates in offline/mock mode for testing.)*

---

## 💻 CLI Usage

Run interactive prompt:
```powershell
.\.venv\Scripts\python.exe main.py
```

Or pass a query directly:
```powershell
.\.venv\Scripts\python.exe main.py --query "I need a gaming laptop under 120000 BDT in Bangladesh"
```

### Example Queries:
- `Suggest best phone under 45k taka with great camera`
- `Need a monitor under 20000 BDT for programming and daily work`
- `amar 30k er moddhe bhalo phone lagbe` *(Banglish support)*

## 🌐 Streamlit Web UI (Week 2)

Launch the interactive web interface:
```powershell
.\.venv\Scripts\streamlit.exe run app.py
```
Open your browser at `http://localhost:8501`.

### Web Features:
- **Hero Card:** Highlights the winning recommendation with value score, BDT price, and direct retailer button.
- **Product Grid:** Responsive cards with CPU/GPU/RAM/Camera tags, "Why Buy", "Why NOT Buy", and Bangladesh market notes.
- **Side-by-Side Comparison:** Interactive tabular matrix comparing products on specs, price, and warranty.
- **Real-Time LangGraph Stepper:** Visualizes the 4-node workflow as it executes live.
- **Quick-Start Chips:** Pre-built queries for Laptops, Phones, Monitors, and Banglish searches.

---

## 🧪 Testing

Run all unit and end-to-end tests:
```powershell
.\.venv\Scripts\pytest.exe -v tests/
```

---

## 🗺️ Roadmap
- [x] **Week 1:** LangGraph Core Pipeline + Search & Jina Extractor + CLI + Test Suite.
- [x] **Week 2:** Streamlit Web UI + Product Cards + Side-by-Side Comparison Matrix + Live Stepper.
- [ ] **Week 3:** Bangladesh Warranty Detection + Gray Market Price Gap Detector + Bangla Voice/Chat.
- [ ] **Week 4:** PostgreSQL Database + Price History + User Preferences Memory.


