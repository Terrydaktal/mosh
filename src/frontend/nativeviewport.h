/* Native scrollback extension. GPL-3.0-or-later, with Mosh's OpenSSL exception. */
#ifndef MOSH_NATIVE_VIEWPORT_H
#define MOSH_NATIVE_VIEWPORT_H

#include <limits.h>
#include <stdint.h>
#include <algorithm>
#include <string>

namespace Terminal {
class ResizeDebouncer {
  int columns, rows;
  bool pending_;
  uint64_t deadline;

public:
  ResizeDebouncer(int width = 0, int height = 0)
    : columns(width), rows(height), pending_(false), deadline(0) {}

  bool observe(int width, int height, uint64_t now)
  {
    if (width < 1 || height < 1 || width > 10000 || height > 10000
        || (width == columns && height == rows)) return false;
    columns = width;
    rows = height;
    pending_ = true;
    deadline = now + 120;
    return true;
  }

  bool pending() const { return pending_; }
  bool ready(uint64_t now) const { return pending_ && now >= deadline; }
  void sent() { pending_ = false; }
  int wait_time(uint64_t now) const
  {
    if (!pending_) return INT_MAX;
    return now >= deadline ? 0 : static_cast<int>(deadline - now);
  }
};

// DEC's private cursor reply cannot be confused with an ordinary function key.
// Keep the query local: these bytes must never become shell input on the server.
class ResizeCursorQuery {
  bool enabled_, pending_, stale_, received_, awaiting_;
  int columns_, rows_, expected_row_, row_;
  uint64_t deadline_, partial_deadline_;
  std::string partial_, buffered_;

public:
  ResizeCursorQuery() : enabled_(true), pending_(false), stale_(false), received_(false), awaiting_(false),
    columns_(0), rows_(0), expected_row_(0), row_(0), deadline_(0), partial_deadline_(0), partial_(), buffered_() {}

  bool enabled() const { return enabled_; }
  bool pending() const { return pending_; }
  bool received() const { return received_; }
  void invalidate() { stale_ = true; }
  void begin(int columns, int rows, int expected_row, uint64_t now) {
    columns_ = columns; rows_ = rows; expected_row_ = expected_row;
    buffered_ += partial_; partial_.clear();
    pending_ = true; stale_ = false; received_ = false; awaiting_ = true;
    deadline_ = now + 250;
  }
  int scroll(int columns, int rows) const {
    return received_ && !stale_ && columns == columns_ && rows == rows_
      ? std::max(0, row_ - expected_row_) : -1;
  }
  void consume() { received_ = false; }
  int wait_time(uint64_t now) const {
    int wait = !pending_ ? INT_MAX : now >= deadline_ ? 0 : static_cast<int>(deadline_ - now);
    if (!partial_.empty())
      wait = std::min(wait, now >= partial_deadline_ ? 0 : static_cast<int>(partial_deadline_ - now));
    return wait;
  }
  void expire(uint64_t now) {
    if (pending_ && now >= deadline_) {
      // An unsupported terminal must not stall rendering or swallow Escape.
      pending_ = false; enabled_ = false;
    }
    if (!partial_.empty() && now >= partial_deadline_) {
      // A lone Escape is a real key. A truncated private reply is not.
      if (partial_.compare(0, 3, "\033[?") != 0) buffered_ += partial_;
      partial_.clear();
    }
  }
  std::string take_buffered() {
    std::string result; result.swap(buffered_); return result;
  }
  std::string input(const std::string &bytes, uint64_t now) {
    std::string output;
    for (char byte : bytes) {
      if (!awaiting_) { output += byte; continue; }
      if (byte == '\033' && !partial_.empty()) {
        output += partial_; partial_.clear();
      }
      partial_ += byte;
      partial_deadline_ = now + (partial_.compare(0, 3, "\033[?") == 0 ? 1000 : 20);
      const std::string prefix("\033[?");
      if (partial_.size() <= prefix.size()) {
        if (prefix.compare(0, partial_.size(), partial_) == 0) continue;
      } else if (partial_.compare(0, prefix.size(), prefix) == 0) {
        const bool parameter = (byte >= '0' && byte <= '9') || byte == ';';
        if (parameter && partial_.size() < 32) continue;
        if (byte == 'R') {
          int parameters[3] = {0, 0, 1};
          int count = 1;
          bool valid = true;
          for (size_t i = 3; valid && i + 1 < partial_.size(); ++i) {
            const char digit = partial_[i];
            if (digit == ';') {
              valid = parameters[count - 1] > 0 && count < 3;
              if (valid) parameters[count++] = 0;
            } else if (digit >= '0' && digit <= '9') {
              parameters[count - 1] = parameters[count - 1] * 10 + digit - '0';
              valid = parameters[count - 1] <= 10000;
            } else valid = false;
          }
          if (valid && count >= 2 && parameters[0] > 0 && parameters[1] > 0 && parameters[2] == 1) {
            row_ = parameters[0] - 1;
            received_ = pending_;
            stale_ = stale_ || parameters[0] > rows_ || parameters[1] > columns_;
            pending_ = false; awaiting_ = false; partial_.clear();
            continue;
          }
        }
      }
      output += partial_; partial_.clear();
    }
    return output;
  }
};
}

#endif
