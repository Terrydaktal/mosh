/* Native scrollback extension. GPL-3.0-or-later, with Mosh's OpenSSL exception. */
#include "nativehistory.h"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <stdio.h>

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
  std::string output = clear_viewport(height);
  if (batch.first > next) {
    char notice[128];
    snprintf(notice, sizeof(notice), "[mosh-native: %llu history records expired while disconnected]\r\n",
             static_cast<unsigned long long>(batch.first - next));
    output += notice;
  }
  for (size_t i = next > batch.first ? next - batch.first : 0; i < batch.records.size(); ++i)
    output += batch.records[i];
  output += "\033[0m";
  for (int i = 1; i < height; ++i) output += "\r\n";
  return output;
}

void HistoryReplay::commit(const HistoryBatch &batch)
{
  if (!batch.valid()) throw std::invalid_argument("invalid native history batch");
  next = std::max(next, batch.end());
}
