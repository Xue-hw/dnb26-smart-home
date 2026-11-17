#pragma once
#include <Arduino.h>
#include <array>
#define NEO_GRB 0
#define NEO_KHZ800 0
class Adafruit_NeoPixel {
public:
  std::array<unsigned long, 8> pixels{};
  byte brightness = 0;
  Adafruit_NeoPixel(byte, byte, int) {}
  void begin() {}
  void clear() { pixels.fill(0); }
  static unsigned long Color(byte red, byte green, byte blue) {
    return (static_cast<unsigned long>(red) << 16) | (green << 8) | blue;
  }
  void setPixelColor(byte index, unsigned long value) { pixels.at(index) = value; }
  void show() {}
  void setBrightness(byte value) { brightness = value; }
};
