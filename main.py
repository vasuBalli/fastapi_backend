from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from urllib.parse import quote
import yt_dlp
import requests

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------
# MODELS
# ----------------------------------------

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


# ----------------------------------------
# UTIL
# ----------------------------------------

def _format_duration(seconds: Optional[int]) -> str:
    """Convert seconds to M:SS format."""
    if seconds is None:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


# ----------------------------------------
# API: GET VIDEO INFO (yt-dlp)
# ----------------------------------------

@app.post("/api/info", response_model=InfoResponse)
def get_info(payload: InfoRequest):
    url = payload.url.strip()

    try:
        ydl_opts = {
            "quiet": True,
            "nocheckcertificate": True,
            "extract_flat": False,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Referer": "https://www.instagram.com/"
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        items: List[VideoItem] = []

        def build(entry, idx):
            return VideoItem(
                index=idx,
                title=entry.get("title") or f"Clip {idx+1}",
                duration=_format_duration(entry.get("duration")),
                download_url=f"/api/download?url={quote(url, safe='')}&index={idx}"
            )

        # Support carousel posts
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


# ----------------------------------------
# API: DOWNLOAD VIDEO (Streaming)
# ----------------------------------------

@app.get("/api/download")
def download(url: str = Query(...), index: int = Query(0)):
    try:
        ydl_opts = {
            "quiet": True,
            "nocheckcertificate": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Referer": "https://www.instagram.com/"
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entry = info["entries"][index] if "entries" in info else info
        direct_url = entry["url"]

        filename = (entry.get("title") or "instagram_video").replace(" ", "_") + ".mp4"

        # Stream video from Instagram CDN
        cdn_stream = requests.get(
            direct_url,
            stream=True,
            timeout=20,
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


# ----------------------------------------
# HEALTH CHECK
# ----------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "status": "running"}
