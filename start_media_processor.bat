@echo off
title Media Automation Processor Service
echo ================================================================================
echo  Starting Media Automation Processor Service on port 5050...
echo  Reachable inside Docker n8n at: http://host.docker.internal:5050/api/process-video
echo ================================================================================
python media_processor.py
pause
