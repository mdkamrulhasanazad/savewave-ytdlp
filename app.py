import os
import re
import shutil
import tempfile
from urllib.parse import quote

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)  # allow requests from thesavewave.blogspot.com

YOUTUBE_RE = re.compile(r'(youtube\.com|youtu\.be)', re.IGNORECASE)

# Standard quality ladder — only qualities actually available for a given
# video are offered to the user (checked against real format heights).
STANDARD_QUALITIES = [2160, 1440, 1080, 720, 480, 360, 240]


def is_youtube_url(url: str) -> bool:
    return bool(url) and bool(YOUTUBE_RE.search(url))


def safe_title(title: str) -> str:
    title = re.sub(r'[\\/:*?"<>|]', '', title or '').strip()
    return title[:80] or 'video'


@app.route('/')
def health():
    return jsonify({"status": "ok", "service": "savewave-ytdlp"})


@app.route('/youtube/info', methods=['POST'])
def youtube_info():
    """
    Step 1: given a YouTube URL, return the title/thumbnail plus a list of
    quality options that actually exist for this video (no downloading
    yet — this is just a metadata lookup, so it's fast).
    """
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()

    if not is_youtube_url(url):
        return jsonify({"status": "error", "error": {"code": "invalid_url"}}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        # Uncomment if YouTube starts blocking this server's IP too:
        # 'cookiefile': '/etc/secrets/youtube_cookies.txt',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"status": "error", "error": {"code": "extract_failed", "message": str(e)}}), 502

    formats = info.get('formats', []) or []
    available_heights = {
        f.get('height') for f in formats
        if f.get('height') and f.get('vcodec') not in (None, 'none')
    }

    qualities = [h for h in STANDARD_QUALITIES if h in available_heights]
    if not qualities and available_heights:
        qualities = [max(available_heights)]

    base = request.url_root.rstrip('/')
    encoded_url = quote(url, safe='')

    quality_list = [
        {
            "label": f"{h}p" + (" (HD)" if h >= 720 else ""),
            "height": h,
            "downloadUrl": f"{base}/youtube/download?url={encoded_url}&type=video&height={h}",
        }
        for h in qualities
    ]

    return jsonify({
        "status": "success",
        "title": info.get('title', 'video'),
        "thumbnail": info.get('thumbnail'),
        "duration": info.get('duration'),
        "qualities": quality_list,
        "audioDownloadUrl": f"{base}/youtube/download?url={encoded_url}&type=audio",
    })


@app.route('/youtube/download', methods=['GET'])
def youtube_download():
    """
    Step 2: actually download (and, for video, merge video+audio with
    ffmpeg; for audio, extract to MP3), then stream the resulting file
    straight to the browser as an attachment. The temp file is deleted
    right after it's fully streamed.
    """
    url = (request.args.get('url') or '').strip()
    dtype = request.args.get('type', 'video')
    height = request.args.get('height', '1080')

    if not is_youtube_url(url):
        return jsonify({"status": "error", "error": {"code": "invalid_url"}}), 400

    tmpdir = tempfile.mkdtemp(prefix='sw_')
    outtmpl = os.path.join(tmpdir, 'out.%(ext)s')

    if dtype == 'audio':
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        mimetype = 'audio/mpeg'
    else:
        fmt = (
            f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]'
            f'/best[height<={height}][ext=mp4]/best[height<={height}]'
        )
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'format': fmt,
            'outtmpl': outtmpl,
            'merge_output_format': 'mp4',  # requires ffmpeg on PATH
        }
        mimetype = 'video/mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify({"status": "error", "error": {"code": "download_failed", "message": str(e)}}), 502

    produced = [f for f in os.listdir(tmpdir) if f.startswith('out.')]
    if not produced:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify({"status": "error", "error": {"code": "no_output_file"}}), 502

    filepath = os.path.join(tmpdir, produced[0])
    ext = produced[0].rsplit('.', 1)[-1]
    download_name = f"{safe_title(title)}.{ext}"

    def generate():
        try:
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return Response(
        generate(),
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename="{download_name}"'},
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
