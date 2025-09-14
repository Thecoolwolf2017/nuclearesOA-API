# Nucleares Operating Assistant API

This project provides an API backend and client for connecting the game **Nucleares** with a GPT-powered “Operating Assistant.”  
It collects live telemetry data from the in-game plant webserver, forwards it to a cloud API (Render), and makes it accessible to GPT agents for reasoning and operator guidance.

A stripped version of the assistant, without API capabilities can be found [HERE](https://chatgpt.com/g/g-68c7033fc76c819184cb9d619d5908fc-nucleares-oa)

## How it works
The GPT is fed data stored in `GPT/documentation`. It uses this data to help and guide the user in operating the in-game Nuclear Power Plant. A private copy of this GPT can be made by OpenAI Plus members, with the capability to query the game’s WebServer through the API. A guide describing the process, as well as example use cases, can be viewed in the GPT catalog. The API receives data from the sender script running locally, which routes it from the local webserver to a public one. The server uses a JSON schema to group and translate the data into a GPT-readable form, accessible through a public URL.

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
