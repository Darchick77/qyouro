import requests
import urllib3
urllib3.disable_warnings()

API = "https://127.0.0.1:8443"
errors = []

def test(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        errors.append(name)

# 1. Health
print("1. Backend health")
test("GET /health", lambda: requests.get(f"{API}/health", verify=False).raise_for_status())

# 2. Frontend page
print("2. Frontend page")
r = requests.get(f"{API}/dm-scanner", verify=False)
test("dm-scanner loads", lambda: None if r.status_code == 200 else exec('raise Exception("status " + str(r.status_code))'))
html = r.text
test("no arrow functions (=>)", lambda: None if "=>" not in html else exec("raise Exception('found arrow function')"))
test("has bolt-btn", lambda: None if "bolt-btn" in html else exec("raise Exception('missing')"))
test("has flash-btn", lambda: None if "flash-btn" in html else exec("raise Exception('missing')"))
test("has scan-square", lambda: None if "/scan-square" in html else exec("raise Exception('missing')"))
test("has scan-photo", lambda: None if "/scan-photo" in html else exec("raise Exception('missing')"))
test("has scan-v5", lambda: None if "/scan-v5" in html else exec("raise Exception('missing')"))

# 3. API endpoints
print("3. Scan endpoints")
with open("C:/datamatrix_restorer/test/000_clean.png", "rb") as f:
    files = {"file": ("test.png", f, "image/png")}

    r = requests.post(f"{API}/scan-v5", files=files, verify=False)
    data = r.json()
    test("POST /scan-v5 returns code", lambda: None if data.get("code") else exec("raise Exception('no code')"))

with open("C:/datamatrix_restorer/test/000_clean.png", "rb") as f:
    files = {"file": ("test.png", f, "image/png")}
    r = requests.post(f"{API}/scan-square", files=files, verify=False)
    data = r.json()
    test("POST /scan-square returns code", lambda: None if data.get("code") else exec("raise Exception('no code')"))

with open("C:/datamatrix_restorer/test/000_clean.png", "rb") as f:
    files = {"file": ("test.png", f, "image/png")}
    r = requests.post(f"{API}/scan-photo", files=files, verify=False)
    data = r.json()
    test("POST /scan-photo returns code", lambda: None if data.get("code") else exec("raise Exception('no code')"))

# Summary
print()
print("=" * 40)
if errors:
    print(f"FAILED {len(errors)} test(s): {', '.join(errors)}")
else:
    print("ALL TESTS PASSED")
print("=" * 40)
