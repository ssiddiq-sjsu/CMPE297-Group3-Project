# CMPE297-Group3-Project
# Vacay Plan — Vacation Planning Website

A local web app to plan vacations: choose home airport, dates, destination, budget, and activity types. The backend uses in-memory Python variables and **stub (uncompleted) functions** for flight/hotel/activity processing.

## Features

- **Welcome page** with a call-to-action to start planning
- **New trip form**: home airport (dropdown), departure date, destination (dropdown), return date
- **Budget slider** (e.g. $500–$15,000)
- **Activity checkboxes**: museum, park, rental car, beach, hiking, dining, nightlife, shopping
- **Output text area** showing the generated plan (placeholder until real APIs are connected)

## Setup

```bash
cd /path/to/website_test
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

Default port is **5000**. Override with the `PORT` environment variable:

```bash
# Default: http://127.0.0.1:5000 (local only)
python server.py

# Custom port, e.g. 8080
PORT=8080 python server.py

# Listen on all interfaces (0.0.0.0) so other devices on the network can connect
LISTEN_ALL=1 python server.py
# Or explicitly:
HOST=0.0.0.0 python server.py
```

Then open `http://127.0.0.1:5000` (or your chosen port) in a browser. If using `LISTEN_ALL=1`, use your machine’s IP and port from other devices.

## Backend

- **Config**: `config.py` — `PORT`, `HOST`, `DEBUG` (env: `PORT`, `HOST`, `DEBUG`)
- **Data**: Trips are stored in the `TRIPS` list; airports and destinations are preset in `server.py`
- **Stubs**: `search_flights()`, `search_hotels()`, `search_activities()` are unimplemented; `build_trip_plan()` returns a text summary and placeholders. Replace these with real API calls when ready.

## Project layout

```
website_test/
├── config.py          # Port & host config
├── server.py          # Flask app, APIs, stub logic
├── requirements.txt
├── README.md
└── static/
    ├── index.html
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```
