#!/usr/bin/env python

# Superfsmon - Supervisor plugin to watch a directory and restart
#              programs on changes
#
# Copyright (C) 2018  Tim Schumacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import os
import sys
import time
import argparse
import re
import signal
import threading

try:
    import xmlrpc.client as xmlrpclib
except ImportError:
    import xmlrpclib

from supervisor import childutils
from watchdog.observers import Observer
from watchdog.events import (PatternMatchingEventHandler,
                             RegexMatchingEventHandler)


parser = argparse.ArgumentParser(
        description='Supervisor plugin to watch a directory and restart '
                    'programs on changes')

parser.add_argument('-e', '--enable', metavar='FLAG', type=int,
        help='disable functionality if flag is not set')
parser.add_argument('--disable', metavar='FLAG', nargs='?', type=int, const=1,
        help='disable functionality if flag is set ')

monitor_group = parser.add_argument_group('directory monitoring')
monitor_group.add_argument('path', metavar='PATH',
        help='directory path to watch for changes')
monitor_group.add_argument('-r', '--recognize', metavar='PATTERN',
        action='append', default=None,
        help='recognize changes to file paths matching the pattern')
monitor_group.add_argument('-i', '--ignore', metavar='PATTERN',
        action='append', default=[],
        help='ignore changes to file paths matching the pattern')
monitor_group.add_argument('--recognize-regex', metavar='REGEX',
        action='append', default=None,
        help='recognize changes to file paths matching the regular expression')
monitor_group.add_argument('--ignore-regex', metavar='REGEX',
        action='append', default=[],
        help='ignore changes to file paths matching the regular expression')
monitor_group.add_argument('-f', '--hidden-files',
        dest='ignore_hidden', action='store_false',
        help='recognize changes to hidden files')
monitor_group.add_argument('-c', '--case-insensitive', 
        dest='case_sensitive', action='store_false',
        help='case insensitive file path matching')
monitor_group.add_argument('-d', '--directories',
        dest='ignore_directories', action='store_false',
        help='recognize changes to directories')
monitor_group.add_argument('--no-recursion',
        dest='recursive', action='store_false',
        help="don't watch for changes in subdirectories")

program_group = parser.add_argument_group('programs')
program_group.add_argument('program', metavar='PROG', nargs='*',
        help="supervisor program name to restart")
program_group.add_argument('-g', '--group', action='append', default=[],
        help='supervisor group name to restart')
program_group.add_argument('-a', '--any', action='store_true',
        help='restart any child of this supervisor')


pre_restarting_lock = threading.Lock()
restarting_lock = threading.Lock()


def info(msg, file=sys.stdout):
    print('superfsmon: ' + msg, file=file)
    file.flush()


def error(msg, status=1):
    info('error: ' + msg, file=sys.stderr)
    sys.exit(status)


def usage_error(msg):
    parser.print_usage(file=sys.stderr)
    error(msg, status=2)


def validate_args(args):
    if args.enable is not None and args.disable is not None:
        usage_error('argument --enable not allowed with --disable')

    if ((args.recognize or args.ignore) and
        (args.recognize_regex or args.ignore_regex)):
        usage_error('arguments --recognize and --ignore not allowed with '
                    '--recognize-regex and --ignore-regex')

    if args.program and args.any:
        usage_error('argument PROG not allowed with --any')
    if args.group and args.any:
        usage_error('argument --group not allowed with --any')
    if not args.program and not args.group and not args.any:
        usage_error('one of the arguments PROG --group --any is required')


def handle_term(signum, frame):
    info('terminating')
    try:
        observer.stop()
    except NameError:
        sys.exit()


def requires_restart(proc):
    name = proc['name']
    group = proc['group']
    statename = proc['statename']
    pid = proc['pid']

    programs_regex = f'^(({")|(".join(args.program)}))$' if args.program else None
    groups_regex = f'^(({")|(".join(args.group)}))$' if args.group else None

    return ((statename == 'STARTING' or statename == 'RUNNING') and
            (
              args.any
              or (programs_regex and re.search(programs_regex, name))
              or (groups_regex and re.search(groups_regex, group))
            ) and
            pid != os.getpid())


def restart_programs():
    info('restarting programs')

    procs = rpc.supervisor.getAllProcessInfo()
    restart_names = [proc['group'] + ':' + proc['name']
                     for proc in procs if requires_restart(proc)]

    for name in list(restart_names):
        try:
            rpc.supervisor.stopProcess(name, False)
        except xmlrpclib.Fault as exc:
            info('warning: failed to stop process: ' + exc.faultString)
            restart_names.remove(name)

    while restart_names:
        for name in list(restart_names):
            proc = rpc.supervisor.getProcessInfo(name)
            if proc['statename'] != 'STOPPED':
                continue
            try:
                rpc.supervisor.startProcess(name, False)
                restart_names.remove(name)
            except xmlrpclib.Fault as exc:
                info('warning: failed to start process: ' + exc.faultString)
                restart_names.remove(name)
        time.sleep(0.1)


def commence_restart():
    if not pre_restarting_lock.acquire(False):
        return
    info('detected change, commencing restart of programs')
    time.sleep(0.1)
    restarting_lock.acquire()
    pre_restarting_lock.release()
    restart_programs()
    restarting_lock.release()


class RestartEventHandler(object):

    def on_any_event(self, event):
        thread = threading.Thread(target=commence_restart)
        thread.start()


class RestartRegexMatchingEventHandler(RestartEventHandler,
                                       RegexMatchingEventHandler):
    pass


class RestartPatternMatchingEventHandler(RestartEventHandler,
                                         PatternMatchingEventHandler):
    pass


def main():
    global args
    args = parser.parse_args()
    validate_args(args)

    if args.enable == 0 or args.disable:
        info('functionality disabled, waiting for termination signal')
        signal.signal(signal.SIGINT,  handle_term)
        signal.signal(signal.SIGTERM, handle_term)
        signal.pause()

    if args.recognize_regex or args.ignore_regex:
        try:
            event_handler = RestartRegexMatchingEventHandler(
                    regexes=args.recognize_regex or ['.*'],
                    ignore_regexes=args.ignore_regex
                    + ['.*/\..*'] if args.ignore_hidden else [],
                    ignore_directories=args.ignore_directories,
                    case_sensitive=args.case_sensitive)
        except re.error as exc:
            error('regex: ' + str(exc))
    else:
        event_handler = RestartPatternMatchingEventHandler(
                patterns=args.recognize,
                ignore_patterns=args.ignore
                + ['*/.*'] if args.ignore_hidden else [],
                ignore_directories=args.ignore_directories,
                case_sensitive=args.case_sensitive)

    observer = Observer()
    observer.schedule(event_handler, args.path, recursive=args.recursive)

    try:
        global rpc
        rpc = childutils.getRPCInterface(os.environ)
    except KeyError as exc:
        error('missing environment variable ' + str(exc))

    info('watching ' + args.path)

    try:
        observer.start()
    except OSError as exc:
        error(str(exc))

    signal.signal(signal.SIGINT,  handle_term)
    signal.signal(signal.SIGTERM, handle_term)

    while observer.is_alive():
        observer.join(1)

if __name__ == '__main__':
    main()
