# app.py
import os
import time
import threading
import logging
from flask import Flask, Response, render_template, jsonify, request
import cv2
import base64

from camera import CameraStream
from processor import measure_holes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Tunables
FPS_STREAM = int(os.getenv("STREAM_FPS", "10"))      # MJPEG stream FPS
FPS_ANALYZE = int(os.getenv("ANALYZE_FPS", "1"))     # analysis rate to save CPU
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "20"))

app = Flask(__name__)

# Start camera
# cam = CameraStream(
#     width=1280,
#     height=720,
#     fps=1,           # encoder FPS
#     quality=100,       # MJPEG quality (1-100)
#     extra_args=["--nopreview"],   # add rpicam flags here if needed
#     max_decode_fps=1 # limit JPEG→BGR decode load
# )

cam = CameraStream(width=1920,height=1080,fps=20)

cam.start()

# Shared state
last_jpeg = None
last_metrics = {"count": 0, "holes_mm": [], "timestamp": 0}
_state_lock = threading.Lock()

def _encode_jpeg(bgr):
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()

def producer_loop():
    """Grab frames quickly for smooth streaming."""
    global last_jpeg
    dt = 1.0 / max(1, FPS_STREAM)
    while True:
        frame = cam.get_frame()
        if frame is not None:
            try:
                with _state_lock:
                    last_jpeg = _encode_jpeg(frame)
            except Exception as e:
                logging.error(f"MJPEG encode error: {e}")
        time.sleep(dt)

def analyzer_loop():
    """Run OpenCV hole detection at a lower rate; also draw overlays for streaming."""
    global last_jpeg, last_metrics
    dt = 1.0 / max(1, FPS_ANALYZE)
    while True:
        frame = cam.get_frame()
        if frame is not None:
            holes, annotated = measure_holes(frame)  # updated measure_holes
            with _state_lock:
                last_metrics = {
                    "count": len(holes),
                    "holes_mm": [round(h.diameter_mm, 3) for h in holes],
                    "timestamp": time.time(),
                }
                # Always stream annotated frame
                try:
                    last_jpeg = _encode_jpeg(annotated)
                except Exception as e:
                    logging.error(f"Annotated JPEG encode error: {e}")
        time.sleep(dt)

# Start background workers
#threading.Thread(target=producer_loop, daemon=True).start()
threading.Thread(target=analyzer_loop, daemon=True).start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/focus", methods=["POST"])
def focus():
    pos = float(request.args.get("pos", 11.5))
    try:
        cam.impl.set_focus(pos)  # call the new method
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/video")
def video():
    boundary = b"--frame"
    def gen():
        while True:
            with _state_lock:
                jpg = last_jpeg
            if jpg is None:
                time.sleep(0.05)
                continue
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/metrics")
def metrics():
    with _state_lock:
        return jsonify(last_metrics)

@app.route("/health")
def health():
    return jsonify(status="ok")

@app.route("/video_snapshot")
def video_snapshot():
    frame = cam.get_frame()
    if frame is None:
        return jsonify({"error": "No frame available"}), 500

    # Measure holes and get annotated frame
    holes, annotated = measure_holes(frame)

    # Encode annotated frame to JPEG, then base64
    _, buffer = cv2.imencode(".jpg", annotated)
    img_b64 = base64.b64encode(buffer).decode("utf-8")

    return jsonify({
        "image_base64": img_b64,
        "holes_mm": [round(h.diameter_mm, 2) for h in holes],
        "timestamp": int(time.time())
    })

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host=host, port=port, threaded=True)