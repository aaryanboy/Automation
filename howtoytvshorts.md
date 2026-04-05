# Project Context: Flask YouTube Shorts Uploader

This file is meant to be read by an AI coding assistant
to understand the full context of this project before writing or editing any code.

---

## What This Project Does

A Flask web application that authenticates with Google OAuth 2.0 and uploads videos
to YouTube using the YouTube Data API v3. The upload feature is one part of a larger
project — this module specifically handles the final "post to YouTube" step.

The uploaded videos are intended to qualify as YouTube Shorts (vertical, ≤60 seconds,
#Shorts in description).

---

## Tech Stack

- **Backend:** Python 3, Flask
- **Auth:** Google OAuth 2.0 via `google-auth-oauthlib`
- **YouTube API:** YouTube Data API v3 via `google-api-python-client`
- **Token storage:** Pickle file (`token.pkl`) — local only, never committed
- **Video:** Pre-existing `.mp4` file passed to the uploader (not recorded in-app)

---

## Dependencies

```
flask
google-api-python-client
google-auth-httplib2
google-auth-oauthlib
```

Install with:
```bash
pip install flask google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

---

## Project File Structure

```
project/
├── app.py                  ← Main Flask app (auth + upload logic)
├── credentials.json        ← OAuth client secret from Google Cloud Console (never commit)
├── token.pkl               ← Auto-generated after first login (never commit)
├── test_short.mp4          ← Test video file (vertical, ≤60s)
├── requirements.txt        ← Pip dependencies
├── .gitignore              ← Must exclude credentials.json and token.pkl
└── README.md
```

---

## Google Cloud Setup (Already Done / To Be Done)

1. Project created in Google Cloud Console
2. YouTube Data API v3 enabled
3. OAuth 2.0 Client ID created — type: **Web Application** (not Desktop)
4. Authorized Redirect URI set to: `http://localhost:5000/callback`
5. `credentials.json` downloaded and placed in project root

---

## OAuth Flow (How Auth Works in Flask)

Unlike a pure Python script (which opens a browser popup directly), Flask OAuth works like this:

```
User visits /login
    → Flask builds Google auth URL using credentials.json
    → User is redirected to Google login page
    → After login, Google redirects to /callback with an auth code
    → Flask exchanges the code for credentials (access token + refresh token)
    → Credentials saved to token.pkl
    → User redirected to homepage
```

Key detail: The redirect URI in the code MUST exactly match what is registered
in Google Cloud Console. For local dev: `http://localhost:5000/callback`

Environment variable required for local HTTP (dev only):
```python
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
```
Remove this line in production (use HTTPS).

---

## Upload Logic (How the YouTube Upload Works)

1. Load credentials from `token.pkl`
2. Auto-refresh token if expired (using `creds.refresh(Request())`)
3. Build YouTube API client: `build("youtube", "v3", credentials=creds)`
4. Construct video metadata body (title, description, tags, categoryId, privacyStatus)
5. Use `MediaFileUpload` with `resumable=True` for reliable upload
6. Call `youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()`
7. Response contains `video_id` — construct URL as `https://youtube.com/shorts/{video_id}`

---

## YouTube Shorts Requirements

For YouTube to classify the video as a Short, ALL of these must be true:

| Requirement | Value |
|---|---|
| Duration | 60 seconds or less |
| Aspect ratio | 9:16 vertical (1080×1920 recommended) |
| Description | Must contain `#Shorts` |
| Tags | Should include `"Shorts"` |

---

## API Scopes Used

```python
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
```

Only the upload scope is requested. Do not add broader scopes unless needed.

---

## Video Metadata Structure

```python
body = {
    "snippet": {
        "title": "Your Short Title",
        "description": "Your description here. #Shorts",
        "tags": ["tag1", "tag2", "Shorts"],
        "categoryId": "22"   # 22 = People & Blogs
    },
    "status": {
        "privacyStatus": "private"  # "private" | "unlisted" | "public"
    }
}
```

During testing, always use `"private"` so nothing goes public accidentally.

---

## Flask Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Homepage — shows login or upload button based on auth state |
| `/login` | GET | Starts Google OAuth flow, redirects to Google |
| `/callback` | GET | Google redirects here after login, saves token |
| `/logout` | GET | Deletes token.pkl, resets auth state |
| `/upload` | GET | Loads token, uploads test_short.mp4 to YouTube |

---

## Token Handling Rules

- Token is saved as `token.pkl` using `pickle.dump(creds, f)`
- Token is loaded with `pickle.load(f)`
- Before using, check: `if creds.expired and creds.refresh_token: creds.refresh(Request())`
- After refresh, save the updated token back to file
- If token file is missing, redirect user to `/login`

---

## Error Handling Expectations

The upload route should handle:
- Missing video file → show clear error, do not crash
- Expired/invalid token → redirect to `/login`
- API errors (quota exceeded, bad request) → catch exception, show error message with details
- Successful upload → show video ID and YouTube URL

---

## Security Rules

- `credentials.json` and `token.pkl` must NEVER be committed to version control
- `.gitignore` must include both files
- `OAUTHLIB_INSECURE_TRANSPORT = "1"` is for local dev only — remove for production
- In production, use HTTPS and store credentials securely (env vars or secret manager)

---

## Current State of the Project

- [x] Auth flow works (login → callback → token saved)
- [x] Upload route implemented
- [x] Test upload set to `private`
- [ ] Full project integration (this upload module will be called from a larger app)
- [ ] Production deployment
- [ ] Dynamic video path (currently hardcoded to `test_short.mp4`)

---

## Known Constraints

- YouTube Data API v3 free quota: **10,000 units/day**
- One video upload costs: **~1,600 units**
- Max uploads per day on free tier: **~6**
- Quota resets at midnight Pacific Time
- To increase quota: apply via Google Cloud Console → APIs → YouTube Data API v3 → Quotas

---

## What the AI Should Know When Helping

- This is NOT a pure Python script — it is a Flask web app with proper routes
- OAuth uses the web application flow with a `/callback` redirect URI, NOT `run_local_server()`
- The upload is the FINAL step of a larger pipeline — keep the upload function modular
- Do not suggest switching to pure Python — Flask is intentional
- Privacy status should default to `"private"` unless explicitly changed
- Always include `#Shorts` in the description for proper YouTube classification
- The project is in active development — keep code clean and easy to extend