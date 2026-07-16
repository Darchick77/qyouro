"""DataMatrix Super Scanner v5 — priority-queue based multi-phase pipeline."""
import cv2
import numpy as np
from PIL import Image
from pylibdmtx.pylibdmtx import decode
import time, math

try:
    import zxingcpp
    _has_zxing = True
except:
    _has_zxing = False


def _attempt(pil_img, shrink=1, threshold=None, deviation=25,
             min_edge=None, max_edge=None, timeout=80, max_count=1):
    kwargs = dict(shrink=shrink, deviation=deviation, timeout=timeout, max_count=max_count)
    if threshold is not None:
        kwargs["threshold"] = threshold
    if min_edge is not None:
        kwargs["min_edge"] = min_edge
    if max_edge is not None:
        kwargs["max_edge"] = max_edge
    try:
        res = decode(pil_img, **kwargs)
        if res:
            d = res[0]
            return d.data.decode('utf-8', errors='replace'), \
                   (d.rect.left, d.rect.top, d.rect.width, d.rect.height)
    except:
        pass
    return None


def _try(gray, s=1, t=None, timeout=50):
    return _attempt(Image.fromarray(gray), shrink=s, threshold=t, timeout=timeout)


def _try_dev(gray, s=1, t=None, timeout=50, deviation=50):
    """Like _try but with specified deviation for faded finder patterns."""
    return _attempt(Image.fromarray(gray), shrink=s, threshold=t, deviation=deviation, timeout=timeout)


def _try_faded(gray, s=1, timeout=50):
    """Try multiple deviations to find faded DM finder patterns."""
    for dev in [50, 75, 100, 150]:
        r = _attempt(Image.fromarray(gray), shrink=s, deviation=dev, timeout=timeout // 2)
        if r:
            return r
    return None


def _try_zxing(gray, timeout=100):
    if not _has_zxing:
        return None
    try:
        results = zxingcpp.read_barcodes(gray, try_rotate=True, try_downscale=True,
                                          try_invert=True, timeout=timeout)
        if results:
            for r in results:
                if r.valid and r.text:
                    return r.text, (0, 0, 0, 0)
    except:
        pass
    return None


# --- PREPROCESSING -----------------------------------------------------

def sharpen(gray):
    b = cv2.GaussianBlur(gray, (0, 0), 3.0)
    return cv2.addWeighted(gray, 1.5, b, -0.5, 0)


def deblur_wiener(gray, kernel_size=9, noise_var=0.001):
    gray_f = gray.astype(np.float64) / 255.0
    psf = np.zeros((kernel_size, kernel_size))
    psf[kernel_size // 2, :] = 1.0 / kernel_size
    psf_pad = np.zeros_like(gray_f)
    kh, kw = psf.shape
    psf_pad[:kh, :kw] = psf
    PSF = np.fft.fft2(psf_pad)
    PSF_conj = np.conj(PSF)
    I = np.fft.fft2(gray_f)
    result = np.fft.ifft2((PSF_conj * I) / (PSF_conj * PSF + noise_var))
    return np.clip(np.real(result) * 255, 0, 255).astype(np.uint8)


def auto_scale(gray, max_dim=1600):
    h, w = gray.shape
    if max(w, h) > max_dim:
        s = max_dim / max(w, h)
        gray = cv2.resize(gray, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return gray


def clahe_equalized(gray):
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)


def local_normalize(gray, blur_size=51):
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
    return np.clip(cv2.subtract(gray, blurred) + 128, 0, 255).astype(np.uint8)


def multi_scale_retinex(gray, scales=(5, 20, 80)):
    """Enhance local contrast invariantly to illumination."""
    f = gray.astype(np.float32) + 1.0
    out = np.zeros_like(f)
    for s in scales:
        if s % 2 == 0:
            s += 1
        b = cv2.GaussianBlur(f, (s, s), 0)
        out += np.log(f) - np.log(b + 1.0)
    out = (out - out.min()) / (out.max() - out.min() + 1e-10) * 255
    return out.astype(np.uint8)


def diff_of_gaussians(gray, sigma1=1.0, sigma2=4.0):
    """Edge enhancement via DoG — excellent for module boundaries."""
    g1 = cv2.GaussianBlur(gray, (0, 0), sigma1)
    g2 = cv2.GaussianBlur(gray, (0, 0), sigma2)
    dog = g1.astype(np.float32) - g2.astype(np.float32)
    dog = np.clip(dog + 128, 0, 255).astype(np.uint8)
    return dog


def morph_reconstruct(gray, ksize=15):
    """Morphological closing to bridge gaps in faded finder patterns."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    return closed

# --- DM REGION EXTRACTION (improved) ------------------------------------

def extract_dm_region(gray):
    h, w = gray.shape
    if h < 10 or w < 10:
        return None, 0

    big_rect = None
    angled_rect = None
    big_score = 0
    angled_score = 0
    max_area_ratio = 0.95 if max(w, h) < 120 else 0.6

    for method in ["otsu_inv", "adaptive", "otsu"]:
        try:
            if method == "otsu_inv":
                _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            elif method == "otsu":
                _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 31, 5)

            bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
            ct, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in ct:
                area = cv2.contourArea(c)
                if area < h * w * 0.01 or area > h * w * max_area_ratio:
                    continue
                rect = cv2.minAreaRect(c)
                box_w, box_h = rect[1]
                if box_w < 10 or box_h < 10:
                    continue
                hull = cv2.convexHull(c)
                hull_area = cv2.contourArea(hull)
                solidity = area / hull_area if hull_area > 0 else 0
                fill = area / (box_w * box_h) if box_w * box_h > 0 else 0
                angle = rect[2]
                if box_w < box_h:
                    angle = 90 + angle
                angle_norm = abs(angle) % 90
                if angle_norm > 45:
                    angle_norm = 90 - angle_norm
                score = int(area * solidity)

                if angle_norm < 3 and fill > 0.3 and score > big_score:
                    big_score = score
                    big_rect = rect
                if angle_norm > 3 and solidity > 0.3 and score > angled_score:
                    angled_score = score
                    angled_rect = rect
        except:
            pass

    if big_rect and angled_rect:
        center, size = big_rect[0], big_rect[1]
        angle2 = angled_rect[2]
        if angled_rect[1][0] < angled_rect[1][1]:
            angle2 = 90 + angle2
        combined = (center, size, angle2)
        box = np.array(cv2.boxPoints(combined), dtype=np.float32)
    elif angled_rect:
        box = np.array(cv2.boxPoints(angled_rect), dtype=np.float32)
        angle2 = angled_rect[2]
        if angled_rect[1][0] < angled_rect[1][1]:
            angle2 = 90 + angle2
    elif big_rect:
        box = np.array(cv2.boxPoints(big_rect), dtype=np.float32)
        angle2 = big_rect[2]
        if big_rect[1][0] < big_rect[1][1]:
            angle2 = 90 + angle2
    else:
        return None, 0

    s = box.sum(axis=1)
    tl = box[np.argmin(s)]
    br = box[np.argmax(s)]
    d = np.diff(box, axis=1)
    tr = box[np.argmin(d)]
    bl = box[np.argmax(d)]

    wA = np.linalg.norm(br - bl)
    wB = np.linalg.norm(tr - tl)
    maxW = max(int(wA), int(wB)) + 20
    hA = np.linalg.norm(tr - br)
    hB = np.linalg.norm(tl - bl)
    maxH = max(int(hA), int(hB)) + 20
    if maxW < 10 or maxH < 10:
        return None, 0

    dst = np.array([[10, 10], [maxW - 11, 10],
                     [maxW - 11, maxH - 11], [10, maxH - 11]], dtype=np.float32)
    src = np.array([tl, tr, br, bl], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warp = cv2.warpPerspective(gray, M, (maxW, maxH))
    return warp, angle2


# --- ROI EXTRACTION FOR REAL-WORLD IMAGES -----------------------------

def find_dm_rois(gray, max_candidates=12):
    """Find square-ish contour regions that could contain DataMatrix codes.
    Returns list of (roi_img, bbox) for further processing."""
    h, w = gray.shape
    candidates = []

    # Multi-method contour search — include CLAHE + adaptive for faded DMs
    cl = clahe_equalized(gray)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    grad = cv2.magnitude(cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3),
                         cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))
    grad_norm = np.clip(grad / grad.max() * 255, 0, 255).astype(np.uint8)

    methods = [
        ("otsu_inv", lambda: cv2.threshold(cl, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]),
        ("otsu", lambda: cv2.threshold(cl, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        ("canny", lambda: cv2.morphologyEx(cv2.Canny(cl, 20, 80), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))),
        ("grad", lambda: cv2.threshold(grad_norm, 30, 255, cv2.THRESH_BINARY)[1]),
    ]
    for win in [11, 21, 31, 51, 71]:
        if win < min(h, w):
            try:
                methods.append((f"adapt{win}", lambda w=win: cv2.adaptiveThreshold(
                    cl, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, w, 2)))
            except:
                pass

    for method_name, fn in methods:
        try:
            bw = fn()
            if method_name != "canny" and method_name != "grad":
                bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

            # For canny/grad: connect nearby edges
            if method_name in ("canny", "grad"):
                bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

            ct, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except:
            continue

        for c in ct:
            area = cv2.contourArea(c)
            if area < 200 or area > w * h * 0.6:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            if cw < 20 or ch < 20:
                continue
            aspect = max(cw, ch) / min(cw, ch) if min(cw, ch) > 0 else 99
            if aspect > 4.0:
                continue

            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0
            fill = area / (cw * ch) if cw * ch > 0 else 0
            if solidity < 0.2 or fill < 0.1:
                continue

            pad = max(10, int(min(cw, ch) * 0.15))
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + cw + pad)
            y2 = min(h, y + ch + pad)
            roi = gray[y1:y2, x1:x2]
            quality = solidity * fill * (0.8 if "inv" in method_name else 0.5)
            candidates.append((roi, (x1, y1, x2, y2), quality, area, method_name))

    # Dedup by overlap
    uniq = []
    for roi, box, quality, area, method_name in sorted(candidates, key=lambda x: -x[2]):
        dup = False
        for i, (_, ub, q_other, a_other, _) in enumerate(uniq):
            ax1, ay1, ax2, ay2 = box
            bx1, by1, bx2, by2 = ub
            ox1, oy1 = max(ax1, bx1), max(ay1, by1)
            ox2, oy2 = min(ax2, bx2), min(ay2, by2)
            if ox1 < ox2 and oy1 < oy2:
                inter = (ox2 - ox1) * (oy2 - oy1)
                if inter / min((ax2-ax1)*(ay2-ay1), (bx2-bx1)*(by2-by1)) > 0.5:
                    if quality > q_other:
                        uniq[i] = (roi, box, quality, area, method_name)
                    dup = True
                    break
        if not dup:
            uniq.append((roi, box, quality, area, method_name))

    return [(r, b) for r, b, _, _, _ in uniq[:max_candidates]]


def try_roi_decode(gray, shrink_list, timeout=20):
    """Find DM candidate ROIs and try decoding with CLAHE preprocessing."""
    rois = find_dm_rois(gray)
    if not rois:
        return None

    for roi, bbox in rois:
        for s in shrink_list:
            r = _try(roi, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"roi_s{s}"

            cl = clahe_equalized(roi)
            r = _try(cl, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"roi_clahe_s{s}"

            sh = sharpen(roi)
            r = _try(sh, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"roi_sharp_s{s}"

        # Try CLAHE + rotations (first shrink only)
        cl = clahe_equalized(roi)
        s0 = shrink_list[0]
        for angle in [90, 180, 270]:
            rh, rw = cl.shape
            M = cv2.getRotationMatrix2D((rw // 2, rh // 2), angle, 1.0)
            rot = cv2.warpAffine(cl, M, (rw, rh))
            r = _try(rot, s=s0, timeout=timeout)
            if r:
                return r[0], r[1], f"roi_clahe_rot{angle}_s{s0}"

        # Try CLAHE + upscale for small ROIs
        if max(cl.shape) < 150:
            sc = max(2, min(4, 200 // max(cl.shape)))
            up = cv2.resize(cl, (cl.shape[1]*sc, cl.shape[0]*sc), cv2.INTER_CUBIC)
            r = _try(up, s=s0, timeout=timeout)
            if r:
                return r[0], r[1], f"roi_clahe_up{sc}_s{s0}"

        # Try with high deviation (faded finder)
        r = _try_faded(roi, s=2, timeout=timeout)
        if r:
            return r[0], r[1], "roi_faded_s2"

    return None


def try_grid_decode(gray, shrink_list, timeout=20):
    """Brute-force: divide image into overlapping grid tiles, try decode each.
    Essential when DMs are missed by contour-based ROI detection."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    cl = clahe_equalized(gray)
    tile_size = 100
    overlap = 50

    for y in range(0, h - tile_size + 1, tile_size - overlap):
        for x in range(0, w - tile_size + 1, tile_size - overlap):
            tile = cl[y:y + tile_size, x:x + tile_size]
            for s in [1, 2]:
                r = _try(tile, s=s, timeout=timeout // 4)
                if r:
                    return r[0], r[1], f"grid_{x}_{y}_s{s}"
                r = _try_faded(tile, s=s, timeout=timeout // 4)
                if r:
                    return r[0], r[1], f"grid_fade_{x}_{y}_s{s}"

    return None


# --- SCANNING HELPERS --------------------------------------------------

def try_rotations(gray, angles, shrink_list, timeout=30):
    for angle in angles:
        if angle == 0:
            img = gray
        else:
            h, w = gray.shape
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            img = cv2.warpAffine(gray, M, (w, h))
        for s in shrink_list:
            r = _try(img, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"rot{angle}_s{s}" if angle != 0 else f"direct_s{s}"
    return None


def try_warp_and_rotations(gray, shrink_list, timeout=30):
    warp, angle = extract_dm_region(gray)
    if warp is None:
        return None
    for a in [0, 90, 180, 270]:
        if a == 0:
            img = warp
        else:
            h, w = warp.shape
            M = cv2.getRotationMatrix2D((w // 2, h // 2), a, 1.0)
            img = cv2.warpAffine(warp, M, (w, h))
        for s in shrink_list:
            r = _try(img, s=s, timeout=timeout)
            if r:
                label = f"warp{angle:.0f}_rot{a}_s{s}" if a != 0 else f"warp{angle:.0f}_s{s}"
                return r[0], r[1], label
    return None


def try_deskew(gray, shrink_list, timeout=30):
    warp, angle = extract_dm_region(gray)
    if warp is None or abs(angle) < 3:
        return None
    h, w = gray.shape
    sc = max(2, min(4, 300 // max(w, h)))
    up = cv2.resize(gray, (w * sc, h * sc), interpolation=cv2.INTER_CUBIC)
    pad = int(max(up.shape) * 0.5)
    padded = cv2.copyMakeBorder(up, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    h2, w2 = padded.shape
    M = cv2.getRotationMatrix2D((w2 // 2, h2 // 2), -angle, 1.0)
    deskewed = cv2.warpAffine(padded, M, (w2, h2), flags=cv2.INTER_NEAREST)
    crop = deskewed[pad:pad + up.shape[0], pad:pad + up.shape[1]]
    return try_rotations(crop, [0, 90, 180, 270], shrink_list, timeout)


def try_upscale(gray, shrink_list, timeout=30):
    h, w = gray.shape
    if max(w, h) >= 500:
        return None
    for sc in [2, 3]:
        up = cv2.resize(gray, (w * sc, h * sc), interpolation=cv2.INTER_CUBIC)
        r = try_warp_and_rotations(up, shrink_list, timeout)
        if r:
            return r[0], r[1], f"up{sc}_" + r[2]
        r = try_rotations(up, [0, 90, 180, 270], shrink_list, timeout)
        if r:
            return r
    return None


def try_binary_candidates(gray, shrink_list, timeout=15, prefix=""):
    cand = []
    h, w = gray.shape
    if h < 4 or w < 4:
        return None
    cand.append((f"{prefix}direct", gray.copy()))
    _, oi = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cand.append((f"{prefix}otsu_inv", oi))
    _, od = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cand.append((f"{prefix}otsu", od))
    for win in [11, 21, 31, 51]:
        if win > min(h, w):
            continue
        try:
            ad = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, win, 2)
            cand.append((f"{prefix}adapt{win}", ad))
        except:
            pass
    for s in shrink_list:
        for label, img in cand:
            r = _try(img, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"{prefix}bin_s{s}_{label}"
    return None


def try_perspective_fixes(gray, shrink_list, timeout=15):
    h, w = gray.shape
    if max(w, h) < 30:
        return None
    shifts = [1, 3, 5, 7, 9, 11, 13, -3, -5, -7]
    s0 = shrink_list[0]
    for shift in shifts:
        try:
            src = np.float32([[shift, 0],
                              [w - 1 - 2*shift, shift],
                              [0, h - 1],
                              [w - 1, h - 1]])
            dst = np.float32([[0, 0],
                              [w - 1, 0],
                              [0, h - 1],
                              [w - 1, h - 1]])
            M = cv2.getPerspectiveTransform(src, dst)
            corr = cv2.warpPerspective(gray, M, (w, h))
        except:
            continue
        r = _try(corr, s=s0, timeout=timeout)
        if r:
            return r[0], r[1], f"persp{shift}_{s0}"
    return None


def try_zxing_fallback(gray, timeout=100):
    if not _has_zxing:
        return None
    for img_v, label in [(gray, "raw"), (255 - gray, "inv")]:
        r = _try_zxing(img_v, timeout=timeout)
        if r:
            return r[0], r[1], f"zx_{label}"
    h, w = gray.shape
    if max(w, h) < 500:
        up = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        r = _try_zxing(up, timeout=timeout)
        if r:
            return r[0], r[1], "zx_up2"
    return None


def try_edge_grid(gray, shrink_list, timeout=15):
    """Fast grid scan: find high-edge-density blocks, extract ROIs, decode."""
    h, w = gray.shape
    if max(w, h) < 300:
        return None

    block = 64
    bh, bw = max(1, h // block), max(1, w // block)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)

    density = np.zeros((bh, bw), dtype=np.float32)
    for by in range(bh):
        y0, y1 = by * block, min(h, (by + 1) * block)
        for bx in range(bw):
            x0, x1 = bx * block, min(w, (bx + 1) * block)
            density[by, bx] = float(np.mean(mag[y0:y1, x0:x1]))

    thresh = np.percentile(density, 80)
    mask = (density > thresh).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    num, labeled = cv2.connectedComponents(mask)

    cl = clahe_equalized(gray)

    for lbl in range(1, num):
        ys, xs = np.where(labeled == lbl)
        if len(ys) < 2:
            continue
        y1 = max(0, ys.min() * block - block)
        y2 = min(h, (ys.max() + 1) * block + block)
        x1 = max(0, xs.min() * block - block)
        x2 = min(w, (xs.max() + 1) * block + block)

        crop = cl[y1:y2, x1:x2]
        if crop.shape[0] < 30 or crop.shape[1] < 30:
            continue

        for s in shrink_list:
            r = _try(crop, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"grid_s{s}"

    return None


def try_multi_threshold(gray, shrink_list, timeout=15):
    """Sweep many fixed thresholds to find DM finder pattern at ANY binarization level.
    Even very faded DMs become visible at the right threshold."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    # Downsample for speed
    scale = 1.0
    small = gray
    if max(w, h) > 1000:
        scale = 800.0 / max(w, h)
        small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape

    mn, mx = int(gray.min()) + 2, int(gray.max()) - 2
    if mx - mn < 10:
        return None

    candidates = []

    # Sweep thresholds
    step = max(1, (mx - mn) // 25)
    for th in range(mn, mx, step):
        _, bw = cv2.threshold(small, th, 255, cv2.THRESH_BINARY)
        # Also try inverse
        _, bwi = cv2.threshold(small, th, 255, cv2.THRESH_BINARY_INV)

        for binarized, inv in [(bw, False), (bwi, True)]:
            # Close small gaps to connect finder pattern segments
            closed = cv2.morphologyEx(binarized, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            ct, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in ct:
                area = cv2.contourArea(c)
                if area < 200 or area > sh * sw * 0.3:
                    continue
                x, y, cw, ch = cv2.boundingRect(c)
                if cw < 20 or ch < 20:
                    continue
                aspect = max(cw, ch) / min(cw, ch) if min(cw, ch) > 0 else 99
                if aspect > 4.0:
                    continue
                hull = cv2.convexHull(c)
                hull_area = cv2.contourArea(hull)
                solidity = area / hull_area if hull_area > 0 else 0
                fill = area / (cw * ch) if cw * ch > 0 else 0

                # DM-like: good solidity (L-shape is ~50% of bounding box for DM) and fill
                # The finder pattern is about 50% of a DM quadrant
                if solidity > 0.3 and fill > 0.2:
                    # Map back to original coordinates
                    ox = int(x / scale) if scale < 1.0 else x
                    oy = int(y / scale) if scale < 1.0 else y
                    ocw = int(cw / scale) if scale < 1.0 else cw
                    och = int(ch / scale) if scale < 1.0 else ch

                    pad = max(10, int(min(ocw, och) * 0.2))
                    x1 = max(0, ox - pad)
                    y1 = max(0, oy - pad)
                    x2 = min(w, ox + ocw + pad)
                    y2 = min(h, oy + och + pad)

                    quality = solidity * fill * (1 + 0.5 * (not inv))
                    candidates.append(((x1, y1, x2, y2), quality, area, th, inv))

    if not candidates:
        return None

    # Dedup
    uniq = []
    for box, quality, area, th, inv in sorted(candidates, key=lambda x: -x[1]):
        dup = False
        for ub, _, _, _, _ in uniq:
            ax1, ay1, ax2, ay2 = box
            bx1, by1, bx2, by2 = ub
            ox1, oy1 = max(ax1, bx1), max(ay1, by1)
            ox2, oy2 = min(ax2, bx2), min(ay2, by2)
            if ox1 < ox2 and oy1 < oy2:
                inter = (ox2 - ox1) * (oy2 - oy1)
                if inter / min((ax2-ax1)*(ay2-ay1), (bx2-bx1)*(by2-by1)) > 0.5:
                    dup = True
                    break
        if not dup:
            uniq.append((box, quality, area, th, inv))

    # Try each candidate with aggressive enhancement
    for (x1, y1, x2, y2), quality, area, th, inv in uniq[:10]:
        roi = gray[y1:y2, x1:x2]
        if roi.shape[0] < 30 or roi.shape[1] < 30:
            continue

        # KEY: try the EXACT threshold that found this candidate on the full-res ROI
        exact = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6,6)).apply(roi)
        if inv:
            _, roi_bw = cv2.threshold(exact, th, 255, cv2.THRESH_BINARY_INV)
        else:
            _, roi_bw = cv2.threshold(exact, th, 255, cv2.THRESH_BINARY)
        r = _try(roi_bw, s=1, timeout=timeout)
        if r:
            return r[0], r[1], f"mthr_exact{th}_s1"

        # Try multiple enhancements
        for prep_name, prep_fn in [
            ("raw", lambda x: x),
            ("clahe", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(x)),
            ("ln", lambda x: np.clip(cv2.subtract(x, cv2.GaussianBlur(x, (51,51), 0)) + 128, 0, 255).astype(np.uint8)),
            ("ln_cl", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(
                np.clip(cv2.subtract(x, cv2.GaussianBlur(x, (51,51), 0)) + 128, 0, 255).astype(np.uint8))),
        ]:
            img = prep_fn(roi)
            for s in shrink_list:
                r = _try(img, s=s, timeout=timeout)
                if r:
                    return r[0], r[1], f"mthr_{prep_name}_s{s}"

        # Also try fixed thresholds on the ROI
        cl = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(roi)
        for th in range(30, 225, 15):
            _, bw = cv2.threshold(cl, th, 255, cv2.THRESH_BINARY)
            r = _try(bw, s=2, timeout=timeout // 2)
            if r:
                return r[0], r[1], f"mthr_fix{th}_s2"

    return None


def try_clahe_variants(gray, shrink_list, timeout=15):
    """Try multiple CLAHE parameter combinations."""
    for clip in [2.0, 4.0, 6.0]:
        for tile in [(6,6), (12,12), (16,16)]:
            cl = cv2.createCLAHE(clipLimit=clip, tileGridSize=tile).apply(gray)
            for angle in [0, 90, 180, 270]:
                if angle == 0:
                    img = cl
                else:
                    h, w = cl.shape
                    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
                    img = cv2.warpAffine(cl, M, (w, h))
                for s in shrink_list:
                    r = _try(img, s=s, timeout=timeout)
                    if r:
                        return r[0], r[1], f"cl{clip}_{tile[0]}_rot{angle}_s{s}" if angle != 0 else f"cl{clip}_{tile[0]}_direct_s{s}"
    return None


def try_local_norm(gray, shrink_list, timeout=15):
    """Local normalization + CLAHE."""
    ln = local_normalize(gray, blur_size=51)
    cl = clahe_equalized(ln)
    for angle in [0, 90, 180, 270]:
        if angle == 0:
            img = cl
        else:
            h, w = cl.shape
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            img = cv2.warpAffine(cl, M, (w, h))
        for s in shrink_list:
            r = _try(img, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"lnorm_rot{angle}_s{s}" if angle != 0 else f"lnorm_direct_s{s}"
    return None


def try_projection_lfinder(gray, shrink_list, timeout=15):
    """Find DM finder pattern using projection analysis.
    The L-shaped finder creates a row and column that are consistently darker
    than their neighbors over a stretch of N pixels."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    # Work on downsampled version for speed
    scale = 1.0
    img = gray
    if max(w, h) > 1000:
        scale = 800.0 / max(w, h)
        img = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ih, iw = img.shape

    # CLAHE for better local contrast
    cl = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(img)

    candidates = []

    # Try multiple projections: original, CLAHE, inverted
    for src_name, src in [("raw", img), ("clahe", cl)]:
        # Compute row profiles: for each row, find the min and mean
        # The finder bar is a contiguous dark segment
        for direction, axis in [("h", 1), ("v", 0)]:
            length = ih if axis == 1 else iw
            scan_len = iw if axis == 1 else ih

            for pos in range(length):
                if axis == 1:
                    row = src[pos, :]
                else:
                    row = src[:, pos]

                # Find the darkest stretch in this row/column
                # Smooth to remove noise
                smoothed = cv2.GaussianBlur(row.astype(np.float32), (1, 5), 0).flatten()
                mn_val = smoothed.min()
                if mn_val > 200:  # Too bright, no dark content
                    continue

                # Find contiguous regions where pixels are below mean
                mean_val = smoothed.mean()
                below = smoothed < mean_val * 0.85

                # Find runs of consecutive True
                runs = []
                in_run = False
                run_start = 0
                for i_val, val in enumerate(below):
                    if val and not in_run:
                        run_start = i_val
                        in_run = True
                    elif not val and in_run:
                        run_len = i_val - run_start
                        if run_len > 20:
                            runs.append((run_start, run_len))
                        in_run = False
                if in_run:
                    run_len = len(below) - run_start
                    if run_len > 20:
                        runs.append((run_start, run_len))

                for rstart, rlen in runs:
                    # For DM: the dark bar should be > 20px and < 60% of image dimension
                    if rlen < 20 or rlen > max(ih, iw) * 0.6:
                        continue

                    # Check: is this stretch consistently dark?
                    stretch = row[rstart:rstart + rlen]
                    stretch_mean = stretch.mean()
                    stretch_std = stretch.std()
                    bg_mean = (smoothed.mean() * len(smoothed) - stretch_mean * rlen) / max(1, len(smoothed) - rlen)

                    # The stretch should be darker than background (lower mean)
                    contrast = bg_mean - stretch_mean
                    if contrast < 5:  # At least 5 gray levels darker
                        continue

                    # Low std within stretch = uniform darkness (finder bar property)
                    if stretch_std > 30:  # Too much variation = probably text, not bar
                        continue

                    # Scale back to original coordinates
                    opos = int(pos / scale) if scale < 1.0 else pos
                    orstart = int(rstart / scale) if scale < 1.0 else rstart
                    orlen = int(rlen / scale) if scale < 1.0 else rlen

                    candidates.append({
                        "direction": direction,
                        "pos": opos,
                        "start": orstart,
                        "length": orlen,
                        "contrast": contrast,
                        "src": src_name,
                        "stretch_std": stretch_std,
                    })

    if len(candidates) < 2:
        return None

    # Find pairs: a horizontal bar and a vertical bar that intersect
    hbars = [c for c in candidates if c["direction"] == "h"]
    vbars = [c for c in candidates if c["direction"] == "v"]

    best_score = 0
    best_roi = None

    for hb in hbars:
        for vb in vbars:
            # The vertical bar's position (column) should be within the horizontal bar's run
            # The horizontal bar's position (row) should be within the vertical bar's run
            if vb["pos"] >= hb["start"] and vb["pos"] <= hb["start"] + hb["length"]:
                if hb["pos"] >= vb["start"] and hb["pos"] <= vb["start"] + vb["length"]:
                    # Found an intersection! This is the L-corner
                    corner_x = vb["pos"]
                    corner_y = hb["pos"]

                    # Estimate DM size: the lengths of both bars (roughly DM size)
                    dm_w = hb["length"]
                    dm_h = vb["length"]
                    dm_size = max(dm_w, dm_h)

                    if dm_size < 30 or dm_size > max(w, h) * 0.5:
                        continue

                    # Expand ROI to include full DM
                    pad = int(dm_size * 0.15)
                    x1 = max(0, corner_x - pad)
                    y1 = max(0, corner_y - pad)
                    x2 = min(w, corner_x + dm_size + pad)
                    y2 = min(h, corner_y + dm_size + pad)

                    score = (hb["contrast"] + vb["contrast"]) * dm_size
                    if score > best_score:
                        best_score = score
                        best_roi = (x1, y1, x2, y2)

    if best_roi is None:
        return None

    x1, y1, x2, y2 = best_roi
    roi = gray[y1:y2, x1:x2]
    if roi.shape[0] < 30 or roi.shape[1] < 30:
        return None

    # Try multiple enhancements
    for prep_name, prep_fn in [
        ("raw", lambda x: x),
        ("clahe", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(x)),
        ("ln", lambda x: np.clip(cv2.subtract(x, cv2.GaussianBlur(x, (51,51), 0)) + 128, 0, 255).astype(np.uint8)),
        ("ln_cl", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(
            np.clip(cv2.subtract(x, cv2.GaussianBlur(x, (51,51), 0)) + 128, 0, 255).astype(np.uint8))),
    ]:
        img = prep_fn(roi)
        for s in shrink_list:
            r = _try(img, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"proj_{prep_name}_s{s}"

    return None


def try_exhaustive_threshold(gray, shrink_list, timeout=15):
    """Brute-force: try EVERY threshold on CLAHE-enhanced downsampled image.
    Uses very generous libdmtx parameters for each attempt."""
    h, w = gray.shape
    if max(w, h) < 50:
        return None

    scale = 1.0
    img = gray
    if max(w, h) > 600:
        scale = 500.0 / max(w, h)
        img = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    cl = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(img)
    mn, mx = int(cl.min()) + 2, int(cl.max()) - 2
    if mx - mn < 5:
        return None

    step = max(1, (mx - mn) // 40)
    attempts = []
    for th in range(mn, mx, step):
        _, fwd = cv2.threshold(cl, th, 255, cv2.THRESH_BINARY)
        _, inv = cv2.threshold(cl, th, 255, cv2.THRESH_BINARY_INV)
        attempts.append((fwd, th, False))
        attempts.append((inv, th, True))

    # Shuffle to diversify coverage
    import random
    random.shuffle(attempts)

    per_t = max(20, timeout * 1000 // len(attempts))
    for bw_img, th_val, is_inv in attempts:
        # Try standard
        r = _try(bw_img, s=2, timeout=max(5, per_t))
        if r:
            return r[0], r[1], f"exh_th{th_val}_{'inv' if is_inv else 'fwd'}"
        # Try with higher deviation + max_count=0 (find all)
        r = _attempt(Image.fromarray(bw_img), shrink=2, deviation=50,
                     timeout=max(5, per_t), max_count=0)
        if r:
            return r[0], r[1], f"exh_dev{th_val}"
        # Try with min_edge=2 for tiny patterns
        r = _attempt(Image.fromarray(bw_img), shrink=2, deviation=25,
                     min_edge=2, timeout=max(5, per_t))
        if r:
            return r[0], r[1], f"exh_edge{th_val}"
    return None


def try_bimodal_grid(gray, shrink_list, timeout=15):
    """Find DM by locating tiles with strong bimodal distribution,
    which indicates DM module pattern."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    tile = 32
    bh, bw = max(1, h // tile), max(1, w // tile)
    scores = np.zeros((bh, bw), dtype=np.float32)

    for ty in range(bh):
        y0, y1 = ty * tile, min(h, (ty + 1) * tile)
        for tx in range(bw):
            x0, x1 = tx * tile, min(w, (tx + 1) * tile)
            patch = gray[y0:y1, x0:x1]
            if patch.size < 100:
                continue
            hist = cv2.calcHist([patch], [0], None, [64], [0, 256]).flatten()
            hist = hist / hist.sum() if hist.sum() > 0 else hist
            mean = (np.arange(64) * hist).sum()
            variance = ((np.arange(64) - mean) ** 2 * hist).sum()
            # Bimodality coefficient: > 0.555 indicates bimodal
            if variance < 1e-6:
                continue
            skew = ((np.arange(64) - mean) ** 3 * hist).sum() / (variance ** 1.5 + 1e-10)
            kurt = ((np.arange(64) - mean) ** 4 * hist).sum() / (variance ** 2 + 1e-10) - 3
            bc = (skew ** 2 + 1) / (kurt + 3 * ((len(patch) - 1) ** 2) / ((len(patch) - 2) * (len(patch) - 3)) + 1e-10)
            scores[ty, tx] = bc

    mask = (scores > 0.6).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    num, labeled = cv2.connectedComponents(mask)

    cl = clahe_equalized(gray)
    for lbl in range(1, num):
        ys, xs = np.where(labeled == lbl)
        if len(ys) < 2:
            continue
        y1 = max(0, ys.min() * tile - tile)
        y2 = min(h, (ys.max() + 1) * tile + tile)
        x1 = max(0, xs.min() * tile - tile)
        x2 = min(w, (xs.max() + 1) * tile + tile)
        crop = cl[y1:y2, x1:x2]
        if crop.shape[0] < 30 or crop.shape[1] < 30:
            continue

        for angle in [0, 90]:
            if angle == 0:
                img = crop
            else:
                M = cv2.getRotationMatrix2D((crop.shape[1] // 2, crop.shape[0] // 2), angle, 1.0)
                img = cv2.warpAffine(crop, M, (crop.shape[1], crop.shape[0]))
            for s in shrink_list:
                r = _try(img, s=s, timeout=timeout)
                if r:
                    return r[0], r[1], f"bimodal_{'rot' if angle else 'dir'}_s{s}"
    return None


def try_retinex_scan(gray, shrink_list, timeout=15):
    """Multi-scale Retinex + CLAHE for extreme low-contrast DM."""
    mr = multi_scale_retinex(gray)
    cl = clahe_equalized(mr)
    for angle in [0, 90, 180, 270]:
        if angle == 0:
            img = cl
        else:
            M = cv2.getRotationMatrix2D((cl.shape[1]//2, cl.shape[0]//2), angle, 1.0)
            img = cv2.warpAffine(cl, M, (cl.shape[1], cl.shape[0]))
        for s in shrink_list:
            r = _try(img, s=s, timeout=timeout)
            if r: return r[0], r[1], f"retinex_rot{angle}_s{s}" if angle else f"retinex_s{s}"
    return None


def try_wide_locnorm(gray, shrink_list, timeout=15):
    """Sweep many blur sizes for local normalization to handle any DM scale."""
    for bs in [11, 21, 31, 51, 71, 101, 151]:
        ln = local_normalize(gray, blur_size=bs)
        cl = clahe_equalized(ln)
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                img = cl
            else:
                M = cv2.getRotationMatrix2D((cl.shape[1]//2, cl.shape[0]//2), angle, 1.0)
                img = cv2.warpAffine(cl, M, (cl.shape[1], cl.shape[0]))
            for s in shrink_list:
                r = _try(img, s=s, timeout=timeout)
                if r: return r[0], r[1], f"ln{bs}_r{angle}_s{s}" if angle else f"ln{bs}_s{s}"
    return None


def try_dog_scan(gray, shrink_list, timeout=15):
    """Difference-of-Gaussians edge enhancement for module boundaries."""
    for s1, s2 in [(0.5, 2.0), (1.0, 4.0), (2.0, 8.0), (3.0, 12.0)]:
        dog = diff_of_gaussians(gray, sigma1=s1, sigma2=s2)
        cl = clahe_equalized(dog)
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                img = cl
            else:
                M = cv2.getRotationMatrix2D((cl.shape[1]//2, cl.shape[0]//2), angle, 1.0)
                img = cv2.warpAffine(cl, M, (cl.shape[1], cl.shape[0]))
            for s in shrink_list:
                r = _try(img, s=s, timeout=timeout)
                if r: return r[0], r[1], f"dog{s1}_{s2}_r{angle}_s{s}" if angle else f"dog{s1}_{s2}_s{s}"
    return None


def try_morph_close_scan(gray, shrink_list, timeout=15):
    """Strong morphological closing to connect fragmented finder patterns."""
    cl = clahe_equalized(gray)
    for ks in [7, 11, 15, 21]:
        closed = morph_reconstruct(cl, ksize=ks)
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                img = closed
            else:
                M = cv2.getRotationMatrix2D((closed.shape[1]//2, closed.shape[0]//2), angle, 1.0)
                img = cv2.warpAffine(closed, M, (closed.shape[1], closed.shape[0]))
            for s in shrink_list:
                r = _try(img, s=s, timeout=timeout)
                if r: return r[0], r[1], f"morph{ks}_r{angle}_s{s}" if angle else f"morph{ks}_s{s}"
                # Also try multiple thresholds on the closed image
                for th in range(40, 220, 20):
                    _, bw = cv2.threshold(img, th, 255, cv2.THRESH_BINARY)
                    r = _try(bw, s=2, timeout=timeout // 2)
                    if r: return r[0], r[1], f"morph{ks}_th{th}"
    return None


def try_template_match(gray, shrink_list, timeout=15):
    """Use template matching with synthetic L-finder patterns to locate DM regions.
    Works even when finder pattern is very faded because correlation is
    robust to contrast variations."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    # Build synthetic L-finder templates at multiple sizes
    templates = []
    for dm_size in [16, 24, 32, 48, 64, 80, 96, 128]:
        # L-shape: solid bar along left and top edges, (dm_size/2) thick
        thick = max(1, dm_size // 4)
        half = dm_size // 2
        tpl = np.ones((dm_size, dm_size), dtype=np.uint8) * 128
        # Left bar (full height, thick columns)
        tpl[:dm_size, :thick] = 0
        # Top bar (thick rows, full width)
        tpl[:thick, :dm_size] = 0
        # Optional: add alternating modules in data region for stronger match
        # Don't add modules - pure L-shape is what makes DM unique
        templates.append(tpl)
        # Also add a half-size version
        tpl_small = cv2.resize(tpl, (half, half), interpolation=cv2.INTER_AREA)
        templates.append(tpl_small)

    # Work on downsampled image
    scale = 1.0
    img = gray
    if max(w, h) > 1000:
        scale = 600.0 / max(w, h)
        img = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ih, iw = img.shape

    # Enhance
    cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6,6)).apply(img)
    ln = local_normalize(cl, blur_size=31)

    candidates = []
    for src_name, src in [("cl", cl), ("ln", ln)]:
        src_f = src.astype(np.float32)
        for tpl in templates:
            th, tw = tpl.shape
            if th > ih or tw > iw:
                continue
            # Normalized cross-correlation (robust to contrast changes)
            try:
                result = cv2.matchTemplate(src_f, tpl.astype(np.float32), cv2.TM_CCOEFF_NORMED)
            except:
                continue
            # Find good matches
            locs = np.where(result >= 0.35)
            for pt in zip(*locs[::-1]):
                x, y = pt
                # Map to original coords
                ox = int(x / scale) if scale < 1.0 else x
                oy = int(y / scale) if scale < 1.0 else y
                dm = int(max(th, tw) / scale) if scale < 1.0 else max(th, tw)
                score = float(result[y, x])
                candidates.append({
                    "x": ox, "y": oy, "size": dm * 2, "score": score,
                    "src": src_name
                })

    if not candidates:
        return None

    # Sort by score, dedup
    candidates.sort(key=lambda c: -c["score"])
    uniq = []
    for c in candidates:
        dup = False
        for u in uniq:
            dx = abs(c["x"] - u["x"])
            dy = abs(c["y"] - u["y"])
            if dx < 30 and dy < 30:
                dup = True
                break
        if not dup:
            uniq.append(c)

    # Try decode on top candidates
    for cand in uniq[:10]:
        x1 = max(0, cand["x"])
        y1 = max(0, cand["y"])
        x2 = min(w, cand["x"] + cand["size"])
        y2 = min(h, cand["y"] + cand["size"])
        roi = gray[y1:y2, x1:x2]
        if roi.shape[0] < 30 or roi.shape[1] < 30:
            continue

        # Try multiple enhancements
        for prep_name, prep_fn in [
            ("raw", lambda x: x),
            ("clahe", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(x)),
            ("ln", lambda x: local_normalize(x, 31)),
        ]:
            img_p = prep_fn(roi)
            for s in shrink_list:
                r = _try(img_p, s=s, timeout=timeout)
                if r:
                    return r[0], r[1], f"tmpl_{prep_name}_s{s}"
            # Also try with high deviation
            r = _try_faded(img_p, s=2, timeout=timeout)
            if r:
                return r[0], r[1], f"tmpl_faded_{prep_name}"

    return None


def try_manual_lfinder(gray, shrink_list, timeout=15):
    """Manual L-finder pattern detection using row/column scanning.
    Looks for the characteristic L-shape by finding dark perpendicular bars."""
    h, w = gray.shape
    if max(w, h) < 80:
        return None

    scale = 1.0
    img = gray
    if max(w, h) > 800:
        scale = 600.0 / max(w, h)
        img = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ih, iw = img.shape

    cl = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8)).apply(img)

    # Try exhaustive: for each possible L-corner position, evaluate if
    # there's a dark L-shape
    best_score = 0
    best_rect = None

    # Use gradient to find candidate corners
    gx = cv2.Sobel(cl, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(cl, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    # In DM finder corner: strong gradients in both x and y directions
    corner_score = np.abs(gx) + np.abs(gy)

    # Find regions with high corner response
    block = 16
    bh, bw = max(1, ih // block), max(1, iw // block)
    grid_scores = np.zeros((bh, bw), dtype=np.float32)
    for by in range(bh):
        y0, y1 = by * block, min(ih, (by + 1) * block)
        for bx in range(bw):
            x0, x1 = bx * block, min(iw, (bx + 1) * block)
            grid_scores[by, bx] = float(np.mean(corner_score[y0:y1, x0:x1]))

    # Find top blocks
    flat_idx = np.argsort(grid_scores.flatten())[::-1]
    for idx in flat_idx[:50]:
        by = idx // bw
        bx = idx % bw
        if grid_scores[by, bx] < 30:
            break

        cx = bx * block + block // 2
        cy = by * block + block // 2

        # Evaluate if this point is an L-corner
        # Check: rightward from corner, top row should be dark for some distance
        # Check: downward from corner, left column should be dark for some distance
        margin = 4
        search_radius = min(ih, iw) // 4

        # Sample the row to the right of the corner (top bar)
        row_right = cl[cy, cx:min(iw, cx + search_radius)]
        # Sample the column below the corner (left bar)
        col_down = cl[cy:min(ih, cy + search_radius), cx]

        # The finder bar should be consistently darker than background
        if len(row_right) < 8 or len(col_down) < 8:
            continue

        # Find how long the bar is by looking for a significant increase in brightness
        # (end of dark bar = start of finder pattern alternation or data region)
        row_smooth = cv2.GaussianBlur(row_right.astype(np.float32), (1, 5), 0).flatten()
        col_smooth = cv2.GaussianBlur(col_down.astype(np.float32), (1, 5), 0).flatten()

        row_brightness = cl[cy, cx:].mean()
        col_brightness = cl[cy:, cx].mean()

        # Find where each bar ends (transition from dark to lighter)
        row_bar_end = len(row_smooth)
        for i in range(margin, len(row_smooth)):
            if row_smooth[i] > row_smooth[:i].mean() + 3:  # +3 gray levels above bar mean
                row_bar_end = i
                break

        col_bar_end = len(col_smooth)
        for i in range(margin, len(col_smooth)):
            if col_smooth[i] > col_smooth[:i].mean() + 3:
                col_bar_end = i
                break

        bar_len = min(row_bar_end, col_bar_end)
        if bar_len < 10:
            bar_len = max(row_bar_end, col_bar_end)  # Use longer if one is short
        if bar_len < 10 or bar_len > min(ih, iw) // 2:
            continue

        # The bar should be dark relative to surrounding area
        bar_region = cl[max(0, cy-2):cy+bar_len, max(0, cx-2):cx+bar_len]
        bg = cl[max(0, cy-16):min(ih, cy+bar_len+16),
                max(0, cx-16):min(iw, cx+bar_len+16)]
        bar_mean = float(np.mean(bar_region))
        bg_mean = float(np.mean(bg))
        if bg_mean - bar_mean < 4 or bar_mean > bg_mean:
            continue

        dm_size = bar_len * 2  # DM is roughly 2x the finder bar length
        if dm_size > min(w, h) * 0.8:
            continue

        # Score based on bar length * contrast
        score = bar_len * (bg_mean - bar_mean)
        if score > best_score:
            best_score = score
            pad = int(dm_size * 0.15)
            x1 = max(0, cx - pad)
            y1 = max(0, cy - pad)
            x2 = min(w, int((cx + dm_size + pad) / scale) if scale < 1.0 else cx + dm_size + pad)
            y2 = min(h, int((cy + dm_size + pad) / scale) if scale < 1.0 else cy + dm_size + pad)
            best_rect = (x1, y1, x2, y2)

    if best_rect is None:
        return None

    x1, y1, x2, y2 = best_rect

    # Map from downsampled coords
    if scale < 1.0:
        x1 = int(x1 / scale)
        y1 = int(y1 / scale)
        x2 = int(x2 / scale)
        y2 = int(y2 / scale)

    roi = gray[y1:y2, x1:x2]
    if roi.shape[0] < 30 or roi.shape[1] < 30:
        return None

    for prep_name, prep_fn in [
        ("raw", lambda x: x),
        ("clahe", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(x)),
        ("ln", lambda x: local_normalize(x, 31)),
    ]:
        img_p = prep_fn(roi)
        for s in shrink_list:
            r = _try(img_p, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"manual_{prep_name}_s{s}"
        r = _try_faded(img_p, s=2, timeout=timeout)
        if r:
            return r[0], r[1], f"manual_faded_{prep_name}"

    return None


def fft_periodicity_score(patch):
    """Score patch by DM-like periodicity using 2D autocorrelation via FFT.
    Returns score (higher = more periodic grid pattern)."""
    h, w = patch.shape
    if h < 32 or w < 32:
        return 0.0
    # Zero-mean
    f = patch.astype(np.float32)
    f -= f.mean()
    # FFT → power spectrum → IFFT → autocorrelation
    F = np.fft.fft2(f)
    power = np.fft.fftshift(np.abs(F) ** 2)
    # Remove DC (center)
    cy, cx = h // 2, w // 2
    r = 3
    power[cy - r:cy + r, cx - r:cx + r] = 0
    # Look for strong non-DC peaks
    pmax = power.max()
    if pmax < 1e-6:
        return 0.0
    # Normalize and count strong peaks
    power_norm = power / pmax
    peaks = power_norm > 0.15
    peak_count = int(peaks.sum())
    # Score combines peak count and strength
    score = peak_count * float(power_norm[peaks].mean())
    return score


def try_fft_periodic_detect(gray, shrink_list, timeout=15):
    """Find DM by FFT periodicity — DM grid creates strong FFT peaks
    even when contrast is too low for conventional detection."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    # Downsample for speed
    scale = 1.0
    img = gray
    if max(w, h) > 800:
        scale = 500.0 / max(w, h)
        img = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ih, iw = img.shape

    cl = clahe_equalized(img)
    tile, overlap = 64, 48
    candidates = []
    for y in range(0, ih - tile, tile - overlap):
        for x in range(0, iw - tile, tile - overlap):
            patch = cl[y:y + tile, x:x + tile]
            score = fft_periodicity_score(patch)
            if score > 1.0:
                candidates.append((x, y, tile, score))

    if not candidates:
        return None

    candidates.sort(key=lambda c: -c[3])

    for cx, cy, ts, score in candidates[:15]:
        # Map back to original
        ox = int(cx / scale) if scale < 1.0 else cx
        oy = int(cy / scale) if scale < 1.0 else cy
        # Larger region around the periodic tile
        margin = int(ts * 2.5 / scale) if scale < 1.0 else ts * 2
        x1 = max(0, ox - margin)
        y1 = max(0, oy - margin)
        x2 = min(w, ox + ts + margin)
        y2 = min(h, oy + ts + margin)

        roi = gray[y1:y2, x1:x2]
        if roi.shape[0] < 30 or roi.shape[1] < 30:
            continue

        r = _try_extreme_decode(roi, shrink_list, timeout)
        if r:
            return r[0], r[1], f"fft_{r[2]}"

    return None


def _try_extreme_decode(roi, shrink_list, timeout=15):
    """Maximal enhancement pipeline for found DM regions:
    extreme gamma, CLAHE, morphological rebuild, threshold sweep."""
    for gamma in [0.05, 0.1, 0.15, 0.3]:
        inv_g = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_g) * 255 for i in range(256)]).astype(np.uint8)
        gm = cv2.LUT(roi, table)
        cl = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(4, 4)).apply(gm)

        # Morphological close to connect modules
        for ks in [3, 5, 7]:
            closed = cv2.morphologyEx(cl, cv2.MORPH_CLOSE,
                                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
            for s in shrink_list:
                r = _try(closed, s=s, timeout=timeout)
                if r:
                    return r[0], r[1], f"ext_g{gamma}_k{ks}_s{s}"
                r = _try(255 - closed, s=s, timeout=timeout)
                if r:
                    return r[0], r[1], f"ext_g{gamma}_k{ks}_inv_s{s}"

            # Fixed thresholds
            for th in range(30, 226, 15):
                _, bw = cv2.threshold(closed, th, 255, cv2.THRESH_BINARY)
                r = _try(bw, s=2, timeout=timeout // 2)
                if r:
                    return r[0], r[1], f"ext_g{gamma}_k{ks}_th{th}"
                r = _try(255 - bw, s=2, timeout=timeout // 2)
                if r:
                    return r[0], r[1], f"ext_g{gamma}_k{ks}_th{th}_inv"

            # Also try with _try_faded
            r = _try_faded(closed, s=2, timeout=timeout)
            if r:
                return r[0], r[1], f"ext_g{gamma}_k{ks}_faded"

    # Raw extreme: subtract local mean, amplify
    for bs in [31, 51, 101]:
        blurred = cv2.GaussianBlur(roi, (bs, bs), 0)
        ln = np.clip(cv2.subtract(roi, blurred) + 128, 0, 255).astype(np.uint8)
        cl = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(4, 4)).apply(ln)
        for s in shrink_list:
            r = _try(cl, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"ext_ln{bs}_s{s}"

    return None


def try_otsu_quality_scan(gray, shrink_list, timeout=15):
    """Scan windows by Otsu bimodality quality — DM has 2 clusters
    (dark modules + light background), giving high Otsu separation."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    # Use CLAHE for better separation
    cl = clahe_equalized(gray)
    tile = 80
    overlap = 64
    otsu_scores = []

    for y in range(0, h - tile, tile - overlap):
        for x in range(0, w - tile, tile - overlap):
            patch = cl[y:y + tile, x:x + tile]
            if patch.size < 400:
                continue
            # Otsu within-class variance (lower = better bimodal separation)
            hist = cv2.calcHist([patch], [0], None, [64], [0, 256]).flatten()
            total = hist.sum()
            if total < 1:
                continue
            w0 = 0
            sumB = 0
            best_var = 0
            for t in range(64):
                w0 += hist[t]
                if w0 == 0:
                    continue
                w1 = total - w0
                if w1 == 0:
                    break
                sumB += t * hist[t]
                m0 = sumB / w0
                sumB2 = 0
                for i2 in range(t + 1, 64):
                    sumB2 += i2 * hist[i2]
                m1 = sumB2 / w1 if w1 > 0 else 0
                var = w0 * w1 * (m0 - m1) ** 2
                if var > best_var:
                    best_var = var
            if best_var > 100000:  # Strong bimodal separation
                otsu_scores.append((x, y, tile, best_var))

    otsu_scores.sort(key=lambda c: -c[3])

    for cx, cy, ts, quality in otsu_scores[:20]:
        margin = ts // 2
        x1 = max(0, cx - margin)
        y1 = max(0, cy - margin)
        x2 = min(w, cx + ts + margin)
        y2 = min(h, cy + ts + margin)

        roi = gray[y1:y2, x1:x2]
        if roi.shape[0] < 30 or roi.shape[1] < 30:
            continue

        r = _try_extreme_decode(roi, shrink_list, timeout)
        if r:
            return r[0], r[1], f"otsu_{r[2]}"

    return None


def try_aggressive_morphology(gray, shrink_list, timeout=15):
    """Recover broken finder pattern via aggressive morphological operations.
    CLAHE + morphological close fills gaps in faded L-shape."""
    h, w = gray.shape
    if max(w, h) < 100:
        return None

    # Use local normalization to remove background illumination
    blurred = cv2.GaussianBlur(gray, (31, 31), 0)
    ln = np.clip(cv2.subtract(gray, blurred) + 128, 0, 255).astype(np.uint8)
    
    # Try multiple CLAHE params on normalized image
    for clip in [3.0, 5.0, 8.0]:
        for tile in [(6, 6), (8, 8)]:
            cl = cv2.createCLAHE(clipLimit=clip, tileGridSize=tile).apply(ln)
            
            # Morphological closing with various kernel sizes to bridge gaps
            for ksize in [7, 9, 11, 13, 15]:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
                closed = cv2.morphologyEx(cl, cv2.MORPH_CLOSE, kernel)
                
                # Opening to remove small noise
                opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
                
                for angle in [0, 90, 180, 270]:
                    if angle == 0:
                        img = opened
                    else:
                        M = cv2.getRotationMatrix2D((opened.shape[1]//2, opened.shape[0]//2), angle, 1.0)
                        img = cv2.warpAffine(opened, M, (opened.shape[1], opened.shape[0]))
                    
                    for s in shrink_list:
                        r = _try(img, s=s, timeout=timeout)
                        if r:
                            return r[0], r[1], f"morph_{ksize}_clip{clip}_rot{angle}_s{s}"
                        # Also try inverted
                        r = _try(255 - img, s=s, timeout=timeout)
                        if r:
                            return r[0], r[1], f"morph_{ksize}_clip{clip}_rot{angle}_inv_s{s}"

    return None


def try_rs_ecc_decode(gray, shrink_list, timeout=20):
    """Brute-force grid sampling with Reed-Solomon error correction."""
    from recon_sampler import detect_grids, sample_all_offsets
    h, w = gray.shape
    
    grids = detect_grids(gray)
    if not grids:
        return None
    
    for grid_info in grids[:5]:
        result = sample_all_offsets(gray, grid_info)
        if result:
            return result[0], result[1], f"rs_{result[2]}"
    
    return None


def try_nn_detect(gray, shrink_list, timeout=20):
    """NN-based DM detection using HOG features + MLP."""
    from dm_nn_fast import DMDetectorFast
    
    detector = DMDetectorFast()
    if not detector.load():
        return None
    
    detections = detector.detect(gray, step=32, threshold=0.6)
    
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        roi = gray[y1:y2, x1:x2]
        if roi.shape[0] < 30 or roi.shape[1] < 30:
            continue
        
        cl = clahe_equalized(roi)
        for s in shrink_list:
            r = _try(cl, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"nn_{r[2]}"
            r = _try(255 - cl, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"nn_inv_{r[2]}"
    
    return None


def scan_v5(gray, max_total_time=10.0):
    start_t = time.time()
    h, w = gray.shape

    if h < 4 or w < 4:
        return None, None, None, None

    gray = auto_scale(gray)
    h, w = gray.shape
    max_shrink = max(1, min(10, max(h, w) // 30))
    sr3 = list(range(1, min(max_shrink, 3) + 1))

    is_large = max(h, w) > 600

    def tl():
        return max(1, int((max_total_time - (time.time() - start_t)) * 1000))

    def timed_out():
        return (time.time() - start_t) >= max_total_time or tl() < 50

    def try_until(attempts):
        for label, fn, shrink_list, t in attempts:
            if timed_out():
                break
            r = fn(shrink_list, t)
            if r and r[0] is not None:
                return r[0], r[1], f"{label}_{r[2]}", {"method": label}
        return None

    building = [
        ("direct", lambda sl, t: try_rotations(gray, [0, 90, 180, 270], sl, t),
         sr3, 12),
        ("sharp", lambda sl, t: try_rotations(sharpen(gray), [0, 90, 180, 270], sl, t),
         sr3, 12),
        ("clahe", lambda sl, t: try_rotations(clahe_equalized(gray), [0, 90, 180, 270], sl, t),
         sr3, 12),
        ("clahe_var", lambda sl, t: try_clahe_variants(gray, sl, t),
         sr3, 12),
        ("locnorm", lambda sl, t: try_local_norm(gray, sl, t),
         sr3, 15),
        ("wide_ln", lambda sl, t: try_wide_locnorm(gray, sl, t),
         sr3, 20),
        ("retinex", lambda sl, t: try_retinex_scan(gray, sl, t),
         sr3, 15),
        ("dog", lambda sl, t: try_dog_scan(gray, sl, t),
         sr3, 15),
        ("morph_close", lambda sl, t: try_morph_close_scan(gray, sl, t),
         sr3, 20),
        ("warp", lambda sl, t: try_warp_and_rotations(gray, sl, t),
         sr3, 20),
        ("warp_sharp", lambda sl, t: try_warp_and_rotations(sharpen(gray), sl, t),
         sr3, 20),
        ("up", lambda sl, t: try_upscale(gray, sl, t),
         sr3, 20),
        ("deskew", lambda sl, t: try_deskew(gray, sl, t),
         sr3, 20),
        ("persp", lambda sl, t: try_perspective_fixes(gray, sl, t),
         sr3, 20),
    ]

    if is_large:
        building.insert(0, ("roi", lambda sl, t: try_roi_decode(gray, sl, t),
                          sr3, 25))
        building.insert(1, ("roi_clahe", lambda sl, t: try_roi_decode(clahe_equalized(gray), sl, t),
                          sr3, 25))
        building.insert(2, ("grid", lambda sl, t: try_grid_decode(gray, sl, t),
                          [1, 2], 30))

        # Large-window adaptive threshold on CLAHE for faded document DMs
        cl_full = clahe_equalized(gray)
        for win in [31, 51, 71]:
            if win > min(h, w): continue
            try:
                th = cv2.adaptiveThreshold(cl_full, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, win, 2)
            except:
                continue
            building.append((f"adapt{win}", lambda sl, t, img=th: try_rotations(img, [0, 90, 180, 270], sl, t),
                          sr3, 15))

    building += [
        ("wiener", lambda sl, t: try_rotations(deblur_wiener(gray), [0, 90, 180, 270], sl, t),
         sr3, 25),
        ("bin", lambda sl, t: try_binary_candidates(gray, sl, t),
         sr3, 10),
        ("bin_sharp", lambda sl, t: try_binary_candidates(sharpen(gray), sl, t),
         sr3, 10),
        ("bin_clahe", lambda sl, t: try_binary_candidates(clahe_equalized(gray), sl, t),
         sr3, 10),
    ]

    if is_large:
        building.append(("edge_grid", lambda sl, t: try_edge_grid(gray, sl, t),
                        sr3, 20))
        building.append(("mthr", lambda sl, t: try_multi_threshold(gray, sl, t),
                        sr3, 20))
        building.append(("proj", lambda sl, t: try_projection_lfinder(gray, sl, t),
                        sr3, 20))

    r = try_until(building)
    if r:
        return r

    # -- Final hopes for faded DMs --
    if is_large and not timed_out():
        building_final = [
            ("morph", lambda sl, t: try_aggressive_morphology(gray, sl, t), sr3, 25),
            ("nn", lambda sl, t: try_nn_detect(gray, sl, t), [1, 2], 30),
            ("fft", lambda sl, t: try_fft_periodic_detect(gray, sl, t), sr3, 30),
            ("otsu_q", lambda sl, t: try_otsu_quality_scan(gray, sl, t), [1, 2], 30),
            ("tmpl", lambda sl, t: try_template_match(gray, sl, t), sr3, 25),
            ("manual", lambda sl, t: try_manual_lfinder(gray, sl, t), sr3, 25),
            ("exh_thr", lambda sl, t: try_exhaustive_threshold(gray, sl, t), [2], 30),
        ]
        r = try_until(building_final)
        if r:
            return r

    if not timed_out():
        # Absolute last resort: try the gray image at multiple shrink levels with max_count=0
        for s in range(1, 6):
            if timed_out():
                break
            r = _try(gray, s=s, timeout=max(50, tl()))
            if r:
                return r[0], r[1], f"last_s{s}", {"method": "last"}
            r = _try_faded(gray, s=s, timeout=max(50, tl()))
            if r:
                return r[0], r[1], f"last_fade_s{s}", {"method": "last_fade"}

    if not timed_out() and _has_zxing:
        r = try_zxing_fallback(gray, timeout=min(80, tl()))
        if r:
            return r[0], r[1], r[2], {"method": "zx_fallback"}

    return None, None, None, None
