# SaveWave YouTube Backend (yt-dlp + ffmpeg)

A Flask microservice that handles **only YouTube** downloads using
yt-dlp, since Cobalt gets blocked by YouTube's bot detection
(`error.api.youtube.login`). Your existing Cobalt instance still
handles Instagram, TikTok, Facebook, Twitter/X, and Reddit — nothing
changes there.

This version gives a **full quality picker** like Vidmate/Snaptube:
1080p/1440p/2160p (merged with ffmpeg when needed), 720p/480p/360p, and
an "Audio only (MP3)" option.

## How it works

Two endpoints, two steps:

1. **`POST /youtube/info`** — `{"url": "..."}` -> returns the title,
   thumbnail, and a list of quality options that actually exist for
   that specific video, each with a ready-to-use `downloadUrl`. This
   is just a metadata lookup, so it's fast (no downloading yet).
2. **`GET /youtube/download?url=...&type=video&height=1080`** — does
   the real work: downloads the video+audio streams, merges them with
   ffmpeg (or extracts MP3 for `type=audio`), and streams the result
   straight back as a file attachment. The temp file is deleted right
   after it's fully sent.

## Deploy on Render (Docker)

This needs **ffmpeg**, which Render's plain Python runtime doesn't
include — so deploy it as a **Docker** service instead (the
`Dockerfile` here handles installing ffmpeg).

1. Push this folder (including `Dockerfile`) to a GitHub repo, e.g.
   `savewave-ytdlp`.
2. On Render: **New +** -> **Web Service** -> connect the repo.
3. Render should auto-detect the `Dockerfile` and set **Runtime:
   Docker**. If it doesn't, set it manually.
4. **Instance Type:** Free (see limitations below).
5. Deploy. You'll get a URL like `https://savewave-ytdlp.onrender.com`.
6. Test the info endpoint:
   ```bash
   curl -X POST https://savewave-ytdlp.onrender.com/youtube/info \
     -H "Content-Type: application/json" \
     -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
   ```
   You should get JSON back with a `qualities` array and
   `audioDownloadUrl`. Open one of the `downloadUrl` links directly in
   a browser to confirm the actual file download works.

## Update the SaveWave frontend

In `theme.xml`, set `YTDLP_BACKEND` to your Render **base URL** (no
trailing path this time — the frontend appends `/youtube/info`
itself):
```js
const YTDLP_BACKEND = 'https://savewave-ytdlp.onrender.com';
```

## Limitations to know about

- **Free tier RAM (512MB):** ffmpeg merging is usually just a fast
  "stream copy" (no re-encoding), so it's light — but very long videos
  (1hr+) at high resolution could still strain it. Test with typical
  short-to-medium videos first.
- **Request timeout:** Render's free tier may cut off requests that
  run too long (large 1080p+ downloads on a slow cold-started
  instance). If users hit timeouts on big files, consider upgrading
  the Render plan or capping the max offered quality to 720p.
- **Cold starts:** same as your Cobalt instance — free tier sleeps
  after inactivity, first request can take 30–50s.
- **Direct IP blocking:** if Render's IP gets rate-limited by YouTube
  too, use cookies from a throwaway Google account (never your
  personal one). Export with a browser extension like "Get
  cookies.txt", upload as a Render **Secret File**, and uncomment the
  `cookiefile` line in `app.py` (`youtube_info` function).
- **Ephemeral disk:** temp files are deleted automatically after each
  download completes or fails — no manual cleanup needed.
