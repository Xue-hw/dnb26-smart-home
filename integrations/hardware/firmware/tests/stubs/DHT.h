#pragma once
#include <Arduino.h>
#define DHT11 11
class DHT {
public:
  DHT(byte, int) {}
  void begin() {}
  float readHumidity() { return 45; }
  float readTemperature() { return 26; }
};
