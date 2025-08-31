# Nucleares Operating Assistant API

This project provides an API backend and client for connecting the game **Nucleares** with a GPT-powered “Operating Assistant.”  
It collects live telemetry data from the in-game plant webserver, forwards it to a cloud API (Render), and makes it accessible to GPT agents for reasoning and operator guidance.

## How it works
1. Start the webserver in game (`http://localhost:8785`).  
2. Run the client (`sender.py`), which routes all telemetry to the cloud API.  
3. The GPT Operating Assistant calls the API via `/api/state` to read the latest plant conditions.  
4. GPT uses both the manuals and the live state to answer operator questions and guide gameplay.

## Deployment
The server is designed to run on [Render](https://render.com).  
- Python 3.11+  
- FastAPI + Uvicorn  
- HMAC signature validation for client POSTs.  

See `render.yaml` for service configuration.

---

## 🔒 Privacy

This API is designed **only for simulation/gameplay purposes**.  

- **What data is collected:**  
  - Only **plant status variables** exposed by the Nucleares game (e.g. temperatures, pressures, valve states).  
  - A timestamp of when the data was last updated.  

- **What data is not collected:**  
  - No personal, sensitive, or user-identifiable data is collected, stored, or transmitted.  
  - No chat content, account information, or system details are recorded.  

- **How the data is used:**  
  - Data is sent from the local client to the API.  
  - It is stored in memory only for the current snapshot.  
  - It is retrieved by the GPT “Operating Assistant” **solely to answer questions about the plant simulation**.  
  - No logs, databases, or historical storage are kept.  

- **Retention:**  
  - Data is overwritten with each update.  
  - If the client is not running, no new data is uploaded.  

This ensures the system is safe for public GPT usage and only reflects **game simulation telemetry**.
