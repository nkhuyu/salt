# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
"""
    :copyright: © 2012 UfSoft.org - :email:`Pedro Algarvio (pedro@algarvio.me)`
    :license: Apache 2.0, see LICENSE for more details
"""

# Import python modules
import os
import logging
import cPickle
import tempfile

# Import Salt modules
from salt.exceptions import CommandExecutionError


log = logging.getLogger(__name__)


def __virtual__():
    if __grains__.get('id') not in ('minion', 'sub_minion'):
        return 'runtests'
    return None


def run_tests(module=False, state=False, client=False, shell=False,
              runner=False, unit=False, verbose=1, xml=False, name=[],
              clean=False, no_clean=False, run_destructive=False,
              no_report=False, coverage=False, no_coverage_report=False,
              coverage_output=None, pnum=70):

    """
    Run tests.
    """
    python_bin = '/tmp/ve/bin/python'
    runtests_bin = '/salt/source/tests/runtests.py'

    if not __salt__['cmd.has_exec'](python_bin):
        raise CommandExecutionError(
            'The python binary {0!r} not found or not executable'.format(
                python_bin
            )
        )

    if not __salt__['cmd.has_exec'](runtests_bin):
        raise CommandExecutionError(
            'The runtests binary {0!r} not found or not executable'.format(
                runtests_bin
            )
        )

    try:
        verbose = int(verbose)
    except ValueError, err:
        log.error(
            'Failed to convert {0!r} to an int. '
            'Defaulting to verbose=1. Error: {1}'.format(
                verbose, err
            )
        )
        verbose = 1

    arg = []
    if module:
        arg.append('--module')
    if state:
        arg.append('--state')
    if client:
        arg.append('--client')
    if shell:
        arg.append('--shell')
    if runner:
        arg.append('--runner')
    if unit:
        arg.append('--unit')
    if verbose > 0:
        arg.append('-{0}'.format('v' * verbose))
    if xml:
        arg.append('--xml')
    for test in name:
        arg.append('-n {0}'.format(test))
    if clean:
        arg.append('--clean')
    if no_clean:
        arg.append('--no-clean')
    if run_destructive:
        arg.append('--run-destructive')
    if no_report:
        arg.append('--no-report')
    if coverage:
        arg.append('--coverage')
    if no_coverage_report:
        arg.append('--no-coverage-report')
    if coverage_output:
        arg.append('--coverage-output={0}'.format(coverage_output))

    env = dict(COLUMNS=str(pnum), PNUM=str(pnum))
    cmd = 'COLUMNS={0} {1} {2} {3}'.format(
        pnum, python_bin, runtests_bin, ' '.join(arg)
    )
    log.info('Running command {0!r}'.format(cmd))
    return __salt__['cmd.run_all'](cmd, cwd='/tmp', runas='root', env=env)


def get_coverage():
    COVERAGE_FILE = os.path.join(tempfile.gettempdir(), '.coverage')
    if not os.path.isfile(COVERAGE_FILE):
        return {}
    try:
        return cPickle.load(open(COVERAGE_FILE))
    except Exception, err:
        log.error('Failed to load coverage pickled data: {0}'.format(err))
    return {}
