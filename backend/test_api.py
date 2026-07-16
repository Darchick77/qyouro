import requests
import os

API_URL = "https://127.0.0.1:8443"

# Test health
r = requests.get(f"{API_URL}/health", verify=False)
print("Health:", r.json())

# Test scan-photo
test_img = "C:/datamatrix_restorer/test/000_clean.png"
if os.path.exists(test_img):
    with open(test_img, "rb") as f:
        files = {"file": ("test.png", f, "image/png")}
        r = requests.post(f"{API_URL}/scan-photo", files=files, verify=False, timeout=30)
        print("scan-photo:", r.json())
else:
    print("No test image")
