import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
from evdev import InputDevice, categorize, ecodes
import threading

def main():
    pipeline = (
        "v4l2src device=/dev/video0 ! "
        "video/x-raw,width=320,height=180 ! "
        "videoconvert ! appsink"
    )

    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    # cap = cv2.VideoCapture(0)
    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    # # cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # Enable auto exposure
    # cap.set(cv2.CAP_PROP_AUTO_WB, 1)           # Enable auto white balance
    # cap.set(cv2.CAP_PROP_BRIGHTNESS, 8)
    # cap.set(cv2.CAP_PROP_CONTRAST, 128)
    # cap.set(cv2.CAP_PROP_SATURATION, 255)
    # # cap.set(cv2.CAP_PROP_GAIN, 0)


    invert_mode = threading.Event()
    show_camera_event = threading.Event()
    import time

    def keyboard_thread():
        device = InputDevice('/dev/input/by-id/usb-SayoDevice_SayoDevice_O2L_V2_03CDAB573972BC96A1FFFFFFFF00-event-kbd')
        key_z = 'KEY_Z'
        key_x = 'KEY_X'

        for event in device.read_loop():
            if event.type == ecodes.EV_KEY and event.value == 1:  # key down
                keycode = categorize(event).keycode
                show_camera_event.set()  # Any key press triggers camera display
                if keycode == key_z:
                    invert_mode.clear()
                elif keycode == key_x:
                    invert_mode.set()

    threading.Thread(target=keyboard_thread, daemon=True).start()

    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 32
    options.chain_length = 1
    options.hardware_mapping = 'adafruit-hat'
    options.led_rgb_sequence = "GBR"
    # options.pixel_mapper_config = "U-mapper"
    # options.pwm_bits = 6
    options.pwm_lsb_nanoseconds = 200
    options.gpio_slowdown = 2
    options.pwm_bits = 8
    # options.brightness = 100

    matrix = RGBMatrix(options=options)

    if not cap.isOpened():
        print("Cannot open camera")
        return


    from PIL import ImageDraw
    import os
    try:
        black_img = Image.new("RGB", (32, 32), (0, 0, 0))
        last_show_time = 0
        showing_camera = False
        showing_last_frame = False
        last_frame_image = None
        last_frame_time = 0
        while True:
            # If not showing camera or last frame, display black
            if not showing_camera and not showing_last_frame:
                matrix.SetImage(black_img)
                # Wait for event
                if show_camera_event.wait(timeout=0.1):
                    show_camera_event.clear()
                    last_show_time = time.time()
                    showing_camera = True
                continue


            # If showing camera, check time
            if showing_camera:
                elapsed = time.time() - last_show_time
                if elapsed > 15:
                    # Flash sequence: white/black/white, 0.3s each
                    white_img = Image.new("RGB", (32, 32), (255, 255, 255))
                    black_img = Image.new("RGB", (32, 32), (0, 0, 0))
                    for img in [white_img, black_img, white_img]:
                        matrix.SetImage(img)
                        time.sleep(0.1)
                    showing_camera = False
                    showing_last_frame = True
                    last_frame_time = time.time()
                    # Save last frame image to /opt/webcam_rgb_matrix_app/last_frame.png
                    save_dir = "/opt/webcam_rgb_matrix_app"
                    save_path = os.path.join(save_dir, "last_frame.png")
                    if last_frame_image is not None:
                        try:
                            if not os.path.exists(save_dir):
                                os.makedirs(save_dir, exist_ok=True)
                            last_frame_image.save(save_path)
                            os.chmod(save_path, 0o666)
                        except Exception as e:
                            print(f"Failed to save {save_path}: {e}")
                    continue

                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                h, w = frame.shape[:2]
                min_dim = min(h, w)
                if min_dim <= 0:
                    continue

                start_x = max((w - min_dim) // 2, 0)
                start_y = max((h - min_dim) // 2, 0)

                cropped = frame[start_y:start_y+min_dim, start_x:start_x+min_dim]
                if cropped.shape[0] <= 0 or cropped.shape[1] <= 0:
                    continue

                # Adjust brightness and contrast
                contrast = 2  # Example: 1.0 = no change
                brightness = -30 # Example: 0 = no change
                adjusted = cv2.convertScaleAbs(cropped, alpha=contrast, beta=brightness)

                # Adjust saturation
                hsv = cv2.cvtColor(adjusted, cv2.COLOR_BGR2HSV)
                h, s, v = cv2.split(hsv)
                saturation_factor = 2  # Example: 1.0 = no change
                s = cv2.multiply(s, saturation_factor)
                s = np.clip(s, 0, 255).astype(np.uint8)
                hsv = cv2.merge([h, s, v])
                saturated = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

                try:
                    resized = cv2.resize(saturated, (32, 32))
                except Exception as e:
                    print(f"Resize error: {e}")
                    continue

                if resized.shape[0] != 32 or resized.shape[1] != 32:
                    print(f"Resized shape invalid: {resized.shape}")
                    continue

                if invert_mode.is_set():
                    contrastInv = 2
                    brightnessInv = 30 
                    adjustedInv = cv2.convertScaleAbs(resized, alpha=contrast, beta=brightness)
                    inverted = cv2.bitwise_not(adjustedInv)
                    hsv = cv2.cvtColor(inverted, cv2.COLOR_BGR2HSV)
                    h, s, v = cv2.split(hsv)
                    h = (h + 90) % 180
                    hsv = cv2.merge([h, s, v])
                    resized = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

                try:
                    frame_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(frame_rgb)
                    # Rotate the image 90 degrees clockwise
                    image = image.rotate(-270, expand=True)
                except Exception as e:
                    print(f"Image conversion error: {e}")
                    continue

                if image.size != (32, 32):
                    print(f"Image size invalid: {image.size}")
                    continue

                # Draw vertical timer bar (shrinks from top and bottom)
                bar_total = 30
                bar_left = 15
                shrink_steps = int(elapsed // 1)
                bar_length = max(0, bar_total - shrink_steps * 2)  # 2 pixels from each end per step
                if bar_length > 0:
                    bar_top = (32 - bar_length) // 2
                    image_with_bar = image.copy()
                    draw = ImageDraw.Draw(image_with_bar)
                    draw.rectangle([bar_left, bar_top, bar_left, bar_top + bar_length - 1], fill=(255,0,0))
                else:
                    image_with_bar = image.copy()

                try:
                    matrix.SetImage(image_with_bar)
                    last_frame_image = image.copy()
                except Exception as e:
                    print(f"SetImage error: {e}")
                    continue
                continue

            # If showing last frame, check time
            if showing_last_frame:
                elapsed = time.time() - last_frame_time
                # After 15 seconds, allow interruption by Z or X key, otherwise show for up to 2 minutes
                if elapsed > 15:
                    # Clear any queued key events from the first 15 seconds
                    while show_camera_event.is_set():
                        show_camera_event.clear()
                    # Wait for Z or X key or timeout (2 minutes)
                    interrupted = show_camera_event.wait(timeout=120 - elapsed)
                    if interrupted:
                        show_camera_event.clear()
                        last_show_time = time.time()
                        showing_camera = True
                        showing_last_frame = False
                        continue
                    else:
                        showing_last_frame = False
                        continue
                if last_frame_image is not None:
                    matrix.SetImage(last_frame_image)
                else:
                    matrix.SetImage(black_img)
                time.sleep(0.05)
                continue

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        matrix.Clear()

if __name__ == "__main__":
    main()
