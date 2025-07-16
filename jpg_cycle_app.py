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

# Global variables
current_images = [None, None, None, None]  # One image per screen
image_index = 0
image_files = []
image_lock = threading.Lock()

def load_image_files():
    """Load all JPG files from the exhibition folder and shuffle order"""
    global image_files
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
    """Load an image and resize it to 32x32 for the LED matrix"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"Failed to load image: {image_path}")
            return None
        
        # Crop to square first
        h, w = img.shape[:2]
        min_dim = min(h, w)
        start_x = max((w - min_dim) // 2, 0)
        start_y = max((h - min_dim) // 2, 0)
        cropped = img[start_y:start_y+min_dim, start_x:start_x+min_dim]
        
        # Resize to 32x32
        resized = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_AREA)
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
        # Load 4 different images for the 4 screens
        for screen in range(4):
            if image_index + screen < len(image_files):
                img_path = image_files[image_index + screen]
                current_images[screen] = load_and_resize_image(img_path)
                print(f"Screen {screen + 1}: {os.path.basename(img_path)}")
            else:
                # Wrap around if we don't have enough images
                wrap_index = (image_index + screen) % len(image_files)
                img_path = image_files[wrap_index]
                current_images[screen] = load_and_resize_image(img_path)
                print(f"Screen {screen + 1} (wrapped): {os.path.basename(img_path)}")

def create_matrix_image():
    """Create a 128x32 image by concatenating 4 screen images"""
    with image_lock:
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
        
        # Rotate the entire 128x32 image 180 degrees for upside-down displays
        matrix_img = cv2.rotate(matrix_img, cv2.ROTATE_180)
        
        # Convert BGR to RGB for PIL
        matrix_img_rgb = cv2.cvtColor(matrix_img, cv2.COLOR_BGR2RGB)
        return Image.fromarray(matrix_img_rgb)

def matrix_loop():
    """Main loop for the RGB matrix display"""
    global image_index
    total_images = 0
    
    # Setup RGB Matrix
    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 32
    options.chain_length = 4
    options.hardware_mapping = 'adafruit-hat'
    # options.brightness = 50  # Uncomment to set brightness
    matrix = RGBMatrix(options=options)
    
    print("Starting RGB matrix display...")
    print("Press Ctrl+C to exit")
    
    # Initial load of images
    if not load_image_files():
        print("No images found in exhibition folder. Please add some JPG files.")
        return
    total_images = len(image_files)
    update_images()
    
    cycle_time = 5.0  # Show each set of images for 5 seconds
    last_update = time.time()
    
    try:
        while True:
            current_time = time.time()
            
            # Check if it's time to cycle to the next set of images
            if current_time - last_update >= cycle_time:
                # For this cycle, update one panel at a time, 0.2s apart
                for panel in range(4):
                    # Compute which image to show on this panel
                    next_image_index = (image_index + panel) % total_images
                    img_path = image_files[next_image_index]
                    img = load_and_resize_image(img_path)
                    with image_lock:
                        # Only update the current panel, keep others as they are
                        current_images[panel] = img
                    matrix_image = create_matrix_image()
                    matrix.SetImage(matrix_image)
                    time.sleep(0.1)
                # After all 4 panels updated, advance image_index by 4
                image_index = (image_index + 4) % total_images
                last_update = time.time()
                print(f"Cycled one panel at a time, starting at index {image_index}")
                # After a full cycle, shuffle if needed
                if image_index == 0 and total_images > 1:
                    random.shuffle(image_files)
                    print("Shuffled image order for new cycle.")
            else:
                # Just keep displaying the current image
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
