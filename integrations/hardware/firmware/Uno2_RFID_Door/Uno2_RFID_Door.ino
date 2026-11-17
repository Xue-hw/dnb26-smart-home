#include <MFRC522.h>
#include <Servo.h>
#include <SPI.h>
#include <ctype.h>
#include <string.h>
#include <DnbLink.h>
#include <DnbPin.h>

// UNO board 2: garage RFID access and garage door servo.
// D0/D1 stay free for USB serial.
//
// Sensor Shield V5.0 wiring:
//   RC522 SDA/SS -> D10 S
//   RC522 RST    -> D9 S
//   RC522 MOSI   -> D11 S
//   RC522 MISO   -> D12 S
//   RC522 SCK    -> D13 S
//   RC522 3.3V   -> POWER 3V3
//   RC522 GND    -> POWER GND
//   RC522 IRQ    -> not connected
//   Servo signal  -> D5 S
//   Servo VCC     -> external 5V or shield servo power V
//   Servo GND     -> common GND with UNO
//   MH-FMD IN      -> D6 S
//   MH-FMD VCC     -> 5V
//   MH-FMD GND     -> GND
const byte GARAGE_SERVO_PIN = 5;
const byte BEEP_PIN = 6;
const byte RFID_RST_PIN = 9;
const byte RFID_SS_PIN = 10;
const byte RFID_MOSI_PIN = 11;
const byte RFID_MISO_PIN = 12;
const byte RFID_SCK_PIN = 13;

const int DOOR_CLOSED_ANGLE = 0;
const int DOOR_OPEN_ANGLE = 90;

const unsigned long DOOR_OPEN_TIME_MS = 5000UL;
const unsigned long SERVO_HOLD_TIME_MS = 1200UL;
const unsigned long SERVO_STEP_DELAY_MS = 25UL;
const unsigned long BEEP_TIME_MS = 150UL;
const unsigned long RFID_UNLOCK_COOLDOWN_MS = 2000UL;
const unsigned long RFID_RECOVERY_INTERVAL_MS = 3000UL;
const unsigned long SERIAL_IDLE_COMMAND_MS = 800UL;
const unsigned long STATUS_INTERVAL_MS = 1000UL;

DnbPin garagePin("1234");

MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
Servo garageServo;

bool doorIsOpen = false;
unsigned long doorOpenedAt = 0;
unsigned long servoDetachAt = 0;
unsigned long lastRfidUnlockAt = 0;
unsigned long lastRfidInitAt = 0;
unsigned long lastStatusPrintAt = 0;
int currentDoorAngle = DOOR_CLOSED_ANGLE;
int targetDoorAngle = DOOR_CLOSED_ANGLE;
bool doorMoving = false;
unsigned long lastServoStepAt = 0;
void printDnbState();
const char *executeDnb(const char *op, char *args, unsigned long now);

void setup() {
  Serial.begin(9600);
  garagePin.begin();

  pinMode(RFID_SS_PIN, OUTPUT);
  digitalWrite(RFID_SS_PIN, HIGH);
  pinMode(RFID_RST_PIN, OUTPUT);
  digitalWrite(RFID_RST_PIN, HIGH);
  pinMode(BEEP_PIN, OUTPUT);
  digitalWrite(BEEP_PIN, HIGH);

  SPI.begin();
  setupRfid(true);

  Serial.println(F("UNO2 RFID garage door controller started."));
  Serial.println(F("Present a readable RFID card or enter the access code."));
  printHelp();
  moveDoorServoTo(DOOR_CLOSED_ANGLE, millis());
  DnbLink::identity(F("UNO2"));
}

void loop() {
  handleSerialInput(millis());
  handleRfidAccess(millis());
  updateDoor(millis());
  printStatusIfNeeded(millis());
}

void setupRfid(bool printDetails) {
  rfid.PCD_Init();
  delay(100);
  rfid.PCD_AntennaOn();
  rfid.PCD_SetAntennaGain(MFRC522::RxGain_avg);
  rfid.PCD_StopCrypto1();
  lastRfidInitAt = millis();

  if (!printDetails) {
    return;
  }

  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print(F("RC522 ready. SS=D10 RST=D9 Version=0x"));
  Serial.println(version, HEX);
  Serial.println(F("RFID wiring on Sensor Shield:"));
  Serial.print(F("  SDA/SS -> D"));
  Serial.print(RFID_SS_PIN);
  Serial.println(F(" S"));
  Serial.print(F("  RST    -> D"));
  Serial.print(RFID_RST_PIN);
  Serial.println(F(" S"));
  Serial.print(F("  MOSI   -> D"));
  Serial.print(RFID_MOSI_PIN);
  Serial.println(F(" S"));
  Serial.print(F("  MISO   -> D"));
  Serial.print(RFID_MISO_PIN);
  Serial.println(F(" S"));
  Serial.print(F("  SCK    -> D"));
  Serial.print(RFID_SCK_PIN);
  Serial.println(F(" S"));
  Serial.println(F("  3.3V   -> POWER 3V3"));
  Serial.println(F("  GND    -> POWER GND"));
  Serial.println(F("RC522 receiver gain=average."));

  if (version == 0x00 || version == 0xFF) {
    Serial.println(F("RC522 not responding. Check 3.3V, GND, D9/D10/D11/D12/D13."));
  }
}

void recoverRfid() {
  Serial.println(F("Reinitializing RC522 and antenna..."));
  rfid.PCD_AntennaOff();
  delay(50);
  setupRfid(false);
}

void handleRfidAccess(unsigned long now) {
  if (now - lastRfidUnlockAt < RFID_UNLOCK_COOLDOWN_MS) {
    return;
  }

  if (!rfid.PICC_IsNewCardPresent()) {
    if (now - lastRfidInitAt >= RFID_RECOVERY_INTERVAL_MS) {
      recoverRfid();
    }
    return;
  }

  const bool readOk = rfid.PICC_ReadCardSerial();
  const bool validSize = rfid.uid.size == 4 || rfid.uid.size == 7 || rfid.uid.size == 10;
  if (!readOk || !validSize) {
    Serial.println(F("RFID read failed; access denied."));
    DnbLink::event(F("UNO2"), F("rfid_denied"));
    if (readOk) rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    lastRfidUnlockAt = now;
    return;
  }
  Serial.println(F("RFID read accepted."));
  DnbLink::event(F("UNO2"), F("rfid_granted"));
  beepOnce();
  openDoor(millis());
  lastRfidUnlockAt = millis();
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

void beepOnce() {
  digitalWrite(BEEP_PIN, LOW);
  delay(BEEP_TIME_MS);
  digitalWrite(BEEP_PIN, HIGH);
}

void updateDoor(unsigned long now) {
  if (doorMoving && now - lastServoStepAt >= SERVO_STEP_DELAY_MS) {
    unsigned long steps = (now - lastServoStepAt) / SERVO_STEP_DELAY_MS;
    int remaining = abs(targetDoorAngle - currentDoorAngle);
    if (steps > (unsigned long)remaining) steps = remaining;
    currentDoorAngle += targetDoorAngle > currentDoorAngle ? (int)steps : -(int)steps;
    lastServoStepAt = now;
    garageServo.write(currentDoorAngle);
    if (currentDoorAngle == targetDoorAngle) {
      doorMoving = false;
      doorIsOpen = targetDoorAngle == DOOR_OPEN_ANGLE;
      if (doorIsOpen) doorOpenedAt = now;
      servoDetachAt = now + SERVO_HOLD_TIME_MS;
      printDnbState();
    }
  }
  if (!doorMoving && doorIsOpen && now - doorOpenedAt >= DOOR_OPEN_TIME_MS) {
    closeDoor(now);
  }

  releaseServoIfReady(now);
}

void moveDoorServoTo(int targetAngle, unsigned long now) {
  targetAngle = constrain(targetAngle, 0, 180);

  if (!garageServo.attached()) {
    garageServo.attach(GARAGE_SERVO_PIN);
  }

  targetDoorAngle = targetAngle;
  doorMoving = targetDoorAngle != currentDoorAngle;
  lastServoStepAt = now;
  servoDetachAt = doorMoving ? 0 : now + SERVO_HOLD_TIME_MS;
  garageServo.write(currentDoorAngle);
}

void releaseServoIfReady(unsigned long now) {
  if (garageServo.attached() && servoDetachAt > 0 && (long)(now - servoDetachAt) >= 0) {
    garageServo.detach();
    servoDetachAt = 0;
  }
}

void openDoor(unsigned long now) {
  moveDoorServoTo(DOOR_OPEN_ANGLE, now);
  if (!doorMoving) { doorIsOpen = true; doorOpenedAt = now; }
  Serial.println(F("Garage opening requested."));
}

void closeDoor(unsigned long now) {
  moveDoorServoTo(DOOR_CLOSED_ANGLE, now);
  if (!doorMoving) doorIsOpen = false;
  Serial.println(F("Garage closing requested."));
}

void handleSerialInput(unsigned long now) {
  DnbLink::poll(now, F("UNO2"), executeDnb, printDnbState, processCommand);
}

void processCommand(char *rawCommand, unsigned long now) {
  char *command = trimText(rawCommand);

  if (command[0] == '\0') {
    return;
  }

  if (matchesAccessCode(command) || equalsIgnoreCase(command, "OPEN")) {
    openDoor(now);
  } else if (equalsIgnoreCase(command, "CLOSE")) {
    closeDoor(now);
  } else if (equalsIgnoreCase(command, "STATUS")) {
    printStatus(true);
  } else if (equalsIgnoreCase(command, "HELP")) {
    printHelp();
  } else {
    Serial.println(F("Unknown command. Type HELP."));
  }
}

bool matchesAccessCode(char *command) {
  char *code = command;

  if (startsWithIgnoreCase(command, "PIN ")) {
    code = trimText(command + 4);
  } else if (startsWithIgnoreCase(command, "CODE ")) {
    code = trimText(command + 5);
  }

  return garagePin.matches(code);
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

void printHelp() {
  Serial.println(F("Commands: STATUS, OPEN, CLOSE, PIN <code>, HELP; DNB1 GARAGE_PIN"));
}

void printStatusIfNeeded(unsigned long now) {
  if (now - lastStatusPrintAt < STATUS_INTERVAL_MS) {
    return;
  }

  lastStatusPrintAt = now;
  printStatus(false);
  printDnbState();
}

void printStatus(bool forceHeader) {
  if (forceHeader) {
    Serial.println(F("---- UNO2 STATUS ----"));
  }

  Serial.print(F("Garage door="));
  Serial.println(doorIsOpen ? F("OPEN") : F("CLOSED"));
  printRfidCommunicationStatus();
}

void printRfidCommunicationStatus() {
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);

  Serial.print(F("RC522 communication="));
  if (version == 0x00 || version == 0xFF) {
    Serial.print(F("NO_RESPONSE"));
  } else {
    Serial.print(F("OK"));
  }

  Serial.print(F(" VersionReg=0x"));
  if (version < 0x10) {
    Serial.print('0');
  }
  Serial.println(version, HEX);
}

const char *executeDnb(const char *op, char *args, unsigned long now) {
  if (DnbLink::opcode(op, F("GARAGE_PIN"))) {
    if (!DnbPin::valid(args)) return "invalid_pin";
    return garagePin.save(args) ? 0 : "pin_write_failed";
  }
  if (args && *args) return "unexpected_args";
  if (DnbLink::opcode(op, F("DOOR_OPEN"))) openDoor(now);
  else if (DnbLink::opcode(op, F("DOOR_CLOSE"))) closeDoor(now);
  else return "unsupported_command";
  return 0;
}

void printDnbState() {
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print(F("DNB1 {\"type\":\"state\",\"board\":\"UNO2\",\"garage\":\""));
  Serial.print(doorMoving ? F("moving") : doorIsOpen ? F("open") : F("closed"));
  Serial.print(F("\",\"state_basis\":\"actuator\",\"rfid_ok\":"));
  Serial.print(version != 0 && version != 255 ? F("true") : F("false"));
  Serial.print(F(",\"rfid_restricted\":")); Serial.print(F("false"));
  Serial.println('}');
}
