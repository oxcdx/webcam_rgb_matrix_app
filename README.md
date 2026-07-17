# RGB Matrix Image Display App

A Python application for displaying images and test patterns on RGB LED matrix panels using the `rgbmatrix` library. Supports both single-panel and multi-panel configurations with various display modes and effects.

## Features

- **Multi-Panel Support**: Display images across 1 or 4 chained RGB matrix panels
- **Image Cycling**: Automatically cycle through JPG images in the exhibition folder
- **Test Patterns**: Built-in 4-color test pattern for panel mapping and diagnostics
- **Multiple Display Modes**: 
  - Single image test mode
  - Image cycling mode
  - 4-color test pattern mode
- **Realtime Webcam Display**: Stream live webcam feed directly to the matrix via GStreamer
- **Realtime Effects**: Adjust brightness, contrast, saturation, and blur via a Flask web UI
- **Interactive Keyboard Control**: Trigger display and toggle invert mode using a physical USB keyboard (evdev)
- **Multi-Pi Coordination**: Coordinate image cycling across multiple Raspberry Pi displays with no repetition
- **Grid Visualisation**: Web UI for monitoring panel image assignments across displays in real time
- **Flexible Configuration**: Easy toggles for different panel configurations and display modes
- **Multiplexing Support**: Built-in support for different RGB matrix multiplexing modes

## Hardware Requirements

- Raspberry Pi (recommended: Pi 3B+ or Pi 4)
- RGB LED Matrix Panel(s) (32x32 pixels)
- Adafruit RGB Matrix HAT or equivalent
- Proper power supply for LED panels

## Software Dependencies

```bash
# Install required Python packages
pip install opencv-python pillow numpy flask

# For realtime webcam apps (GStreamer pipeline)
sudo apt install python3-gst-1.0 gstreamer1.0-tools gstreamer1.0-plugins-good

# For interactive keyboard control (webacm_single_interactive.py)
pip install evdev

# Install RGB Matrix library (follow official instructions)
# https://github.com/hzeller/rpi-rgb-led-matrix
```

## File Structure

- `app.py` - Main webcam/scanner application with multi-panel support
- `app-realtime-effects-working-slow.py` - Flask + webcam app with realtime effect controls; 2-panel chained (16×32, U-mapper)
- `app-realitime-scanner-version.py` - Flask + still image app with realtime effect controls; single 32×32 panel
- `webacm_single_interactive.py` - Headless webcam display for single 32×32 panel; keyboard-triggered via evdev
- `jpg_cycle_app.py` - JPG cycling application for 4-panel mode
- `jpg_cycle_app_2_screen.py` - JPG cycling application for 2-panel mode
- `jpg_cycle_app_alt_screen_type.py` - Flexible display app with multiple modes
- `image_coordinator.py` - Flask service that coordinates image cycling across multiple Pi displays with no repetition
- `visualise_grid.py` - Flask web UI for monitoring panel image assignments across displays
- `webcam_rgb_matrix.py` - Core webcam functionality
- `setup_pi.py` - Raspberry Pi setup/configuration script
- `exhibition/` - Folder containing JPG images to display
- `uploads/` - Folder for uploaded/processed images
- `static/` - Web interface assets
- `templates/` - HTML templates for web interface

## Configuration

### Main Configuration Flags (in `jpg_cycle_app_alt_screen_type.py`)

```python
TOGGLE_4_SCREEN_MODE = True   # True for 4-panel, False for single panel
TOGGLE_TEST_PATTERN = False   # True for test pattern mode
TEST_JPG_MODE = False         # True to display single test image
MULTIPLEX_MODE = 0            # Multiplexing mode (0-7)
```

### Multiplexing Modes

- `0`: No multiplexing (default)
- `1`: Strip multiplexing
- `2`: Checker multiplexing  
- `3`: Spiral multiplexing
- `4`: ZStrip multiplexing
- `5`: ZnMirrorZStrip multiplexing
- `6`: Coreman multiplexing
- `7`: Kaler2020 multiplexing

## Usage

### Realtime Webcam Apps

Both realtime apps use a GStreamer pipeline for camera capture and expose a Flask web UI on port 5000.

#### Effects app — 2-panel chained (16×32, U-mapper)
```bash
sudo python3 app-realtime-effects-working-slow.py
```

#### Scanner version -- single 32x32 panel
```bash
sudo python3 app-realitime-scanner-version.py
```

### Running app.py with sudo (production)

The main `app.py` must run as root for LED matrix GPIO access. However, the `rpi-rgb-led-matrix` library **drops privileges to uid 1 (daemon)** after hardware init, so Flask runs as an unprivileged user.

**One-time setup:**
```bash
# Create venv with system site-packages (for rpi-rgb-led-matrix)
sudo bash /opt/webcam_rgb_matrix_app/setup_venv.sh

# Fix file permissions so daemon user can read templates/static and write uploads
sudo chmod 755 /opt/webcam_rgb_matrix_app/templates/ /opt/webcam_rgb_matrix_app/static/
sudo chmod -R a+r /opt/webcam_rgb_matrix_app/
sudo chmod -R a+rwX /opt/webcam_rgb_matrix_app/uploads/
```

**Run:**
```bash
bash /opt/webcam_rgb_matrix_app/run.sh
```

**Why permissions matter:**
- `RGBMatrix()` init requires root (GPIO / `/dev/mem`)
- After init, the library drops to uid 1 (daemon) for safety
- Flask template rendering, static file serving, and image uploads all happen after the privilege drop
- Without world-readable permissions on `templates/` and `static/`, Flask gets `PermissionError`
- Without world-writable on `uploads/`, image saves fail

**If you copy new files to /opt/, always re-run:**
```bash
sudo chmod 755 /opt/webcam_rgb_matrix_app/templates/ /opt/webcam_rgb_matrix_app/static/
sudo chmod -R a+r /opt/webcam_rgb_matrix_app/
sudo chmod -R a+rwX /opt/webcam_rgb_matrix_app/uploads/
```

#### Web endpoints (both realtime Flask apps)
| Endpoint | Description |
|---|---|
| `/` | Main web UI |
| `/video_feed` | Raw webcam MJPEG stream |
| `/video_feed_mosaic` | Pixelated mosaic MJPEG stream |
| `/video_feed_effect` | Effect-processed MJPEG stream |
| `/set_effect_params` | POST JSON to update effect parameters |

**Effect parameters** (POST JSON to `/set_effect_params`):
```json
{ "brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "blur": 0, "highlights": 0.0 }
```

#### Interactive keyboard-controlled display
```bash
# Requires a SayoDevice USB keyboard connected (evdev path set in script)
sudo python3 webacm_single_interactive.py
# Any key: show camera feed
# Z: normal mode  |  X: invert mode
```

### Image Coordinator (multi-Pi)
```bash
# Run on a central Pi or server to coordinate images across all displays
python3 image_coordinator.py
# Manages 3 Pis by default (4 + 4 + 2 screens).
# Configure NUM_DISPLAYS and SCREENS_PER_DISPLAY at the top of the file.
```

### Grid Visualiser
```bash
python3 visualise_grid.py
# Connects to image_coordinator and shows current panel assignments in browser
```

### 1. Single Panel Display
```bash
# Edit configuration in jpg_cycle_app_alt_screen_type.py
TOGGLE_4_SCREEN_MODE = False
TOGGLE_TEST_PATTERN = False

python jpg_cycle_app_alt_screen_type.py
```

### 2. Multi-Panel Display
```bash
# Edit configuration
TOGGLE_4_SCREEN_MODE = True
TOGGLE_TEST_PATTERN = False

python jpg_cycle_app_alt_screen_type.py
```

### 3. Test Pattern Mode
```bash
# Edit configuration
TOGGLE_TEST_PATTERN = True

python jpg_cycle_app_alt_screen_type.py
```

### 4. Single Image Test
```bash
# Edit configuration
TEST_JPG_MODE = True
# Place test image: exhibition/20250712142130-rose-mosaic-final.jpg

python jpg_cycle_app_alt_screen_type.py
```

## Adding Images

1. Place JPG images in the `exhibition/` folder
2. Supported formats: `.jpg`, `.jpeg`, `.JPG`, `.JPEG`
3. Images are automatically resized and cropped to fit panel dimensions
4. Images cycle automatically (unless in test mode)

## Troubleshooting

### Panel Mapping Issues
1. Try different `MULTIPLEX_MODE` values (0-7)
2. Use test pattern mode to diagnose color and orientation issues
3. Check hardware connections and power supply
4. Verify `options.hardware_mapping` setting

### Display Issues
- **Image appears on half screen**: Check chain_length and image dimensions
- **Colors are wrong**: Try different multiplexing modes
- **Image is rotated**: Adjust the `cv2.rotate()` calls in `create_matrix_image()`
- **Panels show wrong content**: Verify chain_length matches physical setup

### Common Hardware Mapping Options
- `'adafruit-hat'` - For Adafruit RGB Matrix HAT
- `'adafruit-hat-pwm'` - For Adafruit HAT with PWM
- `'regular'` - For direct GPIO connection

## Development

### Key Functions
- `load_and_resize_image()` - Loads and processes images for display
- `create_matrix_image()` - Creates the final matrix image for display
- `matrix_loop()` - Main display loop with cycling logic
- `update_images()` - Updates current images for each panel

### Adding New Features
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with your hardware setup
5. Submit a pull request

## License

This project is open source. Please check individual file headers for specific license information.

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## Hardware Setup Notes

- Ensure proper power supply for LED panels (5V, sufficient amperage)
- Use quality jumper wires for stable connections
- Consider heat dissipation for long-running displays
- Test with single panel before adding multiple panels
- Verify GPIO pin connections match your HAT/hardware setup
