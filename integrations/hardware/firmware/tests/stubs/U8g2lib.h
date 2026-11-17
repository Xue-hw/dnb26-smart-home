#pragma once
#include <Arduino.h>
#define U8G2_R0 0
#define U8X8_PIN_NONE 255
static const byte u8g2_font_6x10_tr[] = {0};
static const byte u8g2_font_logisoso24_tn[] = {0};
class U8G2_SSD1306_128X64_NONAME_1_4W_HW_SPI {
public:
  U8G2_SSD1306_128X64_NONAME_1_4W_HW_SPI(byte, byte, byte, byte) {}
  void setBusClock(unsigned long) {}
  void begin() {}
  void setContrast(byte) {}
  void firstPage() {}
  bool nextPage() { return false; }
  void setFont(const byte *) {}
  void drawStr(int, int, const char *) {}
  void setCursor(int, int) {}
  template <typename T> void print(T) {}
  template <typename T> void print(T, int) {}
};
