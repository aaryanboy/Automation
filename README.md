---
title: Shorts
emoji: 🎬
colorFrom: red
colorTo: purple
sdk: docker
app_file: app.py
pinned: false
---

# YouTube Shorts Automation Bot

This web application automates the process of fetching videos (e.g., from TikTok) using `yt-dlp`, processing them via `FFmpeg` / `moviepy` to ensure they fit YouTube Shorts requirements (duration <= 3 mins, 9:16 aspect ratio), and uploading them directly to YouTube using the Google OAuth API.

## Local Development

### Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. You will need a `credentials.json` file from Google Cloud (OAuth 2.0 Client IDs for a Web application) placed in the root directory.
   - Authorized redirect URI for local: `http://localhost:5000/callback`

3. Run the application:
   ```bash
   $env:FLASK_ENV="development"
   python app.py
   ```
4. Visit `http://localhost:5000` to use the bot.

## Deployment to Hugging Face Spaces (Docker)

This repository includes a `Dockerfile` to easily deploy the application, configured specifically for Hugging Face Spaces (running on port `7860` as a non-root user).

### Secrets

When deploying to production in Hugging Face, you should set the following Secrets in your Space settings:

- `GOOGLE_CLIENT_ID`: Your Google OAuth Client ID
- `GOOGLE_CLIENT_SECRET`: Your Google OAuth Client Secret
- `FLASK_SECRET_KEY`: A secure random string to cryptographically sign session cookies

*Note: Make sure to add your production Space URL (e.g., `https://your-space-name.hf.space/callback`) to your Google Cloud Console "Authorized redirect URIs".*