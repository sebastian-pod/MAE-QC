# camera.py  (Spoof camera that returns a constant black frame)
import time
import threading
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class CameraStream:
    """
    Spoof camera stream that returns a black BGR frame.
    Implements the same minimal interface as the real CameraStream used by app.py:
      - start()
      - get_frame() -> numpy BGR image (H, W, 3) dtype=uint8
      - stop()
    Useful for local testing without Picamera2 or a physical camera.
    """
    def __init__(self, width=1280, height=720, fps=15, reconnect_delay=2):
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))
        self.reconnect_delay = reconnect_delay

        # Pre-create a single black frame to avoid allocations every loop
        self._black_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        self._lock = threading.Lock()
        self._frame = self._black_frame.copy()
        self._running = False
        self._thread = None

        logging.info(f"Spoof CameraStream initialized (black frame {self.width}x{self.height} @ {self.fps} FPS)")

    def start(self):
        """Start background thread that 'captures' the black frame at target FPS."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SpoofCameraThread")
        self._thread.start()
        logging.info("Spoof CameraStream started")

    def _loop(self):
        """Background loop that periodically updates the latest frame (keeps same black frame)."""
        target_dt = 1.0 / self.fps
        while self._running:
            t0 = time.time()
            # For realism we copy the black frame (so callers can modify safely)
            with self._lock:
                self._frame = self._black_frame.copy()
            # sleep to maintain fps
            dt = time.time() - t0
            if dt < target_dt:
                time.sleep(target_dt - dt)

    def get_frame(self):
        """Return the latest BGR frame (numpy uint8)."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        """Stop the background thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logging.info("Spoof CameraStream stopped")
