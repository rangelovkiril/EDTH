// Seeed XIAO ESP32S3 Sense + camera expansion board.
// USB Mode: Hardware CDC and JTAG. USB CDC On Boot: Enabled. PSRAM: OPI.
#include <Arduino.h>
#include "esp_camera.h"
#include "esp_timer.h"
#include "driver/usb_serial_jtag.h"

#if !ARDUINO_USB_CDC_ON_BOOT
#error "Enable USB CDC On Boot. XIAO ESP32S3 Arduino 3.3.8 uses CDCOnBoot=default for Enabled."
#endif
#if ARDUINO_USB_MODE != 1
#error "Select Hardware CDC and JTAG (USBMode=hwcdc)."
#endif

static uint32_t sequence = 0;
static bool ready = false;

uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t crc = 0xffffffff;
  for (size_t i = 0; i < size; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
  }
  return ~crc;
}

bool sendAll(const uint8_t *data, size_t length) {
  const uint32_t started = millis();
  while (length && millis() - started < 3000) {
    // Each enqueue must fit inside the driver's ring buffer.
    int sent = usb_serial_jtag_write_bytes(data, min(length, size_t(1024)), pdMS_TO_TICKS(100));
    if (sent > 0) { data += sent; length -= sent; }
    else delay(1);
  }
  return length == 0;
}

bool readAll(uint8_t *data, size_t length) {
  const uint32_t started = millis();
  while (length && millis() - started < 100) {
    int count = usb_serial_jtag_read_bytes(data, length, pdMS_TO_TICKS(10));
    if (count > 0) { data += count; length -= count; }
  }
  return length == 0;
}

void setup() {
  // Use the ESP-IDF driver directly: Arduino 3.3.8 HWCDC dropped 64-byte
  // packets during sustained JPEG tests. Do not call Serial.begin(), which
  // would attach a competing interrupt handler to the same peripheral.
  usb_serial_jtag_driver_config_t usb = {8192, 256};
  ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = 15; c.pin_d1 = 17; c.pin_d2 = 18; c.pin_d3 = 16;
  c.pin_d4 = 14; c.pin_d5 = 12; c.pin_d6 = 11; c.pin_d7 = 48;
  c.pin_xclk = 10; c.pin_pclk = 13; c.pin_vsync = 38; c.pin_href = 47;
  c.pin_sccb_sda = 40; c.pin_sccb_scl = 39;
  c.pin_pwdn = -1; c.pin_reset = -1;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_VGA;
  c.jpeg_quality = 12;
  c.fb_count = psramFound() ? 2 : 1;
  c.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  ready = esp_camera_init(&c) == ESP_OK;
}

void loop() {
  uint8_t command;
  if (usb_serial_jtag_read_bytes(&command, 1, pdMS_TO_TICKS(10)) != 1) return;
  if (command == 'T') {
    // Host brackets this reply with its monotonic clock to estimate boot-clock offset.
    uint32_t nonce;
    if (!readAll(reinterpret_cast<uint8_t *>(&nonce), 4)) return;
    uint8_t reply[20];
    memcpy(reply, "SKYTIME2", 8);
    memcpy(reply + 8, &nonce, 4);
    uint64_t timestamp = esp_timer_get_time();
    memcpy(reply + 12, &timestamp, 8);
    sendAll(reply, sizeof(reply));
    return;
  }
  if (command != 'F') return;
  if (!ready) {
    const char *error = "CAMERA_INIT_FAILED: check Sense module and OPI PSRAM\n";
    sendAll(reinterpret_cast<const uint8_t *>(error), strlen(error));
    return;
  }
  // Continuous capture keeps a recent frame ready. Its DMA timestamp identifies
  // the actual acquisition time, independently of when the host polls it.
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return;
  uint8_t header[28];
  memcpy(header, "SKYCAM01", 8);
  uint32_t size = fb->len;
  uint64_t capture_us = uint64_t(fb->timestamp.tv_sec) * 1000000ULL + fb->timestamp.tv_usec;
  uint32_t checksum = crc32(fb->buf, fb->len);
  ++sequence;
  // ESP32 is little endian; wire format matches Python <IIQI.
  memcpy(header + 8, &size, 4);
  memcpy(header + 12, &sequence, 4);
  memcpy(header + 16, &capture_us, 8);
  memcpy(header + 24, &checksum, 4);
  if (sendAll(header, sizeof(header))) sendAll(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}
