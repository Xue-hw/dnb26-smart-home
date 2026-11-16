#pragma once
#include <Arduino.h>
#include <array>
#include <stdexcept>

struct TestEEPROM {
  std::array<byte, 1024> bytes;
  int writes = 0;
  int fail_after = -1;
  TestEEPROM() { reset(); }
  void reset() { bytes.fill(255); writes = 0; fail_after = -1; }
  byte read(int address) const { return bytes.at(address); }
  void update(int address, byte value) {
    if (fail_after == writes) throw std::runtime_error("simulated power loss");
    bytes.at(address) = value;
    ++writes;
  }
};
extern TestEEPROM EEPROM;
