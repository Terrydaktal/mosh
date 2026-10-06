/*
    Mosh: the mobile shell
    Copyright 2012 Keith Winstein

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    In addition, as a special exception, the copyright holders give
    permission to link the code of portions of this program with the
    OpenSSL library under certain conditions as described in each
    individual source file, and distribute linked combinations including
    the two.

    You must obey the GNU General Public License in all respects for all
    of the code used other than OpenSSL. If you modify file(s) with this
    exception, you may extend this exception to your version of the
    file(s), but you are not obligated to do so. If you do not wish to do
    so, delete this exception statement from your version. If you delete
    this exception statement from all source files in the program, then
    also delete it here.
*/

#include "completeterminal.h"
#include "fatal_assert.h"

#include "hostinput.pb.h"

#include <limits.h>

using namespace std;
using namespace Parser;
using namespace Terminal;
using namespace HostBuffers;

string Complete::act( const string &str )
{
  for ( unsigned int i = 0; i < str.size(); i++ ) {
    /* parse octet into up to three actions */
    parser.input( str[ i ], actions );
    
    /* apply actions to terminal and delete them */
    for ( Actions::iterator it = actions.begin();
	  it != actions.end();
	  it++ ) {
      Action &act = **it;
      act.act_on_terminal( &terminal );
    }
    actions.clear();
  }

  refresh_history();
  return terminal.read_octets_to_host();
}

string Complete::act( const Action &act )
{
  /* apply action to terminal */
  act.act_on_terminal( &terminal );
  refresh_history();
  return terminal.read_octets_to_host();
}

void Complete::enable_history(size_t bytes, size_t records)
{
  terminal.set_history_log(make_shared<HistoryLog>(bytes, records));
  history_ack = 0;
  refresh_history();
}

void Complete::refresh_history()
{
  shared_ptr<HistoryLog> log = terminal.get_fb().get_history_log();
  if (log) history_batch = log->after(history_ack);
}

void Complete::acknowledge_history(uint64_t ack)
{
  // Never acknowledge future output. This cursor is separate from replaceable
  // screen snapshots and moves only after the client has written the history.
  if (ack > history_ack && ack <= history_batch.end()) {
    history_ack = ack;
    refresh_history();
  }
}

void Complete::finish_history()
{
  shared_ptr<HistoryLog> log = terminal.get_fb().get_history_log();
  if (log) log->break_line();
  refresh_history();
}

/* interface for Network::Transport */
string Complete::diff_from( const Complete &existing ) const
{
  HostBuffers::HostMessage output;
  if (!(history_batch == existing.history_batch)) {
    NativeHistory *history = output.add_instruction()->MutableExtension(native_history);
    history->set_first(history_batch.first);
    for (size_t i = 0; i < history_batch.records.size(); ++i)
      history->add_record(history_batch.records[i]);
  }

  if ( existing.get_echo_ack() != get_echo_ack() ) {
    assert( get_echo_ack() >= existing.get_echo_ack() );
    Instruction *new_echo = output.add_instruction();
    new_echo->MutableExtension( echoack )->set_echo_ack_num( get_echo_ack() );
  }

  if ( !(existing.get_fb() == get_fb()) ) {
    if ( (existing.get_fb().ds.get_width() != terminal.get_fb().ds.get_width())
	 || (existing.get_fb().ds.get_height() != terminal.get_fb().ds.get_height()) ) {
      Instruction *new_res = output.add_instruction();
      new_res->MutableExtension( resize )->set_width( terminal.get_fb().ds.get_width() );
      new_res->MutableExtension( resize )->set_height( terminal.get_fb().ds.get_height() );
    }
    string update = display.new_frame( true, existing.get_fb(), terminal.get_fb() );
    if ( !update.empty() ) {
      Instruction *new_inst = output.add_instruction();
      new_inst->MutableExtension( hostbytes )->set_hoststring( update );
    }
  }
  
  return output.SerializeAsString();
}

string Complete::init_diff( void ) const
{
  return diff_from( Complete( get_fb().ds.get_width(), get_fb().ds.get_height() ));
}

void Complete::apply_string( const string & diff )
{
  HostBuffers::HostMessage input;
  fatal_assert( input.ParseFromString( diff ) );

  for ( int i = 0; i < input.instruction_size(); i++ ) {
    if (input.instruction(i).HasExtension(native_history)) {
      const NativeHistory &history = input.instruction(i).GetExtension(native_history);
      fatal_assert(history.has_first());
      fatal_assert(history.record_size() <= static_cast<int>(HistoryBatch::MAX_RECORDS));
      HistoryBatch batch;
      batch.first = history.first();
      for (int j = 0; j < history.record_size(); ++j) batch.records.push_back(history.record(j));
      fatal_assert(batch.valid());
      history_batch = batch;
    } else if ( input.instruction( i ).HasExtension( hostbytes ) ) {
      string terminal_to_host = act( input.instruction( i ).GetExtension( hostbytes ).hoststring() );
      assert( terminal_to_host.empty() ); /* server never interrogates client terminal */
    } else if ( input.instruction( i ).HasExtension( resize ) ) {
      act( Resize( input.instruction( i ).GetExtension( resize ).width(),
				      input.instruction( i ).GetExtension( resize ).height() ) );
    } else if ( input.instruction( i ).HasExtension( echoack ) ) {
      uint64_t inst_echo_ack_num = input.instruction( i ).GetExtension( echoack ).echo_ack_num();
      assert( inst_echo_ack_num >= echo_ack );
      echo_ack = inst_echo_ack_num;
    }
  }
}

bool Complete::operator==( Complete const &x ) const
{
  //  assert( parser == x.parser ); /* parser state is irrelevant for us */
  return (terminal == x.terminal) && (echo_ack == x.echo_ack) && (history_batch == x.history_batch);
}

bool Complete::set_echo_ack( uint64_t now )
{
  bool ret = false;
  uint64_t newest_echo_ack = 0;

  for ( input_history_type::const_iterator i = input_history.begin();
        i != input_history.end();
        i++ ) {
    if ( i->second <= now - ECHO_TIMEOUT ) {
      newest_echo_ack = i->first;
    }
  }

  for ( input_history_type::iterator i = input_history.begin();
	i != input_history.end(); ) {
    input_history_type::iterator i_next = i;
    i_next++;
    if ( i->first < newest_echo_ack ) {
      input_history.erase( i );
    }
    i = i_next;
  }

  if ( echo_ack != newest_echo_ack ) {
    ret = true;
  }

  echo_ack = newest_echo_ack;

  return ret;
}

void Complete::register_input_frame( uint64_t n, uint64_t now )
{
  input_history.push_back( std::make_pair( n, now ) );
}

int Complete::wait_time( uint64_t now ) const
{
  if ( input_history.size() < 2 ) {
    return INT_MAX;
  }

  input_history_type::const_iterator it = input_history.begin();
  it++;

  uint64_t next_echo_ack_time = it->second + ECHO_TIMEOUT;
  if ( next_echo_ack_time <= now ) {
    return 0;
  }
  return next_echo_ack_time - now;
}

bool Complete::compare( const Complete &other ) const
{
  bool ret = false;
  const Framebuffer &fb = terminal.get_fb();
  const Framebuffer &other_fb = other.terminal.get_fb();
  const int height = fb.ds.get_height();
  const int other_height = other_fb.ds.get_height();
  const int width = fb.ds.get_width();
  const int other_width = other_fb.ds.get_width();

  if ( height != other_height || width != other_width ) {
    fprintf( stderr, "Framebuffer size (%dx%d, %dx%d) differs.\n", width, height, other_width, other_height );
    return true;
  }

  for ( int y = 0; y < height; y++ ) {
    for ( int x = 0; x < width; x++ ) {
      if ( fb.get_cell( y, x )->compare( *other_fb.get_cell( y, x ) ) ) {
	fprintf( stderr, "Cell (%d, %d) differs.\n", y, x );
	ret = true;
      }
    }
  }

  if ( (fb.ds.get_cursor_row() != other_fb.ds.get_cursor_row())
       || (fb.ds.get_cursor_col() != other_fb.ds.get_cursor_col()) ) {
    fprintf( stderr, "Cursor mismatch: (%d, %d) vs. (%d, %d).\n",
	     fb.ds.get_cursor_row(), fb.ds.get_cursor_col(),
	     other_fb.ds.get_cursor_row(), other_fb.ds.get_cursor_col() );
    ret = true;
  }
  /* XXX should compare other terminal state too (mouse mode, bell. etc.) */

  return ret;
}
