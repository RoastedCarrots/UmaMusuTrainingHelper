import os
import cv2
import numpy as np
import pyautogui
import keyboard
import time
import threading
import tkinter as tk
from PIL import Image, ImageTk
from concurrent.futures import ThreadPoolExecutor

# ==============================
# CONFIG
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_FOLDER = os.path.join(BASE_DIR, "templates")
DEBUG_FOLDER = os.path.join(BASE_DIR, "debug")
os.makedirs(TEMPLATES_FOLDER, exist_ok=True)
os.makedirs(DEBUG_FOLDER, exist_ok=True)

MATCH_THRESHOLD = 0.89
DOWNSCALE_FACTOR = 0.5
KEY_ACTIONS = {
    "g": "Speed",
    "h": "Stamina",
    "j": "Power",
    "k": "Guts",
    "l": "Wits"
}
EXTRA_Q = ["hint.png", ]
OVERLAY_BG, OVERLAY_FG, OVERLAY_ALPHA = "#3A0968", "#FFFFFF", 0.70
OVERLAY_PAD_X, OVERLAY_PAD_Y = 8, 6
OVERLAY_FONT = ("Segoe UI", 11)

# ==============================
# HELPERS: load & downscale
# ==============================
def load_image_grayscale(path):
    if not os.path.exists(path):
        return None
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    elif img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    if DOWNSCALE_FACTOR != 1.0:
        gray = cv2.resize(gray, (0, 0), fx=DOWNSCALE_FACTOR, fy=DOWNSCALE_FACTOR)
    return gray

def load_templates_grayscale(folder):
    templates = {}
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Templates folder not found: {folder}")
    for f in os.listdir(folder):
        if f.lower().endswith(".png") and f.lower() not in [x.lower() for x in EXTRA_Q]:
            path = os.path.join(folder, f)
            gray = load_image_grayscale(path)
            if gray is not None:
                templates[f] = gray
    return templates

# ==============================
# Matching helpers
# ==============================
def match_template_all(screen_gray, template_gray, threshold=MATCH_THRESHOLD):
    """
    Return a list of matches (dicts with top_left,w,h,max_val) for all locations
    where template match >= threshold. Performs simple spatial suppression to avoid duplicates.
    """
    th, tw = template_gray.shape[:2]
    H, W = screen_gray.shape[:2]
    if tw > W or th > H:
        return []

    res = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)
    points = list(zip(*loc[::-1]))  # list of (x,y)

    # suppression: keep a point only if not near existing kept points
    kept = []
    min_dist = max(1, int(min(tw, th) * 0.6))
    for pt in sorted(points, key=lambda p: (p[1], p[0])):
        if any(abs(pt[0]-kp[0]) < min_dist and abs(pt[1]-kp[1]) < min_dist for kp in kept):
            continue
        kept.append(pt)

    matches = []
    for pt in kept:
        matches.append({
            "max_val": float(res[pt[1], pt[0]]),
            "top_left": (int(pt[0]), int(pt[1])),
            "w": tw,
            "h": th
        })
    return matches

# CPU single best (kept for compatibility if needed)
def match_template_noscale(screen_gray, template_gray):
    th, tw = template_gray.shape[:2]
    H, W = screen_gray.shape[:2]
    if tw > W or th > H:
        return {"max_val": -np.inf, "top_left": None, "w": 0, "h": 0}
    res = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return {"max_val": float(max_val), "top_left": tuple(map(int, max_loc)), "w": tw, "h": th}

# ==============================
# Debug screenshot
# ==============================
def save_debug_image(screen_color, match_infos):
    os.makedirs(DEBUG_FOLDER, exist_ok=True)
    img = screen_color.copy()
    for info in match_infos:
        if info.get("top_left") is None:
            continue
        x, y, w, h = *info["top_left"], info["w"], info["h"]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
        label = f"{os.path.splitext(info.get('name',''))[0]} {info.get('max_val',0):.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(img, (x, max(y - th - 6, 0)), (x + tw + 6, y), (0, 0, 255), -1)
        cv2.putText(img, label, (x + 3, max(y - 6, 0) + th - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    fname = os.path.join(DEBUG_FOLDER, f"{time.strftime('%d-%m-%y-%H-%M-%S')}.png")
    cv2.imwrite(fname, img)
    # small console log to help debugging
    print(f"[DEBUG] Saved debug image: {fname} (matches={len(match_infos)})")

# ==============================
# Screenshot helper
# ==============================
def take_screenshot_gray_and_color():
    pil = pyautogui.screenshot()
    color = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    if DOWNSCALE_FACTOR != 1.0:
        color = cv2.resize(color, (0, 0), fx=DOWNSCALE_FACTOR, fy=DOWNSCALE_FACTOR)
        gray = cv2.resize(gray, (0, 0), fx=DOWNSCALE_FACTOR, fy=DOWNSCALE_FACTOR)
    return gray, color

# ==============================
# Overlay
# ==============================
class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", OVERLAY_ALPHA)
        self.frame = tk.Frame(root, bg=OVERLAY_BG)
        self.frame.pack(fill="both", expand=True)
        self.text_var = tk.StringVar()
        label = tk.Label(self.frame, textvariable=self.text_var, bg=OVERLAY_BG, fg=OVERLAY_FG,
                         font=OVERLAY_FONT, justify="left", anchor="w")
        label.pack(padx=OVERLAY_PAD_X, pady=OVERLAY_PAD_Y, fill="both", expand=True)
        self.root.geometry("+5+5")
        self.data = {}
        self.update_loop()

    def update_loop(self):
        lines = []
        for stat, info in self.data.items():
            # info is expected to be a dict: {"matches": [...], "training": float}
            matches_list = info.get("matches", [])
            matches_str = ", ".join(matches_list) if matches_list else "None"

            training_display = str(info.get("training", 0.0))
            try:
                # Good training threshold
                if float(info.get("training", 0.0)) > 4.5:
                    training_display += "  Good training."
            except Exception:
                pass

            lines.append(f"{stat}:\n  Matches: {matches_str}\n  Training value: {training_display}")
        self.text_var.set("\n".join(lines) if lines else "No data")
        self.root.after(200, self.update_loop)

    def set_stat_data(self, stat, matches_list, training_val):
        # store a consistent dict so update_loop can read it safely
        self.data[stat] = {"matches": matches_list, "training": training_val}

    def reset_all(self):
        self.data.clear()

# ==============================
# Extra templates (hint top-half only, rainbow full)
# ==============================
def check_extra_templates(screen_gray, match_infos):
    for extra, tpl_gray in extra_templates_gray.items():
        if tpl_gray is None:
            continue
        if extra.lower().startswith("hint"):
            h, w = screen_gray.shape
            search_img = screen_gray[: h // 2, :]
        else:
            search_img = screen_gray

        matches = match_template_all(search_img, tpl_gray)
        for m in matches:
            # If we matched on cropped (top half), top_left is relative to that crop; keep as-is (top half starts at y=0)
            entry = m.copy()
            entry["name"] = extra
            entry["scale"] = 1.0
            match_infos.append(entry)

# ==============================
# Training calculation helper
# ==============================
def calculate_training(match_infos, stat):
    """
    match_infos: list of match dicts (each must have 'name')
    returns: (training_value:float, breakdown:dict)
    """
    # counts
    normal_count = 0
    director_count = 0
    etsuko_count = 0
    hint_count = 0
    rainbow_count = 0
    notfull_count = 0

    for info in match_infos:
        name = os.path.splitext(info.get("name", ""))[0].lower()
        if "director" in name:
            director_count += 1
        elif "etsuko" in name:
            etsuko_count += 1
        elif "rainbow" in name:
            rainbow_count += 1
        elif "hint" in name:
            hint_count += 1
        elif "notfull" in name:
            notfull_count += 1
        else:
            normal_count += 1

    training_value = 0.0
    training_value += normal_count * 1.0
    training_value += director_count * 0.5
    training_value += etsuko_count * 0.5
    if hint_count > 0:
        training_value += 0.5  # hint only once
    training_value += rainbow_count * 2.0
    training_value += notfull_count * 0.5

    matched_any = (normal_count + director_count + etsuko_count + hint_count + rainbow_count + notfull_count) > 0
    if matched_any:
        s = stat.lower()
        if s == "speed":
            training_value += 1.0
        elif s in ("stamina", "power", "wits"):
            training_value += 0.5

    training_value = round(training_value, 2)
    breakdown = {
        "normal": normal_count,
        "director": director_count,
        "etsuko": etsuko_count,
        "hint": hint_count,
        "rainbow": rainbow_count,
        "notfull": notfull_count,
        "stat": stat
    }
    return training_value, breakdown

# ==============================
# Detection loop
# ==============================
stop_event = threading.Event()

def detection_loop(templates):
    # templates: dict filename -> grayscale image
    while not stop_event.is_set():
        try:
            if keyboard.is_pressed("]"):
                print("[INFO] ']' pressed -> stopping")
                stop_event.set()
                overlay_root.after(10, overlay_root.destroy)
                break
            if keyboard.is_pressed("p"):
                    overlay_app.reset_all()
                    print("[INFO] Resetting overlay data")
                    time.sleep(0.3)  # small debounce so it doesn't trigger repeatedly
                    continue

            for key, stat in KEY_ACTIONS.items():
                if keyboard.is_pressed(key):
                    # ✅ Handle reset here
                    

                    screen_gray, screen_color = take_screenshot_gray_and_color()
                    match_infos = []

                    # --- main templates: parallel multi-match ---
                    def match_worker_all(item):
                        name, tpl_gray = item
                        if tpl_gray is None:
                            return []
                        matches = match_template_all(screen_gray, tpl_gray)
                        out = []
                        for m in matches:
                            mm = m.copy()
                            mm["name"] = name
                            out.append(mm)
                        return out

                    if templates:
                        with ThreadPoolExecutor(max_workers=min(len(templates), os.cpu_count() or 1)) as executor:
                            for result_list in executor.map(match_worker_all, templates.items()):
                                if not result_list:
                                    continue
                                for r in result_list:
                                    match_infos.append(r)

                    # --- extras (hint/rainbow) ---
                    check_extra_templates(screen_gray, match_infos)

                    # Build a display list of names (keep duplicates for counts)
                    matched_names_noext = [os.path.splitext(m.get("name",""))[0] for m in match_infos]

                    # Calculate training and breakdown from match_infos
                    training_value, breakdown = calculate_training(match_infos, stat)

                    # Tidy matched_names_noext for display:
                    # - collapse rainbows into "rainbow × N" if multiple
                    # - show only one "hint" if multiple
                    display_names = [n for n in matched_names_noext if "rainbow" not in n.lower() and "hint" not in n.lower()]
                    if breakdown["rainbow"] > 0:
                        display_names.insert(0, f"rainbow × {breakdown['rainbow']}" if breakdown["rainbow"] > 1 else "rainbow")
                    if breakdown["hint"] > 0:
                        display_names.append("hint")

                    # Save debug image once
                    save_debug_image(screen_color, match_infos)

                    # Update overlay (consistent format)
                    overlay_app.set_stat_data(stat, display_names, training_value)

                    # Debug print
                    print(f"{stat}: matches={display_names} -> training={training_value} breakdown={breakdown}")

                    # small debounce
                    time.sleep(0.4)

            time.sleep(0.05)
        except Exception as e:
            print("[ERROR] detection loop exception:", e)
            time.sleep(0.5)

# ==============================
# ENTRY POINT
# ==============================
if __name__ == "__main__":
    print("[INFO] Loading templates from:", TEMPLATES_FOLDER)
    templates = load_templates_grayscale(TEMPLATES_FOLDER)
    if not templates:
        print("[ERROR] No templates found. Exiting.")
        raise SystemExit(1)
    print(f"[INFO] Loaded {len(templates)} main templates.")

    # Preload extra templates once
    extra_templates_gray = {}
    for extra in EXTRA_Q:
        path = os.path.join(TEMPLATES_FOLDER, extra)
        gray = load_image_grayscale(path)
        if gray is not None:
            extra_templates_gray[extra] = gray
    print(f"[INFO] Preloaded {len(extra_templates_gray)} extra templates: {list(extra_templates_gray.keys())}")

    os.makedirs(DEBUG_FOLDER, exist_ok=True)
    overlay_root = tk.Tk()
    overlay_app = OverlayApp(overlay_root)
    det_thread = threading.Thread(target=detection_loop, args=(templates,), daemon=True)
    det_thread.start()
    try:
        overlay_root.mainloop()
    except KeyboardInterrupt:
        pass
    stop_event.set()
    det_thread.join(timeout=2.0)
    print("[INFO] Program exited cleanly.")
