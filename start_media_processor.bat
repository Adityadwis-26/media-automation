@echo off
title YouTube Shorts Media Processor Service
echo ================================================================================
echo  Starting YouTube Shorts Media Processor Service on port 5050...
echo  Reachable inside Docker n8n at: http://host.docker.internal:5050/api/process-video
echo ================================================================================
python media_processor.py
pause
