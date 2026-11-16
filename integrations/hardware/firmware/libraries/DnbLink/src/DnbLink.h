#ifndef DNB_LINK_H
#define DNB_LINK_H
#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

namespace DnbLink {
typedef const char *(*Executor)(const char *, char *, unsigned long);
typedef void (*Legacy)(char *, unsigned long);
typedef void (*State)();

inline bool opcode(const char *actual, const __FlashStringHelper *expected) {
  return strcmp_P(actual, (PGM_P)expected) == 0;
}

inline void identity(const __FlashStringHelper *board) {
  Serial.print(F("DNB1 {\"type\":\"identity\",\"protocol\":1,\"board\":\""));
  Serial.print(board);
  Serial.println(F("\"}"));
}

inline void ack(const __FlashStringHelper *board, const char *id, const char *error) {
  Serial.print(F("DNB1 {\"type\":\"ack\",\"board\":\""));
  Serial.print(board);
  Serial.print(F("\",\"command_id\":\""));
  Serial.print(id);
  Serial.print(F("\",\"status\":\""));
  Serial.print(error ? F("failed") : F("acked"));
  Serial.print(F("\""));
  if (error) {
    Serial.print(F(",\"error\":\""));
    Serial.print(error); // Only fixed error codes from the firmware, never user text.
    Serial.print('"');
  }
  Serial.println('}');
}

inline void event(const __FlashStringHelper *board, const __FlashStringHelper *name,
                  byte command = 0, const char *uid = 0) {
  Serial.print(F("DNB1 {\"type\":\"event\",\"board\":\""));
  Serial.print(board);
  Serial.print(F("\",\"event\":\""));
  Serial.print(name);
  Serial.print('"');
  if (command >= 1 && command <= 6) {
    Serial.print(F(",\"command\":"));
    Serial.print(command);
  }
  if (uid) {
    Serial.print(F(",\"uid\":\""));
    Serial.print(uid);
    Serial.print('"');
  }
  Serial.println('}');
}

inline bool integer(const char *text, long minimum, long maximum, long &result) {
  if (!text || !*text) return false;
  char *end;
  result = strtol(text, &end, 10);
  return *end == '\0' && result >= minimum && result <= maximum;
}

inline bool decimal(const char *text, float &result) {
  if (!text || !*text) return false;
  const bool negative = *text == '-';
  if (negative) ++text;
  if (*text < '0' || *text > '9') return false;
  unsigned int tenths = 0;
  while (*text >= '0' && *text <= '9') {
    tenths = tenths * 10 + (*text++ - '0');
    if (tenths > 1000) return false;
  }
  tenths *= 10;
  if (*text == '.') {
    ++text;
    if (*text < '0' || *text > '9') return false;
    tenths += *text++ - '0';
  }
  if (*text) return false;
  result = (negative ? -(int)tenths : (int)tenths) / 10.0f;
  return true;
}

inline void command(char *line, unsigned long now, const __FlashStringHelper *board,
                    Executor execute, State state) {
  if (strcmp(line, "ID") == 0) { identity(board); return; }
  if (strcmp(line, "STATE") == 0) { state(); return; }
  // line = DNB1 <32 lowercase hex characters> <OPCODE> [space-separated args]
  char *id = line + 5;
  if (strlen(id) < 34 || id[32] != ' ') return;
  for (byte i = 0; i < 32; ++i) {
    if (!((id[i] >= '0' && id[i] <= '9') || (id[i] >= 'a' && id[i] <= 'f'))) return;
  }
  id[32] = '\0';
  char *op = id + 33;
  char *args = strchr(op, ' ');
  if (args) *args++ = '\0';
  // Protect a retried immediately preceding command from actuating twice.
  static char lastId[33] = "";
  static unsigned long lastHash = 0;
  static const char *lastError = 0;
  unsigned long hash = 2166136261UL;
  for (const char *p = op; *p; ++p) hash = (hash ^ (byte)*p) * 16777619UL;
  hash = (hash ^ ' ') * 16777619UL;
  if (args) for (const char *p = args; *p; ++p) hash = (hash ^ (byte)*p) * 16777619UL;
  if (strcmp(lastId, id) == 0) {
    ack(board, id, hash == lastHash ? lastError : "id_conflict");
    return;
  }
  const char *error = execute(op, args, now);
  strcpy(lastId, id);
  lastHash = hash;
  lastError = error;
  ack(board, id, error);
  state();
}

inline void poll(unsigned long now, const __FlashStringHelper *board,
                 Executor execute, State state, Legacy legacy) {
  static char buffer[96];
  static byte length = 0;
  static bool overflow = false;
  static unsigned long lastChar = 0;
  byte processed = 0;
  while (Serial.available() && processed++ < 64) {
    char c = Serial.read();
    if (c == '\r') continue;
    lastChar = now;
    if (c != '\n' && ((unsigned char)c < 32 || (unsigned char)c > 126)) {
      overflow = true;
      continue;
    }
    if (c == '\n') {
      buffer[length] = '\0';
      if (!overflow && length) {
        if (strncmp(buffer, "DNB1 ", 5) == 0 || strcmp(buffer, "ID") == 0 || strcmp(buffer, "STATE") == 0)
          command(buffer, now, board, execute, state);
        else legacy(buffer, now);
      }
      length = 0; overflow = false;
    } else if (length < sizeof(buffer) - 1 && !overflow) {
      buffer[length++] = c;
    } else overflow = true;
  }
  if ((length || overflow) && now - lastChar >= 800UL) {
    buffer[length] = '\0';
    // Never execute an incomplete structured command through the legacy path.
    if (!overflow && strncmp(buffer, "DNB1", 4) != 0) legacy(buffer, now);
    length = 0; overflow = false;
  }
}
}
#endif
