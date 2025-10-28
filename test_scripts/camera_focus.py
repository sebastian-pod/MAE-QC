from picamera2 import Picamera2
import time, os

SAVE_DIR = os.path.expanduser("~/focus_sweep")
RES = (4656, 3496)
STEP = 1  # 1..100

os.makedirs(SAVE_DIR, exist_ok=True)

# Prefer enums (safer than guessing values)
try:
    from libcamera import controls
    AF_MODE_MANUAL = controls.AfModeEnum.Manual
    AF_MODE_AUTO = controls.AfModeEnum.Auto
    AF_TRIGGER_START = controls.AfTriggerEnum.Start
except Exception:
    AF_MODE_MANUAL = 0
    AF_MODE_AUTO = 1
    AF_TRIGGER_START = 0

def try_manual_sweep(p, start=1, stop=2, step=1):
    # Put AF into MANUAL first; if AF algo isn’t present, IPA may refuse LensPosition
    p.set_controls({"AfMode": AF_MODE_MANUAL})
    time.sleep(0.2)

    # Quick probe: try a single position and read metadata back
    try:
        p.set_controls({"LensPosition": float(start)})
        time.sleep(0.25)
        m = p.capture_metadata()
        # Some builds echo back "LensPosition" or change AfState; not guaranteed.
        return True  # assume we can proceed
    except Exception as e:
        print("⚠️ Manual LensPosition write failed:", e)
        return False

pic = Picamera2()
pic.configure(pic.create_still_configuration(main={"size": RES}))
pic.start()
time.sleep(0.8)

manual_ok = try_manual_sweep(pic, 1, 100, STEP)

if manual_ok:
    print("🔧 Manual focus sweep via LensPosition (1 → 100)")
    for pos in range(1, 101, STEP):
        try:
            pic.set_controls({"LensPosition": float(pos)})
        except Exception as e:
            print("⚠️ LensPosition set failed mid-sweep:", e)
            break
        time.sleep(0.30)  # let lens settle
        fn = os.path.join(SAVE_DIR, f"focus_{pos:03d}.jpg")
        pic.capture_file(fn)
        print(f"📷 {fn} | LensPosition={pos}")
else:
    print("ℹ️ AF algorithm not accepting LensPosition. Falling back to one-shot AF per frame.")
    # One-shot AF each frame: set Auto + Trigger before every capture
    for pos in range(1, 101, STEP):
        pic.set_controls({"AfMode": AF_MODE_AUTO, "AfTrigger": AF_TRIGGER_START})
        # Let AF scan; 300–600 ms is usually enough
        time.sleep(0.6)
        fn = os.path.join(SAVE_DIR, f"focus_autoscan_{pos:03d}.jpg")
        pic.capture_file(fn)
        print(f"📷 {fn} | One-shot AF triggered")

pic.stop()
print(f"✅ Done. Images saved in {SAVE_DIR}")
