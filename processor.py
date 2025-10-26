# processor.py
import cv2
import numpy as np
from dataclasses import dataclass

PIXELS_PER_MM = 13.75 / 0.701  # your scale: 10 px = 1 mm

@dataclass
class Hole:
    cx: float
    cy: float
    diameter_mm: float
    diameter_px: float

def zoom_frame(frame, zoom_factor=2.0):
    """
    Zoom in on the center of the frame by zoom_factor.
    zoom_factor > 1 zooms in.
    """
    h, w = frame.shape[:2]
    new_w, new_h = int(w / zoom_factor), int(h / zoom_factor)
    x0, y0 = (w - new_w) // 2, (h - new_h) // 2
    cropped = frame[y0:y0+new_h, x0:x0+new_w]
    zoomed = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
    return zoomed

def measure_holes(frame_bgr, min_d_mm=5, max_d_mm=100, circularity_thresh=0.7):
    """
    Detect large holes in aluminum part with white paper background.
    Uses adaptive threshold to handle reflections and uneven lighting.
    """
    # Zoom in before processing
    frame_bgr = zoom_frame(frame_bgr, zoom_factor=1)  # adjust factor as needed

    img = frame_bgr.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)  # blur to remove reflections

    # Adaptive threshold (white holes -> black background)
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 51, 5
    )

    # Morph to remove small noise
    kernel = np.ones((5, 5), np.uint8)
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel)
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    holes = []
    min_r_px = (min_d_mm * PIXELS_PER_MM) / 2.0
    max_r_px = (max_d_mm * PIXELS_PER_MM) / 2.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area <= 0:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri <= 0:
            continue
        circularity = 4 * np.pi * area / (peri * peri)
        if circularity < circularity_thresh:
            continue

        (x, y), r = cv2.minEnclosingCircle(cnt)
        if r < min_r_px or r > max_r_px:
            continue

        diameter_px = 2 * r
        diameter_mm = diameter_px / PIXELS_PER_MM
        holes.append(Hole(cx=float(x), cy=float(y), diameter_mm=diameter_mm, diameter_px=diameter_px))

        # Draw circle + label
        cv2.circle(img, (int(x), int(y)), int(r), (0, 255, 0), 2)
        cv2.putText(img, f"{diameter_mm:.2f} mm", (int(x - r), int(y - r) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 220, 30), 2, cv2.LINE_AA)

    holes.sort(key=lambda h: (h.cy, h.cx))
    return holes, img

