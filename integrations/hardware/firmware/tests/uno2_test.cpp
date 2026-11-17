#include <Arduino.h>
#include "firmware_prototypes.h"
#include "../Uno2_RFID_Door/Uno2_RFID_Door.ino"
#include <cassert>
#include <iostream>
#include <vector>

TestSerial Serial;
TestEEPROM EEPROM;
unsigned long fake_millis = 5000;
int fake_pwm = -1;

bool matchesCode(const char *input) {
  std::vector<char> writable(input, input + std::strlen(input) + 1);
  return matchesAccessCode(writable.data());
}

int main() {
  setup();
  assert(matchesCode("1234"));
  assert(matchesCode("PIN 1234"));
  char new_pin[] = "0077";
  assert(executeDnb("GARAGE_PIN", new_pin, fake_millis) == nullptr);
  assert(!matchesCode("1234"));
  assert(matchesCode("0077"));
  assert(matchesCode("pin 0077"));
  assert(matchesCode("CODE 0077"));
  char invalid[] = "00778";
  assert(executeDnb("GARAGE_PIN", invalid, fake_millis) != nullptr);
  DnbPin rebooted("1234");
  rebooted.begin();
  assert(rebooted.matches("0077"));

  Serial.output.clear();
  rfid.uid.size = 4;
  loop();
  assert(doorMoving);
  assert(currentDoorAngle == DOOR_CLOSED_ANGLE);
  assert(Serial.output.find("rfid_granted") != std::string::npos);
  assert(Serial.output.find("04A12B00") == std::string::npos);
  assert(Serial.output.find("\"uid\"") == std::string::npos);
  closeDoor(fake_millis);
  doorMoving = false;
  doorIsOpen = false;
  Serial.output.clear();
  rfid.read_ok = false;
  fake_millis += 2001;
  handleRfidAccess(fake_millis);
  assert(!doorIsOpen && !doorMoving);
  assert(Serial.output.find("rfid_denied") != std::string::npos);
  assert(Serial.output.find("\"uid\"") == std::string::npos);
  rfid.read_ok = true;
  rfid.uid.size = 11;
  Serial.output.clear();
  fake_millis += 2001;
  handleRfidAccess(fake_millis);
  assert(!doorIsOpen && !doorMoving);
  assert(Serial.output.find("rfid_denied") != std::string::npos);
  Serial.output.clear();
  printHelp();
  printDnbState();
  assert(Serial.output.find("0077") == std::string::npos);
  assert(Serial.output.find("1234") == std::string::npos);
  std::cout << "Actual UNO2 PIN and valid-card access without card identifiers passed\n";
}
