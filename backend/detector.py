import cv2
import numpy as np
import base64
import os
import sys

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from super_scanner import scan_v5, clahe_equalized, local_normalize


def detect_datamatrix_fast(image_bytes):
    """Fast detection using simple pylibdmtx - for real-time camera preview."""
    from pylibdmtx import pylibdmtx
    
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    results = pylibdmtx.decode(gray, timeout_ms=300, max_count=20)

    boxes = []
    for result in results:
        rect = result.rect
        boxes.append({
            "x": rect.left, "y": rect.top,
            "width": rect.width, "height": rect.height
        })
    return boxes


def detect_datamatrix_super(image_bytes):
    """Intensive detection using scan_v5 - for lightning bolt mode."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Run the intensive scan_v5 algorithm
    code, rect, method, info = scan_v5(gray, max_total_time=15.0)
    
    if code and rect:
        x, y, w, h = rect
        return {
            "code": code,
            "x": x, "y": y,
            "width": w, "height": h,
            "method": method
        }
    return None


def draw_boxes(image_bytes, boxes):
    """Draw bounding boxes on image."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    for box in boxes:
        x, y, w, h = box["x"], box["y"], box["width"], box["height"]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(img, "DM", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    success, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not success:
        return image_bytes
    return encoded.tobytes()


def draw_super_result(image_bytes, result):
    """Draw super scan result with code info."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    x, y, w, h = result["x"], result["y"], result["width"], result["height"]
    
    # Draw thick green box
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 4)
    
    # Draw method label
    method = result.get("method", "unknown")[:20]
    cv2.putText(img, method, (x, y - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    success, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        return image_bytes
    return encoded.tobytes()
