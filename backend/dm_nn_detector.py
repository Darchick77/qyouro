"""
CNN-based DataMatrix detector using PyTorch.
Detects faded DM bounding boxes, reconstructs and decodes.
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import cv2
import numpy as np
import os, sys, time, pickle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dm_encode import encode as dm_encode
from super_scanner import clahe_equalized, _try


# ─── CNN MODEL ─────────────────────────────────────────────────────────

class DMDetector(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(32 * 16 * 16, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 5),  # [has_dm, x1, y1, x2, y2]
            nn.Sigmoid(),
        )

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


# ─── SYNTHETIC DATA GENERATION ─────────────────────────────────────────

def generate_dm_training_data(n_samples=3000, patch_size=64):
    """Generate synthetic DM patches with known bounding boxes."""
    X = np.zeros((n_samples, 1, patch_size, patch_size), dtype=np.float32)
    y = np.zeros((n_samples, 5), dtype=np.float32)
    
    # Pre-generate codes
    codes = []
    for _ in range(100):
        code_len = np.random.randint(6, 20)
        code = ''.join([chr(np.random.randint(48, 90)) for _ in range(code_len)])
        codes.append(code)
    
    for i in range(n_samples):
        # Random DM parameters
        mod_size = np.random.randint(2, 5)
        n_mod = np.random.randint(8, 18)
        code = codes[i % len(codes)]
        
        # Generate DM
        try:
            dm = dm_encode(code, module_size=mod_size, margin=2)
            dm_arr = np.array(dm.convert('L'))
            dm_bin = (dm_arr < 128).astype(np.uint8) * 255
        except:
            dm_bin = np.ones((n_mod * mod_size + 4, n_mod * mod_size + 4), dtype=np.uint8) * 255
        
        # Resize if too large
        h, w = dm_bin.shape
        max_dim = patch_size - 10
        if h > max_dim or w > max_dim:
            scale = max_dim / max(h, w)
            dm_bin = cv2.resize(dm_bin, (int(w * scale), int(h * scale)))
            h, w = dm_bin.shape
        
        # Apply degradations (vectorized where possible)
        fade = np.random.uniform(0.2, 0.7)
        blur = np.random.uniform(0.5, 2.0)
        noise_std = np.random.uniform(0, 20)
        
        dm_f = dm_bin.astype(np.float32)
        if blur > 0:
            dm_f = cv2.GaussianBlur(dm_f, (0, 0), blur)
        dm_f = dm_f * (1 - fade) + 255 * fade
        if noise_std > 0:
            dm_f += np.random.randn(h, w) * noise_std
        dm_f = np.clip(dm_f, 0, 255).astype(np.uint8)
        
        # JPEG compression (skip for speed)
        # if np.random.random() < 0.5:
        #     _, buf = cv2.imencode('.jpg', dm_f, [cv2.IMWRITE_JPEG_QUALITY, np.random.randint(15, 40)])
        #     dm_f = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        
        # Place in patch
        patch = np.ones((patch_size, patch_size), dtype=np.uint8) * 255
        cx = np.random.randint(5, patch_size - w - 4)
        cy = np.random.randint(5, patch_size - h - 4)
        patch[cy:cy+h, cx:cx+w] = dm_f
        
        # Normalize
        X[i, 0] = patch.astype(np.float32) / 255.0
        
        # Bounding box normalized to [0, 1]
        x1 = cx / patch_size
        y1 = cy / patch_size
        x2 = (cx + w) / patch_size
        y2 = (cy + h) / patch_size
        has_dm = 1.0
        
        y[i] = [has_dm, x1, y1, x2, y2]
        
        if (i + 1) % 500 == 0:
            print(f'  Generated {i+1}/{n_samples}')
    
    return X, y


# ─── TRAINING ──────────────────────────────────────────────────────────

def train_detector(n_epochs=50, batch_size=64, n_samples=10000):
    """Train CNN DM detector."""
    print('Generating training data...')
    X, y = generate_dm_training_data(n_samples)
    
    X_t = torch.FloatTensor(X)
    y_t = torch.FloatTensor(y)
    
    dataset = TensorDataset(X_t, y_t)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')
    
    model = DMDetector().to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()
    
    print('Training...')
    for epoch in range(n_epochs):
        model.train()
        total_loss = 0
        n_batches = 0
        
        for X_batch, y_batch in loader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)
            
            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            n_batches += 1
        
        avg_loss = total_loss / max(1, n_batches)
        print(f'Epoch {epoch+1}/{n_epochs}, loss={avg_loss:.6f}')
        
        if (epoch + 1) % 10 == 0:
            torch.save(model.state_dict(), 'dm_detector_epoch.pth')
            print(f'  Saved checkpoint')
    
    # Save final model
    torch.save(model.state_dict(), 'dm_detector_final.pth')
    print('Training complete. Model saved.')
    return model


# ─── INFERENCE ─────────────────────────────────────────────────────────

def detect_dm_regions(model, gray, patch_size=64, step=16, threshold=0.5):
    """Detect DM regions in image using sliding window."""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = model.to(device)
    model.eval()
    
    h, w = gray.shape
    detections = []
    
    for y in range(0, h - patch_size, step):
        for x in range(0, w - patch_size, step):
            patch = gray[y:y+patch_size, x:x+patch_size]
            if patch.shape[0] < patch_size or patch.shape[1] < patch_size:
                continue
            
            patch_f = patch.astype(np.float32) / 255.0
            X = torch.FloatTensor(patch_f).unsqueeze(0).unsqueeze(0).to(device)
            
            with torch.no_grad():
                pred = model(X)[0].cpu().numpy()
            
            has_dm, x1_n, y1_n, x2_n, y2_n = pred
            
            if has_dm > threshold:
                # Convert normalized coords to absolute
                x1 = int(x + x1_n * patch_size)
                y1 = int(y + y1_n * patch_size)
                x2 = int(x + x2_n * patch_size)
                y2 = int(y + y2_n * patch_size)
                
                # Clamp to image bounds
                x1 = max(0, min(w, x1))
                y1 = max(0, min(h, y1))
                x2 = max(0, min(w, x2))
                y2 = max(0, min(h, y2))
                
                if x2 - x1 > 30 and y2 - y1 > 30:
                    detections.append({
                        'bbox': (x1, y1, x2, y2),
                        'score': float(has_dm)
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


def reconstruct_and_decode(gray, bbox, timeout=10):
    """Crop DM region, enhance, and try to decode."""
    x1, y1, x2, y2 = bbox
    roi = gray[y1:y2, x1:x2]
    
    if roi.shape[0] < 30 or roi.shape[1] < 30:
        return None
    
    # Apply CLAHE
    cl = clahe_equalized(roi)
    
    # Try libdmtx
    for s in [1, 2, 3]:
        for dev in [25, 50, 100, 150]:
            r = _try(cl, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"cnn_{r[2]}"
            # Inverted
            r = _try(255 - cl, s=s, timeout=timeout)
            if r:
                return r[0], r[1], f"cnn_inv_{r[2]}"
    
    return None


# ─── MAIN PIPELINE ─────────────────────────────────────────────────────

def scan_with_cnn(gray, max_time=30.0, model_path='dm_detector_final.pth'):
    """Full pipeline: CNN detection → reconstruction → decode."""
    start = time.time()
    
    # Try standard scan first
    from super_scanner import scan_v5
    r = scan_v5(gray, max_total_time=min(10.0, max_time))
    if r and r[0]:
        return r[0], r[1], r[2], r[3]
    
    # Load CNN model
    if not os.path.exists(model_path):
        print('CNN model not found. Training...')
        model = train_detector(n_epochs=30, batch_size=64, n_samples=5000)
    else:
        model = DMDetector()
        model.load_state_dict(torch.load(model_path, map_location='cpu'))
        model.eval()
    
    # Detect DM regions
    print('Detecting DM regions with CNN...')
    detections = detect_dm_regions(model, gray)
    print(f'  Found {len(detections)} candidates')
    
    # Try to decode each
    for i, det in enumerate(detections):
        if time.time() - start > max_time:
            break
        
        bbox = det['bbox']
        print(f'  Testing region {i+1}: bbox={bbox} score={det["score"]:.3f}')
        
        result = reconstruct_and_decode(gray, bbox)
        if result:
            return result[0], result[1], f"cnn_{result[2]}", {"method": "cnn"}
    
    return None, None, None, None


if __name__ == '__main__':
    print('=== CNN DM Detector ===')
    
    # Check if model exists
    model_path = 'dm_detector_final.pth'
    
    if not os.path.exists(model_path):
        print('Training model from scratch...')
        model = train_detector(n_epochs=30, batch_size=128, n_samples=3000)
    else:
        print('Loading trained model...')
        model = DMDetector()
        model.load_state_dict(torch.load(model_path, map_location='cpu'))
        model.eval()
        print('Model loaded')
    
    # Test on working image
    work = cv2.imread('realtest/f2ec3103-49fd-4b7b-8e2d-fcc5956e1ac0.jpg', 0)
    if work is not None:
        print(f'\nTesting on working image: {work.shape}')
        detections = detect_dm_regions(model, work)
        print(f'Found {len(detections)} regions')
        for i, det in enumerate(detections[:3]):
            print(f'  Region {i+1}: bbox={det["bbox"]} score={det["score"]:.3f}')
            result = reconstruct_and_decode(work, det['bbox'])
            if result:
                print(f'    DECODED: {result[0][:60]}')
            else:
                print(f'    Failed to decode')
