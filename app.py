import os
import shutil
import tempfile
import subprocess

import flask
from flask import Flask, redirect, request, url_for
from datetime import timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

import imageio_ffmpeg
import yt_dlp

import google.oauth2.credentials
from google.auth.transport.requests import Request
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "shorts-secret")
app.permanent_session_lifetime = timedelta(days=90)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

DEV = os.environ.get("FLASK_ENV") == "development"
if DEV:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REDIRECT_URI = "http://localhost:5000/callback" if DEV else "https://god69851-shorts.hf.space/callback"
TEMP_DIR = "/tmp/shorts"
os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
def load_credentials():
    d = flask.session.get("credentials")
    if not d:
        return None
    creds = google.oauth2.credentials.Credentials(
        token=d["token"], refresh_token=d["refresh_token"],
        token_uri=d["token_uri"], client_id=d["client_id"],
        client_secret=d["client_secret"], scopes=d["scopes"],
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception:
            return None
    return creds


def _save_credentials(creds):
    flask.session.permanent = True
    flask.session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }


def _get_flow(state=None):
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csecret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if cid and csecret:
        cfg = {"web": {
            "client_id": cid,
            "client_secret": csecret,
            "project_id": "shorts",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [REDIRECT_URI],
        }}
        flow = google_auth_oauthlib.flow.Flow.from_client_config(cfg, scopes=SCOPES, state=state)
    else:
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            "credentials.json", scopes=SCOPES, state=state)
    flow.redirect_uri = REDIRECT_URI
    return flow


# ─────────────────────────────────────────────
# Video processing
# Always runs FFmpeg — guarantees:
#   • 1080x1920 (9:16) with black bars for non-vertical content
#   • AAC audio present every time
#   • Trimmed to 178s max
#   • +faststart for faster YouTube processing
# ─────────────────────────────────────────────
def process_for_shorts(input_path, tmp_dir, max_duration=178.0):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    fd, out = tempfile.mkstemp(suffix=".mp4", dir=tmp_dir)
    os.close(fd)

    result = subprocess.run([
        ffmpeg, "-y", "-i", input_path,
        "-t", str(max_duration),
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1"
        ),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        out,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode())
    return out


# ─────────────────────────────────────────────
# YouTube upload
# ─────────────────────────────────────────────
def upload_to_youtube(youtube, path, title, description, tags):
    if "#Shorts" not in description:
        description = (description + " #Shorts").strip()
    if "Shorts" not in tags:
        tags.append("Shorts")

    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=MediaFileUpload(path, chunksize=5 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        _, response = req.next_chunk()
    return response["id"]


# ─────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────
def render_page(logged_in, success=False, error=""):
    status_color = "#4ade80" if logged_in else "#6b7280"

    if logged_in:
        body_html = """
        <div class="input-row">
          <input type="url" id="url" placeholder="TikTok URL" autocomplete="off">
          <button class="paste-btn" onclick="doPaste()" title="Paste">&#x2398;</button>
        </div>
        <button class="post-btn" onclick="doSubmit()">Post</button>
        <a href="/logout" class="signout">sign out</a>
        """
    else:
        body_html = '<a href="/login" class="login-btn">Connect Google account</a>'

    toast_html = '<div class="toast">Uploaded successfully</div>' if success else ""
    error_html = f'<div class="error">{error}</div>' if error else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shorts Bot</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0e0e0e;
    color: #e8e8e8;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }}

  .wrap {{
    width: 100%;
    max-width: 360px;
  }}

  .title {{
    font-size: 17px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 6px;
  }}

  .status {{
    font-size: 12px;
    color: {status_color};
    margin-bottom: 28px;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .status::before {{
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: {status_color};
    display: inline-block;
    flex-shrink: 0;
  }}

  .input-row {{
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }}

  input[type=url] {{
    flex: 1;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    color: #e8e8e8;
    font-size: 14px;
    padding: 11px 14px;
    outline: none;
    transition: border-color 0.15s;
    min-width: 0;
  }}
  input[type=url]:focus {{ border-color: #555; }}
  input[type=url]::placeholder {{ color: #3a3a3a; }}

  .paste-btn {{
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    color: #666;
    font-size: 16px;
    padding: 0 13px;
    cursor: pointer;
    transition: color 0.15s;
    flex-shrink: 0;
  }}
  .paste-btn:hover {{ color: #e8e8e8; }}

  .post-btn {{
    width: 100%;
    background: #e8e8e8;
    color: #0e0e0e;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    padding: 12px;
    cursor: pointer;
    transition: background 0.15s;
    display: block;
  }}
  .post-btn:hover {{ background: #fff; }}

  .login-btn {{
    width: 100%;
    background: transparent;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    color: #e8e8e8;
    font-size: 14px;
    font-weight: 500;
    padding: 12px;
    cursor: pointer;
    text-decoration: none;
    display: block;
    text-align: center;
    transition: border-color 0.15s;
  }}
  .login-btn:hover {{ border-color: #555; }}

  .signout {{
    display: inline-block;
    margin-top: 14px;
    font-size: 12px;
    color: #3a3a3a;
    text-decoration: none;
    transition: color 0.15s;
  }}
  .signout:hover {{ color: #777; }}

  .error {{
    font-size: 13px;
    color: #f87171;
    margin-bottom: 16px;
    line-height: 1.5;
    word-break: break-word;
  }}

  /* Loading overlay */
  #overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: #0e0e0e;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    z-index: 100;
  }}

  .steps {{
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 180px;
  }}

  .step {{
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 14px;
    color: #2a2a2a;
    transition: color 0.3s;
  }}
  .step.active {{ color: #e8e8e8; }}
  .step.done {{ color: #4ade80; }}

  .step-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #2a2a2a;
    flex-shrink: 0;
    transition: background 0.3s;
  }}
  .step.active .step-dot {{
    background: #e8e8e8;
    animation: pulse 1.4s ease infinite;
  }}
  .step.done .step-dot {{ background: #4ade80; }}

  @keyframes pulse {{
    0%, 100% {{ box-shadow: 0 0 0 3px rgba(232,232,232,0.12); }}
    50%       {{ box-shadow: 0 0 0 6px rgba(232,232,232,0.04); }}
  }}

  /* Toast */
  .toast {{
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(60px);
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #4ade80;
    padding: 10px 20px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
    opacity: 0;
    white-space: nowrap;
    animation: toast-in 0.3s ease 0.1s forwards, toast-out 0.3s ease 3.5s forwards;
  }}
  @keyframes toast-in {{
    to {{ opacity: 1; transform: translateX(-50%) translateY(0); }}
  }}
  @keyframes toast-out {{
    to {{ opacity: 0; transform: translateX(-50%) translateY(60px); }}
  }}
</style>
</head>
<body>

{toast_html}

<div id="overlay">
  <div class="steps">
    <div class="step" id="s1"><div class="step-dot"></div>Downloading</div>
    <div class="step" id="s2"><div class="step-dot"></div>Converting</div>
    <div class="step" id="s3"><div class="step-dot"></div>Uploading</div>
  </div>
</div>

<div class="wrap">
  <div class="title">Shorts Bot</div>
  <div class="status">{"Connected" if logged_in else "Not connected"}</div>
  {error_html}
  {body_html}
</div>

<script>
function doPaste() {{
  navigator.clipboard.readText().then(t => document.getElementById("url").value = t.trim());
}}

function doSubmit() {{
  const url = document.getElementById("url").value.trim();
  if (!url) return;

  const overlay = document.getElementById("overlay");
  overlay.style.display = "flex";

  // Animate steps based on rough real-world timing:
  // download ~6s, ffmpeg ~12s, upload ~8s
  activate("s1", 0);
  activate("s2", 6000);
  activate("s3", 18000);

  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/post";
  const inp = document.createElement("input");
  inp.type = "hidden";
  inp.name = "url";
  inp.value = url;
  form.appendChild(inp);
  document.body.appendChild(form);
  form.submit();
}}

function activate(id, delay) {{
  setTimeout(() => {{
    document.querySelectorAll(".step").forEach(s => {{
      if (s.id === id) {{
        s.classList.add("active");
      }} else if (s.classList.contains("active")) {{
        s.classList.remove("active");
        s.classList.add("done");
      }}
    }});
  }}, delay);
}}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────
@app.route("/")
def index():
    creds = load_credentials()
    return render_page(
        logged_in=creds is not None and creds.valid,
        success=bool(request.args.get("success")),
        error=request.args.get("error", ""),
    )


@app.route("/login")
def login():
    flow = _get_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    flask.session["state"] = state
    flask.session["code_verifier"] = flow.code_verifier
    return redirect(auth_url)


@app.route("/callback")
def callback():
    state = flask.session.get("state")
    if not state:
        return "Session state missing — enable cookies and try again.", 400
    flow = _get_flow(state=state)
    flow.code_verifier = flask.session.get("code_verifier")
    auth_response = request.url
    if not DEV and auth_response.startswith("http://"):
        auth_response = auth_response.replace("http://", "https://", 1)
    try:
        flow.fetch_token(authorization_response=auth_response)
    except Exception as e:
        return f"OAuth error: {e}", 500
    _save_credentials(flow.credentials)
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    flask.session.pop("credentials", None)
    return redirect(url_for("index"))


@app.route("/post", methods=["POST"])
def post():
    url = request.form.get("url", "").strip()
    if not url:
        return redirect(url_for("index", error="No URL provided."))

    creds = load_credentials()
    if not creds or not creds.valid:
        return redirect(url_for("login"))

    tmp = tempfile.mkdtemp(dir=TEMP_DIR)
    try:
        # 1. Download — metadata comes straight from the info dict,
        #    no writeinfojson so no extra file written to disk
        with yt_dlp.YoutubeDL({
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }) as ydl:
            info = ydl.extract_info(url, download=True)

        # 2. Find downloaded file
        video_path = next(
            (os.path.join(tmp, f) for f in os.listdir(tmp)
             if f.endswith((".mp4", ".mkv", ".webm"))),
            None,
        )
        if not video_path:
            raise FileNotFoundError("Download produced no video file.")

        # 3. Metadata from info dict (no disk read needed)
        raw_title = info.get("title") or ""
        title = (raw_title[:90] + "…") if len(raw_title) > 95 else (raw_title or "TikTok Video")
        description = info.get("description") or raw_title or ""
        tags = list(info.get("tags") or [])

        # 4. Process — always runs FFmpeg:
        #    forces 9:16 with black bars + guaranteed AAC audio
        processed = process_for_shorts(video_path, tmp)

        # 5. Upload
        yt = build("youtube", "v3", credentials=creds)
        upload_to_youtube(yt, processed, title, description, tags)

        return redirect(url_for("index", success=1))

    except HttpError as e:
        return redirect(url_for("index", error=f"YouTube error: {e}"))
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("index", error=str(e)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(
        host="localhost" if DEV else "0.0.0.0",
        port=5000 if DEV else 7860,
    )