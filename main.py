#!/usr/bin/python3

import sys
import re

from util import *
import matcher
import session as wl_session
import wl.parse_debug as parse
from wl import protocol
import gdb_integration as gdb
from output import stream
from output import Output
import util

example_usage = 'WAYLAND_DEBUG=1 program 2>&1 1>/dev/null | ' + sys.argv[0]

def interactive_shell(session):
    while session.stopped():
        if session.quit():
            break
        cmd = input('wl debug $ ')
        session.command(cmd)

def parse_messages(session, input_file, allow_shell):
    session.out.log('Parsing messages')
    known_connections = {}
    last_time = 0
    for conn_id, msg in parse.file(input_file, session.out):
        last_time = msg.timestamp
        if not conn_id in known_connections:
            known_connections[conn_id] = True
            is_server = None
            if msg.name ==  'get_registry':
                is_server = not msg.sent
            session.open_connection(conn_id, is_server, last_time)
        session.message(conn_id, msg)
    for conn_id in known_connections.keys():
        session.close_connection(conn_id, last_time)
    if allow_shell:
        interactive_shell(session)
    session.out.log('Done')

def piped_input_main(session):
    session.out.log('Getting input piped from stdin')
    parse_messages(session, sys.stdin, False)

def file_input_main(session, file_path):
    session.out.log('Opening ' + file_path)
    try:
        input_file = open(file_path)
        parse_messages(session, input_file, True)
        input_file.close()
    except FileNotFoundError:
        session.out.error(file_path + ' not found')

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Debug Wayland protocol messages, see https://github.com/wmww/wayland-debug for additional info')
    parser.add_argument('--matcher-help', action='store_true', help='show how to write matchers and exit')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output, mostly used for debugging this program')
    parser.add_argument('-l', '--load', dest='path', type=str, help='load Wayland events from a file instead of stdin')
    parser.add_argument('-s', '--supress', action='store_true', help='supress non-wayland output of the program')
    parser.add_argument('-c', '--color', action='store_true', help='force color output (default for interactive sessions)')
    parser.add_argument('-C', '--no-color', action='store_true', help='disable color output (default for non-interactive sessions)')
    parser.add_argument('-f', '--filter', dest='f', type=str, help='only show these objects/messages (see --matcher-help for syntax)')
    parser.add_argument('-b', '--break', dest='b', type=str, help='stop on these objects/messages (see --matcher-help for syntax)')
    parser.add_argument('-g', '--gdb', action='store_true', help='run inside gdb, all subsequent arguments are sent to gdb, when inside gdb start commands with \'wl\'')
    # NOTE: -d/--gdb is here only for the help text, it is processed without argparse in gdb_runner.main()

    args = parser.parse_args()

    assert not args.gdb, 'GDB argument should have been intercepted by gdb.runner.parse_args()'

    if check_gdb():
        out_stream, err_stream = gdb.plugin.output_streams()
    else:
        out_stream = stream.Std(sys.stdout)
        err_stream = stream.Std(sys.stderr)

    if args.no_color:
        set_color_output(False)
    elif args.color:
        set_color_output(True)

    verbose = bool(args.verbose)
    unprocessed_output = not bool(args.supress)
    output = Output(verbose, unprocessed_output, out_stream, err_stream)

    if verbose:
        set_verbose(True)
        output.log('Verbose output enabled')

    if args.no_color:
        if args.color:
            output.warn('Ignoring --color, since --no-color was also specified')
        output.log('Color output disabled')
    elif args.color:
        s = ''
        i = 0
        for i, c in enumerate('Color output enabled'):
            s += color('1;' + str(i % 6 + 31), c)
        output.log(s)

    if unprocessed_output:
        output.log('Showing unparsable output')

    if args.matcher_help:
        matcher.print_help()
        exit(1)

    filter_matcher = matcher.always
    if args.f:
        try:
            filter_matcher = matcher.parse(args.f).simplify()
            output.log('Filter matcher: ' + str(filter_matcher))
        except RuntimeError as e:
            output.error(e)

    stop_matcher = matcher.never
    if args.b:
        try:
            stop_matcher = matcher.parse(args.b).simplify()
            output.log('Break matcher: ' + str(stop_matcher))
        except RuntimeError as e:
            output.error(e)

    protocol.load_all(output)

    session = wl_session.Session(filter_matcher, stop_matcher, output)

    file_path = args.path

    if check_gdb():
        try:
            if file_path:
                output.warn('Ignoring load file because we\'re inside GDB')
            gdb.plugin.main(session)
        except:
            import traceback
            traceback.print_exc()
    elif file_path:
        file_input_main(session, file_path)
    else:
        if args.b:
            output.warn('Ignoring stop matcher when stdin is used for messages')
        piped_input_main(session)

if __name__ == '__main__':
    # If both of these are false, we might be redirecting to a file (or in another non-interactive context)
    # If we're not being run interactivly, we shouldn't use terminal color codes
    if util.check_gdb() or (hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()):
        set_color_output(True)

    # If we want to run inside GDB, the normal main does not get called in this instance of the script
    # Instead GDB is run, an instance of wayland-debug is run inside it and main() is run in that
    # gdb.runner.parse_args() will check if this needs to happen, and gdb.runner.main() will do it
    gdb_runner_args = None
    if not util.check_gdb():
        gdb_runner_args = gdb.runner.parse_args(sys.argv)
    if gdb_runner_args:
        gdb.runner.main(gdb_runner_args)
    else:
        main()

