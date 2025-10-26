# camera.py

import time
import logging
import threading
import cv2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class _PiCam2Wrapper:
    """Picamera2 wrapper; returns frames as BGR for OpenCV. No libcamera.Transform needed."""
    def __init__(self, width=1920, height=1080, fps=30):
        from picamera2 import Picamera2  # no libcamera import

        self.picam2 = Picamera2()
        # Basic RGB888 stream; omit transform so we don't depend on libcamera.Transform
        config = self.picam2.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self.picam2.configure(config)

        # Optional: if your sensor supports these controls, you can flip via controls
        # (uncomment if you need flips and your camera exposes them)
        # try:
        #     self.picam2.set_controls({"HorizontalFlip": False, "VerticalFlip": False})
        # except Exception:
        #     pass

        self.picam2.start()
        time.sleep(0.5)  # let AE settle

    def read(self):
        frame_rgb = self.picam2.capture_array()  # RGB
        return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    def stop(self):
        try:
            self.picam2.stop()
        except Exception:
            pass

    def set_focus(self, pos):
        """
        Set manual focus if supported. 
        pos = focus value, e.g., 0-100 or sensor units.
        """
        try:
            # Turn off autofocus
            self.picam2.set_controls({"AfMode": 0})
            # Set absolute focus (scale may need adjustment)
            self.picam2.set_controls({"FocusAbsolute": int(pos*100)})  
        except Exception as e:
            logging.warning(f"Focus not supported: {e}")


class _OpenCVCamWrapper:
    """Fallback webcam (e.g., USB)"""
    def __init__(self, device=0, width=1280, height=720, fps=30):
        self.cap = cv2.VideoCapture(device)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        ok, _ = self.cap.read()
        if not ok:
            raise RuntimeError("OpenCV camera failed to initialize")

    def read(self):
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise RuntimeError("OpenCV camera read failed")
        return frame  # already BGR

    def stop(self):
        try:
            self.cap.release()
        except Exception:
            pass


class CameraStream:
    """
    - Tries Picamera2 first; falls back to OpenCV VideoCapture.
    - Runs a background thread to grab frames at target FPS.
    - Provides latest frame via .get_frame() (BGR).
    """
    def __init__(self, width=1280, height=720, fps=20, reconnect_delay=2):
        self.width = width
        self.height = height
        self.fps = max(1, int(fps))
        self.reconnect_delay = reconnect_delay

        self.impl = None
        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

    def _init_impl(self):
        # Prefer Picamera2 (now without libcamera.Transform dependency)
        try:
            self.impl = _PiCam2Wrapper(self.width, self.height, self.fps)
            logging.info("CameraStream: using Picamera2")
            return
        except Exception as e:
            logging.warning(f"Picamera2 failed: {e}")

        # Fallback to OpenCV
        self.impl = _OpenCVCamWrapper(0, self.width, self.height, self.fps)
        logging.info("CameraStream: using OpenCV VideoCapture fallback")

    def start(self):
        if self._running:
            return
        self._running = True
        self._init_impl()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        dt = 1.0 / self.fps
        while self._running:
            t0 = time.time()
            try:
                frame = self.impl.read()
                with self._lock:
                    self._frame = frame
            except Exception as e:
                logging.error(f"Camera read error: {e}. Reconnecting...")
                try:
                    self.impl.stop()
                except Exception:
                    pass
                self.impl = None
                time.sleep(self.reconnect_delay)
                try:
                    self._init_impl()
                except Exception as e2:
                    logging.error(f"Re-init error: {e2}")
                    time.sleep(self.reconnect_delay)
            elapsed = time.time() - t0
            if elapsed < dt:
                time.sleep(max(0, dt - elapsed))

    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        try:
            if self.impl:
                self.impl.stop()
        except Exception:
            pass
