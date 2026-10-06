#include "completeterminal.h"
#include "nativehistory.h"
#include "nativeviewport.h"
#include "user.h"
#include <assert.h>
#include <cctype>
#include <clocale>
#include <iostream>
#include <set>
#include <stdexcept>

using namespace Terminal;

static size_t occurrences(const std::string &text, const std::string &needle)
{
  size_t n = 0, pos = 0;
  while ((pos = text.find(needle, pos)) != std::string::npos) { ++n; pos += needle.size(); }
  return n;
}

static std::string lines(int count)
{
  std::string result;
  for (int i = 0; i < count; ++i) result += "record-" + std::to_string(i) + "-end\r\n";
  return result;
}

static void transfer()
{
  Complete server(80, 24), client(80, 24);
  server.enable_history();
  server.act(lines(4000));
  server.act(std::string(24, '\n'));
  HistoryReplay replay;
  std::string transcript;
  std::string delayed;
  for (int round = 0; round < 300 && replay.acknowledged() < 4000; ++round) {
    // Keep changing the live screen while history is backlogged.
    server.act("\033[Hlive-" + std::to_string(round) + "\033[K");
    const std::string update = server.init_diff();
    if (round % 5 == 0) continue; // lost host update
    client.apply_string(update);
    const HistoryBatch batch = client.get_history();
    const std::string rendered = replay.prepare(batch, 24);
    transcript += rendered;
    replay.commit(batch);
    assert(replay.prepare(batch, 24).empty()); // duplicate
    if (!delayed.empty()) {
      Complete old(80, 24);
      old.apply_string(delayed);
      assert(replay.prepare(old.get_history(), 24).empty()); // delayed old batch
    }
    delayed = update;
    assert(client.get_fb().get_cell(0, 0)->debug_contents().find("l") != std::string::npos);
    Network::UserStream ack, decoded;
    ack.acknowledge_history(replay.acknowledged());
    decoded.apply_string(ack.init_diff());
    assert(decoded.empty()); // acknowledgements are not keystrokes
    if (round % 4 != 0) server.acknowledge_history(decoded.get_history_ack()); // lost ACK
  }
  assert(replay.acknowledged() >= 4000);
  for (int i = 0; i < 4000; ++i)
    assert(occurrences(transcript, "record-" + std::to_string(i) + "-end") == 1);
  assert(transcript.find("\033[2J") == std::string::npos);
  assert(transcript.find("\033[3J") == std::string::npos);
  assert(transcript.find("\033[?1049h") == std::string::npos);
}

static void bounds()
{
  Complete server(80, 4);
  server.enable_history(1024, 8);
  server.act(lines(100));
  const HistoryBatch batch = server.get_history();
  assert(batch.valid());
  assert(batch.first > 0 && batch.records.size() <= 8);
  HistoryReplay replay;
  assert(replay.prepare(batch, 4).find("expired while disconnected") != std::string::npos);
  server.acknowledge_history(UINT64_MAX);
  assert(server.get_history() == batch);
  HistoryBatch invalid;
  invalid.first = UINT64_MAX;
  invalid.records.push_back("x");
  assert(!invalid.valid());
  invalid.first = 0;
  invalid.records[0] = std::string(HistoryBatch::MAX_RECORD + 1, 'x');
  assert(!invalid.valid());
  bool rejected = false;
  try { replay.prepare(invalid, 24); } catch (const std::invalid_argument &) { rejected = true; }
  assert(rejected);
  Complete longline(20, 4);
  longline.enable_history();
  longline.act(std::string(50000, 'x') + "\r\n" + std::string(4, '\n'));
  assert(longline.get_history().valid());
  assert(longline.get_history().records[0].find("overlong history line omitted") != std::string::npos);
}

static void modes()
{
  Complete terminal(20, 4);
  terminal.enable_history();
  terminal.act("\033[?1049h" + lines(40));
  assert(terminal.get_history().end() == 0);
  terminal.act("\033[?1049l\033[2;4r" + lines(40));
  assert(terminal.get_history().end() == 0);
  terminal.act("\033[r\033[H\033[2J\033[31m" + std::string(100, 'X') + "\033[0m\r\n" + std::string(4, '\n'));
  const auto batch = terminal.get_history();
  assert(!batch.records.empty());
  assert(occurrences(batch.records[0], "X") == 100);
  assert(batch.records[0].find("31") != std::string::npos);
  assert(occurrences(batch.records[0], "\r\n") == 1);
  Display native(false, true);
  assert(native.open().find("1049h") == std::string::npos);
  assert(native.new_frame(false, terminal.get_fb(), terminal.get_fb()).find("\033[2J") == std::string::npos);
}

static void resize_bursts()
{
  ResizeDebouncer resize(80, 24);
  assert(!resize.observe(80, 24, 0));
  assert(!resize.observe(0, 0, 0));
  assert(!resize.pending());
  assert(resize.observe(80, 20, 100));
  assert(!resize.ready(219));
  assert(resize.ready(220));
  assert(resize.observe(80, 16, 150));
  assert(resize.observe(80, 12, 200));
  assert(!resize.observe(80, 12, 250)); // duplicate must not prolong the pause
  assert(!resize.ready(319));
  assert(resize.wait_time(319) == 1);
  assert(resize.ready(320));
  resize.sent();
  assert(!resize.pending() && !resize.ready(400));
  assert(resize.wait_time(400) == INT_MAX);
  assert(resize.observe(80, 24, 500));
  assert(!resize.ready(619) && resize.ready(620));
}

static std::string compact_contents(const Complete &terminal)
{
  std::string text;
  for (const auto &record : terminal.get_history().records) text += record;
  const Framebuffer &fb = terminal.get_fb();
  for (int row = 0; row < fb.ds.get_height(); ++row)
    for (int col = 0; col < fb.ds.get_width(); col += fb.get_cell(row, col)->get_width())
      fb.get_cell(row, col)->print_grapheme(text);
  std::string compact;
  for (size_t i = 0; i < text.size(); ++i) {
    if (text[i] == '\033' && i + 1 < text.size() && text[i + 1] == '[') {
      i += 2;
      while (i < text.size() && !(text[i] >= '@' && text[i] <= '~')) ++i;
    } else if (!std::isspace(static_cast<unsigned char>(text[i]))) compact += text[i];
  }
  return compact;
}

static void wrapped_resize()
{
  Complete terminal(93, 71);
  terminal.enable_history();
  std::string output("header\r\n\033[31m");
  for (int row = 0; row < 18; ++row)
    output += "row-" + std::to_string(row) + std::string(170, char('a' + row))
      + "\xe7\xba\xa2\xe9\xad\x94-end\r\n";
  output += "\033[0mprompt> ";
  terminal.act(output);
  const std::string before = compact_contents(terminal);
  for (const auto &size : {std::pair<int, int>(61, 38), {93, 20}, {93, 71},
                           {51, 85}, {81, 85}, {93, 71}}) {
    terminal.act(Parser::Resize(size.first, size.second));
    assert(compact_contents(terminal) == before);
  }
  terminal.act("typed-after-zoom");
  assert(compact_contents(terminal) == before + "typed-after-zoom");

  HistoryReplay replay;
  replay.remember_resize(terminal.get_fb(), 93, 20);
  terminal.act(Parser::Resize(93, 20));
  const HistoryBatch first = terminal.get_history();
  replay.prepare(first, 20);
  replay.commit(first);
  assert(replay.prepare(first, 20).empty());
  const uint64_t wider = replay.rows_at_width(93);
  assert(replay.rows_at_width(51) >= wider);
  assert(replay.rows_at_width(93) == wider);
}

static void resize_history_spans_batches()
{
  for (bool record_limit : {false, true}) {
    Complete terminal(record_limit ? 20 : 93, record_limit ? 300 : 71);
    terminal.enable_history();
    if (record_limit) {
      terminal.act(lines(240) + "prompt> ");
    } else {
      std::string output;
      for (int row = 0; row < 18; ++row) {
        output += "row-" + std::to_string(row) + ": ";
        for (int part = 0; part < 6; ++part)
          output += "[abcdefghijklmnopqrstuvwxyz\xe7\xba\xa2\xe9\xad\x94\xe7\x95\x8c-e\xcc\x81]";
        output += "-end\r\n";
      }
      terminal.act(output + "prompt> ");
    }
    const int width = record_limit ? 20 : 5;
    HistoryReplay replay(true);
    replay.remember_resize(terminal.get_fb(), width, 4);

    Framebuffer resized(terminal.get_fb());
    shared_ptr<HistoryLog> log = make_shared<HistoryLog>();
    resized.set_history_log(log);
    resized.resize(width, 4, false, true);
    log->break_line();
    assert(log->end() > log->after(0).end());

    int batches = 0;
    while (replay.acknowledged() < log->end()) {
      const HistoryBatch batch = log->after(replay.acknowledged());
      assert(!batch.records.empty());
      // Every packet is already in native scrollback, not only the first one.
      assert(replay.prepare(batch, 4).empty());
      replay.commit(batch);
      ++batches;
    }
    assert(batches > 1);
  }
}

static void resize_cursor_queries()
{
  ResizeCursorQuery query;
  assert(query.input("ordinary\033[1;2R", 0) == "ordinary\033[1;2R");
  query.begin(152, 161, 0, 100);
  assert(query.input("typed\033[?", 101) == "typed");
  assert(query.input("81;12;1Rmore", 102) == "more");
  assert(query.received() && !query.pending());
  assert(query.scroll(152, 161) == 80);
  assert(query.scroll(81, 59) == -1);
  query.consume();

  query.begin(80, 24, 4, 200);
  assert(query.input("\033", 201).empty());
  assert(query.input("\033[?6;10R", 202) == "\033");
  assert(query.scroll(80, 24) == 1);
  query.consume();

  query.begin(80, 24, 0, 300);
  query.invalidate();
  assert(query.input("\033[?10;2;1R", 301).empty());
  assert(query.received() && query.scroll(80, 24) == -1);
  query.consume();

  query.begin(80, 24, 0, 400);
  const std::string overflow("\033[?9999999999999999999999999;2;1R");
  assert(query.input(overflow, 401) == overflow);
  assert(query.input("\033[A\003", 402) == "\033[A\003");
  assert(!query.received());
  assert(query.input("\033", 403).empty());
  query.expire(425);
  assert(query.take_buffered() == "\033");
  assert(query.pending());
  query.expire(650);
  assert(!query.pending() && !query.enabled());
  assert(query.wait_time(650) == INT_MAX);
  assert(query.input("late\033[?4;2;1Rkeys", 651) == "latekeys");
  assert(!query.received());
}

static void cursor_boundary_resize()
{
  Complete original(152, 161);
  original.enable_history();
  original.act(lines(24) + "prompt> ");
  for (int width : {2, 3, 5, 8, 12, 20}) {
    Framebuffer reflowed(original.get_fb());
    reflowed.set_history_log(shared::make_shared<HistoryLog>());
    reflowed.resize(width, 6, false, true);
    // Independently measured with the Google Play Termux emulator. The cursor
    // reflows with its blank cell, including when prompt length % width == 0.
    assert(reflowed.ds.get_cursor_row() == 4);
    assert(reflowed.ds.get_cursor_col() == 8 % width);
  }
}

int main()
{
  std::setlocale(LC_ALL, "C.UTF-8");
  transfer();
  bounds();
  modes();
  resize_bursts();
  wrapped_resize();
  resize_history_spans_batches();
  resize_cursor_queries();
  cursor_boundary_resize();
  std::cout << "native history: transfer, loss, duplicate, bounds, wrap, modes, resize bursts, wide viewport conservation, multi-batch resize replay, bounded cursor-query input isolation, cursor-boundary reflow passed\n";
}
