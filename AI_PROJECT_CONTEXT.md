# AI_PROJECT_CONTEXT.md
# TikTok → YouTube Shorts Automation — Flutter App
> This file is the single source of truth for any AI assistant (Cursor, Copilot, Claude, etc.)
> working on this project. Read this entire file before writing or suggesting any code.
> Never suggest a server, backend API, or hosted solution — this app is fully self-contained on-device.

---

## 1. Project Overview

This is a **personal automation tool** built as an Android APK using Flutter/Dart.
It downloads TikTok videos (without watermark), processes them to meet YouTube Shorts
requirements, and uploads them to one or more YouTube channels — all running entirely
on the user's Android phone with zero backend server or hosting.

**This app was migrated from a Python/Flask web app.** The core logic (ffmpeg commands,
YouTube API calls, metadata construction) is identical — only the language and wrapper
libraries changed. Do not reinvent the logic; replicate it faithfully in Dart.

**Owner:** Personal use only. Single developer. Not a SaaS product.
**Target platform:** Android only (minSdkVersion 21, targetSdkVersion 34).
**No iOS support planned.**

---

## 2. Golden Rules for AI Suggestions

1. **No servers. Ever.** Do not suggest Express, Flask, FastAPI, Node.js, or any hosted backend.
   All logic runs inside the APK on the device.
2. **No REST API layer between screens and services.** Screens call service classes directly
   via Dart function calls — not HTTP requests.
3. **No Firebase.** Do not suggest Firebase Auth, Firestore, or Firebase Storage.
4. **No state management overkill.** Use `setState` or `Provider` only. Do not suggest
   Riverpod, BLoC, or GetX unless explicitly asked.
5. **Preserve ffmpeg command strings.** The ffmpeg filter arguments (trim, pad, re-encode)
   were tuned in the original Python app. Copy them exactly — do not "optimize" them.
6. **Multi-account is a core feature.** Every auth and upload function must accept an
   account parameter. Never hardcode a single token or assume one channel.
7. **Always handle cleanup.** After every successful upload, delete temp video files from
   the device's cache directory using `File(path).deleteSync()`.
8. **Uploads default to Private.** Never change the default YouTube privacy status from
   `private` without explicit instruction.

---

## 3. Tech Stack — Exact Packages

Only use these packages. Do not add new dependencies without asking.

```yaml
# pubspec.yaml dependencies
dependencies:
  flutter:
    sdk: flutter

  # TikTok downloading (no API key needed, runs on-device)
  youtube_explode_dart: ^2.0.0

  # Video processing (ffmpeg bundled inside APK for Android ARM)
  ffmpeg_kit_flutter: ^6.0.3

  # Google OAuth — native Android flow, no redirect URI needed
  google_sign_in: ^6.2.1

  # YouTube Data API v3 — direct HTTPS calls to Google
  googleapis: ^13.1.0
  googleapis_auth: ^1.5.1

  # Encrypted token storage per account
  flutter_secure_storage: ^9.0.0

  # Receive shared TikTok links from the Android share sheet
  receive_sharing_intent: ^1.8.0

  # Background processing during upload/download
  flutter_background_service: ^5.0.5

  # File path resolution across Android versions
  path_provider: ^2.1.3

  # HTTP client for YouTube resumable upload
  dio: ^5.4.3
```

---

## 4. Project Folder Structure

```
lib/
├── main.dart                        # App entry, MaterialApp, routing
│
├── screens/                         # UI only — no business logic here
│   ├── home_screen.dart             # Paste URL, select channel, trigger pipeline
│   ├── accounts_screen.dart         # List, add, remove YouTube accounts
│   └── progress_screen.dart         # Live status: downloading → trimming → uploading
│
├── services/                        # All business logic — called directly by screens
│   ├── tiktok_service.dart          # Download TikTok video + extract metadata
│   ├── ffmpeg_service.dart          # Trim to 178s, pad to 1080x1920, re-encode
│   ├── youtube_service.dart         # Resumable upload to YouTube Data API v3
│   └── auth_service.dart            # Google Sign-In, token storage, account switching
│
├── models/                          # Plain Dart data classes (no logic)
│   ├── yt_account.dart              # { id, channelName, accessToken, refreshToken }
│   └── video_metadata.dart          # { title, description, tags, localPath }
│
└── utils/
    ├── metadata_builder.dart        # Constructs title (≤100 chars), desc with #Shorts
    └── file_utils.dart              # Temp dir path, cleanup after upload
```

**Rule:** Screens import services. Services import models and utils.
Services never import screens. Utils never import services or screens.

---

## 5. Core Workflow — Step by Step

This is the exact pipeline that runs when the user taps "Process & Upload".
Replicate this order precisely. Do not skip or reorder steps.

```
1. AUTH CHECK
   └─ auth_service.dart: load token for selected account from flutter_secure_storage
      └─ if expired: refresh via googleapis_auth
      └─ if missing: trigger google_sign_in flow

2. DOWNLOAD
   └─ tiktok_service.dart: use youtube_explode_dart to fetch video stream
      └─ get highest quality mp4 stream
      └─ save to: (await getTemporaryDirectory()).path + '/raw_video.mp4'
      └─ extract: title, description, hashtags → VideoMetadata model (held in memory)

3. PROCESS (ffmpeg_kit_flutter)
   └─ ffmpeg_service.dart:
      Step A — Duration check + trim:
        FFmpegKit.executeAsync('-i raw_video.mp4 -t 178 -c copy trimmed.mp4')
      Step B — Aspect ratio check + pad to 9:16:
        FFmpegKit.executeAsync(
          '-i trimmed.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,'
          'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" '
          '-c:v libx264 -preset fast -crf 23 -c:a aac final.mp4'
        )
      └─ output: (await getTemporaryDirectory()).path + '/final.mp4'

4. BUILD METADATA
   └─ metadata_builder.dart:
      title       = tiktokCaption.length > 100
                    ? tiktokCaption.substring(0, 97) + '...'
                    : tiktokCaption
      description = tiktokCaption + '\n\n#Shorts'
      tags        = ['Shorts']
      privacyStatus = 'private'

5. UPLOAD
   └─ youtube_service.dart: resumable multipart upload via googleapis
      └─ endpoint: YouTube Data API v3 — videos.insert
      └─ use account-specific accessToken from selected YtAccount
      └─ upload in chunks (dio handles resumable)
      └─ on success: return videoId + YouTube URL

6. CLEANUP
   └─ file_utils.dart:
      File(rawVideoPath).deleteSync()
      File(trimmedPath).deleteSync()
      File(finalPath).deleteSync()

7. NOTIFY USER
   └─ progress_screen.dart: show ✓ success + direct link to YouTube Studio
```

---

## 6. Multi-Account System

This is a core feature. Every account is stored independently.

### YtAccount model:
```dart
class YtAccount {
  final String id;             // unique UUID generated at sign-in
  final String channelName;    // display name shown in dropdown
  final String channelId;      // YouTube channel ID (UCxxxxxxx)
  final String accessToken;    // short-lived, refresh when expired
  final String refreshToken;   // long-lived, store permanently
  final String email;          // Google account email

  // Storage key pattern: 'account_{id}'
  // Stored as JSON string in flutter_secure_storage
}
```

### Auth service behaviour:
- On "Add Account": trigger `google_sign_in` → get tokens → save as new `YtAccount`
  with unique UUID key in `flutter_secure_storage`
- On app start: load all keys matching `'account_*'` pattern → populate accounts list
- On upload: pass selected `YtAccount` token to `youtube_service.dart`
- On "Upload to All": loop through all saved accounts, upload sequentially using each token
- On token expiry: use `refreshToken` via `googleapis_auth` to silently get new `accessToken`
- On "Remove Account": delete key from `flutter_secure_storage`, remove from UI list

---

## 7. ffmpeg Commands — Do Not Modify

These commands were tested and tuned in the original Python/Flask app.
Copy them character-for-character into `ffmpeg_service.dart`.

### Trim to 178 seconds:
```
-i {inputPath} -t 178 -c copy {trimmedPath}
```

### Pad to 1080x1920 (9:16 vertical) + re-encode:
```
-i {trimmedPath}
-vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
-c:v libx264 -preset fast -crf 23
-c:a aac
{finalPath}
```

### In Dart (ffmpeg_kit_flutter):
```dart
await FFmpegKit.executeAsync(
  '-i $trimmedPath '
  '-vf "scale=1080:1920:force_original_aspect_ratio=decrease,'
  'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" '
  '-c:v libx264 -preset fast -crf 23 -c:a aac $finalPath',
  (session) async {
    final returnCode = await session.getReturnCode();
    if (ReturnCode.isSuccess(returnCode)) {
      // proceed to upload
    } else {
      // handle error
    }
  }
);
```

---

## 8. YouTube Upload — Key Details

- **API:** YouTube Data API v3, `videos.insert` method
- **Scope required:** `https://www.googleapis.com/auth/youtube.upload`
- **Upload type:** `resumable` (handles poor Nepal internet connections)
- **Default privacy:** `private` — user reviews in YouTube Studio before publishing
- **Required metadata fields:**
  - `snippet.title` — max 100 characters
  - `snippet.description` — include `#Shorts` at end
  - `snippet.tags` — `['Shorts']`
  - `snippet.categoryId` — `'22'` (People & Blogs, safe default)
  - `status.privacyStatus` — `'private'`
- **Shorts qualification:** Video must be vertical (9:16) AND ≤180 seconds. Both are
  guaranteed by the ffmpeg processing step above.

---

## 9. Screens — UI Behaviour

### home_screen.dart
- Text field for TikTok URL (auto-filled if app opened via share intent)
- Dropdown to select active YouTube channel (populated from saved accounts)
- "Upload to All Channels" toggle switch
- "Process & Upload" button — disabled while pipeline is running
- Tapping button navigates to `progress_screen.dart` and starts pipeline

### accounts_screen.dart
- ListView of saved `YtAccount` objects showing channel name + email
- "Add Account" button triggers `google_sign_in` flow
- Swipe-to-delete or delete icon removes account from storage
- Accessible from home screen via top-right icon button

### progress_screen.dart
- Shows live pipeline status with step indicators:
  `[ Downloading ] → [ Trimming ] → [ Padding ] → [ Uploading ] → [ Done ]`
- Progress bar during upload (use `dio` onSendProgress callback)
- On success: show YouTube URL as tappable link
- On error: show error message + "Retry" button
- Cannot go back during processing (use `WillPopScope`)

---

## 10. Share Intent — TikTok Integration

When the user taps "Share" in TikTok and selects this app:

```dart
// In main.dart — listen for incoming shared URLs
ReceiveSharingIntent.instance.getMediaStream().listen((List<SharedMediaFile> value) {
  if (value.isNotEmpty && value.first.type == SharedMediaType.url) {
    // navigate to home screen with URL pre-filled
    urlController.text = value.first.path;
  }
});
```

Register in `AndroidManifest.xml`:
```xml
<intent-filter>
  <action android:name="android.intent.action.SEND" />
  <category android:name="android.intent.category.DEFAULT" />
  <data android:mimeType="text/plain" />
</intent-filter>
```

---

## 11. Background Processing

Video processing and uploading can take 2-5 minutes. Use `flutter_background_service`
so the pipeline continues if the user minimizes the app or the screen locks.

- Start background service when pipeline begins
- Pass progress updates back to UI via service stream
- Stop background service after cleanup step completes
- Show an Android notification during processing: "Uploading to YouTube..."

---

## 12. Error Handling — Required Cases

Handle all of these explicitly. Never let them crash silently.

| Error | Where | Handling |
|---|---|---|
| Invalid TikTok URL | `tiktok_service.dart` | Show "Invalid or unsupported URL" on progress screen |
| TikTok video unavailable | `tiktok_service.dart` | Show "Video is private or deleted" |
| ffmpeg failure | `ffmpeg_service.dart` | Show return code + "Processing failed, try again" |
| Token expired + refresh fails | `auth_service.dart` | Prompt re-login for that specific account |
| YouTube quota exceeded | `youtube_service.dart` | Show "YouTube daily upload quota reached (10,000 units)" |
| Upload interrupted | `youtube_service.dart` | Auto-retry up to 3 times using resumable upload URI |
| No internet | Anywhere | Check connectivity before starting, show "No internet connection" |

---

## 13. File Path Conventions

Always use `path_provider` for file paths. Never hardcode paths.

```dart
import 'package:path_provider/path_provider.dart';

final tempDir = await getTemporaryDirectory();
final rawPath     = '${tempDir.path}/raw_video.mp4';
final trimmedPath = '${tempDir.path}/trimmed_video.mp4';
final finalPath   = '${tempDir.path}/final_video.mp4';
```

All three files must be deleted in the cleanup step after a successful upload.
On failure, leave files in place so the user can retry without re-downloading.

---

## 14. Android Permissions — AndroidManifest.xml

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
```

No storage permissions needed — the app only writes to its own temp directory.

---

## 15. What This App Is NOT

- Not a public app (no Play Store release planned)
- Not multi-user (personal tool for one developer)
- Not a web app (no browser, no server, no HTML)
- Not connected to any database
- Not using Firebase in any form
- Not supporting iOS
- Not supporting video sources other than TikTok (for now)

---

## 16. Migration Reference — Python to Dart

| Python/Flask component | Dart/Flutter equivalent |
|---|---|
| `yt-dlp` | `youtube_explode_dart` |
| `ffmpeg` subprocess | `FFmpegKit.executeAsync()` |
| `google-auth` library | `googleapis_auth` package |
| `googleapiclient` | `googleapis` package |
| `token.json` file | `flutter_secure_storage` |
| Flask `/callback` route | Not needed — native Android OAuth |
| `os.remove()` | `File(path).deleteSync()` |
| `tempfile.mkdtemp()` | `getTemporaryDirectory()` |
| Python dict for metadata | `VideoMetadata` Dart model |
| `.env` secrets | Android keystore + Google Cloud Console SHA-1 |

---

*Last updated: 2026. Maintained by project owner.*
*Do not modify the architecture described here without explicit instruction from the owner.*
