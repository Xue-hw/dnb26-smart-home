#ifndef DNB_PIN_H
#define DNB_PIN_H
#include <Arduino.h>
#include <EEPROM.h>
#include <string.h>

// Alternating records retain the previous PIN if power fails during a write.
class DnbPin {
  static const byte VERSION = 1;
  static const byte COMMITTED = 0xA6;
  byte slot = 1;
  byte generation = 0;
  char value[5];

  static byte checksum(const byte *record) {
    byte crc = 0;
    for (byte i = 1; i < 7; ++i) {
      crc ^= record[i];
      for (byte bit = 0; bit < 8; ++bit)
        crc = (crc & 0x80) ? (byte)((crc << 1) ^ 0x07) : (byte)(crc << 1);
    }
    return crc;
  }

  static bool read(byte index, byte *record) {
    for (byte i = 0; i < 8; ++i) record[i] = EEPROM.read(index * 8 + i);
    if (record[0] != COMMITTED || record[1] != VERSION || record[7] != checksum(record)) return false;
    for (byte i = 3; i < 7; ++i) if (record[i] < '0' || record[i] > '9') return false;
    return true;
  }

public:
  explicit DnbPin(const char *initial) { memcpy(value, initial, 5); }

  static bool valid(const char *pin) {
    if (!pin || strlen(pin) != 4) return false;
    for (byte i = 0; i < 4; ++i) if (pin[i] < '0' || pin[i] > '9') return false;
    return true;
  }

  void begin() {
    byte record[8];
    bool found = false;
    for (byte index = 0; index < 2; ++index) {
      if (read(index, record) && (!found || (byte)(record[2] - generation) < 128)) {
        slot = index;
        generation = record[2];
        memcpy(value, record + 3, 4);
        value[4] = '\0';
        found = true;
      }
    }
  }

  bool matches(const char *pin) const { return pin && strcmp(value, pin) == 0; }

  bool save(const char *pin) {
    if (!valid(pin)) return false;
    if (matches(pin)) return true;
    byte next = slot ^ 1;
    byte record[8] = {COMMITTED, VERSION, (byte)(generation + 1), 0, 0, 0, 0, 0};
    memcpy(record + 3, pin, 4);
    record[7] = checksum(record);
    EEPROM.update(next * 8, 0);
    for (byte i = 1; i < 8; ++i) EEPROM.update(next * 8 + i, record[i]);
    EEPROM.update(next * 8, COMMITTED);
    if (!read(next, record) || memcmp(record + 3, pin, 4)) return false;
    slot = next;
    generation = record[2];
    memcpy(value, pin, 5);
    return true;
  }
};
#endif
