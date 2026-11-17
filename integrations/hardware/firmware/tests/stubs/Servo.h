#pragma once
#include <Arduino.h>
class Servo {
  bool active = false;
public:
  bool attached() const { return active; }
  void attach(byte) { active = true; }
  void detach() { active = false; }
  void write(int) {}
};
