"""
Media Processor Service for YouTube -> Shorts/Reels Automation
Provides automated video downloading, multilingual transcript & language analysis,
segment selection, FFmpeg 9:16 vertical reframing with native ASS captions,
and public direct CDN hosting.
"""

import os
import re
import sys
import glob
import time
import shutil
import logging
import tempfile
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("media_processor")

app = FastAPI(title="Media Automation Processor", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_work")
os.makedirs(TEMP_BASE_DIR, exist_ok=True)

LANGUAGE_NAMES = {
    "pa": "Punjabi",
    "hi": "Hindi",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "bn": "Bengali",
    "ur": "Urdu",
    "tr": "Turkish",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati"
}


class ProcessRequest(BaseModel):
    youtube_url: str
    short_count: int = 2
    target_duration_min: float = 27.0
    target_duration_max: float = 33.0


def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def detect_script_language(text: str) -> Optional[str]:
    """Detects language script from unicode characters."""
    for ch in text:
        code = ord(ch)
        if 0x0A00 <= code <= 0x0A7F:
            return "pa"  # Gurmukhi / Punjabi
        elif 0x0900 <= code <= 0x097F:
            return "hi"  # Devanagari / Hindi
        elif 0x0600 <= code <= 0x06FF:
            return "ar"  # Arabic / Urdu
        elif 0x0400 <= code <= 0x04FF:
            return "ru"  # Cyrillic
        elif 0x3040 <= code <= 0x30FF:
            return "ja"  # Japanese
        elif 0xAC00 <= code <= 0xD7AF:
            return "ko"  # Korean
        elif 0x4E00 <= code <= 0x9FFF:
            return "zh"  # Chinese
    return None


def clean_transcript_text(text: str) -> str:
    """Removes music markers, sound effect brackets, and formatting noise."""
    t = re.sub(r'\[.*?\]|\(.*?\)|♪+|>>+', '', text)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def detect_and_fetch_transcript(
    video_id: str,
    ydl_info: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], str, str]:
    """
    Fetches transcript segments in ANY language, prioritizing manual transcripts over generated.
    Returns: (segments, language_code, language_name)
    """
    detected_code = "en"
    segments: List[Dict[str, Any]] = []

    # 1. Try YouTubeTranscriptApi across ALL available languages
    try:
        yta = YouTubeTranscriptApi()
        t_list = yta.list(video_id)
        manual = [t for t in t_list if not t.is_generated]
        generated = [t for t in t_list if t.is_generated]
        chosen = manual[0] if manual else (generated[0] if generated else None)

        if chosen:
            raw_code = chosen.language_code
            # Normalize e.g. en-US -> en, pa-IN -> pa (preserve zh-Hans/zh-Hant)
            if '-' in raw_code and not raw_code.startswith('zh-'):
                detected_code = raw_code.split('-')[0]
            else:
                detected_code = raw_code

            raw_snippets = chosen.fetch()
            for s in raw_snippets:
                raw_text = getattr(s, 'text', None) or (s.get('text') if isinstance(s, dict) else '')
                clean_text = clean_transcript_text(str(raw_text))
                if not clean_text:
                    continue
                st = getattr(s, 'start', None) or (s.get('start') if isinstance(s, dict) else 0.0)
                d = getattr(s, 'duration', None) or (s.get('duration') if isinstance(s, dict) else 0.0)
                segments.append({'text': clean_text, 'start': float(st), 'duration': float(d)})

            logger.info(f"Retrieved {len(segments)} transcript segments in '{detected_code}' ({chosen.language}) for {video_id}")
    except Exception as e:
        logger.warning(f"Could not retrieve transcript via YouTubeTranscriptApi for {video_id}: {e}")

    # 2. Fallback to ydl_info if language is undetermined or transcripts were empty
    if detected_code == "en" and ydl_info:
        info_lang = ydl_info.get("language")
        if info_lang and info_lang != "und":
            detected_code = info_lang.split('-')[0]
        else:
            sub_keys = list(ydl_info.get('automatic_captions', {}).keys()) + list(ydl_info.get('subtitles', {}).keys())
            orig_keys = [k for k in sub_keys if k.endswith('-orig')]
            if orig_keys:
                detected_code = orig_keys[0].replace('-orig', '').split('-')[0]
            elif sub_keys and sub_keys[0] != 'live_chat':
                detected_code = sub_keys[0].split('-')[0]

        title_desc = (ydl_info.get("title", "") + " " + ydl_info.get("description", ""))
        script_lang = detect_script_language(title_desc)
        if script_lang:
            detected_code = script_lang

    lang_name = LANGUAGE_NAMES.get(detected_code, detected_code.upper())
    return segments, detected_code, lang_name


def analyze_and_select_segments(
    transcript: List[Dict[str, Any]],
    video_duration: float,
    short_count: int,
    target_min: float = 27.0,
    target_max: float = 33.0,
    heatmap: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Analyzes YouTube replay heatmap and transcript to pinpoint the absolute PEAK moment
    and the most famous lines / hook / chorus of the video, strictly targeting ~30-second Shorts.
    """
    candidate_segments = []
    heatmap = heatmap or []

    # Exclude the 0-5s intro burst from the content heatmap to find the true content replay peaks
    content_heat = [p for p in heatmap if p.get('start_time', 0.0) >= 5.0]
    if content_heat:
        max_global_heat = max(p.get('value', 0.0) for p in content_heat)
        top_heat_point = max(content_heat, key=lambda p: p.get('value', 0.0))
        global_peak_time = (top_heat_point.get('start_time', 0.0) + top_heat_point.get('end_time', 0.0)) / 2.0
    else:
        max_global_heat = 1.0
        global_peak_time = video_duration / 2.0

    # Detect repeated phrases (chorus/refrain/famous lines) across full transcript
    repeated_phrases = set()
    if transcript and len(transcript) > 0:
        all_words = []
        for entry in transcript:
            cleaned_words = [re.sub(r'[\.,!?।|\n]', '', w).lower() for w in entry.get('text', '').split()]
            all_words.extend([w for w in cleaned_words if w])

        bigrams = [' '.join(all_words[k:k+2]) for k in range(len(all_words) - 1)]
        trigrams = [' '.join(all_words[k:k+3]) for k in range(len(all_words) - 2)]
        for phrase, count in Counter(bigrams + trigrams).items():
            if count >= 2 and len(phrase) >= 4:
                repeated_phrases.add(phrase)

    hook_keywords = {
        "secret", "never", "always", "why", "how", "reason", "mistake",
        "truth", "money", "think", "best", "stop", "remember", "important",
        "power", "success", "future", "key", "lesson", "rule", "change"
    }

    if transcript and len(transcript) > 0:
        n_entries = len(transcript)
        for i in range(n_entries):
            start_time = transcript[i]['start']
            text_acc = []
            snippets_acc = []
            end_time = start_time

            for j in range(i, n_entries):
                entry = transcript[j]
                entry_end = entry['start'] + entry.get('duration', 0)
                dur = entry_end - start_time
                text_acc.append(entry.get('text', ''))
                snippets_acc.append(entry)

                if dur >= target_min:
                    end_time = entry_end
                    full_text = " ".join(text_acc)
                    words = full_text.split()
                    word_count = len(words)
                    speech_rate = word_count / dur if dur > 0 else 0

                    # 1. Heatmap Replay Score (0 to 55 pts) - Prioritize highest viewer replay spikes
                    if heatmap and content_heat:
                        overlapping_heat = [
                            p.get('value', 0.0) for p in heatmap
                            if p.get('end_time', 0) >= start_time and p.get('start_time', 0) <= end_time
                        ]
                        if overlapping_heat:
                            avg_heat = sum(overlapping_heat) / len(overlapping_heat)
                            max_heat = max(overlapping_heat)
                            peak_ratio = (max_heat / max_global_heat) if max_global_heat > 0 else 0.8

                            # Massive boost for encompassing the global maximum replay peak
                            is_global_peak = (max_global_heat - max_heat) < 0.015
                            peak_boost = 22.0 if is_global_peak else 0.0

                            # Peak placement bonus: peak drop hits 3.5s to 16s into the 30s Short (ideal buildup & drop)
                            peak_offset = global_peak_time - start_time
                            placement_bonus = 8.0 if (3.5 <= peak_offset <= 16.0 and is_global_peak) else 0.0

                            heatmap_score = (peak_ratio ** 2 * 25.0) + (avg_heat * 10.0) + peak_boost + placement_bonus
                        else:
                            heatmap_score = 15.0
                    else:
                        heatmap_score = 30.0  # Neutral baseline when heatmap is unavailable

                    # 2. Chorus & Hook Repetition Score (0 to 25 pts) - Most famous lines / hooks
                    text_lower = full_text.lower()
                    chorus_hits = sum(1 for rp in repeated_phrases if rp in text_lower)
                    hook_hits = sum(1 for kw in hook_keywords if kw in text_lower)

                    # Bonus if the famous repeated phrase appears right at the start of the clip (instant hook)
                    first_few_lines = ' '.join(text_acc[:min(len(text_acc), 4)]).lower()
                    hook_at_start = any(rp in first_few_lines for rp in repeated_phrases)
                    hook_start_bonus = 5.0 if hook_at_start else 0.0

                    hook_score = min(25.0, (chorus_hits * 5.0) + (hook_hits * 4.0) + hook_start_bonus)

                    # 3. Speech / Singing Flow (0 to 10 pts) - optimal 1.8 to 3.2 wps
                    rate_score = 10.0 - abs(speech_rate - 2.5) * 3.0
                    rate_score = max(3.0, min(10.0, rate_score))

                    # 4. Exact 30-Second Target Fit Bonus (0 to 10 pts)
                    dur_diff = abs(dur - 30.0)
                    duration_fit = max(0.0, 10.0 - dur_diff * 2.5)

                    total_score = heatmap_score + hook_score + rate_score + duration_fit
                    total_score = min(99.0, max(50.0, total_score))

                    # Generate clean title from first sentence / line
                    first_sent = re.split(r'[.!?।|\n]', full_text)[0].strip()
                    title = first_sent[:50] if len(first_sent) > 5 else f"Peak Highlight at {int(start_time)}s"

                    candidate_segments.append({
                        "start_time": round(start_time, 2),
                        "end_time": round(end_time, 2),
                        "duration": round(dur, 2),
                        "score": round(total_score, 1),
                        "text": full_text,
                        "title": title,
                        "snippets": snippets_acc[:]
                    })

                    if dur >= target_max:
                        break

    # Fallback if transcript was empty or insufficient candidate segments
    if len(candidate_segments) < short_count:
        logger.info("Transcript lacked sufficient segments; generating 30s clips from peak heatmap points or equidistant windows.")
        clip_len = 30.0

        # Try peak heatmap points first
        if content_heat:
            sorted_peaks = sorted(content_heat, key=lambda p: p.get('value', 0.0), reverse=True)
            for peak in sorted_peaks:
                if len(candidate_segments) >= short_count:
                    break
                p_mid = (peak.get('start_time', 0.0) + peak.get('end_time', 0.0)) / 2.0
                # Position peak ~8s into the 30s clip for optimal buildup
                s = max(0.0, min(p_mid - 8.0, video_duration - clip_len))
                e = min(video_duration, s + clip_len)

                # Check overlap with existing candidates
                overlap = any(not (e <= c["start_time"] or s >= c["end_time"]) for c in candidate_segments)
                if not overlap:
                    candidate_segments.append({
                        "start_time": round(s, 2),
                        "end_time": round(e, 2),
                        "duration": round(e - s, 2),
                        "score": round(peak.get('value', 0.8) * 100.0, 1),
                        "text": "Peak viewer replay moment",
                        "title": f"Peak Highlight at {int(s)}s",
                        "snippets": []
                    })

        # Fallback to equidistant 30s windows
        if len(candidate_segments) < short_count:
            step = video_duration / max(1, short_count + 1)
            for idx in range(short_count):
                s = round((idx + 1) * step - clip_len / 2, 2)
                s = max(0.0, min(s, video_duration - clip_len))
                candidate_segments.append({
                    "start_time": s,
                    "end_time": round(s + clip_len, 2),
                    "duration": round(clip_len, 2),
                    "score": 75.0,
                    "text": "Key moment from video",
                    "title": f"Key Highlight {idx + 1}",
                    "snippets": []
                })

    candidate_segments.sort(key=lambda x: x["score"], reverse=True)

    selected = []
    for cand in candidate_segments:
        if len(selected) >= short_count:
            break
        overlap = False
        for s in selected:
            if not (cand["end_time"] <= s["start_time"] or cand["start_time"] >= s["end_time"]):
                overlap = True
                break
        if not overlap:
            selected.append(cand)

    selected.sort(key=lambda x: x["start_time"])
    return selected[:short_count]


def download_source_video(youtube_url: str, output_path: str) -> Dict[str, Any]:
    """Download video and audio using optimized resolution for rapid processing."""
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=True)
        return {
            "title": info.get('title', 'YouTube Video'),
            "duration": info.get('duration', 0),
            "categories": info.get('categories', []),
            "tags": info.get('tags', []),
            "description": info.get('description', ''),
            "language": info.get('language'),
            "automatic_captions": info.get('automatic_captions', {}),
            "subtitles": info.get('subtitles', {}),
            "heatmap": info.get('heatmap', [])
        }


def classify_video_type(info: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    """
    Identifies whether the video is a SONG / MUSIC / LYRIC VIDEO
    or a PODCAST / INTERVIEW / TALKING-HEAD VIDEO according to user rules.
    """
    title = (info.get('title') or '').lower()
    categories = [c.lower() for c in (info.get('categories') or [])]
    tags = [t.lower() for t in (info.get('tags') or [])]

    if 'music' in categories:
        return 'SONG'

    music_keywords = [
        'official music video', 'official video', 'music video',
        'lyric video', 'lyrics video', 'official audio',
        'feat.', 'ft.', 'vevo', 'album', 'remix', 'audio',
        'soundtrack', 'ost', 'chorus', 'single', 'mv'
    ]
    if any(k in title for k in music_keywords):
        return 'SONG'

    tag_str = " ".join(tags)
    if any(k in tag_str for k in ['music', 'song', 'lyrics', 'vevo', 'singer', 'track']):
        return 'SONG'

    return 'PODCAST'


def format_ass_time(seconds: float) -> str:
    """Formats seconds into ASS timestamp: H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass_subtitles(
    snippets: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    language_code: str,
    output_ass_path: str
) -> bool:
    """
    Generates a beautifully styled ASS subtitle file aligned with the trimmed clip.
    Uses Nirmala UI for Indic scripts (Gurmukhi/Devanagari) and Segoe UI for Latin.
    """
    if language_code in ("pa", "hi", "bn", "ta", "te", "mr", "gu"):
        font_name = "Nirmala UI"
    else:
        font_name = "Segoe UI"

    clip_dur = clip_end - clip_start
    events = []

    for snip in snippets:
        s_abs = snip['start']
        e_abs = snip['start'] + snip.get('duration', 2.5)

        s_rel = max(0.0, s_abs - clip_start)
        e_rel = min(clip_dur, e_abs - clip_start)

        if e_rel > s_rel and s_rel < clip_dur and e_rel > 0:
            text = clean_transcript_text(snip['text']).replace('\n', ' ').strip()
            if text:
                t_start = format_ass_time(s_rel)
                t_end = format_ass_time(e_rel)
                # Viral caption styling: Bold, white primary with subtle dark outline and shadow
                events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{{\\b1}}{text}{{\\b0}}")

    if not events:
        return False

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},62,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    return True


def trim_and_reframe_to_9_16(
    input_video: str,
    output_clip: str,
    start_time: float,
    duration: float,
    video_type: str = "PODCAST",
    ass_subtitle_path: Optional[str] = None
) -> None:
    """
    Trims with millisecond accuracy and reframes to 9:16 (1080x1920) with blurred background.
    Optionally burns accurate ASS native subtitles.
    """
    if video_type == "SONG":
        base_vf = (
            "[0:v]fps=30,scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=12:12,eq=brightness=-0.14:contrast=1.06,scale=1080:1920[bg];"
            "[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2-60"
        )
    else:
        base_vf = (
            "[0:v]fps=30,scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:8,scale=1080:1920[bg];"
            "[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

    if ass_subtitle_path and os.path.exists(ass_subtitle_path):
        # Escape path for FFmpeg libass filter on Windows
        escaped_ass = os.path.abspath(ass_subtitle_path).replace('\\', '/').replace(':', '\\:')
        vf_filter = f"{base_vf}[vcomposed];[vcomposed]ass='{escaped_ass}'"
    else:
        vf_filter = base_vf

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start_time),
        "-i", input_video,
        "-t", str(duration),
        "-filter_complex", vf_filter,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-r", "30",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_clip
    ]

    logger.info(f"Running FFmpeg ({video_type} style, Subtitles: {bool(ass_subtitle_path)}): {' '.join(cmd[:12])}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg failed: {res.stderr}")
        raise RuntimeError(f"FFmpeg reframing failed: {res.stderr[:300]}")


CLIPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exported_clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*"
}


def upload_to_catbox(file_path: str) -> str:
    """Uploads clip to Catbox.moe with full Chrome User-Agent and fast retries."""
    for attempt in range(2):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (os.path.basename(file_path), f)},
                    headers=HEADERS,
                    timeout=45
                )
            if resp.status_code == 200 and resp.text.strip().startswith("http"):
                return resp.text.strip()
            logger.warning(f"Catbox attempt {attempt+1} returned: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            logger.warning(f"Catbox attempt {attempt+1} failed: {e}")
            time.sleep(1)

    # Fallback to local server serving
    filename = os.path.basename(file_path)
    target_path = os.path.join(CLIPS_DIR, filename)
    shutil.copyfile(file_path, target_path)
    local_url = f"http://host.docker.internal:5050/clips/{filename}"
    logger.info(f"Using local server URL fallback: {local_url}")
    return local_url


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "media_processor", "version": "1.2.0"}


@app.get("/clips/{filename}")
def get_clip(filename: str):
    from fastapi.responses import FileResponse
    p = os.path.join(CLIPS_DIR, filename)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(p, media_type="video/mp4")


@app.post("/api/process-video")
def process_video(req: ProcessRequest):
    youtube_url = req.youtube_url.strip()
    short_count = req.short_count

    video_id = extract_video_id(youtube_url)
    if not video_id:
        raise HTTPException(status_code=400, detail=f"Invalid YouTube URL: {youtube_url}")

    work_dir = tempfile.mkdtemp(prefix=f"short_{video_id}_", dir=TEMP_BASE_DIR)
    source_file = os.path.join(work_dir, "source.mp4")

    try:
        # Step 1: Download YouTube Video & Metadata
        logger.info(f"Downloading source video {video_id}...")
        info = download_source_video(youtube_url, source_file)
        video_duration = float(info.get("duration", 0))
        video_title = info.get("title", "YouTube Video")

        if video_duration < 15.0:
            raise HTTPException(status_code=400, detail="Source video is too short to produce Shorts.")

        # Step 2: Fetch and Analyze Multilingual Transcripts & Detect Language
        logger.info(f"Detecting language & analyzing transcript for video {video_id}...")
        transcript, lang_code, lang_name = detect_and_fetch_transcript(video_id, info)
        logger.info(f"Detected video language: '{lang_code}' ({lang_name}) with {len(transcript)} transcript segments")

        selected_segments = analyze_and_select_segments(
            transcript=transcript,
            video_duration=video_duration,
            short_count=short_count,
            target_min=req.target_duration_min,
            target_max=req.target_duration_max,
            heatmap=info.get("heatmap", [])
        )

        if len(selected_segments) == 0:
            raise HTTPException(
                status_code=400,
                detail="Source video does not contain sufficient speech/content to create suitable Shorts."
            )

        # Step 3: Classify Video Type (Song vs Podcast)
        video_type = classify_video_type(info, transcript)
        logger.info(f"Video {video_id} ('{video_title}') classified as: {video_type}")

        # Step 4: Trim & Reframe each segment (Clean + Captioned)
        processed_clips = []
        for idx, seg in enumerate(selected_segments):
            clip_clean_name = f"clip_{idx+1}_clean.mp4"
            clip_captioned_name = f"clip_{idx+1}_captioned.mp4"
            clip_clean_path = os.path.join(work_dir, clip_clean_name)
            clip_captioned_path = os.path.join(work_dir, clip_captioned_name)
            ass_path = os.path.join(work_dir, f"clip_{idx+1}.ass")

            # 4a. Render Clean 9:16 Video
            logger.info(f"Trimming and reframing clip {idx+1} ({video_type} style): {seg['start_time']}s -> {seg['end_time']}s...")
            trim_and_reframe_to_9_16(
                input_video=source_file,
                output_clip=clip_clean_path,
                start_time=seg["start_time"],
                duration=seg["duration"],
                video_type=video_type
            )

            # 4b. Generate ASS subtitles & Render Captioned 9:16 Video
            has_subs = False
            if seg.get("snippets") and len(seg["snippets"]) > 0:
                has_subs = generate_ass_subtitles(
                    snippets=seg["snippets"],
                    clip_start=seg["start_time"],
                    clip_end=seg["end_time"],
                    language_code=lang_code,
                    output_ass_path=ass_path
                )

            if has_subs:
                logger.info(f"Rendering captioned clip {idx+1} with native {lang_name} typography...")
                trim_and_reframe_to_9_16(
                    input_video=source_file,
                    output_clip=clip_captioned_path,
                    start_time=seg["start_time"],
                    duration=seg["duration"],
                    video_type=video_type,
                    ass_subtitle_path=ass_path
                )

            # Step 5: Upload to direct public CDN
            logger.info(f"Uploading clean clip {idx+1} to direct CDN...")
            direct_url = upload_to_catbox(clip_clean_path)

            captioned_url = direct_url
            if has_subs and os.path.exists(clip_captioned_path):
                logger.info(f"Uploading captioned clip {idx+1} to direct CDN...")
                try:
                    captioned_url = upload_to_catbox(clip_captioned_path)
                except Exception as ue:
                    logger.warning(f"Could not upload captioned clip {idx+1}, falling back to clean: {ue}")
                    captioned_url = direct_url

            lyrics_text = seg.get("text", "").strip()

            processed_clips.append({
                "clip_index": idx + 1,
                "title": seg["title"],
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
                "duration": seg["duration"],
                "virality_score": seg["score"],
                "transcript_snippet": lyrics_text[:140],
                "lyrics": lyrics_text,
                "language": lang_code,
                "language_name": lang_name,
                "direct_url": direct_url,
                "captioned_url": captioned_url,
                "video_title": video_title,
                "video_type": video_type,
                "recommended_template": "Sara" if video_type == "SONG" else "Hormozi 2",
                "magic_zooms": False if video_type == "SONG" else True,
                "magic_brolls": False if video_type == "SONG" else True
            })

        return {
            "status": "success",
            "video_id": video_id,
            "video_title": video_title,
            "video_type": video_type,
            "language": lang_code,
            "language_name": lang_name,
            "total_requested": short_count,
            "total_created": len(processed_clips),
            "clips": processed_clips
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing video {youtube_url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary working directory: {work_dir}")
        except Exception as ce:
            logger.warning(f"Could not remove {work_dir}: {ce}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
