/* Native scrollback extension. GPL-3.0-or-later, with Mosh's OpenSSL exception. */
#include "nativehistory.h"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <stdio.h>
#include <cwchar>

using namespace Terminal;

bool HistoryBatch::valid() const
{
  if (records.size() > MAX_RECORDS || first > UINT64_MAX - records.size()) return false;
  size_t bytes = 0;
  for (size_t i = 0; i < records.size(); ++i) {
    if (records[i].size() > MAX_RECORD) return false;
    bytes += records[i].size();
  }
  return bytes <= MAX_BYTES || (records.size() == 1 && bytes <= MAX_RECORD);
}

void HistoryLog::finish_line()
{
  if (overlong) pending = "\033[0m[mosh-native: overlong history line omitted]";
  pending += "\033[0m\r\n";
  bytes += pending.size();
  records.push_back(pending);
  pending.clear();
  overlong = false;
  while (!records.empty() && (bytes > max_bytes || records.size() > max_records)) {
    bytes -= records.front().size();
    records.pop_front();
    ++first;
  }
}

void HistoryLog::break_line()
{
  if (!pending.empty() || overlong) finish_line();
}

void HistoryLog::append_row(const Row &row)
{
  const bool wrapped = row.get_wrap();
  size_t limit = row.cells.size();
  const Renditions plain(0);
  if (!wrapped) {
    while (limit && row.cells[limit - 1].is_blank()
           && row.cells[limit - 1].get_renditions() == plain) --limit;
  }
  Renditions rendition(0);
  std::string line("\033[0m");
  for (size_t col = 0; col < limit && !overlong; col += row.cells[col].get_width()) {
    const Cell &cell = row.cells[col];
    if (!(cell.get_renditions() == rendition)) {
      rendition = cell.get_renditions();
      line += rendition.sgr();
    }
    cell.print_grapheme(line);
    if (pending.size() + line.size() + 6 > HistoryBatch::MAX_RECORD) overlong = true;
  }
  if (pending.size() + line.size() + 6 > HistoryBatch::MAX_RECORD) overlong = true;
  if (!overlong) pending += line;
  if (!wrapped) finish_line();
}

HistoryBatch HistoryLog::after(uint64_t acknowledged) const
{
  HistoryBatch batch;
  batch.first = std::max(first, std::min(acknowledged, end()));
  size_t bytes = 0;
  for (size_t i = batch.first - first; i < records.size(); ++i) {
    if (!batch.records.empty()
        && (bytes + records[i].size() > HistoryBatch::MAX_BYTES
            || batch.records.size() == HistoryBatch::MAX_RECORDS)) break;
    batch.records.push_back(records[i]);
    bytes += records[i].size();
  }
  return batch;
}

std::string HistoryReplay::clear_viewport(int height)
{
  if (height < 1 || height > 10000) throw std::invalid_argument("invalid history viewport height");
  std::string output("\033[0m\033[?6l\033[?7h\033[r");
  char position[40];
  // ED 2 archives the old viewport in VTE. Erase individual lines instead.
  for (int row = 1; row <= height; ++row) {
    snprintf(position, sizeof(position), "\033[%d;1H\033[2K", row);
    output += position;
  }
  return output + "\033[H";
}

std::string HistoryReplay::prepare(const HistoryBatch &batch, int height) const
{
  if (!batch.valid()) throw std::invalid_argument("invalid native history batch");
  if (batch.end() <= next) return "";
  std::string output;
  if (batch.first > next) {
    char notice[128];
    snprintf(notice, sizeof(notice), "[mosh-native: %llu history records expired while disconnected]\r\n",
             static_cast<unsigned long long>(batch.first - next));
    output += notice;
  }
  const size_t start = next > batch.first ? next - batch.first : 0;
  const size_t skipped = start + preserved_count(batch);
  for (size_t i = skipped; i < batch.records.size(); ++i)
    output += batch.records[i].substr(i == skipped ? preserved_bytes(batch) : 0);
  if (output.empty()) return "";
  output = clear_viewport(height) + output;
  output += "\033[0m";
  for (int i = 1; i < height; ++i) output += "\r\n";
  return output;
}

void HistoryReplay::commit(const HistoryBatch &batch)
{
  if (!batch.valid()) throw std::invalid_argument("invalid native history batch");
  if (batch.end() <= next) return;
  const size_t start = next > batch.first ? next - batch.first : 0;
  const size_t kept = preserved_count(batch);
  const size_t partial = preserved_bytes(batch) ? 1 : 0;
  preserved.erase(preserved.begin(), preserved.begin() + kept + partial);
  if (start + kept < batch.records.size() || preserved.empty()) {
    preserved.clear();
    preserved_partial = false;
  }
  for (size_t i = start; i < batch.records.size(); ++i) {
    delivered.push_back(batch.records[i]);
    delivered_bytes += batch.records[i].size();
  }
  while (!delivered.empty() && (delivered_bytes > 8 * 1024 * 1024 || delivered.size() > 100000)) {
    delivered_bytes -= delivered.front().size();
    delivered.pop_front();
  }
  cached_width = 0;
  next = std::max(next, batch.end());
}

size_t HistoryReplay::preserved_count(const HistoryBatch &batch) const
{
  if (batch.first > next) return 0;
  const size_t start = next > batch.first ? next - batch.first : 0;
  size_t count = 0;
  while (count < preserved.size() && start + count < batch.records.size()
         && preserved[count] == batch.records[start + count]) ++count;
  return count;
}

void HistoryReplay::remember_resize(const Framebuffer &before, int width, int height)
{
  // Real terminals already archive the displaced main-screen prefix on resize.
  Framebuffer reflowed(before);
  shared_ptr<HistoryLog> log = make_shared<HistoryLog>();
  reflowed.set_history_log(log);
  reflowed.resize(width, height, false, termux_reflow);
  preserved_partial = log->has_pending();
  log->break_line();
  // A resize can archive more than one network batch locally.
  preserved.clear();
  for (uint64_t first = 0; first < log->end();) {
    const HistoryBatch batch = log->after(first);
    preserved.insert(preserved.end(), batch.records.begin(), batch.records.end());
    first = batch.end();
  }
}

size_t HistoryReplay::preserved_bytes(const HistoryBatch &batch) const
{
  if (!preserved_partial || batch.first > next) return 0;
  const size_t count = preserved_count(batch);
  const size_t index = (next > batch.first ? next - batch.first : 0) + count;
  if (count + 1 != preserved.size() || index >= batch.records.size()) return 0;
  const std::string &fragment = preserved[count];
  const std::string ending("\033[0m\r\n");
  if (fragment.size() <= ending.size()
      || fragment.compare(fragment.size() - ending.size(), ending.size(), ending) != 0) return 0;
  const size_t length = fragment.size() - ending.size();
  return batch.records[index].compare(0, length, fragment, 0, length) == 0 ? length : 0;
}

uint64_t HistoryReplay::pulled_rows(const Framebuffer &before, int width, int height)
{
  const uint64_t history_rows = rows_at_width(width);
  if (width == before.ds.get_width())
    return std::min<uint64_t>(history_rows, std::max(0, height - before.ds.get_height()));
  Framebuffer reflowed(before);
  reflowed.set_history_log(make_shared<HistoryLog>());
  reflowed.resize(width, 10000, false, termux_reflow);
  int used = reflowed.ds.get_cursor_row() + 1;
  if (termux_reflow && before.ds.get_cursor_row() < before.ds.get_height() - 1) ++used;
  if (!termux_reflow) {
    const int blank_tail = before.ds.get_height() - before.ds.get_cursor_row() - 1;
    used += std::max(0, blank_tail - std::max(0, before.ds.get_height() - height) - 1);
  }
  return std::min<uint64_t>(history_rows, std::max(0, height - used));
}

uint64_t HistoryReplay::rows_at_width(int width)
{
  if (width < 1) throw std::invalid_argument("invalid history width");
  if (cached_width == width) return cached_rows;
  uint64_t rows = 0;
  for (const std::string &record : delivered) {
    int column = 0;
    mbstate_t state = mbstate_t();
    for (size_t i = 0; i < record.size();) {
      if (record[i] == '\033' && i + 1 < record.size() && record[i + 1] == '[') {
        i += 2;
        while (i < record.size() && !(record[i] >= '@' && record[i] <= '~')) ++i;
        if (i < record.size()) ++i;
        continue;
      }
      if (record[i] == '\r') { ++i; continue; }
      if (record[i] == '\n') { ++rows; column = 0; ++i; continue; }
      wchar_t character;
      size_t length = mbrtowc(&character, record.data() + i, record.size() - i, &state);
      if (length == size_t(-1) || length == size_t(-2)) {
        state = mbstate_t(); character = L'?'; length = 1;
      } else if (!length) length = 1;
      int cells = std::max(0, wcwidth(character));
      if (column && column + cells > width) { ++rows; column = 0; }
      column += cells;
      i += length;
    }
    if (column) ++rows;
  }
  cached_width = width;
  return cached_rows = rows;
}
