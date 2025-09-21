# GPT Builder Guide

These steps wire the custom Operating Assistant GPT to your deployed API plus documentation bundle.

---

## 1. Confirm the backend is ready
- Render service responding on `/api/state` and `/api/commands`.
- `client/sender.py` running locally and printing `API SYNC OK`.
- `COMMAND_TOKEN` is the same value in Render, the sender config, and your notes.

---

## 2. Build the GPT shell
1. Go to [chatgpt.com](https://chatgpt.com/), open **GPTs**, and click **Create**.
2. Give the GPT a name, short description, and optional avatar image.
3. Copy the contents of `GPT/prompt.txt` into the **Instructions** field.
4. Upload every file from `GPT/documentation/` so the OA has manuals and checklists to cite.

---

## 3. Add the Render action
1. In the builder, open **Actions → Add Action**.
2. Paste the schema from `GPT/action.yaml`. Change `https://your-render-service.onrender.com/api` to match your Render base URL.
3. In **Authentication**, choose **API Key** and set:
   - Header name: `X-Command-Token`
   - Value: your command token (same as in Render and `client/config.json`)
4. Save the action and use the **Test Action** tab to queue a tiny command. You should receive a 200 response if the token matches.

---

## 4. Publish and validate
1. Click **Save** (and **Publish/Update** if shown) so the new manifest is live.
2. Start a **new chat** with the GPT—existing chats cache the old manifest.
3. Ask the OA to fetch telemetry or set a simple value. Watch your Render logs for a `200` on `/api/commands`.

Done! The GPT now has instructions, documentation, and a working action targeting your Render service.
