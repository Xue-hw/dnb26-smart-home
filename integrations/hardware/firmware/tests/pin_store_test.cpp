#include <DnbPin.h>
#include <cassert>
#include <iostream>

TestSerial Serial;
TestEEPROM EEPROM;

int main() {
  for (const char *invalid : {"", "123", "12345", "12a4", " 123", "+123"})
    assert(!DnbPin::valid(invalid));
  assert(!DnbPin::valid(nullptr));
  assert(DnbPin::valid("0000"));

  DnbPin initial("4321");
  initial.begin();
  assert(initial.matches("4321"));
  assert(!initial.save("12345"));
  assert(initial.save("0078"));
  DnbPin rebooted("4321");
  rebooted.begin();
  assert(rebooted.matches("0078"));
  assert(!rebooted.matches("4321"));
  const auto old_bytes = EEPROM.bytes;

  // Interrupt every byte update, including invalidation and final commit.
  for (int cutoff = 0; cutoff <= 9; ++cutoff) {
    EEPROM.bytes = old_bytes;
    EEPROM.writes = 0;
    EEPROM.fail_after = -1;
    DnbPin before("4321");
    before.begin();
    EEPROM.fail_after = cutoff;
    try { before.save("9988"); } catch (const std::runtime_error &) {}
    EEPROM.fail_after = -1;
    DnbPin after("4321");
    after.begin();
    assert(after.matches(cutoff < 9 ? "0078" : "9988"));
  }

  // A CRC-invalid newest record falls back to the previous committed record.
  EEPROM.bytes = old_bytes;
  DnbPin changing("4321");
  changing.begin();
  assert(changing.save("9988"));
  EEPROM.bytes[8 + 3] ^= 1;
  DnbPin corrupted("4321");
  corrupted.begin();
  assert(corrupted.matches("0078"));

  // Version mismatch cannot turn arbitrary bytes into a PIN.
  EEPROM.bytes.fill(0);
  DnbPin invalid_version("4321");
  invalid_version.begin();
  assert(invalid_version.matches("4321"));

  EEPROM.reset();
  DnbPin rolling("4321");
  rolling.begin();
  for (int iteration = 0; iteration < 300; ++iteration) {
    const char *pin = iteration % 2 ? "2222" : "1111";
    assert(rolling.save(pin));
    DnbPin check("4321");
    check.begin();
    assert(check.matches(pin));
  }
  int previous_writes = EEPROM.writes;
  assert(rolling.save("2222"));
  assert(EEPROM.writes == previous_writes);
  std::cout << "PIN persistence, corruption, power-loss and rollover checks passed\n";
}
