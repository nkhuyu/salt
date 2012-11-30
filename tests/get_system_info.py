# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
"""
    :copyright: © 2012 UfSoft.org - :email:`Pedro Algarvio (pedro@algarvio.me)`
    :license: BSD, see LICENSE for more details
"""

import sys
import time
import pprint
import psutil


def gather_fds(pid):
    try:
        process = psutil.Process(pid)
    except psutil.error.NoSuchProcess:
        return 0

    try:
        fds = process.get_num_fds()
    except psutil.error.NoSuchProcess:
        return 0

    for child in process.get_children():
        fds += gather_fds(child.pid)
    return fds


def gather_connections(pid):
    try:
        process = psutil.Process(pid)
    except psutil.error.NoSuchProcess:
        return 0

    try:
        connections = len(process.get_connections())
    except psutil.error.NoSuchProcess:
        return 0

    for child in process.get_children():
        connections += gather_connections(child.pid)
    return connections


def gather_open_files_info(pid):
    try:
        process = psutil.Process(pid)
    except psutil.error.NoSuchProcess:
        return 0

    try:
        open_files = len(process.get_open_files())
    except psutil.error.NoSuchProcess:
        return 0

    for child in process.get_children():
        open_files += gather_open_files_info(child.pid)
    return open_files


def get_process_mem_info(pid):
    try:
        process = psutil.Process(pid)
    except psutil.error.NoSuchProcess:
        return -2
    try:
        return process.get_memory_info()
    except psutil.error.NoSuchProcess:
        return -2


def get_process_ext_mem_info(pid):
    try:
        process = psutil.Process(pid)
    except psutil.error.NoSuchProcess:
        return -2
    try:
        return process.get_ext_memory_info()
    except psutil.error.NoSuchProcess:
        return -2


def get_process_memmap(pid):
    try:
        process = psutil.Process(pid)
    except psutil.error.NoSuchProcess:
        return -2
    try:
        return '\n{0}'.format(
            pprint.pformat(
                process.get_memory_maps(), indent=2
            )
        )
    except KeyError:
        return -2


def print_info(pid):
    try:
        fds = gather_fds(pid)
    except:
        fds = -1
    try:
        open_files = gather_open_files_info(pid)
    except:
        open_file = -1

    try:
        connections = gather_connections(pid)
    except:
        connections = -1

    try:
        vmem = psutil.virtual_memory()
    except:
        vmem = -1

    try:
        swap = psutil.swap_memory()
    except:
        swap = -1

    try:
        mi = get_process_mem_info(pid)
    except:
        mi = -1

    try:
        mei = get_process_ext_mem_info(pid)
    except:
        mei = -1

    try:
        mmap = get_process_memmap(pid)
    except Exception, err:
        #print 123, err
        mmap = -1

    thac = threading.active_count()
    mpac = multiprocessing.active_children()
    print
    print '-' * 70
    print '                 Virtual Memory: {0!r}'.format(vmem)
    print '                    Swap Memory: {0!r}'.format(swap)
    print '              Current FDS count: {0}'.format(fds)
    print '             Current open files: {0}'.format(open_files)
    print '      Current connections count: {0}'.format(connections)
    print '            Process Memory Info: {0}'.format(mi)
    print '        Process Ext Memory Info: {0}'.format(mei)
    print '            Active Thread Count: {0}'.format(thac)
    print 'Active Multiprocessing Children: {0}'.format(mpac)
    #print '       Process Memory Map: {0}'.format(mmap)
    print '-' * 70
    print


def run(pid):
    while True:
        try:
            print_info(pid)
            time.sleep(1)
        except KeyboardInterrupt:
            print
            sys.exit(0)

if __name__ == '__main__':
    try:
        pid = int(sys.argv[1])
    except IndexError:
        print 'You need to pass a pid file'
        sys.exit(1)
    except ValueError:
        print '{0} is not a valid pid number'.format(sys.argv[1])
        sys.exit(1)
    run(pid)
