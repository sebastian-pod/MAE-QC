# camera_rpicam.py
import os
import time
import cv2
import sys
import shlex
import errno
import signal
import logging
import threading
import subprocess
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class CameraStream:
    """
    Camera stream that reads MJPEG frames from `rpicam-vid` stdout.

    Public API:
      - start()
      - get_frame() -> latest BGR numpy array or None
      - stop()

    Notes:
      - Designed for Raspberry Pi CSI cameras.
      - If you want USB webcams, use your OpenCV fallback instead.
    """

    def __init__(
        self,
        width=1280,
        height=720,
        fps=20,
        quality=80,
        rpicam_bin="rpicam-vid",
        extra_args=None,
        reconnect_delay=2,
        max_decode_fps=None,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(max(1, fps))
        self.quality = int(np.clip(quality, 1, 100))
        self.rpicam_bin = rpicam_bin
        self.extra_args = list(extra_args) if extra_args else ["--nopreview"]
        self.reconnect_delay = reconnect_delay
        # Limit JPEG->BGR decode rate to save CPU (None = decode every frame)
        self.max_decode_fps = max_decode_fps

        self._proc = None
        self._reader_thread = None
        self._running = False

        self._buf = bytearray()
        self._lock = threading.Lock()
        self._frame_bgr = None

    # ----------------- process management -----------------

    def _rpicam_cmd(self):
        # Emit MJPEG on stdout; --timeout 0 means run indefinitely
        # --framerate affects encoder pacing
        args = [
            self.rpicam_bin,
            "--codec", "mjpeg",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.fps),
            "--quality", str(self.quality),
            "--timeout", "0",
            "-o", "-"  # stdout
        ]
        args.extend(self.extra_args)
        return args

    def _spawn(self):
        cmd = self._rpicam_cmd()
        logging.info("Starting rpicam: %s", " ".join(shlex.quote(a) for a in cmd))
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"'{self.rpicam_bin}' not found. Install with: sudo apt install -y rpicam-apps"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start {self.rpicam_bin}: {e}")

        # Separate thread to log stderr (non-blocking)
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        if not self._proc or not self._proc.stderr:
            return
        for line in iter(self._proc.stderr.readline, b""):
            s = line.decode("utf-8", errors="ignore").rstrip()
            if s:
                logging.debug("[rpicam] %s", s)

    def _stop_proc(self):
        if not self._proc:
            return
        try:
            if self._proc.poll() is None:
                self._proc.send_signal(signal.SIGINT)
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        except Exception:
            pass
        self._proc = None

    # ----------------- MJPEG parsing & decode -----------------

    def _reader_loop(self):
        last_decode_t = 0.0
        decode_interval = None if not self.max_decode_fps else (1.0 / float(self.max_decode_fps))

        while self._running:
            # Ensure process exists
            if not self._proc or self._proc.poll() is not None:
                self._stop_proc()
                time.sleep(self.reconnect_delay)
                try:
                    self._spawn()
                except Exception as e:
                    logging.error("Failed to start rpicam: %s", e)
                    time.sleep(self.reconnect_delay)
                    continue

            # Read chunk from stdout
            try:
                chunk = self._proc.stdout.read(4096)
                if not chunk:
                    # End of stream or hiccup; respawn
                    logging.warning("rpicam stdout empty; restarting...")
                    self._stop_proc()
                    time.sleep(self.reconnect_delay)
                    continue
                self._buf.extend(chunk)
            except Exception as e:
                logging.error("Read error: %s", e)
                self._stop_proc()
                time.sleep(self.reconnect_delay)
                continue

            # Parse JPEG frames by SOI/EOI markers
            # SOI = 0xFFD8, EOI = 0xFFD9
            while True:
                soi = self._buf.find(b"\xff\xd8")
                if soi < 0:
                    # no start yet; keep filling
                    # trim runaway buffer
                    if len(self._buf) > 2 * 1024 * 1024:
                        del self._buf[:-4096]
                    break
                eoi = self._buf.find(b"\xff\xd9", soi + 2)
                if eoi < 0:
                    # have start, but not full frame yet
                    # trim preceding garbage
                    if soi > 0:
                        del self._buf[:soi]
                    break

                # Extract frame bytes (inclusive of EOI)
                eoi += 2
                jpg_bytes = self._buf[soi:eoi]
                del self._buf[:eoi]

                # Throttle decode if requested
                now = time.time()
                if decode_interval and (now - last_decode_t) < decode_interval:
                    # Skip decoding to save CPU; keep latest JPEG undecoded (optional)
                    continue

                # Decode to BGR
                try:
                    arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
                    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if bgr is not None:
                        with self._lock:
                            self._frame_bgr = bgr
                        last_decode_t = now
                except Exception as e:
                    logging.debug("imdecode failed: %s", e)
                    # ignore and continue to next frame

    # ----------------- Public API -----------------

    def start(self):
        if self._running:
            return
        self._running = True
        # start reader thread (it will spawn the process)
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True, name="RPiCamReader")
        self._reader_thread.start()
        logging.info("camera_rpicam: started")

    def get_frame(self):
        with self._lock:
            return None if self._frame_bgr is None else self._frame_bgr.copy()

    def stop(self):
        self._running = False
        try:
            if self._reader_thread and self._reader_thread.is_alive():
                self._reader_thread.join(timeout=2.0)
        except Exception:
            pass
        self._stop_proc()
        logging.info("camera_rpicam: stopped")