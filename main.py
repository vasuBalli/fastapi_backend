from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from urllib.parse import quote
import yt_dlp
import requests
import os

app = FastAPI()

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Models
# ----------------------------

class InfoRequest(BaseModel):
    url: str

class VideoItem(BaseModel):
    index: int
    title: str
    duration: str
    download_url: str

class InfoResponse(BaseModel):
    ok: bool
    message: Optional[str] = None
    items: List[VideoItem] = []
    input_url: str


# ----------------------------
# Utils
# ----------------------------

def _format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


# ----------------------------
# Shared yt-dlp options
# ----------------------------

def get_ydl_opts():
    cookie_path = os.path.join(os.getcwd(), "cookies.txt")

    return {
        "quiet": True,
        "nocheckcertificate": True,
        "extract_flat": False,
        "cookiefile": cookie_path,   # THE FIX!!!
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Referer": "https://www.instagram.com/"
        }
    }


# ----------------------------
# API: /api/info
# ----------------------------

@app.post("/api/info", response_model=InfoResponse)
def get_info(payload: InfoRequest):
    url = payload.url.strip()

    try:
        ydl_opts = get_ydl_opts()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        items: List[VideoItem] = []

        def build(entry, idx):
            title = entry.get("title") or f"Clip {idx+1}"
            return VideoItem(
                index=idx,
                title=title,
                duration=_format_duration(entry.get("duration")),
                download_url=f"/api/download?url={quote(url, safe='')}&index={idx}"
            )

        if "entries" in info and info["entries"]:
            for i, e in enumerate(info["entries"]):
                items.append(build(e, i))
        else:
            items.append(build(info, 0))

        return InfoResponse(ok=True, items=items, input_url=url)

    except Exception as e:
        print("INFO ERROR:", e)
        return InfoResponse(
            ok=False,
            message="Invalid or unsupported URL",
            input_url=url
        )


# ----------------------------
# API: /api/download
# ----------------------------

@app.get("/api/download")
def download(url: str = Query(...), index: int = Query(0)):
    try:
        ydl_opts = get_ydl_opts()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entry = info["entries"][index] if "entries" in info else info
        direct_url = entry["url"]

        filename = (entry.get("title") or "instagram_video").replace(" ", "_") + ".mp4"

        cdn_stream = requests.get(
            direct_url,
            stream=True,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.instagram.com/"
            }
        )

        if cdn_stream.status_code != 200:
            raise Exception(f"CDN error: {cdn_stream.status_code}")

        return StreamingResponse(
            cdn_stream.iter_content(chunk_size=1024 * 64),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        print("DOWNLOAD ERROR:", e)
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Download failed", "error": str(e)}
        )


# ----------------------------
# Health Check
# ----------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "status": "running"}
