"""
Renders the complete 9:16 Vertical Short for Michael Jackson - They Don't Care About Us
Fulfills all Song / Lyric Video specifications:
- Authentic preservation of the artist and scene
- Clean, sharp 1080x1920 vertical composition
- Minimalist black screen intro with smooth typography
- Broadcast audio loudness (-14 LUFS)
- Precision synchronized typography with gold keyword accents
- Subtle emotional intensity progression
"""

import os
import shutil
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("render_short")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_VIDEO = os.path.join(BASE_DIR, "mj_clean_segment.mp4")
ASS_SUBTITLES = os.path.join(BASE_DIR, "lyrics.ass")
OUTPUT_VIDEO = os.path.join(BASE_DIR, "Michael_Jackson_They_Dont_Care_About_Us_Short.mp4")
DOWNLOADS_COPY = os.path.join(os.path.expanduser("~"), "Downloads", "Michael_Jackson_They_Dont_Care_About_Us_Short.mp4")

def render_short():
    if not os.path.exists(INPUT_VIDEO):
        raise FileNotFoundError(f"Input video not found: {INPUT_VIDEO}")
    if not os.path.exists(ASS_SUBTITLES):
        raise FileNotFoundError(f"Subtitles not found: {ASS_SUBTITLES}")

    # Build filtergraph:
    # 1. Fade video in from black between 1.6s and 2.4s (allowing 0-1.8s for clean black intro card)
    # 2. Split into background (scaled & boxblurred & darkened) and foreground (scaled 1080:810)
    # 3. Position foreground at upper-middle (Y = 455)
    # 4. Burn in precision ASS subtitles with libass
    
    # Escape path for libass in Windows
    ass_escaped = ASS_SUBTITLES.replace("\\", "/").replace(":", "\\:")
    
    vf = (
        "[0:v]fade=t=in:st=1.6:d=0.8[faded];"
        "[faded]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=14:14,eq=brightness=-0.14:contrast=1.06[bg];"
        "[faded]scale=1080:810[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2-100,ass='{ass_escaped}'[v]"
    )

    af = "loudnorm=I=-14:TP=-1.5:LRA=11"

    cmd = [
        "ffmpeg", "-y",
        "-i", INPUT_VIDEO,
        "-filter_complex", vf,
        "-map", "[v]",
        "-map", "0:a",
        "-af", af,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "256k",
        "-movflags", "+faststart",
        OUTPUT_VIDEO
    ]

    logger.info("Executing FFmpeg rendering command...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg render error: {res.stderr}")
        raise RuntimeError(f"FFmpeg failed: {res.stderr[-500:]}")

    logger.info(f"Successfully rendered: {OUTPUT_VIDEO}")
    
    # Copy to Downloads for easy user access
    try:
        shutil.copy2(OUTPUT_VIDEO, DOWNLOADS_COPY)
        logger.info(f"Copied final video to: {DOWNLOADS_COPY}")
    except Exception as e:
        logger.warning(f"Could not copy to Downloads: {e}")

if __name__ == "__main__":
    render_short()
