# YouTube Shorts & Reels Automation Service

An automated pipeline and FastAPI microservice designed to transform long-form YouTube videos into vertical (9:16) Shorts and Reels with synchronized subtitles, intelligent reframing, and audio normalization.

---

## Features

- **FastAPI Microservice (`media_processor.py`)**:
  - REST API endpoint (`/api/process-video`) for workflow orchestrators (such as n8n or Make).
  - Automated YouTube video downloading via `yt-dlp`.
  - Multilingual transcript extraction via `youtube-transcript-api`.
  - Automatic language detection and heuristic-based viral segment selection.
  - 9:16 vertical reframing with background blur and foreground centering.
  - Synchronized subtitle burning using ASS formatting and FFmpeg.
  - Direct CDN/file hosting for generated clips.
- **Dedicated Short Renderer (`render_music_short.py`)**:
  - Standalone FFmpeg rendering pipeline.
  - High-fidelity audio normalization (`-14 LUFS` standard).
  - Smooth intro card transitions and synchronized typographic styling.
- **ASS Subtitle Generator (`generate_lyrics_subtitles.py`)**:
  - Custom script for generating high-precision ASS subtitles with custom color accents, positioning, and fade timings.

---

## Prerequisites

- **Python 3.9+**
- **FFmpeg**: Must be installed and added to your system `PATH` (with `libass` support for subtitle burning).

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/<repo-name>.git
   cd <repo-name>
   ```

2. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the Service

### Windows
Double-click [`start_media_processor.bat`](file:///start_media_processor.bat) or run:
```cmd
start_media_processor.bat
```

### Command Line
```bash
python media_processor.py
```
The service will start on port `5050`.

- **API Documentation**: [http://localhost:5050/docs](http://localhost:5050/docs)
- **Process Endpoint**: `POST http://localhost:5050/api/process-video`
