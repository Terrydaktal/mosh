/* Native scrollback extension. GPL-3.0-or-later, with Mosh's OpenSSL exception. */
#ifndef MOSH_NATIVE_HISTORY_H
#define MOSH_NATIVE_HISTORY_H

#include <deque>
#include <string>
#include <vector>
#include <stdint.h>
#include "terminalframebuffer.h"

namespace Terminal {
  struct HistoryBatch {
    static const size_t MAX_RECORD = 32768;
    static const size_t MAX_BYTES = 8192;
    static const size_t MAX_RECORDS = 128;
    uint64_t first;
    std::vector<std::string> records;

    HistoryBatch() : first(0), records() {}
    uint64_t end() const { return first + records.size(); }
    bool valid() const;
    bool operator==(const HistoryBatch &other) const {
      return first == other.first && records == other.records;
    }
  };

  // Shared only by server-side terminal snapshots. The batch in each snapshot
  // is immutable; the bounded recorder itself is never synchronized or copied.
  class HistoryLog {
    std::deque<std::string> records;
    uint64_t first;
    size_t bytes, max_bytes, max_records;
    std::string pending;
    bool overlong;
    void finish_line();
  public:
    HistoryLog(size_t byte_limit = 8 * 1024 * 1024, size_t record_limit = 100000)
      : records(), first(0), bytes(0), max_bytes(byte_limit),
        max_records(record_limit), pending(), overlong(false) {}
    void append_row(const Row &row);
    void break_line();
    HistoryBatch after(uint64_t acknowledged) const;
    uint64_t end() const { return first + records.size(); }
    size_t retained_bytes() const { return bytes; }
    bool has_pending() const { return !pending.empty() || overlong; }
  };

  class HistoryReplay {
    uint64_t next;
    std::deque<std::string> delivered;
    std::vector<std::string> preserved;
    size_t delivered_bytes;
    bool preserved_partial;
    bool termux_reflow;
    int cached_width;
    uint64_t cached_rows;
    size_t preserved_count(const HistoryBatch &batch) const;
    size_t preserved_bytes(const HistoryBatch &batch) const;
  public:
    explicit HistoryReplay(bool termux_resize = false) : next(0), delivered(), preserved(),
      delivered_bytes(0), preserved_partial(false), termux_reflow(termux_resize),
      cached_width(0), cached_rows(0) {}
    uint64_t acknowledged() const { return next; }
    // Does not advance the acknowledgement until commit(), after stdout drains.
    std::string prepare(const HistoryBatch &batch, int height) const;
    void commit(const HistoryBatch &batch);
    void remember_resize(const Framebuffer &before, int width, int height);
    uint64_t rows_at_width(int width);
    uint64_t pulled_rows(const Framebuffer &before, int width, int height);
    static std::string clear_viewport(int height);
  };
}
#endif
