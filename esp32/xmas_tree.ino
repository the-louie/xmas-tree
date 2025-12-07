// Christmas Tree LED Controller for ESP32
// Controls WS2801 RGB LED string via SPI

#include <SPI.h>
#include <math.h>
#include <stdarg.h>

#define LEDCOUNT 100

// Configuration constants
#define SPI_DATA_PIN 23
#define SPI_CLOCK_PIN 18
#define SPI_SPEED 500000

// LED buffer: 3 bytes per LED (RGB)
uint8_t led_buffer[LEDCOUNT * 3];

// Pattern registry - extensible system for adding more patterns
typedef void (*PatternFunc)(unsigned long count);

// Forward declarations
void pattern_colorcycle_no_blue(unsigned long count);
void pattern_blink_random_slow(unsigned long count);

PatternFunc patterns[] = {
  pattern_colorcycle_no_blue,
  pattern_blink_random_slow,
};

const int pattern_count = sizeof(patterns) / sizeof(patterns[0]);
int active_mode = 0;
unsigned long pattern_count_var = 0;
unsigned long mode_start_time = 0;
const unsigned long MODE_SWITCH_INTERVAL = 30000;  // 30 seconds

// Utility functions
void sleep_ms(unsigned long ms) {
  delay(ms);
}

void log(const char* format, ...) {
  if (!Serial) {
    return;  // Serial not initialized
  }
  char buffer[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  Serial.print(millis());
  Serial.print(": ");
  Serial.println(buffer);
}

struct RGB {
  uint8_t r;
  uint8_t g;
  uint8_t b;
};

RGB gradient(float f1, float f2, float f3, float ph1, float ph2, float ph3, float i, float dr = 1.0, float dg = 1.0, float db = 1.0) {
  RGB color;
  float r = (sinf(f1 * i + ph1) * 0.5 + 0.5) * 255.0 * dr;
  float g = (sinf(f2 * i + ph2) * 0.5 + 0.5) * 255.0 * dg;
  float b = (sinf(f3 * i + ph3) * 0.5 + 0.5) * 255.0 * db;

  // Clamp to 0-255 range (Math.max equivalent)
  color.r = (uint8_t)constrain((int)r, 0, 255);
  color.g = (uint8_t)constrain((int)g, 0, 255);
  color.b = (uint8_t)constrain((int)b, 0, 255);

  return color;
}

void leds_connect(int count) {
  // Initialize SPI for WS2801
  // ESP32 uses VSPI by default (pins: CLK=18, MISO=19, MOSI=23, SS=5)
  // For WS2801, we use MOSI (data) and CLK (clock)
  SPI.begin(SPI_CLOCK_PIN, -1, SPI_DATA_PIN, -1);

  // Clear all LEDs
  leds_fill(0, 0, 0);
  leds_update();
}

void leds_setColor(int index, uint8_t r, uint8_t g, uint8_t b) {
  if (index < 0 || index >= LEDCOUNT) {
    return;  // Bounds check
  }

  // WS2801 uses RGB order
  int offset = index * 3;
  led_buffer[offset] = r;
  led_buffer[offset + 1] = g;
  led_buffer[offset + 2] = b;
}

void leds_setColor(int index, uint32_t color) {
  // Extract RGB from 24-bit color value (0xRRGGBB format)
  uint8_t r = (color >> 16) & 0xFF;
  uint8_t g = (color >> 8) & 0xFF;
  uint8_t b = color & 0xFF;
  leds_setColor(index, r, g, b);
}

void leds_fill(uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < LEDCOUNT; i++) {
    leds_setColor(i, r, g, b);
  }
}

void leds_update() {
  // Send all LED data via SPI
  SPI.beginTransaction(SPISettings(SPI_SPEED, MSBFIRST, SPI_MODE0));
  for (int i = 0; i < LEDCOUNT * 3; i++) {
    SPI.transfer(led_buffer[i]);
  }
  SPI.endTransaction();
  // Small delay to ensure data is processed by WS2801
  delayMicroseconds(500);
}

void setup() {
  // Initialize serial for debugging
  Serial.begin(115200);
  delay(1000);
  Serial.println("Christmas Tree LED Controller starting...");

  // Initialize random seed
  randomSeed(analogRead(0));

  // Initialize LEDs
  leds_connect(LEDCOUNT);
  Serial.println("LEDs initialized");

  // Initialize pattern system
  log("Number of modes: %d", pattern_count);
  active_mode = random(0, pattern_count);
  log("Starting mode: %d", active_mode);
  mode_start_time = millis();
}

// Pattern functions
void pattern_colorcycle_no_blue(unsigned long count) {
  for (int j = 0; j < LEDCOUNT; j++) {
    RGB color = gradient(0.3, 0.3, 0.3, 0, 2, 3, (j + count) * 0.1, 1, 1, 0);
    leds_setColor(j, color.r, color.g, color.b);
  }
  sleep_ms(100);
  leds_update();
}

void pattern_blink_random_slow(unsigned long count) {
  // Base fill with orange color (0xFF, 0x19, 0x02)
  leds_fill(0xFF, 0x19, 0x02);

  // Blink 0-2 random LEDs with gray color (0xb4, 0xb4, 0xb4)
  int num_blinks = random(0, 3);  // 0, 1, or 2
  for (int n = 0; n < num_blinks; n++) {
    int led_index = random(0, LEDCOUNT);
    leds_setColor(led_index, 0xb4, 0xb4, 0xb4);
  }

  leds_update();
  sleep_ms(10);

  // Fill with base color again
  leds_fill(0xFF, 0x19, 0x02);
  leds_update();
  sleep_ms(100);
}

void loop() {
  // Call current pattern
  patterns[active_mode](pattern_count_var);
  pattern_count_var++;

  // Check if it's time to switch modes (every 30 seconds)
  unsigned long current_time = millis();
  if (current_time - mode_start_time > MODE_SWITCH_INTERVAL) {
    mode_start_time = current_time;
    active_mode = random(0, pattern_count);
    log("Switched to mode %d", active_mode);
  }
}

