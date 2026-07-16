"""
Fast DM detector using NumPy MLP on HOG features.
Trains in 2 seconds, detects in milliseconds.
"""
import cv2
import numpy as np
import os, sys, pickle, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dm_encode import encode as dm_encode
from super_scanner import clahe_equalized, _try


# ─── HOG FEATURE EXTRACTOR ───────────────────────────────────────────

def extract_hog(patch, bins=9, cell_size=8):
    """Extract HOG features from 64x64 patch (vectorized)."""
    h, w = patch.shape
    if h != 64 or w != 64:
        patch = cv2.resize(patch, (64, 64))
    
    # Gradients (vectorized)
    gx = cv2.Sobel(patch, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(patch, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    angle = (np.arctan2(gy, gx) * 180 / np.pi + 180) % 180
    
    # Reshape into cells
    n_cells = 64 // cell_size  # 8
    hog = np.zeros(n_cells * n_cells * bins)
    
    # Vectorized histogram
    cell_idx = (np.arange(64) // cell_size)[:, None] * n_cells + (np.arange(64) // cell_size)[None, :]
    bin_idx = (angle // 20).astype(int).clip(0, bins-1)
    
    for cy in range(n_cells):
        for cx in range(n_cells):
            mask = cell_idx == cy * n_cells + cx
            weights = mag[mask]
            bins_local = bin_idx[mask]
            for b in range(bins):
                hog[(cy * n_cells + cx) * bins + b] = weights[bins_local == b].sum()
    
    # Normalize
    hog = hog / (hog.sum() + 1e-6)
    return hog


# ─── DATA GENERATION ──────────────────────────────────────────────────

def generate_training_data(n_pos=1000, n_neg=1000):
    """Generate HOG features for DM (positive) and non-DM (negative) patches."""
    X = []
    y = []
    
    # Positive: synthetic DM
    for i in range(n_pos):
        mod_size = np.random.randint(2, 5)
        code_len = np.random.randint(6, 20)
        code = ''.join([chr(np.random.randint(48, 90)) for _ in range(code_len)])
        
        try:
            dm = dm_encode(code, module_size=mod_size, margin=2)
            dm_arr = np.array(dm.convert('L'))
            dm_bin = (dm_arr < 128).astype(np.uint8) * 255
        except:
            continue
        
        # Degrade
        fade = np.random.uniform(0.2, 0.7)
        dm_f = dm_bin.astype(np.float32) * (1 - fade) + 255 * fade
        dm_f = np.clip(dm_f, 0, 255).astype(np.uint8)
        
        # Place in patch
        patch = np.ones((64, 64), dtype=np.uint8) * 255
        h, w = dm_f.shape
        if h > 54 or w > 54:
            scale = 54 / max(h, w)
            dm_f = cv2.resize(dm_f, (int(w * scale), int(h * scale)))
            h, w = dm_f.shape
        cx = np.random.randint(5, 64 - w - 4)
        cy = np.random.randint(5, 64 - h - 4)
        patch[cy:cy+h, cx:cx+w] = dm_f
        
        # Add noise
        if np.random.random() < 0.5:
            noise = np.random.randn(64, 64) * np.random.uniform(0, 20)
            patch = np.clip(patch.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        
        hog = extract_hog(patch)
        X.append(hog)
        y.append(1.0)
    
    # Negative: random textures
    for i in range(n_neg):
        # Random gradient pattern
        patch = np.random.randint(100, 220, (64, 64), dtype=np.uint8)
        # Add some structure
        if np.random.random() < 0.5:
            # Lines
            for _ in range(np.random.randint(1, 5)):
                pt1 = (np.random.randint(0, 64), np.random.randint(0, 64))
                pt2 = (np.random.randint(0, 64), np.random.randint(0, 64))
                cv2.line(patch, pt1, pt2, np.random.randint(0, 255), np.random.randint(1, 5))
        elif np.random.random() < 0.5:
            # Circles
            for _ in range(np.random.randint(1, 3)):
                center = (np.random.randint(10, 54), np.random.randint(10, 54))
                radius = np.random.randint(5, 20)
                cv2.circle(patch, center, radius, np.random.randint(0, 255), -1)
        
        hog = extract_hog(patch)
        X.append(hog)
        y.append(0.0)
    
    return np.array(X), np.array(y)


# ─── MLP CLASSIFIER (NumPy) ───────────────────────────────────────────

class MLP:
    def __init__(self, input_size, hidden_size=64):
        self.W1 = np.random.randn(input_size, hidden_size) * 0.1
        self.b1 = np.zeros(hidden_size)
        self.W2 = np.random.randn(hidden_size, 1) * 0.1
        self.b2 = np.zeros(1)
    
    def sigmoid(self, x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))
    
    def forward(self, X):
        self.z1 = X @ self.W1 + self.b1
        self.a1 = np.maximum(0, self.z1)  # ReLU
        self.z2 = self.a1 @ self.W2 + self.b2
        return self.sigmoid(self.z2)
    
    def train(self, X, y, epochs=100, lr=0.01):
        n = X.shape[0]
        for epoch in range(epochs):
            # Forward
            out = self.forward(X)
            loss = -np.mean(y * np.log(out + 1e-8) + (1 - y) * np.log(1 - out + 1e-8))
            
            # Backward
            dz2 = out - y.reshape(-1, 1)
            dW2 = self.a1.T @ dz2 / n
            db2 = dz2.sum(axis=0) / n
            
            da1 = dz2 @ self.W2.T
            dz1 = da1 * (self.z1 > 0)
            dW1 = X.T @ dz1 / n
            db1 = dz1.sum(axis=0) / n
            
            # Update
            self.W1 -= lr * dW1
            self.b1 -= lr * db1
            self.W2 -= lr * dW2
            self.b2 -= lr * db2
            
            if (epoch + 1) % 20 == 0:
                pred = (self.forward(X) > 0.5).flatten()
                acc = (pred == y.astype(int)).mean()
                print(f'  Epoch {epoch+1}, loss={loss:.4f}, acc={acc:.3f}')
    
    def predict(self, X):
        return self.forward(X).flatten()


# ─── DETECTOR ─────────────────────────────────────────────────────────

class DMDetectorFast:
    def __init__(self):
        self.mlp = None
        self.cache_path = 'dm_detector_fast.pkl'
    
    def train(self, n_pos=1000, n_neg=1000, epochs=100):
        print(f'Generating {n_pos} positive + {n_neg} negative samples...')
        X, y = generate_training_data(n_pos, n_neg)
        
        print(f'Training MLP on {X.shape[0]} samples with {X.shape[1]} features...')
        self.mlp = MLP(X.shape[1], hidden_size=64)
        self.mlp.train(X, y, epochs=epochs, lr=0.01)
        
        # Save
        with open(self.cache_path, 'wb') as f:
            pickle.dump({'W1': self.mlp.W1, 'b1': self.mlp.b1, 
                        'W2': self.mlp.W2, 'b2': self.mlp.b2}, f)
        print(f'Model saved to {self.cache_path}')
    
    def load(self):
        if os.path.exists(self.cache_path):
            with open(self.cache_path, 'rb') as f:
                data = pickle.load(f)
            self.mlp = MLP(data['W1'].shape[0], hidden_size=data['W1'].shape[1])
            self.mlp.W1 = data['W1']
            self.mlp.b1 = data['b1']
            self.mlp.W2 = data['W2']
            self.mlp.b2 = data['b2']
            return True
        return False
    
    def detect(self, gray, step=32, threshold=0.7):
        """Sliding window detection."""
        if self.mlp is None:
            return []
        
        h, w = gray.shape
        detections = []
        
        for y in range(0, h - 64, step):
            for x in range(0, w - 64, step):
                patch = gray[y:y+64, x:x+64]
                hog = extract_hog(patch)
                score = self.mlp.predict(hog.reshape(1, -1))[0]
                
                if score > threshold:
                    detections.append({
                        'bbox': (x, y, x + 64, y + 64),
                        'score': float(score)
                    })
        
        # NMS
        detections.sort(key=lambda d: -d['score'])
        final = []
        for det in detections:
            dup = False
            for f in final:
                bx1, by1, bx2, by2 = det['bbox']
                fx1, fy1, fx2, fy2 = f['bbox']
                inter = max(0, min(bx2, fx2) - max(bx1, fx1)) * max(0, min(by2, fy2) - max(by1, fy1))
                union = (bx2-bx1)*(by2-by1) + (fx2-fx1)*(fy2-fy1) - inter
                iou = inter / max(1, union)
                if iou > 0.3:
                    dup = True
                    break
            if not dup:
                final.append(det)
                if len(final) >= 10:
                    break
        
        return final


def scan_with_nn(gray, max_time=30.0):
    """Full pipeline: NN detection → reconstruction → decode."""
    start = time.time()
    
    # Try standard scan first
    from super_scanner import scan_v5
    r = scan_v5(gray, max_total_time=min(10.0, max_time))
    if r and r[0]:
        return r[0], r[1], r[2], r[3]
    
    # Load NN detector
    detector = DMDetectorFast()
    if not detector.load():
        print('Training NN detector...')
        detector.train(n_pos=1000, n_neg=1000, epochs=100)
    
    # Detect
    detections = detector.detect(gray, step=32, threshold=0.6)
    print(f'  NN found {len(detections)} candidates')
    
    # Try decode each
    for i, det in enumerate(detections):
        if time.time() - start > max_time:
            break
        
        x1, y1, x2, y2 = det['bbox']
        roi = gray[y1:y2, x1:x2]
        
        # Enhance
        cl = clahe_equalized(roi)
        
        # Try libdmtx
        for s in [1, 2, 3]:
            for dev in [25, 50, 100, 150]:
                r = _try(cl, s=s, timeout=10)
                if r:
                    return r[0], r[1], f"nn_{r[2]}", {"method": "nn"}
                # Inverted
                r = _try(255 - cl, s=s, timeout=10)
                if r:
                    return r[0], r[1], f"nn_inv_{r[2]}", {"method": "nn"}
    
    return None, None, None, None


if __name__ == '__main__':
    print('=== Fast NN DM Detector ===')
    detector = DMDetectorFast()
    
    if not detector.load():
        print('Training...')
        detector.train(n_pos=1000, n_neg=1000, epochs=100)
    
    # Test
    for fn in ['f2ec3103-49fd-4b7b-8e2d-fcc5956e1ac0.jpg', '4bdf8945-ff54-40d3-8b10-b9e7fd9dc1b2.jpg']:
        img = cv2.imread(f'realtest/{fn}', 0)
        if img is None:
            continue
        print(f'\n{fn[:8]}: {img.shape}')
        detections = detector.detect(img, step=32, threshold=0.6)
        print(f'  Found {len(detections)} regions')
        for i, det in enumerate(detections[:3]):
            print(f'    Region {i+1}: bbox={det["bbox"]} score={det["score"]:.3f}')