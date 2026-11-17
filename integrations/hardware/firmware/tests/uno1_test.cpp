#include <Arduino.h>
#include "firmware_prototypes.h"
#include "../Uno1_Environment_Garage/Uno1_Environment_Garage.ino"
#include <cassert>
#include <iostream>
#include <vector>

TestSerial Serial;
TestEEPROM EEPROM;
unsigned long fake_millis = 100;
int fake_pwm = -1;

const char *command(const char *opcode, const char *arguments = nullptr) {
  std::vector<char> mutable_args;
  if (arguments) mutable_args.assign(arguments, arguments + std::strlen(arguments) + 1);
  return executeDnb(opcode, arguments ? mutable_args.data() : nullptr, fake_millis);
}

int main() {
  setup();
  assert(voiceEnabled);
  // A reset in the middle of six pulses must not decode the five-pulse tail as open-door.
  for (byte edge = 0; edge < 10; ++edge) {
    fake_millis += 50;
    onAsrPulse();
  }
  fake_millis += ASR_COMMAND_GAP_MS;
  handleAsrCommand(fake_millis);
  assert(lastAsrCommand == 0 && !entranceIsOpen && !voiceWaitingForQuiet);
  assert(!command("BRIGHTNESS", "70"));
  processAsrCommand(4, fake_millis);
  assert(!lampState && asrLampOverrideUntil == fake_millis + 5000);
  const unsigned long existingVoiceDeadline = asrLampOverrideUntil;
  assert(!command("VOICE_OFF") && !voiceEnabled);
  assert(asrLampOverrideUntil == existingVoiceDeadline);
  Serial.output.clear();
  for (byte instruction = 1; instruction <= 6; ++instruction) processAsrCommand(instruction, fake_millis);
  assert(!lampState && !entranceIsOpen);
  assert(Serial.output.find("\"event\":\"voice\"") == std::string::npos);
  fake_millis += 5001;
  updateLightAndLamp(fake_millis);
  assert(lampState && lampBrightnessPercent == 70 && lampMode == LAMP_MANUAL);
  assert(!command("LIGHT_OFF") && !lampState);
  assert(!command("VOICE_ON") && voiceEnabled);
  fake_millis += ASR_COMMAND_GAP_MS;
  handleAsrCommand(fake_millis);
  processAsrCommand(3, fake_millis);
  assert(lampState);
  assert(command("VOICE_OFF", "extra") && voiceEnabled);
  asrEdgeCount = 8;
  assert(!command("VOICE_OFF") && asrEdgeCount == 0);
  assert(!command("VOICE_ON") && asrEdgeCount == 0);
  // A command group that began while disabled cannot resume after enabling.
  fake_millis += ASR_COMMAND_GAP_MS - 1;
  onAsrPulse();
  assert(asrEdgeCount == 0 && voiceWaitingForQuiet);
  handleAsrCommand(fake_millis);
  assert(voiceWaitingForQuiet);
  fake_millis += ASR_COMMAND_GAP_MS;
  handleAsrCommand(fake_millis);
  assert(!voiceWaitingForQuiet);
  printDnbState();
  assert(Serial.output.find("\"voice_enabled\":true") != std::string::npos);
  asrLampOverrideUntil = 0;
  assert(lampCount == 8 && fanSpeedPercent == 40);
  assert(!command("FAN_SPEED", "0") && fanMode == FAN_FORCE_OFF && !fanState);
  assert(!command("FAN_ON") && fanState && fanSpeedPercent == 40 && fake_pwm == 102);
  assert(!command("FAN_SPEED", "60") && fake_pwm == 153);
  setVoiceFanPower(false, fake_millis);
  assert(!fanState);
  fake_millis += 5001;
  updateFan();
  assert(fanState && fanSpeedPercent == 60 && fanMode == FAN_FORCE_ON);

  assert(!command("FAN_SPEED", "0"));
  setVoiceFanPower(true, fake_millis);
  assert(fanState && fanSpeedPercent == 40);
  fake_millis += 1000;
  setVoiceFanPower(false, fake_millis);
  fake_millis += 5001;
  updateFan();
  assert(!fanState && fanSpeedPercent == 0 && fanMode == FAN_FORCE_OFF);
  dhtOk = true;
  temperatureC = 35;
  assert(!command("FAN_AUTO"));
  updateFan();
  assert(fanState && fanSpeedPercent == 40 && fanMode == FAN_AUTO);
  assert(command("FAN_SPEED", "101") && fanSpeedPercent == 40);
  setVoiceFanPower(false, fake_millis);
  assert(!command("FAN_SPEED", "55"));
  fake_millis += 5001;
  updateFan();
  assert(fanState && fanSpeedPercent == 55 && fanMode == FAN_FORCE_ON);

  assert(!command("BRIGHTNESS", "70"));
  for (auto pixel : strip.pixels) assert(pixel == 0xFF9628);
  setVoiceLampPower(false, fake_millis);
  assert(!command("LAMP_RGB", "1 2 3 4") && !lampState);
  fake_millis += 5001;
  updateLightAndLamp(fake_millis);
  assert(lampMode == LAMP_MANUAL && lampState && lampBrightnessPercent == 70);
  for (byte index = 0; index < 8; ++index)
    assert(strip.pixels[index] == (index < 4 ? 0x010203UL : 0));
  assert(command("LAMP_RGB", "255 4 3 9"));
  assert(lampRed == 1 && lampCount == 4);
  assert(!command("LIGHT_AUTO"));
  assert(!command("LAMP_RGB", "255 0 0 8"));
  assert(lampMode == LAMP_AUTO);
  const byte prior_brightness = lampBrightnessPercent;
  assert(!command("LAMP_COLOR", "3 4 5"));
  assert(lampCount == 8 && lampRed == 3 && lampGreen == 4 && lampBlue == 5);
  assert(!command("LAMP_COUNT", "2"));
  assert(lampCount == 2 && lampRed == 3 && lampGreen == 4 && lampBlue == 5);
  assert(lampMode == LAMP_AUTO && lampBrightnessPercent == prior_brightness);
  assert(command("LAMP_COLOR", "6 7 8 4"));
  assert(lampRed == 3 && lampCount == 2);
  assert(command("LAMP_COUNT", "0"));
  assert(command("LAMP_COUNT", "9"));
  assert(!command("LAMP_RGB", "255 0 0 8"));

  // A stale loop timestamp predating the ISR must not split a pulse group.
  const unsigned long old_loop_time = fake_millis;
  lastAsrEdgeAtMs = old_loop_time + 100;
  fake_millis = old_loop_time + 200;
  asrEdgeCount = 4;
  handleAsrCommand(old_loop_time);
  assert(asrEdgeCount == 4);
  fake_millis = lastAsrEdgeAtMs + ASR_COMMAND_GAP_MS;
  handleAsrCommand(old_loop_time);
  assert(asrEdgeCount == 0 && lastAsrCommand == 2);
  assert(asrFanOverrideUntil == fake_millis + ASR_FAN_OVERRIDE_MS);

  Serial.output.clear();
  assert(!command("ENTRANCE_PIN", "0088"));
  assert(command("ENTRANCE_PIN", "00889"));
  for (char key : std::string("4321#")) processKeypadKey(key, fake_millis);
  assert(!entranceIsOpen);
  for (char key : std::string("00889#")) processKeypadKey(key, fake_millis);
  assert(!entranceIsOpen);
  for (char key : std::string("0088#")) processKeypadKey(key, fake_millis);
  assert(entranceIsOpen);
  printDnbState();
  assert(Serial.output.find("0088") == std::string::npos);
  assert(Serial.output.find("4321") == std::string::npos);
  assert(Serial.output.find("Key:") == std::string::npos);
  assert(Serial.output.find("\"lamp_color\":\"#FF0000\"") != std::string::npos);
  assert(Serial.output.find("\"lamp_count\":8") != std::string::npos);
  std::cout << "Actual UNO1 speed, voice restoration, RGB, PIN and telemetry checks passed\n";
}
