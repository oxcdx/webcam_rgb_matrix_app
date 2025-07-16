import os
import sys
import time
import glob
import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import threading
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# Configuration
EXHIBITION_FOLDER = os.path.join(BASE_DIR, "exhibition")
os.makedirs(EXHIBITION_FOLDER, exist_ok=True)

TOGGLE_4_SCREEN_MODE = True  # Set to False for 1-panel mode
TOGGLE_TEST_PATTERN = False  # Set to True for 4-color test pattern
TEST_JPG_MODE = False  # Set to True to use only the test image instead of cycling

# Global variables
if TOGGLE_4_SCREEN_MODE:
    current_images = [None, None, None, None]  # 4 screens
else:
    current_images = [None]  # 1 screen
image_index = 0
image_files = []
image_lock = threading.Lock()

def load_image_files():
    """Load all JPG files from the exhibition folder and shuffle order"""
    global image_files
    if TEST_JPG_MODE:
        # Use only the specific test image
        test_image_path = os.path.join(EXHIBITION_FOLDER, "20250712142130-rose-mosaic-final.jpg")
        if os.path.exists(test_image_path):
            image_files = [test_image_path]
            print(f"TEST_JPG_MODE: Using single test image: {test_image_path}")
            return True
        else:
            print(f"TEST_JPG_MODE: Test image not found: {test_image_path}")
            return False
    else:
        pattern = os.path.join(EXHIBITION_FOLDER, "*.jpg")
        image_files = glob.glob(pattern)
        image_files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.jpeg")))
        image_files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.JPG")))
        image_files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.JPEG")))
        image_files.sort()  # Sort for consistent order before shuffling
        if len(image_files) > 1:
            random.shuffle(image_files)
        print(f"Found {len(image_files)} images in exhibition folder (shuffled)")
        return len(image_files) > 0

def load_and_resize_image(image_path):
    """Load an image and resize it to 32x64 for the LED matrix (to match working display size)"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"Failed to load image: {image_path}")
            return None
        
        # Resize to 32x64 to fill the entire display width
        # resized = cv2.resize(img, (64, 32), interpolation=cv2.INTER_AREA)
        resized = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
        return resized
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None

def update_images():
    """Update the current images for each screen"""
    global current_images, image_index
    if len(image_files) == 0:
        return
    with image_lock:
        if TOGGLE_4_SCREEN_MODE:
            for screen in range(4):
                if image_index + screen < len(image_files):
                    img_path = image_files[image_index + screen]
                    current_images[screen] = load_and_resize_image(img_path)
                    print(f"Screen {screen + 1}: {os.path.basename(img_path)}")
                else:
                    wrap_index = (image_index + screen) % len(image_files)
                    img_path = image_files[wrap_index]
                    current_images[screen] = load_and_resize_image(img_path)
                    print(f"Screen {screen + 1} (wrapped): {os.path.basename(img_path)}")
        else:
            img_path = image_files[image_index % len(image_files)]
            current_images[0] = load_and_resize_image(img_path)
            print(f"Single panel: {os.path.basename(img_path)}")

def create_matrix_image():
    """Create the image for the matrix display"""
    with image_lock:
        if TOGGLE_4_SCREEN_MODE:
            # Create a 32x32 image for the matrix
            matrix_img = np.zeros((32, 32, 3), dtype=np.uint8)
            
            # Create black fallback images if any are missing
            screen_images = []
            for i in range(4):
              if current_images[i] is not None:
                  screen_images.append(current_images[i])
              else:
                  # Create a black 32x32 image as fallback
                  black_img = np.zeros((32, 32, 3), dtype=np.uint8)
                  screen_images.append(black_img)
            # Concatenate horizontally to create 128x32 image
            matrix_img = np.concatenate(screen_images, axis=1) 

            matrix_img = cv2.rotate(matrix_img, cv2.ROTATE_180)
            matrix_img_rgb = cv2.cvtColor(matrix_img, cv2.COLOR_BGR2RGB)
            return Image.fromarray(matrix_img_rgb)
        else:
            # Create a 32x64 image for single panel mode to match working test pattern
            # matrix_img = np.zeros((32, 64, 3), dtype=np.uint8)
            matrix_img = np.zeros((32, 32, 3), dtype=np.uint8)
            if current_images[0] is not None:
                # Place the 32x64 image across the full width
                matrix_img[:, :] = current_images[0]

            
            matrix_img = cv2.rotate(matrix_img, cv2.ROTATE_180)
            matrix_img_rgb = cv2.cvtColor(matrix_img, cv2.COLOR_BGR2RGB)
            return Image.fromarray(matrix_img_rgb)

def matrix_loop():
    """Main loop for the RGB matrix display or test pattern"""
    global image_index
    if TOGGLE_TEST_PATTERN:
        options = RGBMatrixOptions()
        options.rows = 32
        options.cols = 32
        options.chain_length = 1
        options.multiplexing = 6
        options.hardware_mapping = 'adafruit-hat'
        # options.pixel_mapper_config = "V-mapper"
        # options.brightness = 50
        matrix = RGBMatrix(options=options)
        print("Starting RGB matrix display in DEDICATED 4-COLOR TEST PATTERN mode...")
        test_img = np.zeros((32, 32, 3), dtype=np.uint8)
        # Top left: red
        # TBLR
        test_img[0:4, 0:8] = [255, 0, 0]
        # Top right: blue
        # test_img[0:16, 16:32] = [0, 0, 255]
        # # Bottom left: green
        test_img[16:32, 0:16] = [0, 255, 0]
        # # Bottom right: magenta
        test_img[16:32, 16:32] = [255, 0, 255]
        matrix.SetImage(Image.fromarray(test_img))
        while True:
            time.sleep(1)
    else:
        options = RGBMatrixOptions()
        if TOGGLE_4_SCREEN_MODE:
            options.rows = 32
            options.cols = 32
            options.chain_length = 4
        else:
            options.rows = 32
            options.cols = 32
            options.chain_length = 1
        options.multiplexing = 6
        options.hardware_mapping = 'adafruit-hat'
        # options.pixel_mapper_config = "V-mapper"
        options.brightness = 50  # Uncomment to set brightness
        matrix = RGBMatrix(options=options)
        print("Starting RGB matrix display...")
        print("Press Ctrl+C to exit")
        if not load_image_files():
            print("No images found in exhibition folder. Please add some JPG files.")
            return
        total_images = len(image_files)
        update_images()
        cycle_time = 5.0
        last_update = time.time()
        try:
            while True:
                current_time = time.time()
                if not TEST_JPG_MODE and current_time - last_update >= cycle_time:
                    if TOGGLE_4_SCREEN_MODE:
                        for panel in range(4):
                            next_image_index = (image_index + panel) % total_images
                            img_path = image_files[next_image_index]
                            img = load_and_resize_image(img_path)
                            with image_lock:
                                current_images[panel] = img
                            matrix_image = create_matrix_image()
                            matrix.SetImage(matrix_image)
                            time.sleep(0.08)
                        image_index = (image_index + 4) % total_images
                        last_update = time.time()
                        print(f"Cycled one panel at a time, starting at index {image_index}")
                        if image_index < 5 and total_images > 1:
                            random.shuffle(image_files)
                            print("Shuffled image order for new cycle.")
                    else:
                        image_index = (image_index + 1) % total_images
                        update_images()
                        matrix_image = create_matrix_image()
                        matrix.SetImage(matrix_image)
                        last_update = time.time()
                        print(f"Cycled single panel, now at index {image_index}")
                        if image_index == 0 and total_images > 1:
                            random.shuffle(image_files)
                            print("Shuffled image order for new cycle.")
                else:
                    try:
                        matrix_image = create_matrix_image()
                        matrix.SetImage(matrix_image)
                    except Exception as e:
                        print(f"Error setting matrix image: {e}")
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            matrix.Clear()

def main():
    """Main function"""
    print("JPG Cycle App for 4-Panel RGB Matrix")
    print(f"Exhibition folder: {EXHIBITION_FOLDER}")
    
    # Check if exhibition folder exists and has images
    if not os.path.exists(EXHIBITION_FOLDER):
        print(f"Creating exhibition folder: {EXHIBITION_FOLDER}")
        os.makedirs(EXHIBITION_FOLDER, exist_ok=True)
        print("Please add JPG images to the exhibition folder and restart the app.")
        return
    
    # Start the matrix loop
    matrix_loop()

if __name__ == "__main__":
    main()
