#pragma once
#include <Arduino.h>
class MFRC522 {
public:
  static const byte VersionReg = 0;
  static const byte RxGain_avg = 4;
  struct Uid { byte size = 4; byte uidByte[10] = {4, 0xA1, 0x2B, 0}; } uid;
  bool card_present = true;
  bool read_ok = true;
  MFRC522(byte, byte) {}
  void PCD_Init() {}
  void PCD_AntennaOn() {}
  void PCD_AntennaOff() {}
  void PCD_SetAntennaGain(byte) {}
  void PCD_StopCrypto1() {}
  byte PCD_ReadRegister(byte) { return 0x92; }
  bool PICC_IsNewCardPresent() { return card_present; }
  bool PICC_ReadCardSerial() { return read_ok; }
  void PICC_HaltA() {}
};
