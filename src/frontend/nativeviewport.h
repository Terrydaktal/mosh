/* Native scrollback extension. GPL-3.0-or-later, with Mosh's OpenSSL exception. */
#ifndef MOSH_NATIVE_VIEWPORT_H
#define MOSH_NATIVE_VIEWPORT_H

#include <limits.h>
#include <stdint.h>

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
}

#endif
