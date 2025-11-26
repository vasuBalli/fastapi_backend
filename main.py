from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import yt_dlp
import requests
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from fastapi_cache.decorator import cache

app = FastAPI()

# Allow calls from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def _format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


@app.post("/api/info", response_model=InfoResponse)
@cache(expire=3600)
def get_info(payload: InfoRequest):
    url = payload.url.strip()
    try:
        ydl_opts = {"format": "best", "quiet": True}
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
        print("info error:", e)
        return InfoResponse(ok=False, message="Invalid or unsupported URL", input_url=url)


@app.get("/api/download")
@cache(expire=3600)
def download(url: str = Query(...), index: int = Query(0)):
    try:
        ydl_opts = {"format": "best", "quiet": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entry = info["entries"][index] if "entries" in info else info
        direct_url = entry["url"]
        filename = (entry.get("title") or "instagram_video").replace(" ", "_") + ".mp4"

        video_stream = requests.get(direct_url, stream=True)

        return StreamingResponse(
            video_stream.iter_content(chunk_size=1024 * 64),
            media_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        print("download error:", e)
        return {"ok": False, "message": "Download failed"}


@app.get("/api/test")
@cache(expire=3600)
def test_cache():
    return {"ok": True, "message": "Cache is working!"}