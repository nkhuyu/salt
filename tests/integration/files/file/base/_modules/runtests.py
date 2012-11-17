# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
"""
    :copyright: © 2012 UfSoft.org - :email:`Pedro Algarvio (pedro@algarvio.me)`
    :license: Apache 2.0, see LICENSE for more details
"""

# Import python modules
import os
import sys
import shutil
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
              coverage_output=None, screen_width=80, screen_height=25,
              cwd=tempfile.gettempdir()):

    """
    Run tests.
    """
    venv_bin = '/tmp/ve/bin'
    python_bin = os.path.join(venv_bin, 'python')
    runtests_bin = '/salt/source/tests/runtests.py'
    activate_source = os.path.join(venv_bin, 'activate')

    if not __salt__['cmd.has_exec'](python_bin):
        raise CommandExecutionError(
            'The python binary {0!r} not found or not executable'.format(
                python_bin
            )
        )

    if coverage:
        cwd_dirname = os.path.dirname(cwd)
        log.warning(
            'In order to properly combine coverage data, the tests need to '
            'share the same running paths'
        )
        if cwd == tempfile.gettempdir():
            raise CommandExecutionError('You need to specify a proper cwd')

        # Let's mimic the directory paths from the starting runtests call
        if os.path.exists(cwd_dirname):
            log.info(
                'Removing the previous copied salt source tree: {0}'.format(
                    cwd_dirname
                )
            )
            # Leftover from a previous test run
            shutil.rmtree(cwd_dirname, ignore_errors=False)

        # Create the source's parent directory
        log.info('Creating the mimicked salt\'s source parent directory')
        os.makedirs(cwd_dirname)

        # Copy salt's source to the new location
        log.info(
            'Copying salt\'s source tree to the new location: {0}'.format(cwd)
        )
        shutil.copytree('/salt/source/', cwd, symlinks=True)
        runtests_bin = os.path.join(cwd, 'tests', 'runtests.py')

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
    if name:
        arg.extend([
            '-n {0}'.format(test) for test in name.split(':')
        ])
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

    env = dict(
        COLUMNS=str(screen_width),
        LINES=str(screen_height),
        VAGRANT_RUNTESTS='1'
    )
    cmd = (
        'export VAGRANT_RUNTESTS=1; export COLUMNS={0}; export LINES={1}; '
        '. {2}; {3} {4} {5}'.format(
            screen_width, screen_height, activate_source, python_bin,
            runtests_bin, ' '.join(arg)
        )
    )
    log.info('Running command {0!r}'.format(cmd))
    return __salt__['cmd.run_all'](cmd, cwd=cwd, runas='root', env=env)


def get_coverage():
    COVERAGE_FILE = os.path.join(tempfile.gettempdir(), '.coverage')
    if not os.path.isfile(COVERAGE_FILE):
        return ''
    try:
        return open(COVERAGE_FILE).read().encode('base64')
        return cPickle.load(open(COVERAGE_FILE))
    except Exception, err:
        log.error('Failed to load coverage pickled data: {0}'.format(err))
    return ''


# These functions are used within' state files,
def unittest2_required():
    """
    Python versions before 2.7 do not ship with unittest.
    """
    return sys.version_info < (2, 7)


def ordereddict_required():
    '''
    Python versions before 2.7 do not ship with OrderedDict
    '''
    return unittest2_required()


def virtualenv_has_system_site_packages():
    """
    Virtualenv prior to version 1.7 does not have the --system-site-packages
    option available.
    """
    try:
        import virtualenv
    except ImportError:
        return None

    try:
        venv_version = virtualenv.__version__.split('.')
    except AttributeError:
        venv_version = virtualenv.virtualenv_version.split('.')

    return tuple([int(i) for i in venv_version]) >= (1, 7)
