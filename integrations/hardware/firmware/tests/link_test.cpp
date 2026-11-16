#include <DnbLink.h>
#include <cassert>
#include <cmath>
#include <iostream>

TestSerial Serial;
int executions = 0;
int legacy_calls = 0;
int states = 0;

const char *execute(const char *, char *args, unsigned long) {
  ++executions;
  // Firmware parsers can split args in place. Retried frames must still dedupe.
  if (args && std::strchr(args, ' ')) *std::strchr(args, ' ') = '\0';
  return nullptr;
}
void legacy(char *, unsigned long) { ++legacy_calls; }
void state() { ++states; }
void feed(const std::string &input, unsigned long now) {
  Serial.feed(input);
  while (Serial.available()) DnbLink::poll(now, F("UNO1"), execute, state, legacy);
}

int main() {
  float number = 0;
  for (const char *valid : {"30", "28.0", "-20.0", "0.1", "80.0"})
    assert(DnbLink::decimal(valid, number));
  assert(DnbLink::decimal("-19.9", number) && std::fabs(number + 19.9f) < 0.001f);
  for (const char *invalid : {"", "-", ".5", "1.", "1.23", "nan", "inf", "1e2", " 2", "2 ", "1001", "9999999999999"})
    assert(!DnbLink::decimal(invalid, number));

  const std::string id = "00112233445566778899aabbccddeeff";
  const std::string command = "DNB1 " + id + " TEMP_LIMITS 30.0 28.0\n";
  feed(command, 10);
  assert(executions == 1 && states == 1);
  feed(command, 20);
  assert(executions == 1);
  feed("DNB1 " + id + " TEMP_LIMITS 32.0 28.0\n", 30);
  assert(executions == 1 && Serial.output.find("id_conflict") != std::string::npos);

  feed("DNB1 invalid DOOR_OPEN\n", 40);
  feed("DNB1 FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF DOOR_OPEN\n", 40);
  feed(std::string(100, 'X') + "\n", 40);
  feed(std::string("OPEN") + char(1) + "\n", 40);
  assert(executions == 1 && legacy_calls == 0);
  feed("DNB1 " + id + " DOOR_OPEN", 50);
  DnbLink::poll(900, F("UNO1"), execute, state, legacy);
  assert(executions == 1 && legacy_calls == 0);
  feed("STATUS", 1000);
  DnbLink::poll(1800, F("UNO1"), execute, state, legacy);
  assert(legacy_calls == 1);
  feed("ID\nSTATE\n", 2000);
  assert(states == 2 && Serial.output.find("\"protocol\":1") != std::string::npos);

  Serial.output.clear();
  DnbLink::event(F("UNO1"), F("voice"), 4);
  assert(Serial.output.find("\"command\":4") != std::string::npos);
  Serial.output.clear();
  DnbLink::event(F("UNO2"), F("rfid_denied"));
  assert(Serial.output.find("uid") == std::string::npos);
  DnbLink::event(F("UNO2"), F("rfid_granted"), 0, "04A12B00");
  assert(Serial.output.find("\"uid\":\"04A12B00\"") != std::string::npos);
  std::cout << "Protocol framing, dedupe, numeric parsing and event checks passed\n";
}
