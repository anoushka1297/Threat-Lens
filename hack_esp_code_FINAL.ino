#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

#include "idk.h"


unsigned long lastCaptureMs = 0;
int frameCount = 0;
const int MAX_FRAMES = 5;   // stop after this many


#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27

#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22


void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("Connected. IP address: ");
  Serial.println(WiFi.localIP());
}

bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = CAMERA_FRAME_SIZE;
  config.jpeg_quality = CAMERA_JPEG_QUALITY;
  config.fb_count = 1;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  sensor->set_framesize(sensor, CAMERA_FRAME_SIZE);
  return true;
}

bool postFrame(camera_fb_t *frame) {
  HTTPClient http;

  // HTTPClient takes the full URL directly — no manual parsing needed
  http.begin(SERVER_UPLOAD_URL);

  // Set headers
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Id", DEVICE_ID);

  // POST the raw JPEG bytes — HTTPClient handles Content-Length,
  // the connection, and cleanup internally
  int statusCode = http.POST(frame->buf, frame->len);

  if (statusCode > 0) {
    Serial.printf("Server response: %d\n", statusCode);
    http.end();  // properly closes and frees the connection
    return statusCode == 200;
  } else {
    // Negative codes are connection-level errors
    Serial.printf("POST failed: %s\n", http.errorToString(statusCode).c_str());
    http.end();
    return false;
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println();

  connectWiFi();
  Serial.println("Uploading to: " SERVER_UPLOAD_URL);

  if (!initCamera()) {
    Serial.println("Camera setup failed. Restarting.");
    delay(3000);
    ESP.restart();
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // Stop capturing once we've sent enough frames
  if (frameCount >= MAX_FRAMES) {
    delay(1000);
    return;   // do nothing, just idle
  }

  unsigned long now = millis();
  if (now - lastCaptureMs < CAPTURE_INTERVAL_MS) {
    delay(50);
    return;
  }
  lastCaptureMs = now;

  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) {
    Serial.println("Camera capture failed.");
    return;
  }

  Serial.printf("Captured %u bytes\n", static_cast<unsigned int>(frame->len));
  bool uploaded = postFrame(frame);
  Serial.println(uploaded ? "Upload OK" : "Upload failed");

  // Only count successful uploads so a failed one doesn't waste your quota
  if (uploaded) {
    frameCount++;
    Serial.printf("Frame %d of %d sent\n", frameCount, MAX_FRAMES);
  }

  esp_camera_fb_return(frame);
}