"""
DM grid sampler with Reed-Solomon error correction via libdmtx.
Brute-forces all grid offsets and tries libdmtx (which has built-in RS ECC).
"""
import cv2
import numpy as np
import time
from PIL import Image
from pylibdmtx.pylibdmtx import decode
from super_scanner import clahe_equalized, _try


def detect_grids(gray, min_spacing=10, max_spacing=30, max_regions=10):
    """Find candidate DM grids via gradient autocorrelation."""
    h, w = gray.shape
    
    # Local normalization
    blurred = cv2.GaussianBlur(gray, (21, 21), 0)
    ln = np.clip(cv2.subtract(gray, blurred) + 128, 0, 255).astype(np.uint8)
    
    # Gradient magnitude
    gx = cv2.Sobel(ln, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(ln, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    mag -= mag.mean()
    
    # Autocorrelation via FFT
    F = np.fft.fft2(mag)
    acorr = np.fft.ifft2(np.abs(F)**2).real
    acorr = np.fft.fftshift(acorr)
    cy, cx = h // 2, w // 2
    zp = acorr[cy, cx]
    acorr[cy-10:cy+10, cx-10:cx+10] = 0
    
    # Find spacing in X and Y directions
    x_slice = acorr[cy, cx+min_spacing:cx+max_spacing]
    y_slice = acorr[cy+min_spacing:cy+max_spacing, cx]
    
    if len(x_slice) < 2 or len(y_slice) < 2:
        return []
    
    sx = cx + min_spacing + int(np.argmax(x_slice))
    sy = cy + min_spacing + int(np.argmax(y_slice))
    sp_x = abs(sx - cx)
    sp_y = abs(sy - cy)
    
    if sp_x < min_spacing or sp_y < min_spacing:
        return []
    
    # Check consistency
    ratio = min(sp_x, sp_y) / max(sp_x, sp_y) if max(sp_x, sp_y) > 0 else 0
    if ratio < 0.6:
        return []
    
    spacing = int((sp_x + sp_y) / 2)
    
    # Find peak value as score
    px_val = float(x_slice.max()) / (zp + 1e-10)
    py_val = float(y_slice.max()) / (zp + 1e-10)
    score = (px_val + py_val) / 2
    
    if score < 0.05:
        return []
    
    return [{'spacing': spacing, 'score': score}]


def reconstruct_dm_image(binary_matrix, n_modules, module_px=8):
    """Create clean DM image with correct finder/clock pattern.
    binary_matrix: 0=light, 255=dark"""
    margin = 4
    total = n_modules * module_px + margin * 2
    clean = np.ones((total, total), dtype=np.uint8) * 255
    
    # Place data modules
    for my in range(n_modules):
        for mx in range(n_modules):
            val = binary_matrix[my, mx]
            if val > 0:  # Dark module
                clean[margin+my*module_px:margin+(my+1)*module_px,
                      margin+mx*module_px:margin+(mx+1)*module_px] = 0
    
    # LEFT FINDER (solid dark)
    clean[margin:margin+n_modules*module_px, margin:margin+module_px] = 0
    # BOTTOM FINDER (solid dark)
    clean[margin+n_modules*module_px-module_px:margin+n_modules*module_px, 
          margin:margin+n_modules*module_px] = 0
    
    # TOP CLOCK (alternating, starting dark at col 1)
    for col in range(1, n_modules):
        v = 0 if col % 2 == 1 else 255
        clean[margin:margin+module_px, margin+col*module_px:margin+(col+1)*module_px] = v
    
    # RIGHT CLOCK (alternating, starting dark at row 1)
    for row in range(1, n_modules):
        v = 0 if row % 2 == 1 else 255
        clean[margin+row*module_px:margin+(row+1)*module_px, 
              margin+n_modules*module_px-module_px:margin+n_modules*module_px] = v
    
    # Corners (always dark)
    clean[margin:margin+module_px, margin:margin+module_px] = 0
    clean[margin:margin+module_px, margin+n_modules*module_px-module_px:margin+n_modules*module_px] = 0
    clean[margin+n_modules*module_px-module_px:margin+n_modules*module_px, margin:margin+module_px] = 0
    clean[margin+n_modules*module_px-module_px:margin+n_modules*module_px, 
          margin+n_modules*module_px-module_px:margin+n_modules*module_px] = 0
    
    return clean


def sample_all_offsets(gray, grid_info, max_offsets_per_dim=20):
    """Try all grid offsets and attempt libdmtx decode."""
    spacing = grid_info['spacing']
    h, w = gray.shape
    
    # Estimate DM size
    dm_size_px = spacing * 20  # Assume ~20 modules
    if dm_size_px > min(h, w) * 0.9:
        dm_size_px = int(min(h, w) * 0.8)
    
    n_modules = dm_size_px // spacing
    if n_modules < 10 or n_modules > 40:
        return None
    
    # Scan image for DM regions using sliding window
    step = max(20, spacing * 2)
    candidates = []
    
    for y in range(0, h - dm_size_px, step):
        for x in range(0, w - dm_size_px, step):
            # Extract region
            roi = gray[y:y+dm_size_px, x:x+dm_size_px]
            if roi.shape[0] < dm_size_px or roi.shape[1] < dm_size_px:
                continue
            
            # Try multiple offsets
            for ox in range(0, spacing, max(1, spacing // max_offsets_per_dim)):
                for oy in range(0, spacing, max(1, spacing // max_offsets_per_dim)):
                    # Sample modules
                    binary = np.zeros((n_modules, n_modules), dtype=np.uint8)
                    for my in range(n_modules):
                        for mx in range(n_modules):
                            px = ox + mx * spacing
                            py = oy + my * spacing
                            
                            # Center sampling window
                            x0 = max(0, px + 2)
                            y0 = max(0, py + 2)
                            x1 = min(roi.shape[1], px + spacing - 2)
                            y1 = min(roi.shape[0], py + spacing - 2)
                            
                            if x1 <= x0 or y1 <= y0:
                                continue
                            
                            cell = roi[y0:y1, x0:x1]
                            binary[my, mx] = 255 if cell.mean() < 128 else 0
                    
                    # Check dark/light ratio (should be ~40-60% dark)
                    dark_ratio = (binary > 0).sum() / (n_modules * n_modules)
                    if dark_ratio < 0.3 or dark_ratio > 0.7:
                        continue
                    
                    # Reconstruct DM
                    for module_px in [6, 8, 10]:
                        clean = reconstruct_dm_image(binary, n_modules, module_px)
                        
                        # Try libdmtx with various params
                        for s in [1, 2]:
                            for dev in [25, 50, 100, 150, 200]:
                                try:
                                    r = decode(Image.fromarray(clean), 
                                              shrink=s, deviation=dev, 
                                              timeout=30, max_count=1)
                                    if r:
                                        text = r[0].data.decode('utf-8', errors='replace')
                                        rect = (r[0].rect.left, r[0].rect.top, 
                                               r[0].rect.width, r[0].rect.height)
                                        return text, rect, f"offset_{ox}_{oy}_mod{module_px}"
                                except:
                                    pass
                        
                        # Also try inverted
                        for s in [1, 2]:
                            for dev in [25, 50, 100]:
                                try:
                                    r = decode(Image.fromarray(255 - clean), 
                                              shrink=s, deviation=dev, 
                                              timeout=30, max_count=1)
                                    if r:
                                        text = r[0].data.decode('utf-8', errors='replace')
                                        rect = (r[0].rect.left, r[0].rect.top, 
                                               r[0].rect.width, r[0].rect.height)
                                        return text, rect, f"offset_inv_{ox}_{oy}_mod{module_px}"
                                except:
                                    pass
    
    return None
