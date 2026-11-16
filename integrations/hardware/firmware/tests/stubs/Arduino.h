#pragma once
#include <cstdint>
#include <cstring>
#include <sstream>
#include <string>
#include <iomanip>

typedef unsigned char byte;
class __FlashStringHelper;
#define F(value) reinterpret_cast<const __FlashStringHelper *>(value)
typedef const char *PGM_P;
#define strcmp_P std::strcmp
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT 0
#define INPUT_PULLUP 2
#define CHANGE 3
#define HEX 16
const byte A0 = 14, A1 = 15, A2 = 16, A3 = 17, A4 = 18, A5 = 19;
extern unsigned long fake_millis;
extern int fake_pwm;
inline unsigned long millis() { return fake_millis; }
inline unsigned long micros() { return fake_millis * 1000; }
inline void pinMode(byte, byte) {}
inline void digitalWrite(byte, int) {}
inline int digitalRead(byte) { return HIGH; }
inline int analogRead(byte) { return 900; }
inline void analogWrite(byte, int value) { fake_pwm = value; }
inline void delay(unsigned long duration) { fake_millis += duration; }
inline void delayMicroseconds(unsigned int) {}
inline void attachInterrupt(byte, void (*)(), int) {}
inline byte digitalPinToInterrupt(byte pin) { return pin; }
inline void interrupts() {}
inline void noInterrupts() {}
inline long map(long value, long in_low, long in_high, long out_low, long out_high) {
  return (value - in_low) * (out_high - out_low) / (in_high - in_low) + out_low;
}
template <typename T> T constrain(T value, T low, T high) {
  return value < low ? low : value > high ? high : value;
}

struct TestSerial {
  std::string input;
  std::string output;
  std::size_t cursor = 0;
  void begin(unsigned long) {}
  int available() const { return static_cast<int>(input.size() - cursor); }
  char read() { return input.at(cursor++); }
  void feed(const std::string &value) { input = value; cursor = 0; }
  void print(const __FlashStringHelper *value) { output += reinterpret_cast<const char *>(value); }
  void print(const char *value) { output += value; }
  void print(char value) { output += value; }
  void print(byte value) { output += std::to_string(value); }
  void print(byte value, int base) {
    std::ostringstream stream;
    if (base == HEX) stream << std::hex << std::uppercase;
    stream << static_cast<unsigned int>(value);
    output += stream.str();
  }
  void print(float value, int precision) {
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(precision) << value;
    output += stream.str();
  }
  void println() { output += '\n'; }
  template <typename T> void println(T value, int base) { print(value, base); output += '\n'; }
  template <typename T> void print(T value) {
    std::ostringstream stream;
    stream << value;
    output += stream.str();
  }
  template <typename T> void println(T value) { print(value); output += '\n'; }
};
extern TestSerial Serial;
