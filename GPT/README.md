# User Guide
This document describes the setup of each component needed to get the full Operating Assistant GPT functionalities running
### **OpenAI Plus subscription is required to create a private GPT with API functionalities**  
![GPT plus](images/GPT1.png)

## Server Setup

1. Create a free [Render](https://render.com/) account
2. Create a new `Web Service`  
![New Web Svc](images/Server1.png)
3. Link this repo as source code
![Link Repo](images/Server2.png)
4. Everything should configure automatically, except for region - you want it as close to you as we care about POST latency
5. Choose Free `Instance Type`
6. Add, generate and save *(locally)* the `API_KEY` env variable
![Env Var](images/Server3.png)
7. Deploy the service

## GPT Setup

1. On [ChatGPTs website](https://chatgpt.com/), enter the `GPTs` category  
![GPTs](images/GPT2.png)
2. Click `+ Create` in top right corner  
![Create](images/GPT3.png)
3. Fill out `Name`, `Description`, upload image as you see fit
4. Copy contents of `prompt.txt` into the `Instructions` field  
![Filled GPT](images/GPT4.png)
5. Upload documentation from the `GPT/documentation` directory
![Filled Knowledge](images/GPT5.png)
6. Create new action
>If you want the GPT as public for some reason, you an set this repo as the privacy policy
7. Paste the `action.yaml` contents into the `Schema` field  
![Filled Schema](images/GPT6.png)
8. Replace `your-api-url` with your render API url set in [Server Setup](#server-setup)

## Client Setup

1. Fill out `client/config.json`
 - `API_URL`: your render API url set in [Server Setup](#server-setup)
 - `API_KEY`: your API key set in [Server Setup](#server-setup)
 - `GAME_URL`: http://localhost:8785 if default WebServer address set in game
2. Start `client/sender.py`  
![Client running](images/Client1.png)  
If everything is configured correctly and WebServer is running, the script will start synchronizing data with API
3. Client will have to be started every time the game is started again, and **killed manually** after its finished

## Use Cases

1. **Maintenance report**  
![Maintenance report request](images/maintenance_txt.png)  
2. **Remote SITREP**  
![Remote core status report image](images/chemical_pic.png)  
![Remote core status report](images/chemical_txt.png)  
3. **Emergency report**  
![Emergency situation assesment](images/emergency_txt.png)  
4. **Help with operation**  
![balance_txt image](images/balance_pic.png)  
![Steam generation balance support](images/balance_txt.png)  