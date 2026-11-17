#include <Adafruit_NeoPixel.h>
#include <DHT.h>
#include <Servo.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <ctype.h>
#include <math.h>
#include <string.h>

// UNO board 1: environment, fan motor, lamp, OLED, ASRPRO voice input, entrance keypad and entrance servo.
// D0/D1 stay free for USB serial.
const byte ASR_SIGNAL_PIN = 2;
const byte DHT_PIN = 3;
const byte RGB_PIN = 4;
const byte FAN_PWM_PIN = 5;
const byte ENTRANCE_SERVO_PIN = 10;
const byte OLED_RST_PIN = 12;
const byte LIGHT_PIN = A1;
const byte OLED_DC_PIN = A2;

const byte KEYPAD_ROWS = 4;
const byte KEYPAD_COLS = 4;
const byte KEYPAD_ROW_PINS[KEYPAD_ROWS] = {6, 7, 8, 9};
const byte KEYPAD_COL_PINS[KEYPAD_COLS] = {A0, A3, A4, A5};
const char KEYPAD_KEYS[KEYPAD_ROWS][KEYPAD_COLS] = {
  {'1', '2', '3', 'A'},
  {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'},
  {'*', '0', '#', 'D'}
};

#define DHTTYPE DHT11

const byte NUM_LEDS = 8;
const byte FAN_SPEED = 100;
const byte DEFAULT_LAMP_BRIGHTNESS_PERCENT = 30;

// The existing light module reads larger values when the room is darker.
const int LIGHT_DIM_THRESHOLD = 500;
const int LIGHT_DARK_THRESHOLD = 800;
const byte AUTO_LAMP_BRIGHT_BRIGHTNESS = 0;
const byte AUTO_LAMP_DIM_BRIGHTNESS = 20;
const byte AUTO_LAMP_DARK_BRIGHTNESS = 60;

const float FAN_ON_TEMP_C = 29.0;
const float FAN_OFF_TEMP_C = 29.0;

const int ENTRANCE_CLOSED_ANGLE = 90;
const int ENTRANCE_OPEN_ANGLE = 0;

const unsigned long LIGHT_READ_INTERVAL_MS = 100UL;
const unsigned long DHT_READ_INTERVAL_MS = 2000UL;
const unsigned long STATUS_INTERVAL_MS = 3000UL;
const unsigned long ENTRANCE_OPEN_TIME_MS = 5000UL;
const unsigned long SERVO_HOLD_TIME_MS = 1200UL;
const unsigned long DHT_ERROR_PRINT_INTERVAL_MS = 10000UL;
const unsigned long SERIAL_IDLE_COMMAND_MS = 800UL;
const unsigned long OLED_UPDATE_INTERVAL_MS = 5000UL;
const unsigned long KEYPAD_DEBOUNCE_MS = 220UL;
const unsigned long ASR_COMMAND_GAP_MS = 300UL;
const unsigned long ASR_MIN_EDGE_GAP_US = 30000UL;
const unsigned long ASR_LAMP_OVERRIDE_MS = 5000UL;
const unsigned long ASR_FAN_OVERRIDE_MS = 5000UL;

const char ENTRANCE_CODE[] = "4321";

DHT dht(DHT_PIN, DHTTYPE);
Adafruit_NeoPixel strip(NUM_LEDS, RGB_PIN, NEO_GRB + NEO_KHZ800);
Servo entranceServo;

// OLED uses UNO hardware SPI:
// SCK -> D13, SDA/DIN -> D11, DC -> A2, RES -> D12, CS -> GND.
U8G2_SSD1306_128X64_NONAME_1_4W_HW_SPI oled(
  U8G2_R0,
  U8X8_PIN_NONE,
  OLED_DC_PIN,
  OLED_RST_PIN
);

enum FanMode {
  FAN_AUTO,
  FAN_FORCE_ON,
  FAN_FORCE_OFF
};

enum LampMode {
  LAMP_AUTO,
  LAMP_MANUAL
};

FanMode fanMode = FAN_AUTO;
LampMode lampMode = LAMP_AUTO;

bool fanState = false;
bool lampState = false;
bool entranceIsOpen = false;
bool dhtOk = false;
byte lampBrightnessPercent = DEFAULT_LAMP_BRIGHTNESS_PERCENT;
byte manualLampBrightnessPercent = DEFAULT_LAMP_BRIGHTNESS_PERCENT;
bool manualLampOn = false;

float temperatureC = NAN;
float humidityPercent = NAN;

int lightValue = 0;
bool isDark = false;

char keypadBuffer[5] = "";
byte keypadLength = 0;

volatile byte asrEdgeCount = 0;
volatile unsigned long lastAsrEdgeAtMs = 0;
volatile unsigned long lastAsrEdgeAtUs = 0;
byte lastAsrCommand = 0;
byte lastAsrRawEdges = 0;

unsigned long lastLightReadAt = 0;
unsigned long lastDhtReadAt = 0;
unsigned long lastStatusPrintAt = 0;
unsigned long lastDhtErrorPrintAt = 0;
unsigned long lastOledUpdateAt = 0;
unsigned long asrFanOverrideUntil = 0;
unsigned long asrLampOverrideUntil = 0;
unsigned long entranceOpenedAt = 0;
unsigned long servoDetachAt = 0;
unsigned long lastKeyAt = 0;
char lastKey = '\0';

void onAsrPulse();
void handleAsrCommand(unsigned long now);
void processAsrCommand(byte pulseCount, unsigned long now);
void printAsrDebug();
void setVoiceFanPower(bool on, unsigned long now);
void setVoiceLampPower(bool on, unsigned long now);

void setup() {
  Serial.begin(9600);

  pinMode(ASR_SIGNAL_PIN, INPUT);
  pinMode(FAN_PWM_PIN, OUTPUT);
  pinMode(ENTRANCE_SERVO_PIN, OUTPUT);
  pinMode(OLED_RST_PIN, OUTPUT);
  digitalWrite(ENTRANCE_SERVO_PIN, LOW);
  digitalWrite(OLED_RST_PIN, HIGH);
  SPI.begin();
  attachInterrupt(digitalPinToInterrupt(ASR_SIGNAL_PIN), onAsrPulse, CHANGE);

  setupKeypad();
  fanOff();

  dht.begin();

  strip.begin();
  applyLampBrightness();

  setupOled();
  setEffectiveLampBrightness(0);
  closeEntrance(millis());

  Serial.println(F("UNO1 environment and entrance controller started."));
  Serial.println(F("Entrance keypad password: 4321#"));
  printHelp();
  printLampBrightness();
}

void loop() {
  const unsigned long now = millis();

  handleSerialInput(now);
  handleAsrCommand(now);
  handleKeypad(now);
  updateLightAndLamp(now);
  updateTemperature(now);
  updateFan();
  updateEntranceDoor(now);
  updateOled(now);
  printStatusIfNeeded(now);
}

void onAsrPulse() {
  const unsigned long nowUs = micros();

  if (nowUs - lastAsrEdgeAtUs < ASR_MIN_EDGE_GAP_US) {
    return;
  }

  if (asrEdgeCount < 40) {
    asrEdgeCount++;
  }

  lastAsrEdgeAtUs = nowUs;
  lastAsrEdgeAtMs = millis();
}

void handleAsrCommand(unsigned long now) {
  byte pulseCount = 0;
  byte edgeCount = 0;

  noInterrupts();
  if (asrEdgeCount > 0 && now - lastAsrEdgeAtMs >= ASR_COMMAND_GAP_MS) {
    edgeCount = asrEdgeCount;
    asrEdgeCount = 0;
  }
  interrupts();

  if (edgeCount > 0) {
    lastAsrRawEdges = edgeCount;
    pulseCount = (edgeCount + 1) / 2;

    Serial.print(F("ASR raw edges: "));
    Serial.print(edgeCount);
    Serial.print(F(" -> pulses: "));
    Serial.println(pulseCount);

    processAsrCommand(pulseCount, now);
  }
}

void processAsrCommand(byte pulseCount, unsigned long now) {
  lastAsrCommand = pulseCount;

  Serial.print(F("ASR pulse command: "));
  Serial.println(pulseCount);

  switch (pulseCount) {
    case 1:
      setVoiceFanPower(true, now);
      Serial.println(F("Voice command: fan on."));
      break;

    case 2:
      setVoiceFanPower(false, now);
      Serial.println(F("Voice command: fan off."));
      break;

    case 3:
      setVoiceLampPower(true, now);
      Serial.println(F("Voice command: light on."));
      break;

    case 4:
      setVoiceLampPower(false, now);
      Serial.println(F("Voice command: light off."));
      break;

    case 5:
      openEntrance(now);
      Serial.println(F("Voice command: entrance open."));
      break;

    case 6:
      closeEntrance(now);
      Serial.println(F("Voice command: entrance close."));
      break;

    default:
      Serial.println(F("Unknown ASR pulse command."));
      break;
  }
}

void setupKeypad() {
  for (byte row = 0; row < KEYPAD_ROWS; row++) {
    pinMode(KEYPAD_ROW_PINS[row], OUTPUT);
    digitalWrite(KEYPAD_ROW_PINS[row], HIGH);
  }

  for (byte col = 0; col < KEYPAD_COLS; col++) {
    pinMode(KEYPAD_COL_PINS[col], INPUT_PULLUP);
  }
}

void handleKeypad(unsigned long now) {
  char key = readKeypadKey();

  if (key == '\0') {
    lastKey = '\0';
    return;
  }

  if (key == lastKey && now - lastKeyAt < KEYPAD_DEBOUNCE_MS) {
    return;
  }

  lastKey = key;
  lastKeyAt = now;
  processKeypadKey(key, now);
}

char readKeypadKey() {
  for (byte row = 0; row < KEYPAD_ROWS; row++) {
    pinMode(KEYPAD_ROW_PINS[row], OUTPUT);
    digitalWrite(KEYPAD_ROW_PINS[row], LOW);
    delayMicroseconds(20);

    for (byte col = 0; col < KEYPAD_COLS; col++) {
      if (digitalRead(KEYPAD_COL_PINS[col]) == LOW) {
        digitalWrite(KEYPAD_ROW_PINS[row], HIGH);
        return KEYPAD_KEYS[row][col];
      }
    }

    digitalWrite(KEYPAD_ROW_PINS[row], HIGH);
  }

  return '\0';
}

void processKeypadKey(char key, unsigned long now) {
  Serial.print(F("Key: "));
  Serial.println(key);

  if (key == '*') {
    clearKeypadBuffer();
    Serial.println(F("Entrance password cleared."));
    return;
  }

  if (key == '#') {
    checkEntrancePassword(now);
    return;
  }

  if (!isdigit((unsigned char)key)) {
    return;
  }

  if (keypadLength < sizeof(keypadBuffer) - 1) {
    keypadBuffer[keypadLength++] = key;
    keypadBuffer[keypadLength] = '\0';
  }
}

void checkEntrancePassword(unsigned long now) {
  if (keypadLength == 0) {
    Serial.println(F("Entrance password empty. Type 4321#."));
    return;
  }

  if (strcmp(keypadBuffer, ENTRANCE_CODE) == 0) {
    Serial.println(F("Entrance password OK."));
    openEntrance(now);
  } else {
    Serial.println(F("Entrance password wrong."));
  }

  clearKeypadBuffer();
}

void clearKeypadBuffer() {
  keypadLength = 0;
  keypadBuffer[0] = '\0';
}

void updateLightAndLamp(unsigned long now) {
  if (now - lastLightReadAt < LIGHT_READ_INTERVAL_MS) {
    return;
  }

  lastLightReadAt = now;
  lightValue = readLightAverage();
  isDark = lightValue > LIGHT_DARK_THRESHOLD;

  if (asrLampOverrideUntil > 0 && (long)(now - asrLampOverrideUntil) >= 0) {
    asrLampOverrideUntil = 0;
    lampMode = LAMP_AUTO;
    Serial.println(F("Voice light override ended. Lamp mode: AUTO."));
  }

  if (lampMode == LAMP_AUTO) {
    setEffectiveLampBrightness(calculateAutoLampBrightness());
  }
}

int readLightAverage() {
  long sum = 0;

  for (byte i = 0; i < 10; i++) {
    sum += analogRead(LIGHT_PIN);
    delay(2);
  }

  return sum / 10;
}

byte calculateAutoLampBrightness() {
  if (lightValue > LIGHT_DARK_THRESHOLD) {
    return AUTO_LAMP_DARK_BRIGHTNESS;
  }

  if (lightValue > LIGHT_DIM_THRESHOLD) {
    return AUTO_LAMP_DIM_BRIGHTNESS;
  }

  return AUTO_LAMP_BRIGHT_BRIGHTNESS;
}

void updateTemperature(unsigned long now) {
  if (now - lastDhtReadAt < DHT_READ_INTERVAL_MS) {
    return;
  }

  lastDhtReadAt = now;

  const float newHumidity = dht.readHumidity();
  const float newTemperature = dht.readTemperature();

  if (isnan(newHumidity) || isnan(newTemperature)) {
    dhtOk = false;

    if (now - lastDhtErrorPrintAt >= DHT_ERROR_PRINT_INTERVAL_MS) {
      lastDhtErrorPrintAt = now;
      Serial.println(F("DHT11 read failed. Check wiring on D3."));
    }

    return;
  }

  humidityPercent = newHumidity;
  temperatureC = newTemperature;
  dhtOk = true;
}

void updateFan() {
  if (asrFanOverrideUntil > 0 && (long)(millis() - asrFanOverrideUntil) >= 0) {
    asrFanOverrideUntil = 0;
    fanMode = FAN_AUTO;
    Serial.println(F("Voice fan override ended. Fan mode: AUTO."));
  }

  if (fanMode == FAN_FORCE_ON) {
    fanOn(FAN_SPEED);
    return;
  }

  if (fanMode == FAN_FORCE_OFF) {
    fanOff();
    return;
  }

  if (!dhtOk) {
    fanOff();
    return;
  }

  if (!fanState && temperatureC >= FAN_ON_TEMP_C) {
    fanOn(FAN_SPEED);
  } else if (fanState && temperatureC < FAN_OFF_TEMP_C) {
    fanOff();
  }
}

void updateEntranceDoor(unsigned long now) {
  if (entranceIsOpen && now - entranceOpenedAt >= ENTRANCE_OPEN_TIME_MS) {
    closeEntrance(now);
  }

  releaseEntranceServoIfReady(now);
}

void setupOled() {
  oled.setBusClock(1000000UL);
  oled.begin();
  oled.setContrast(180);
  drawOledScreen(F("Starting"));
}

void updateOled(unsigned long now) {
  if (now - lastOledUpdateAt < OLED_UPDATE_INTERVAL_MS) {
    return;
  }

  lastOledUpdateAt = now;
  drawOledScreen(dhtOk ? F("DHT OK") : F("DHT N/A"));
}

void drawOledScreen(const __FlashStringHelper *sensorStatus) {
  oled.firstPage();

  do {
    oled.setFont(u8g2_font_6x10_tf);
    oled.drawStr(0, 10, "UNO1 Home");

    oled.setCursor(82, 10);
    oled.print(sensorStatus);

    oled.setFont(u8g2_font_logisoso24_tf);
    oled.setCursor(0, 43);

    if (dhtOk) {
      oled.print(temperatureC, 1);
      oled.print(F(" C"));
    } else {
      oled.print(F("--.- C"));
    }

    oled.setFont(u8g2_font_6x10_tf);
    oled.setCursor(0, 54);
    oled.print(F("Hum:"));

    if (dhtOk) {
      oled.print(humidityPercent, 0);
      oled.print(F("%"));
    } else {
      oled.print(F("--%"));
    }

    oled.setCursor(70, 54);
    oled.print(F("Fan:"));
    oled.print(fanState ? F("ON") : F("OFF"));

    oled.setCursor(0, 63);
    oled.print(F("Now:"));
    oled.print(lampBrightnessPercent);
    oled.print(lampMode == LAMP_AUTO ? F("A%") : F("M%"));

    oled.setCursor(66, 63);
    oled.print(F("E:"));
    oled.print(entranceIsOpen ? F("OPEN") : F("CLOSE"));
  } while (oled.nextPage());
}

void moveEntranceServoTo(int targetAngle, unsigned long now) {
  if (!entranceServo.attached()) {
    entranceServo.attach(ENTRANCE_SERVO_PIN);
    delay(50);
  }

  entranceServo.write(targetAngle);
  delay(20);
  entranceServo.write(targetAngle);
  servoDetachAt = now + SERVO_HOLD_TIME_MS;
}

void releaseEntranceServoIfReady(unsigned long now) {
  if (entranceServo.attached() && servoDetachAt > 0 && (long)(now - servoDetachAt) >= 0) {
    entranceServo.detach();
    servoDetachAt = 0;
  }
}

void openEntrance(unsigned long now) {
  moveEntranceServoTo(ENTRANCE_OPEN_ANGLE, now);
  entranceIsOpen = true;
  entranceOpenedAt = now;
  Serial.println(F("Entrance door opened."));
  drawOledScreen(dhtOk ? F("DHT OK") : F("DHT N/A"));
}

void closeEntrance(unsigned long now) {
  moveEntranceServoTo(ENTRANCE_CLOSED_ANGLE, now);
  entranceIsOpen = false;
  Serial.println(F("Entrance door closed."));
  drawOledScreen(dhtOk ? F("DHT OK") : F("DHT N/A"));
}

void lampOn() {
  setManualLampPower(true);
}

void lampOff() {
  setManualLampPower(false);
}

void setLampBrightnessPercent(byte percent) {
  if (percent > 100) {
    percent = 100;
  }

  asrLampOverrideUntil = 0;
  lampMode = LAMP_MANUAL;
  manualLampBrightnessPercent = percent;
  manualLampOn = percent > 0;
  setEffectiveLampBrightness(manualLampOn ? manualLampBrightnessPercent : 0);
}

void setManualLampPower(bool on) {
  asrLampOverrideUntil = 0;
  lampMode = LAMP_MANUAL;
  manualLampOn = on;

  if (manualLampOn && manualLampBrightnessPercent == 0) {
    manualLampBrightnessPercent = DEFAULT_LAMP_BRIGHTNESS_PERCENT;
  }

  setEffectiveLampBrightness(manualLampOn ? manualLampBrightnessPercent : 0);
}

void setVoiceLampPower(bool on, unsigned long now) {
  lampMode = LAMP_MANUAL;
  manualLampOn = on;
  asrLampOverrideUntil = now + ASR_LAMP_OVERRIDE_MS;

  if (manualLampOn && manualLampBrightnessPercent == 0) {
    manualLampBrightnessPercent = DEFAULT_LAMP_BRIGHTNESS_PERCENT;
  }

  setEffectiveLampBrightness(manualLampOn ? manualLampBrightnessPercent : 0);
  printLampBrightness();

  Serial.print(F("Voice light override will return to AUTO in "));
  Serial.print(ASR_LAMP_OVERRIDE_MS / 1000UL);
  Serial.println(F("s."));
}

void setLampAutoMode() {
  asrLampOverrideUntil = 0;
  lampMode = LAMP_AUTO;
  setEffectiveLampBrightness(calculateAutoLampBrightness());
  drawOledScreen(dhtOk ? F("DHT OK") : F("DHT N/A"));
}

void setEffectiveLampBrightness(byte percent) {
  if (percent > 100) {
    percent = 100;
  }

  if (lampBrightnessPercent == percent && lampState == (percent > 0)) {
    return;
  }

  lampBrightnessPercent = percent;
  lampState = percent > 0;
  applyLampBrightness();
  renderLamp();
  drawOledScreen(dhtOk ? F("DHT OK") : F("DHT N/A"));
}

void renderLamp() {
  strip.clear();

  if (lampState) {
    strip.setPixelColor(0, strip.Color(255, 150, 40));
  }

  strip.show();
}

void applyLampBrightness() {
  const byte brightnessValue = map(lampBrightnessPercent, 0, 100, 0, 255);
  strip.setBrightness(brightnessValue);
}

void setVoiceFanPower(bool on, unsigned long now) {
  asrFanOverrideUntil = now + ASR_FAN_OVERRIDE_MS;
  fanMode = on ? FAN_FORCE_ON : FAN_FORCE_OFF;

  if (on) {
    fanOn(FAN_SPEED);
  } else {
    fanOff();
  }

  Serial.print(F("Voice fan override will return to AUTO in "));
  Serial.print(ASR_FAN_OVERRIDE_MS / 1000UL);
  Serial.println(F("s."));
}

void fanOn(byte speedValue) {
  if (fanState) {
    return;
  }

  analogWrite(FAN_PWM_PIN, speedValue);
  fanState = true;
  Serial.println(F("Fan on."));
}

void fanOff() {
  if (!fanState) {
    digitalWrite(FAN_PWM_PIN, LOW);
    return;
  }

  digitalWrite(FAN_PWM_PIN, LOW);
  fanState = false;
  Serial.println(F("Fan off."));
}

void handleSerialInput(unsigned long now) {
  static char commandBuffer[32];
  static byte commandLength = 0;
  static unsigned long lastCommandCharAt = 0;

  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      commandBuffer[commandLength] = '\0';
      processCommand(commandBuffer, now);
      commandLength = 0;
      continue;
    }

    if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = c;
      lastCommandCharAt = now;
    }
  }

  if (commandLength > 0 && now - lastCommandCharAt >= SERIAL_IDLE_COMMAND_MS) {
    commandBuffer[commandLength] = '\0';
    processCommand(commandBuffer, now);
    commandLength = 0;
  }
}

void processCommand(char *rawCommand, unsigned long now) {
  char *command = trimText(rawCommand);

  if (command[0] == '\0') {
    return;
  }

  if (equalsIgnoreCase(command, "ENTRANCE OPEN") || equalsIgnoreCase(command, "OPEN")) {
    openEntrance(now);
  } else if (equalsIgnoreCase(command, "ENTRANCE CLOSE") || equalsIgnoreCase(command, "CLOSE")) {
    closeEntrance(now);
  } else if (equalsIgnoreCase(command, "STATUS")) {
    printStatus(true);
  } else if (equalsIgnoreCase(command, "ASR TEST")) {
    printAsrDebug();
  } else if (equalsIgnoreCase(command, "FAN AUTO")) {
    asrFanOverrideUntil = 0;
    fanMode = FAN_AUTO;
    Serial.println(F("Fan mode: AUTO."));
  } else if (equalsIgnoreCase(command, "FAN ON")) {
    asrFanOverrideUntil = 0;
    fanMode = FAN_FORCE_ON;
    fanOn(FAN_SPEED);
    Serial.println(F("Fan mode: FORCE ON."));
  } else if (equalsIgnoreCase(command, "FAN OFF")) {
    asrFanOverrideUntil = 0;
    fanMode = FAN_FORCE_OFF;
    fanOff();
    Serial.println(F("Fan mode: FORCE OFF."));
  } else if (equalsIgnoreCase(command, "LIGHT AUTO") || equalsIgnoreCase(command, "LAMP AUTO")) {
    setLampAutoMode();
    printLampBrightness();
  } else if (equalsIgnoreCase(command, "LIGHT ON") || equalsIgnoreCase(command, "LAMP ON")) {
    lampOn();
    printLampBrightness();
  } else if (equalsIgnoreCase(command, "LIGHT OFF") || equalsIgnoreCase(command, "LAMP OFF")) {
    lampOff();
    printLampBrightness();
  } else if (startsWithIgnoreCase(command, "BRIGHT ")) {
    setLampBrightnessFromCommand(command + 7);
  } else if (startsWithIgnoreCase(command, "LIGHT ")) {
    setLampBrightnessFromCommand(command + 6);
  } else if (startsWithIgnoreCase(command, "B ")) {
    setLampBrightnessFromCommand(command + 2);
  } else if (equalsIgnoreCase(command, "B+")) {
    changeLampBrightnessBy(10);
  } else if (equalsIgnoreCase(command, "B-")) {
    changeLampBrightnessBy(-10);
  } else if (equalsIgnoreCase(command, "B?") || equalsIgnoreCase(command, "BRIGHT?")) {
    printLampBrightness();
  } else if (equalsIgnoreCase(command, "HELP")) {
    printHelp();
  } else {
    Serial.println(F("Unknown command. Type HELP."));
  }
}

void setLampBrightnessFromCommand(char *valueText) {
  char *trimmedValue = trimText(valueText);
  int percent = atoi(trimmedValue);

  if (percent < 0) {
    percent = 0;
  } else if (percent > 100) {
    percent = 100;
  }

  setLampBrightnessPercent((byte)percent);
  printLampBrightness();
}

void changeLampBrightnessBy(int delta) {
  int percent = lampBrightnessPercent + delta;

  if (percent < 0) {
    percent = 0;
  } else if (percent > 100) {
    percent = 100;
  }

  setLampBrightnessPercent((byte)percent);
  printLampBrightness();
}

void printLampBrightness() {
  Serial.print(F("Lamp mode: "));
  Serial.print(lampMode == LAMP_AUTO ? F("AUTO") : F("MANUAL"));
  Serial.print(F(" | state: "));
  Serial.print(lampState ? F("ON") : F("OFF"));
  Serial.print(F(" | brightness: "));
  Serial.print(lampBrightnessPercent);
  Serial.println(F("%"));
}

void printHelp() {
  Serial.println(F("Commands: STATUS, ASR TEST, ENTRANCE OPEN, ENTRANCE CLOSE, FAN AUTO, FAN ON, FAN OFF"));
  Serial.println(F("Lamp: LIGHT AUTO, LIGHT ON, LIGHT OFF, BRIGHT/LIGHT/B 0-100, B+, B-, B?"));
  Serial.println(F("Keypad: enter 4321# to open entrance, * clears input."));
  Serial.println(F("ASRPRO on D2: 1 fan on, 2 fan off, 3 light on, 4 light off, 5 entrance open, 6 entrance close."));
  Serial.println(F("Voice fan/light on/off is temporary; AUTO resumes after 5s."));
}

void printAsrDebug() {
  byte pendingEdges;
  unsigned long lastEdgeAt;

  noInterrupts();
  pendingEdges = asrEdgeCount;
  lastEdgeAt = lastAsrEdgeAtMs;
  interrupts();

  Serial.print(F("ASR D2 level="));
  Serial.print(digitalRead(ASR_SIGNAL_PIN) == HIGH ? F("HIGH") : F("LOW"));
  Serial.print(F(" | pending edges="));
  Serial.print(pendingEdges);
  Serial.print(F(" | last raw edges="));
  Serial.print(lastAsrRawEdges);
  Serial.print(F(" | last command="));
  Serial.print(lastAsrCommand);
  Serial.print(F(" | last edge ms="));
  Serial.println(lastEdgeAt);
}

char *trimText(char *text) {
  while (*text != '\0' && isspace((unsigned char)*text)) {
    text++;
  }

  char *end = text + strlen(text);
  while (end > text && isspace((unsigned char)*(end - 1))) {
    end--;
  }

  *end = '\0';
  return text;
}

bool equalsIgnoreCase(const char *left, const char *right) {
  while (*left != '\0' && *right != '\0') {
    if (toupper((unsigned char)*left) != toupper((unsigned char)*right)) {
      return false;
    }

    left++;
    right++;
  }

  return *left == '\0' && *right == '\0';
}

bool startsWithIgnoreCase(const char *text, const char *prefix) {
  while (*prefix != '\0') {
    if (*text == '\0' || toupper((unsigned char)*text) != toupper((unsigned char)*prefix)) {
      return false;
    }

    text++;
    prefix++;
  }

  return true;
}

void printStatusIfNeeded(unsigned long now) {
  if (now - lastStatusPrintAt < STATUS_INTERVAL_MS) {
    return;
  }

  lastStatusPrintAt = now;
  printStatus(false);
}

void printStatus(bool forceHeader) {
  if (forceHeader) {
    Serial.println(F("---- UNO1 STATUS ----"));
  }

  Serial.print(F("Light="));
  Serial.print(lightValue);
  Serial.print(isDark ? F(" dark") : F(" bright"));

  Serial.print(F(" | ASR last="));
  Serial.print(lastAsrCommand);

  Serial.print(F(" | Lamp="));
  Serial.print(lampState ? F("ON") : F("OFF"));
  Serial.print(F(" Mode="));
  Serial.print(lampMode == LAMP_AUTO ? F("AUTO") : F("MANUAL"));
  if (asrLampOverrideUntil > 0) {
    Serial.print(F("(VOICE)"));
  }
  Serial.print(F(" Bri="));
  Serial.print(lampBrightnessPercent);
  Serial.print(F("%"));

  Serial.print(F(" | Temp="));
  if (dhtOk) {
    Serial.print(temperatureC, 1);
    Serial.print(F("C Hum="));
    Serial.print(humidityPercent, 1);
    Serial.print(F("%"));
  } else {
    Serial.print(F("N/A"));
  }

  Serial.print(F(" | Fan="));
  Serial.print(fanState ? F("ON") : F("OFF"));
  Serial.print(F(" Mode="));
  Serial.print(fanMode == FAN_AUTO ? F("AUTO") : F("MANUAL"));
  if (asrFanOverrideUntil > 0) {
    Serial.print(F("(VOICE)"));
  }

  Serial.print(F(" | Entrance="));
  Serial.println(entranceIsOpen ? F("OPEN") : F("CLOSED"));
}
