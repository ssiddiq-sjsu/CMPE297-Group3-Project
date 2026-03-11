## 🚀 Quick Start

Follow these steps to set up and run the AI Travel Planner locally.

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/ssiddiq-sjsu/CMPE297-Group3-Project.git
cd CMPE297-Group3-Project
git checkout Streamlit_App
```

### 2️⃣ Set Up Virtual Environment

```bash
python -m venv venv
```

Activate the environment:

**Mac / Linux**
```bash
source venv/bin/activate
```

**Windows**
```bash
venv\Scripts\activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Configure Environment Variables

Create a `.env` file in the root directory and add your API keys:

```bash
echo "AMADEUS_CLIENT_ID=your_key_here" > .env
echo "AMADEUS_SECRET=your_secret_here" >> .env
echo "OPENAI_API_KEY=your_openai_key_here" >> .env
echo "PHQ_API_KEY=your phq api key here" >> .env
```

Or manually create a `.env` file with:

```env
AMADEUS_CLIENT_ID=your_key_here
AMADEUS_SECRET=your_secret_here
OPENAI_API_KEY=your_openai_key_here
```

### 5️⃣ Run the Application

```bash
cd final_streamlit_bot
streamlit run app.py
```

---

✅ Once running, open the local URL shown in your terminal (usually `http://localhost:8501`) in your browser.
