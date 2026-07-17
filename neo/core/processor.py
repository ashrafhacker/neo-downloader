import os
import uuid
import shutil
import subprocess
import threading
from pathlib import Path
from neo.core.logger import logger

DOWNLOADS = Path(__file__).parent.parent.parent / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

FFMPEG_OK = shutil.which("ffmpeg") is not None

def clip_media(filename, start, end, task_id=None):
    """Clips media using ffmpeg."""
    if not FFMPEG_OK:
        raise Exception("ffmpeg not found")
        
    filepath = DOWNLOADS / filename
    if not filepath.is_file():
        raise Exception("Source file not found")
        
    uid = uuid.uuid4().hex
    out = DOWNLOADS / f"{uid}_clip_{filepath.stem}.mp4"
    
    cmd = [
        shutil.which("ffmpeg"),
        "-i", str(filepath),
        "-ss", start, "-to", end,
        "-c", "copy",
        "-y", str(out)
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if not out.is_file():
        err = result.stderr.decode() if result.stderr else "Unknown error"
        logger.error(f"Clipping failed: {err}")
        raise Exception(f"Clipping failed: {err}")
        
    # Auto-cleanup timer for the result file
    def cleanup():
        try: os.remove(out)
        except: pass
    threading.Timer(300, cleanup).start()
    
    return {"filename": out.name}

def remove_watermark(filename, zones=None, auto=False, scrub=True, task_id=None):
    """Removes watermark and scrubs metadata."""
    if not FFMPEG_OK:
        raise Exception("ffmpeg not found")
        
    filepath = DOWNLOADS / filename
    if not filepath.is_file():
        raise Exception("Source file not found")
        
    uid = uuid.uuid4().hex
    out = DOWNLOADS / f"{uid}_clean_{filepath.stem}.mp4"
    
    cmd = [shutil.which("ffmpeg"), "-i", str(filepath)]
    
    if scrub:
        cmd += ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
        
    vf_parts = []
    if auto:
        # Default common zones
        zones = [
            (10, 10, 150, 50),    # top-left
            (10, 580, 160, 50),   # bottom-left
            (470, 580, 160, 50),  # bottom-right
            (0, 0, 640, 80),      # top strip
            (0, 550, 640, 80),    # bottom strip
            (280, 40, 120, 50),   # tiktok center-top
            (150, 200, 180, 80),  # center
        ]
    
    if zones:
        for zx, zy, zw, zh in zones:
            vf_parts.append(f"delogo=x={zx}:y={zy}:w={zw}:h={zh}:show=0")
            
    if vf_parts:
        cmd += ["-vf", ",".join(vf_parts)]
        
    cmd += ["-c:a", "copy"]
    
    if scrub:
        cmd += ["-metadata", "title=", "-metadata", "author=", "-metadata", "comment=",
                "-metadata", "description=", "-metadata", "creation_time=",
                "-metadata:s:v", "title=", "-metadata:s:a", "title="]
                
    cmd += ["-y", str(out)]
    
    result = subprocess.run(cmd, capture_output=True, timeout=600)
    if not out.is_file():
        err = result.stderr.decode() if result.stderr else "Unknown error"
        logger.error(f"Watermark removal failed: {err}")
        raise Exception(f"Watermark removal failed: {err}")
        
    # Scrub file system timestamps if requested
    if scrub:
        try:
            t = os.path.getmtime(out)
            os.utime(out, (t, t))
        except: pass
        
    # Auto-cleanup timer
    def cleanup():
        try: os.remove(out)
        except: pass
    threading.Timer(300, cleanup).start()
    
    return {"filename": out.name}
