import shutil
import os

src = "/home/pera/.gemini/antigravity/brain/e64f7837-54ba-494d-9524-76438bed07e9/luna_app_icon_1779233741938.png"
dst = "/home/pera/Luna/luna-desktop/static/logo.png"

try:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    print("SUCCESS: Copied icon to static/logo.png")
except Exception as e:
    print(f"ERROR: {e}")
