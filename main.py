# spitest.py
# A brief demonstration of the Raspberry Pi SPI interface, using the Sparkfun
# Pi Wedge breakout board and a SparkFun Serial 7 Segment display:
# https://www.sparkfun.com/products/11629

import time
import spidev
import math
import random
import datetime
import threading
import logging
import signal
import sys
from flask import Flask, request, jsonify

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# We only have SPI bus 0 available to us on the Pi
bus = 0

#Device is the chip select pin. Set to 0 or 1, depending on the connections
device = 1

# Enable SPI
spi = spidev.SpiDev()

# Open a connection to a specific bus and device (chip select pin)
spi.open(bus, device)

# Set SPI speed and mode
spi.max_speed_hz = 500000
spi.mode = 0

# Clear display
msg = [0] * 300
spi.xfer2(msg)


# Configuration constants
NUM_LEDS = 100
FAVORITE_COLOR = [255, 25, 2]  # Orange-red color

# Animation timing constants
DAYTIME_START_HOUR = 6  # 6 AM


# Helper Functions

def send_color_array(color_array):
    """
    Send color data array to LED strip via SPI.

    Args:
        color_array: List of RGB values (flattened, length should be NUM_LEDS * 3)
    """
    spi.xfer2(color_array)


def repeat_color(color, count):
    """
    Repeat a single RGB color for a given number of LEDs.

    Args:
        color: RGB color as [R, G, B]
        count: Number of LEDs to repeat the color for

    Returns:
        Flattened list of RGB values
    """
    return color * count


def create_led_array(color, num_leds):
    """
    Create a full LED array with the same color for all LEDs.

    Args:
        color: RGB color as [R, G, B]
        num_leds: Number of LEDs in the strip

    Returns:
        Flattened list of RGB values for all LEDs
    """
    return repeat_color(color, num_leds)


def calculate_sine_gradient(frequency_r, frequency_g, frequency_b, phase_r, phase_g, phase_b, position):
    """
    Calculate RGB color values using sine wave gradients.

    Args:
        frequency_r: Frequency for red channel
        frequency_g: Frequency for green channel
        frequency_b: Frequency for blue channel
        phase_r: Phase offset for red channel
        phase_g: Phase offset for green channel
        phase_b: Phase offset for blue channel
        position: Current position in the gradient

    Returns:
        RGB color as [R, G, B] with values 0-255
    """
    r = (math.sin(frequency_r * position + phase_r) * 0.5 + 0.5) * 255
    g = (math.sin(frequency_g * position + phase_g) * 0.5 + 0.5) * 255
    b = (math.sin(frequency_b * position + phase_b) * 0.5 + 0.5) * 255
    return [math.floor(r), math.floor(g), math.floor(b)]


def set_led_color(led_array, led_index, color):
    """
    Set a specific LED's color in the flattened array.

    Args:
        led_array: Flattened LED array (will be modified)
        led_index: Index of the LED (0-based)
        color: RGB color as [R, G, B]
    """
    base_index = led_index * 3
    led_array[base_index] = color[0]
    led_array[base_index + 1] = color[1]
    led_array[base_index + 2] = color[2]


def create_wave_pattern(base_color, wave_color, wave_length, position, num_leds):
    """
    Create a wave pattern that moves across the LED strip.

    Args:
        base_color: Background color as [R, G, B]
        wave_color: Wave highlight color as [R, G, B]
        wave_length: Number of LEDs in the wave
        position: Current position of the wave (0 to num_leds)
        num_leds: Total number of LEDs

    Returns:
        Flattened list of RGB values for all LEDs
    """
    led_array = create_led_array(base_color, num_leds)
    for i in range(wave_length):
        led_pos = (position + i) % num_leds
        set_led_color(led_array, led_pos, wave_color)
    return led_array


def create_fading_wave_pattern(base_color, wave_color, fade_length, position, num_leds):
    """
    Create a fading wave pattern that moves across the LED strip.
    The wave has decreasing brightness from front to back.

    Args:
        base_color: Background color as [R, G, B]
        wave_color: Base wave color as [R, G, B] (will be faded)
        fade_length: Number of LEDs in the fading wave
        position: Current position of the wave (0 to num_leds)
        num_leds: Total number of LEDs

    Returns:
        Flattened list of RGB values for all LEDs
    """
    led_array = []

    # Base color before the wave
    led_array.extend(repeat_color(base_color, position))

    # Fading wave with decreasing brightness
    for fade_step in range(fade_length):
        brightness_factor = 1.0 / (((fade_length - fade_step) * 2) + 1)
        faded_color = [
            math.floor(wave_color[0] * brightness_factor),
            math.floor(wave_color[1] * brightness_factor),
            math.floor(wave_color[2] * brightness_factor)
        ]
        led_array.extend(repeat_color(faded_color, 1))

    # Base color after the wave
    remaining_leds = num_leds - position - fade_length
    if remaining_leds > 0:
        led_array.extend(repeat_color(base_color, remaining_leds))

    return led_array

def animate_rotating_colors(iterations):
    """
    Animate a rotating color pattern across a subset of LEDs.
    Cycles through red, green, blue, and magenta colors.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    colors = [
        [255, 0, 0],    # Red
        [0, 255, 0],    # Green
        [0, 0, 255],    # Blue
        [255, 0, 255]   # Magenta
    ]
    num_leds_in_pattern = 40

    for cycle in range(iterations):
        print('animate_rotating_colors', cycle, iterations)
        for led_offset in range(num_leds_in_pattern):
            color_index = ((cycle + led_offset) % len(colors))
            current_color = colors[color_index]
            color_array = repeat_color(current_color, 3)
            send_color_array(color_array)
        time.sleep(0.1)

def animate_solid_color_cycle(iterations):
    """
    Animate by filling all LEDs with a single color, cycling through red, green, and blue.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    colors = [
        [255, 0, 0],   # Red
        [0, 255, 0],   # Green
        [0, 0, 255]    # Blue
    ]
    num_leds = 40

    for cycle in range(iterations):
        print('animate_solid_color_cycle', cycle, iterations)
        current_color = colors[cycle % len(colors)]
        color_array = repeat_color(current_color, num_leds)
        send_color_array(color_array)
        time.sleep(0.1)

def animate_white_wave(iterations):
    """
    Animate a white wave that moves across the LED strip with a fading tail.
    Creates a wave effect with decreasing brightness behind the leading edge.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    WHITE_WAVE_FADE_LENGTH = 10
    BLACK = [0, 0, 0]
    WHITE = [255, 255, 255]

    for cycle in range(iterations):
        print('animate_white_wave', cycle, iterations)
        for wave_position in range(NUM_LEDS):
            led_array = create_fading_wave_pattern(BLACK, WHITE, WHITE_WAVE_FADE_LENGTH,
                                                  wave_position, NUM_LEDS)
            send_color_array(led_array)
            time.sleep(0.01)

def animate_orange_wave(iterations):
    """
    Animate an orange wave that moves across the LED strip.
    Uses the favorite orange color as background with a bright orange wave.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    WAVE_COLOR = [255, 50, 3]  # Bright orange highlight
    WAVE_LENGTH = 15
    WAVE_DELAY = 0.05

    for cycle in range(iterations):
        print('animate_orange_wave', cycle, iterations)
        for wave_position in range(NUM_LEDS):
            led_array = create_wave_pattern(FAVORITE_COLOR, WAVE_COLOR, WAVE_LENGTH,
                                          wave_position, NUM_LEDS)
            send_color_array(led_array)
            time.sleep(WAVE_DELAY)


def animate_gradient_wave(iterations):
    """
    Animate a smooth gradient wave that cycles through colors using sine wave functions.
    Creates a flowing color effect across all LEDs.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    GRADIENT_STEPS = 418
    GRADIENT_SPEED = 0.1
    FREQUENCY = 0.3
    PHASE_R = 0
    PHASE_G = 2
    PHASE_B = 3

    for cycle in range(iterations):
        for step in range(GRADIENT_STEPS):
            position = step * GRADIENT_SPEED
            color = calculate_sine_gradient(FREQUENCY, FREQUENCY, FREQUENCY,
                                           PHASE_R, PHASE_G, PHASE_B, position)
            color_array = repeat_color(color, NUM_LEDS)
            send_color_array(color_array)
            time.sleep(0.1)

def animate_gradient_wave_no_blue(iterations):
    """
    Animate a smooth gradient wave without blue channel (red and green only).
    Creates a warm color effect across all LEDs.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    GRADIENT_STEPS = 418
    GRADIENT_SPEED = 0.1
    FREQUENCY = 0.3
    PHASE_R = 0
    PHASE_G = 2
    PHASE_B = 3

    for cycle in range(iterations):
        for step in range(GRADIENT_STEPS):
            position = step * GRADIENT_SPEED
            color = calculate_sine_gradient(FREQUENCY, FREQUENCY, FREQUENCY,
                                           PHASE_R, PHASE_G, PHASE_B, position)
            color[2] = 0  # Remove blue channel
            color_array = repeat_color(color, NUM_LEDS)
            send_color_array(color_array)
            time.sleep(0.1)

def animate_sparkle(iterations):
    """
    Animate random sparkles on a background of favorite color.
    Two random LEDs light up with a yellow-white color each frame.

    Args:
        iterations: Number of frames to display
    """
    SPARKLE_COLOR = [200, 200, 80]  # Yellow-white sparkle
    NUM_SPARKLES = 2
    MAX_LED_INDEX = NUM_LEDS - NUM_SPARKLES  # Ensure we don't overflow array

    for frame in range(iterations):
        led_array = create_led_array(FAVORITE_COLOR, NUM_LEDS)

        # Set random LEDs to sparkle color
        for _ in range(NUM_SPARKLES):
            led_index = random.randint(0, MAX_LED_INDEX)
            set_led_color(led_array, led_index, SPARKLE_COLOR)

        send_color_array(led_array)
        time.sleep(0.04)

def animate_slow_sparkle(iterations):
    """
    Animate slow, occasional sparkles on a background of favorite color.
    Sparkles appear infrequently with longer pauses between frames.

    Args:
        iterations: Number of frames to display
    """
    SPARKLE_COLOR = [180, 180, 180]  # White sparkle
    SPARKLE_FREQUENCY = 100  # Sparkle every N frames
    MAX_LED_INDEX = NUM_LEDS - 1
    FRAME_DELAY = 0.05
    PAUSE_DELAY = 2.0

    for frame in range(iterations):
        led_array = create_led_array(FAVORITE_COLOR, NUM_LEDS)

        # Occasionally add a sparkle
        if frame % SPARKLE_FREQUENCY == 0:
            led_index = random.randint(0, MAX_LED_INDEX)
            set_led_color(led_array, led_index, SPARKLE_COLOR)

        send_color_array(led_array)
        time.sleep(FRAME_DELAY)

        # Return to base color with longer pause
        led_array = create_led_array(FAVORITE_COLOR, NUM_LEDS)
        send_color_array(led_array)
        time.sleep(PAUSE_DELAY)

def animate_random_colors(iterations):
    """
    Animate random colors for each LED independently.
    Each LED gets a random RGB value each frame.

    Args:
        iterations: Number of frames to display
    """
    num_color_values = NUM_LEDS * 3  # RGB values for all LEDs

    for frame in range(iterations):
        color_array = [random.randint(0, 255) for _ in range(num_color_values)]
        send_color_array(color_array)
        time.sleep(0.5)

def animate_color_chase(iterations):
    """
    Animate a color chase pattern with red, green, and cyan colors separated by black.
    Creates a moving pattern effect across the LED strip.

    Args:
        iterations: Number of times to repeat the animation cycle
    """
    # Pattern: Red, 2x Black, Green, 2x Black, Cyan, 2x Black (repeating)
    color_pattern = [
        255, 0, 0,      # Red
        0, 0, 0,        # Black
        0, 0, 0,        # Black
        0, 255, 0,      # Green
        0, 0, 0,        # Black
        0, 0, 0,        # Black
        0, 255, 255,    # Cyan
        0, 0, 0,        # Black
        0, 0, 0         # Black
    ]

    for cycle in range(iterations):
        print('animate_color_chase', cycle, iterations)
        num_values = NUM_LEDS * 3
        color_array = [color_pattern[(i + (cycle * 3)) % len(color_pattern)]
                       for i in range(num_values)]
        send_color_array(color_array)
        time.sleep(0.5)

def crazy_police(iterations):
    """
    Flash the top half and bottom half of the LED strand separately in red and blue.
    One half rapidly flashes for 1 second, then the other half for 1 second, repeating.

    Args:
        iterations: Number of times to repeat the full cycle (top + bottom)
    """
    RED = [255, 0, 0]
    BLUE = [0, 0, 255]
    BLACK = [0, 0, 0]
    FLASH_DURATION = 1.0  # seconds
    FLASH_RATE = 0.1  # seconds between flashes

    HALF_LED_COUNT = NUM_LEDS // 2
    TOP_HALF_START = 0
    TOP_HALF_END = HALF_LED_COUNT
    BOTTOM_HALF_START = HALF_LED_COUNT
    BOTTOM_HALF_END = NUM_LEDS

    for cycle in range(iterations):
        # Flash top half (red) for 1 second
        flash_count = int(FLASH_DURATION / FLASH_RATE)
        for flash in range(flash_count):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Set top half to red
            for led_index in range(TOP_HALF_START, TOP_HALF_END):
                set_led_color(led_array, led_index, RED)

            send_color_array(led_array)
            time.sleep(FLASH_RATE)

            # Turn off
            led_array = create_led_array(BLACK, NUM_LEDS)
            send_color_array(led_array)
            time.sleep(FLASH_RATE)

        # Flash bottom half (blue) for 1 second
        for flash in range(flash_count):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Set bottom half to blue
            for led_index in range(BOTTOM_HALF_START, BOTTOM_HALF_END):
                set_led_color(led_array, led_index, BLUE)

            send_color_array(led_array)
            time.sleep(FLASH_RATE)

            # Turn off
            led_array = create_led_array(BLACK, NUM_LEDS)
            send_color_array(led_array)
            time.sleep(FLASH_RATE)


def crazy_strobe(iterations):
    """
    Divide the LED strand into 10 segments and violently flash 3 segments at a time
    in a strobe-like fashion for 500ms, then switch to different segments.

    Args:
        iterations: Number of times to repeat the strobe cycle
    """
    NUM_SEGMENTS = 10
    SEGMENT_SIZE = NUM_LEDS // NUM_SEGMENTS
    SEGMENTS_TO_FLASH = 3
    STROBE_DURATION = 0.5  # seconds
    STROBE_RATE = 0.05  # seconds between strobe flashes
    WHITE = [255, 255, 255]
    BLACK = [0, 0, 0]

    flash_count = int(STROBE_DURATION / STROBE_RATE)

    for cycle in range(iterations):
        # Select 3 random segments to flash
        segments_to_light = random.sample(range(NUM_SEGMENTS), SEGMENTS_TO_FLASH)

        for flash in range(flash_count):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Flash the selected segments
            for segment_index in segments_to_light:
                segment_start = segment_index * SEGMENT_SIZE
                segment_end = min(segment_start + SEGMENT_SIZE, NUM_LEDS)

                for led_index in range(segment_start, segment_end):
                    set_led_color(led_array, led_index, WHITE)

            send_color_array(led_array)
            time.sleep(STROBE_RATE)

            # Turn off
            led_array = create_led_array(BLACK, NUM_LEDS)
            send_color_array(led_array)
            time.sleep(STROBE_RATE)


def crazy_race(iterations):
    """
    Two colors race from opposite ends of the strand, meeting in the middle.
    Creates a high-speed collision effect with rapid color changes.

    Args:
        iterations: Number of times to repeat the race cycle
    """
    RED = [255, 0, 0]
    BLUE = [0, 0, 255]
    BLACK = [0, 0, 0]
    RACE_SPEED = 0.03  # seconds per LED position
    FLASH_DELAY = 0.08  # delay to allow LEDs to turn off

    for cycle in range(iterations):
        # Race from both ends to the middle
        for position in range(NUM_LEDS // 2 + 1):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Red from top (LED 0)
            if position < NUM_LEDS:
                set_led_color(led_array, position, RED)

            # Blue from bottom (LED 99)
            bottom_pos = NUM_LEDS - 1 - position
            if bottom_pos >= 0:
                set_led_color(led_array, bottom_pos, BLUE)

            send_color_array(led_array)
            time.sleep(RACE_SPEED)

        # Flash collision in middle
        led_array = create_led_array(BLACK, NUM_LEDS)
        mid_point = NUM_LEDS // 2
        for i in range(-2, 3):
            if 0 <= mid_point + i < NUM_LEDS:
                set_led_color(led_array, mid_point + i, [255, 0, 255])  # Magenta collision
        send_color_array(led_array)
        time.sleep(FLASH_DELAY)

        # Turn off
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        time.sleep(FLASH_DELAY)


def crazy_pulse(iterations):
    """
    Expanding and contracting pulses of color from the center of the strand.
    Multiple pulses overlap creating a chaotic wave effect.

    Args:
        iterations: Number of times to repeat the pulse cycle
    """
    COLORS = [
        [255, 0, 0],      # Red
        [0, 255, 0],      # Green
        [0, 0, 255],      # Blue
        [255, 255, 0],    # Yellow
        [255, 0, 255],    # Magenta
        [0, 255, 255]     # Cyan
    ]
    BLACK = [0, 0, 0]
    PULSE_SPEED = 0.02  # seconds per expansion step
    CENTER = NUM_LEDS // 2
    MAX_RADIUS = NUM_LEDS // 2

    for cycle in range(iterations):
        color = COLORS[cycle % len(COLORS)]

        # Expand from center
        for radius in range(MAX_RADIUS + 1):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Draw expanding circle
            for offset in range(-radius, radius + 1):
                led_pos = CENTER + offset
                if 0 <= led_pos < NUM_LEDS:
                    # Fade brightness based on distance from center
                    distance = abs(offset)
                    brightness = max(0, 255 - (distance * 20))
                    faded_color = [
                        min(255, int(color[0] * brightness / 255)),
                        min(255, int(color[1] * brightness / 255)),
                        min(255, int(color[2] * brightness / 255))
                    ]
                    set_led_color(led_array, led_pos, faded_color)

            send_color_array(led_array)
            time.sleep(PULSE_SPEED)

        # Contract back
        for radius in range(MAX_RADIUS, -1, -1):
            led_array = create_led_array(BLACK, NUM_LEDS)

            for offset in range(-radius, radius + 1):
                led_pos = CENTER + offset
                if 0 <= led_pos < NUM_LEDS:
                    distance = abs(offset)
                    brightness = max(0, 255 - (distance * 20))
                    faded_color = [
                        min(255, int(color[0] * brightness / 255)),
                        min(255, int(color[1] * brightness / 255)),
                        min(255, int(color[2] * brightness / 255))
                    ]
                    set_led_color(led_array, led_pos, faded_color)

            send_color_array(led_array)
            time.sleep(PULSE_SPEED)


def crazy_rainbow_chase(iterations):
    """
    Rapid rainbow colors chasing each other across the strand.
    Multiple color bands move at different speeds creating a chaotic rainbow effect.

    Args:
        iterations: Number of times to repeat the chase cycle
    """
    RAINBOW_COLORS = [
        [255, 0, 0],      # Red
        [255, 127, 0],    # Orange
        [255, 255, 0],    # Yellow
        [0, 255, 0],      # Green
        [0, 0, 255],      # Blue
        [75, 0, 130],      # Indigo
        [148, 0, 211]     # Violet
    ]
    BLACK = [0, 0, 0]
    CHASE_SPEED = 0.04  # seconds per step
    BAND_WIDTH = 8  # LEDs per color band
    NUM_BANDS = 3  # Number of overlapping bands

    for cycle in range(iterations):
        for step in range(NUM_LEDS + BAND_WIDTH * NUM_BANDS):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Draw multiple overlapping bands
            for band in range(NUM_BANDS):
                band_start = step - (band * BAND_WIDTH * 2)
                color_index = (band + cycle) % len(RAINBOW_COLORS)
                color = RAINBOW_COLORS[color_index]

                for i in range(BAND_WIDTH):
                    led_pos = band_start + i
                    if 0 <= led_pos < NUM_LEDS:
                        set_led_color(led_array, led_pos, color)

            send_color_array(led_array)
            time.sleep(CHASE_SPEED)


def crazy_chaos(iterations):
    """
    Random segments flash violently in different colors creating pure chaos.
    Each segment gets a random color and flashes rapidly.

    Args:
        iterations: Number of chaos cycles
    """
    COLORS = [
        [255, 0, 0],      # Red
        [0, 255, 0],      # Green
        [0, 0, 255],      # Blue
        [255, 255, 0],    # Yellow
        [255, 0, 255],    # Magenta
        [0, 255, 255],    # Cyan
        [255, 255, 255]   # White
    ]
    BLACK = [0, 0, 0]
    NUM_SEGMENTS = 20
    SEGMENT_SIZE = NUM_LEDS // NUM_SEGMENTS
    FLASH_DURATION = 0.15  # seconds per flash
    FLASH_RATE = 0.06  # seconds between flashes

    flash_count = int(FLASH_DURATION / FLASH_RATE)

    for cycle in range(iterations):
        # Assign random colors to each segment
        segment_colors = [random.choice(COLORS) for _ in range(NUM_SEGMENTS)]

        for flash in range(flash_count):
            led_array = create_led_array(BLACK, NUM_LEDS)

            # Flash random segments
            segments_to_flash = random.sample(range(NUM_SEGMENTS), NUM_SEGMENTS // 2)

            for segment_index in segments_to_flash:
                segment_start = segment_index * SEGMENT_SIZE
                segment_end = min(segment_start + SEGMENT_SIZE, NUM_LEDS)
                color = segment_colors[segment_index]

                for led_index in range(segment_start, segment_end):
                    set_led_color(led_array, led_index, color)

            send_color_array(led_array)
            time.sleep(FLASH_RATE)

            # Turn off
            led_array = create_led_array(BLACK, NUM_LEDS)
            send_color_array(led_array)
            time.sleep(FLASH_RATE)


def crazy_meteor(iterations):
    """
    Multiple meteors of different colors shoot across the strand simultaneously.
    Each meteor has a bright head and fading tail creating a streaking effect.

    Args:
        iterations: Number of meteor cycles
    """
    METEOR_COLORS = [
        [255, 100, 50],   # Orange
        [100, 255, 255],  # Cyan
        [255, 50, 255],   # Pink
        [50, 255, 100],   # Green
        [255, 255, 100],  # Yellow
        [100, 100, 255]   # Light Blue
    ]
    BLACK = [0, 0, 0]
    NUM_METEORS = 4
    METEOR_LENGTH = 12  # LEDs in meteor tail
    METEOR_SPEED = 0.05  # seconds per position
    FLASH_DELAY = 0.1  # delay between cycles

    for cycle in range(iterations):
        # Create meteors at random starting positions
        meteors = []
        for _ in range(NUM_METEORS):
            start_pos = random.randint(-METEOR_LENGTH, NUM_LEDS)
            color = random.choice(METEOR_COLORS)
            direction = random.choice([1, -1])  # 1 = left to right, -1 = right to left
            meteors.append({
                'pos': start_pos,
                'color': color,
                'direction': direction
            })

        # Animate meteors moving
        for step in range(NUM_LEDS + METEOR_LENGTH):
            led_array = create_led_array(BLACK, NUM_LEDS)

            for meteor in meteors:
                # Update meteor position
                meteor['pos'] += meteor['direction']

                # Draw meteor with fading tail
                for i in range(METEOR_LENGTH):
                    led_pos = meteor['pos'] - (i * meteor['direction'])

                    if 0 <= led_pos < NUM_LEDS:
                        # Fade brightness from head to tail
                        brightness = 1.0 - (i / METEOR_LENGTH)
                        faded_color = [
                            int(meteor['color'][0] * brightness),
                            int(meteor['color'][1] * brightness),
                            int(meteor['color'][2] * brightness)
                        ]
                        set_led_color(led_array, led_pos, faded_color)

            send_color_array(led_array)
            time.sleep(METEOR_SPEED)

        # Brief pause between cycles
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        time.sleep(FLASH_DELAY)


def test_color_comparison():
    """
    Test function to compare two similar orange colors by alternating between them.
    Useful for fine-tuning color values. Runs indefinitely until interrupted.
    """
    color1 = [255, 25, 2]
    color2 = [255, 30, 2]

    while True:
        color_array = create_led_array(color1, NUM_LEDS)
        print(color1)
        send_color_array(color_array)
        time.sleep(1)

        color_array = create_led_array(color2, NUM_LEDS)
        print(color2)
        send_color_array(color_array)
        time.sleep(1)



# Main animation loop
# Different animation sequences run based on time of day
def is_daytime():
    """
    Check if current time is during daytime hours (after 6 AM).

    Returns:
        True if current time is after 6 AM, False otherwise
    """
    now = datetime.datetime.now()
    return now.hour >= DAYTIME_START_HOUR


def run_daytime_animations():
    """Run gentler animations suitable for daytime viewing."""
    if get_current_mode() != 'force_day' and get_current_mode() != 'timemode':
        return
    animate_orange_wave(60)
    if get_current_mode() != 'force_day' and get_current_mode() != 'timemode':
        return
    animate_slow_sparkle(1800)


def run_nighttime_animations():
    """Run more active animations suitable for nighttime viewing."""
    if get_current_mode() != 'force_night' and get_current_mode() != 'timemode':
        return
    animate_white_wave(60)
    if get_current_mode() != 'force_night' and get_current_mode() != 'timemode':
        return
    animate_sparkle(1800)
    if get_current_mode() != 'force_night' and get_current_mode() != 'timemode':
        return
    animate_random_colors(400)
    if get_current_mode() != 'force_night' and get_current_mode() != 'timemode':
        return
    animate_gradient_wave_no_blue(8)
    if get_current_mode() != 'force_night' and get_current_mode() != 'timemode':
        return
    animate_sparkle(1000)


def animate_crazy_mode(iterations):
    """
    Cycle through all crazy animation patterns in sequence.
    Creates an intense, chaotic light show.
    Checks mode periodically to allow interruption.

    Args:
        iterations: Number of times to cycle through all crazy animations
    """
    animations = [
        (crazy_police, 5),
        (crazy_strobe, 10),
        (crazy_race, 8),
        (crazy_pulse, 6),
        (crazy_rainbow_chase, 5),
        (crazy_chaos, 8),
        (crazy_meteor, 6)
    ]

    for cycle in range(iterations):
        # Check mode before each cycle
        if get_current_mode() != 'force_crazy':
            logger.info("Mode changed, interrupting crazy mode animation")
            break

        for anim_func, anim_iterations in animations:
            # Check mode before each animation
            if get_current_mode() != 'force_crazy':
                logger.info("Mode changed, interrupting crazy mode animation")
                return
            anim_func(anim_iterations)

# Thread-safe mode management
_mode_lock = threading.Lock()
_current_mode = 'timemode'  # available modes: timemode, force_night, force_day, force_crazy

def get_current_mode():
    """Get the current animation mode in a thread-safe manner."""
    with _mode_lock:
        return _current_mode

def set_current_mode(mode):
    """Set the current animation mode in a thread-safe manner.

    Args:
        mode: Mode string to set. If invalid, defaults to 'timemode'.

    Returns:
        True if mode was set, False if defaulted to 'timemode'
    """
    global _current_mode
    valid_modes = ['timemode', 'force_night', 'force_day', 'force_crazy']
    if mode in valid_modes:
        with _mode_lock:
            _current_mode = mode
        return True
    else:
        # Default to timemode if invalid mode provided
        with _mode_lock:
            _current_mode = 'timemode'
        logger.warning(f"Invalid mode '{mode}' provided, defaulting to 'timemode'")
        return False


# Flask web server
app = Flask(__name__)

@app.route('/')
def index():
    """Serve the main web interface."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Christmas Tree LED Control</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }

            .container {
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                max-width: 600px;
                width: 100%;
            }

            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 10px;
                font-size: 28px;
                font-weight: 600;
            }

            .status {
                text-align: center;
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
            }

            .status .current-mode {
                font-weight: 600;
                color: #667eea;
            }

            .buttons {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 20px;
            }

            .mode-button {
                padding: 25px 20px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                text-transform: capitalize;
                color: white;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                position: relative;
                overflow: hidden;
            }

            .mode-button::before {
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                width: 0;
                height: 0;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.3);
                transform: translate(-50%, -50%);
                transition: width 0.6s, height 0.6s;
            }

            .mode-button:hover::before {
                width: 300px;
                height: 300px;
            }

            .mode-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
            }

            .mode-button:active {
                transform: translateY(0);
            }

            .mode-button.active {
                box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.8), 0 4px 15px rgba(0, 0, 0, 0.3);
                transform: scale(1.05);
            }

            .mode-button.timemode {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }

            .mode-button.force_night {
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            }

            .mode-button.force_day {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            }

            .mode-button.force_crazy {
                background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
            }

            .mode-button.timemode:hover {
                background: linear-gradient(135deg, #5568d3 0%, #653a8f 100%);
            }

            .mode-button.force_night:hover {
                background: linear-gradient(135deg, #1a2f5f 0%, #254785 100%);
            }

            .mode-button.force_day:hover {
                background: linear-gradient(135deg, #e081e8 0%, #f24459 100%);
            }

            .mode-button.force_crazy:hover {
                background: linear-gradient(135deg, #f85d87 0%, #fdd02d 100%);
            }

            @media (max-width: 600px) {
                .buttons {
                    grid-template-columns: 1fr;
                }

                .container {
                    padding: 30px 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎄 LED Control</h1>
            <div class="status">
                Current Mode: <span class="current-mode" id="current-mode">Loading...</span>
            </div>
            <div class="buttons">
                <button class="mode-button timemode" onclick="setMode('timemode')">Time Mode</button>
                <button class="mode-button force_night" onclick="setMode('force_night')">Force Night</button>
                <button class="mode-button force_day" onclick="setMode('force_day')">Force Day</button>
                <button class="mode-button force_crazy" onclick="setMode('force_crazy')">Force Crazy</button>
            </div>
        </div>

        <script>
            function updateCurrentMode() {
                fetch('/api/mode')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('current-mode').textContent = data.mode.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                        updateActiveButton(data.mode);
                    })
                    .catch(error => {
                        console.error('Error fetching mode:', error);
                    });
            }

            function updateActiveButton(mode) {
                document.querySelectorAll('.mode-button').forEach(button => {
                    button.classList.remove('active');
                    if (button.classList.contains(mode)) {
                        button.classList.add('active');
                    }
                });
            }

            function setMode(mode) {
                fetch('/api/mode', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ mode: mode })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateCurrentMode();
                    } else {
                        alert('Error: ' + (data.error || 'Failed to set mode'));
                    }
                })
                .catch(error => {
                    console.error('Error setting mode:', error);
                    alert('Error setting mode');
                });
            }

            // Update mode on page load
            updateCurrentMode();

            // Auto-refresh current mode every 2 seconds
            setInterval(updateCurrentMode, 2000);
        </script>
    </body>
    </html>
    """
    return html

@app.route('/api/mode', methods=['GET'])
def get_mode():
    """Get the current animation mode."""
    return jsonify({'mode': get_current_mode()})

@app.route('/api/mode', methods=['POST'])
def set_mode():
    """Set the animation mode."""
    # Validate Content-Type
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400

    # Handle JSON parsing errors
    try:
        data = request.get_json()
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Validate data exists
    if data is None:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    # Get mode with default handling
    mode = data.get('mode')
    if mode is None:
        logger.warning("No mode provided in request, defaulting to 'timemode'")
        set_current_mode('timemode')  # This will set to timemode
        return jsonify({'success': True, 'mode': get_current_mode(), 'message': 'Defaulted to timemode'})

    # Set mode (will default to timemode if invalid)
    was_valid = set_current_mode(mode)
    current_mode = get_current_mode()

    if was_valid:
        logger.info(f"Mode changed to: {current_mode}")
        return jsonify({'success': True, 'mode': current_mode})
    else:
        # Mode was invalid, but set_current_mode already defaulted to timemode
        return jsonify({
            'success': True,
            'mode': current_mode,
            'message': f"Invalid mode provided, defaulted to '{current_mode}'"
        })

def start_web_server():
    """Start the Flask web server in a separate thread."""
    try:
        logger.info("Starting web server on port 80...")
        app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            logger.error(f"Port 80 is already in use. Error: {e}")
        elif e.errno == 13:  # Permission denied
            logger.error(f"Permission denied to bind to port 80. Run with sudo. Error: {e}")
        else:
            logger.error(f"Failed to start web server: {e}")
    except Exception as e:
        logger.error(f"Unexpected error starting web server: {e}")

# Global reference to web thread for graceful shutdown
web_thread = None

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    # Flask server will stop when main thread exits (daemon thread)
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Start web server in background thread
try:
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    # Give the server a moment to start
    time.sleep(0.5)
    logger.info("Web server thread started")
except Exception as e:
    logger.error(f"Failed to start web server thread: {e}")

while True:
    mode = get_current_mode()

    if mode == 'timemode':
        # this is time modes
        if is_daytime():
            run_daytime_animations()
        else:
            run_nighttime_animations()

    elif mode == 'force_night':
        run_nighttime_animations()
    elif mode == 'force_day':
        run_daytime_animations()
    elif mode == 'force_crazy':
        animate_crazy_mode(1000)
