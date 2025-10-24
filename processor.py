# processor.py
import cv2
import numpy as np
from dataclasses import dataclass

PIXELS_PER_MM = 10.0  # your scale: 10 px == 1 mm

@dataclass
class Hole:
    cx: float
    cy: float
    diameter_mm: float
    diameter_px: float

def measure_holes(frame_bgr, min_d_mm=2, max_d_mm=100, circularity_thresh=0.7):
    """
    Returns (holes, annotated_frame)
    - holes: list[Hole]
    - annotated_frame: BGR image with circles and labels
    """
    img = frame_bgr.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Boost contrast & suppress noise
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    # Adaptive threshold tends to work well on matte metal plates
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 35, 5)

    # Morph open to clean specks
    kernel = np.ones((3, 3), np.uint8)
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel, iterations=1)

    # Find contours (holes should be filled white blobs now)
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

        circularity = 4.0 * np.pi * area / (peri * peri)
        if circularity < circularity_thresh:
            continue

        (x, y), r = cv2.minEnclosingCircle(cnt)
        if r < min_r_px or r > max_r_px:
            continue

        diameter_px = 2.0 * r
        diameter_mm = diameter_px / PIXELS_PER_MM
        holes.append(Hole(cx=float(x), cy=float(y), diameter_mm=diameter_mm, diameter_px=diameter_px))

        # Draw annotation
        cv2.circle(img, (int(x), int(y)), int(r), (0, 255, 0), 2)
        label = f"{diameter_mm:.2f} mm"
        cv2.putText(img, label, (int(x - r), int(y - r) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 220, 30), 2, cv2.LINE_AA)

    # Sort by x,y for stable ordering
    holes.sort(key=lambda h: (h.cy, h.cx))
    return holes, img
