#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Discover all instances of unittest.TestCase in this directory.
'''
# Import python libs
import os
import sys
import glob
import shutil
import logging
import optparse
import resource
import tempfile

try:
    import xmlrunner
except ImportError:
    xmlrunner = None


CWD = os.getcwd()
LOGFILE = os.path.join(tempfile.gettempdir(), 'salt-runtests.log')
TEST_DIR = os.path.dirname(os.path.normpath(os.path.abspath(__file__)))
COVERAGE_FILE = os.path.join(tempfile.gettempdir(), '.coverage')
COVERAGE_REPORT = os.path.join(TEST_DIR, 'coverage-report')

SALT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

REQUIRED_OPEN_FILES = 3072
TEST_RESULTS = []

try:
    if SALT_ROOT:
        os.chdir(SALT_ROOT)
except OSError, err:
    print 'Failed to change directory to salt\'s source: {0}'.format(err)


try:
    import coverage
    from coverage.misc import CoverageException
    # Cover any subprocess
    coverage.process_startup()
    # Setup coverage
    code_coverage = coverage.coverage(
        branch=True,
        data_file=COVERAGE_FILE,
        source=[os.path.join(os.getcwd(), 'salt')],
    )
    code_coverage.erase()
except ImportError:
    code_coverage = None


# Import salt libs
import saltunittest
from integration import PNUM, print_header


class STDOutWrapper(object):
    """
    This wrapper is meant to be used with sys.std{out,err} when the tests
    are not running on a tty.
    """
    logger = 'salt.runtests.stdout'

    def __init__(self, original):
        self.original = original

    def write(self, data):
        if isinstance(data, unicode):
            data = data.encode('utf-8')
        self.original.write(data)
        self.original.flush()
        ldata = data.rstrip()
        if ldata:
            logging.getLogger(self.logger).info(ldata)

    def __getattribute__(self, name):
        if name in ('write', 'logger', 'original'):
            return object.__getattribute__(self, name)
        return getattr(self.original, name)


class STDErrWrapper(STDOutWrapper):
    logger = 'salt.runtests.stderr'


def run_suite(opts, path, display_name, suffix='[!_]*.py'):
    '''
    Execute a unit test suite
    '''
    loader = saltunittest.TestLoader()
    if opts.name:
        tests = loader.loadTestsFromName(display_name)
    else:
        tests = loader.discover(path, suffix, TEST_DIR)

    header = '{0} Tests'.format(display_name)
    print_header('Starting {0}'.format(header))

    if opts.xmlout:
        runner = xmlrunner.XMLTestRunner(
            output='test-reports',
            stream=sys.stdin.isatty() and sys.stderr or sys.stdout
        )
        # XMLTestRunner only accepts True/False for verbosity although it
        # subclasses TextTestRunner. Force it to handle verbosity the same way
        runner.verbosity = opts.verbosity
    else:
        runner = saltunittest.TextTestRunner(
            verbosity=opts.verbosity,
            stream=sys.stdin.isatty() and sys.stderr or sys.stdout
        )
    results = runner.run(tests)
    TEST_RESULTS.append((header, results))
    return results.wasSuccessful()


def run_integration_suite(opts, suite_folder, display_name):
    '''
    Run an integration test suite
    '''
    path = os.path.join(TEST_DIR, 'integration', suite_folder)
    return run_suite(opts, path, display_name)


def run_integration_tests(opts):
    '''
    Execute the integration tests suite
    '''
    (smax_open_files,
     hmax_open_files) = resource.getrlimit(resource.RLIMIT_NOFILE)
    if smax_open_files < REQUIRED_OPEN_FILES:
        print('~' * PNUM)
        print('Max open files setting is too low({0}) for running the '
              'tests'.format(smax_open_files))
        print('Trying to raise the limit to {0}'.format(REQUIRED_OPEN_FILES))
        if hmax_open_files < 4096:
            hmax_open_files = 4096  # Decent default?
        try:
            resource.setrlimit(
                resource.RLIMIT_NOFILE,
                (REQUIRED_OPEN_FILES, hmax_open_files)
            )
        except Exception, err:
            print('ERROR: Failed to raise the max open files '
                  'setting -> {0}'.format(err))
            print('Please issue the following command on your console:')
            print('  ulimit -n {0}'.format(REQUIRED_OPEN_FILES))
            sys.exit(1)
        finally:
            print('~' * PNUM)

    print_header('Setting up Salt daemons to execute tests', top=False)
    status = []
    if not any([opts.client, opts.module, opts.runner, opts.shell,
                opts.state, opts.name, opts.vagrant_test]):
        return status

    if opts.vagrant_test:
        # Switch the tests daemon if we'll test within vagrant machines too
        from integration import VagrantTestDaemon as TestDaemon
    else:
        from integration import TestDaemon

    with TestDaemon(opts) as test_daemon:
        if opts.name:
            for name in opts.name:
                results = run_suite(opts, '', name)
                status.append(results)
        if opts.runner:
            status.append(run_integration_suite(opts, 'runners', 'Runner'))
        if opts.module:
            status.append(run_integration_suite(opts, 'modules', 'Module'))
        if opts.state:
            status.append(run_integration_suite(opts, 'states', 'State'))
        if opts.client:
            status.append(run_integration_suite(opts, 'client', 'Client'))
        if opts.shell:
            status.append(run_integration_suite(opts, 'shell', 'Shell'))
        # Local tests finished, enable remote tests progress
        test_daemon.enable_progress()
    return status


def run_unit_tests(opts):
    '''
    Execute the unit tests
    '''
    if not opts.unit:
        return [True]
    status = []
    results = run_suite(
        opts, os.path.join(TEST_DIR, 'unit'), 'Unit', '*_test.py')
    status.append(results)
    return status


def parse_opts():
    '''
    Parse command line options for running specific tests
    '''
    parser = optparse.OptionParser()
    parser.add_option('-m',
            '--module',
            '--module-tests',
            dest='module',
            default=False,
            action='store_true',
            help='Run tests for modules')
    parser.add_option('-S',
            '--state',
            '--state-tests',
            dest='state',
            default=False,
            action='store_true',
            help='Run tests for states')
    parser.add_option('-c',
            '--client',
            '--client-tests',
            dest='client',
            default=False,
            action='store_true',
            help='Run tests for client')
    parser.add_option('-s',
            '--shell',
            dest='shell',
            default=False,
            action='store_true',
            help='Run shell tests')
    parser.add_option('-r',
            '--runner',
            dest='runner',
            default=False,
            action='store_true',
            help='Run runner tests')
    parser.add_option('-u',
            '--unit',
            '--unit-tests',
            dest='unit',
            default=False,
            action='store_true',
            help='Run unit tests')
    parser.add_option('-v',
            '--verbose',
            dest='verbosity',
            default=1,
            action='count',
            help='Verbose test runner output')
    parser.add_option('-x',
            '--xml',
            dest='xmlout',
            default=False,
            action='store_true',
            help='XML test runner output')
    parser.add_option('-n',
            '--name',
            dest='name',
            action='append',
            default=[],
            help='Specific test name to run')
    parser.add_option('--clean',
            dest='clean',
            default=True,
            action='store_true',
            help=('Clean up test environment before and after '
                  'integration testing (default behaviour)'))
    parser.add_option('--no-clean',
            dest='clean',
            action='store_false',
            help=('Don\'t clean up test environment before and after '
                  'integration testing (speed up test process)'))
    parser.add_option('--run-destructive',
            action='store_true',
            default=False,
            help='Run destructive tests. These tests can include adding or '
                 'removing users from your system for example. Default: '
                 '%default')
    parser.add_option('--no-report',
            default=False,
            action='store_true',
            help='Do NOT show the overall tests result')
    parser.add_option('--sysinfo',
            default=False,
            action='store_true',
            help='Print some system information.'
    )

    coverage_group = optparse.OptionGroup(
        parser,
        'Coverage Options'
    )
    coverage_group.add_option(
        '--coverage',
        default=False,
        action='store_true',
        help='Run tests and report code coverage'
    )
    coverage_group.add_option(
        '--no-coverage-report',
        default=False,
        action='store_true',
        help='Do not generate the coverage HTML report. Will only save '
             'coverage information to the filesystem.'
    )
    coverage_group.add_option(
        '--coverage-output',
        default=os.path.join(tempfile.gettempdir(), 'coverage-report'),
        help='The coverage report output directory. WARNING: This directory '
             'WILL be deleted. Default: %default'
    )
    parser.add_option_group(coverage_group)

    vagrant_group = optparse.OptionGroup(
        parser,
        'Vagrant Machines Testing Options',
        'These options will start vagrant machines under \'./{0}/\' if not '
        'running already. In order for a sub-directory under \'./{0}/\' to '
        'be considered as a vagrant machine, a \'Vagrantfile\', which is '
        'the vagrant\'s machine configuration file, must exist. If a '
        '\'Vagrantfile.skip\' exists that machine will be skipped from '
        'running the tests suite.'.format(
            os.path.relpath(os.path.join(TEST_DIR, 'vg'), CWD)
        )
    )
    vagrant_group.add_option(
        '--vagrant-test', '--vg-test',
        default=False,
        action='store_true',
        help='Run the test suite within the testing vagrant machines'
    )
    vagrant_group.add_option(
        '--vagrant-no-stop', '--vg-no-stop',
        default=False,
        action='store_true',
        help='Do NOT stop the vagrant machines when done running the '
             'tests suite.'
    )
    vagrant_group.add_option(
        '--vagrant-same-tests', '--vg-same-tests',
        default=False,
        action='store_true',
        help='Run the same tests both locally and remotely. Useful for '
             'example when passing test names.'
    )
    parser.add_option_group(vagrant_group)

    options, _ = parser.parse_args()

    if options.xmlout and xmlrunner is None:
        parser.error('\'--xml\' is not available. The xmlrunner library '
                     'is not installed.')
    elif options.xmlout:
        # With --xml I've segfaulted using 2048, so, let's double that
        global REQUIRED_OPEN_FILES
        REQUIRED_OPEN_FILES = 4096

    if options.coverage and code_coverage is None:
        parser.error(
            'Cannot run tests with coverage report. '
            'Please install coverage>=3.5.3'
        )
    elif options.coverage:
        coverage_version = tuple(
            [int(part) for part in coverage.__version__.split('.')]
        )
        if coverage_version < (3, 5, 3):
            # Should we just print the error instead of exiting?
            parser.error(
                'Versions lower than 3.5.3 of the coverage library are know '
                'to produce incorrect results. Please consider upgrading...'
            )

        env_runtests = int(os.environ.get('VAGRANT_RUNTESTS', '0'))

        if (not env_runtests and not options.vagrant_test) and any(
                        (options.module, options.client, options.shell,
                         options.unit, options.state, options.runner,
                         options.name, os.geteuid() is not 0,
                         not options.run_destructive)):
            parser.error(
                'No sense in generating the tests coverage report when not '
                'running the full test suite, including the destructive '
                'tests, as \'root\'. It would only produce incorrect '
                'results.'
            )

        # Update environ so that any subprocess started on test are also
        # included in the report
        os.environ['COVERAGE_PROCESS_START'] = '1'

    # Setup logging
    formatter = logging.Formatter(
        '%(asctime)s,%(msecs)03.0f [%(name)-5s:%(lineno)-4d]'
        '[%(levelname)-8s] %(message)s',
        datefmt='%H:%M:%S'
    )
    filehandler = logging.FileHandler(
        mode='w',           # Not preserved between re-runs
        filename=LOGFILE
    )
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(formatter)
    logging.root.addHandler(filehandler)
    logging.root.setLevel(logging.DEBUG)

    # With greater verbosity we can also log to the console
    if options.verbosity > 2 and sys.stdin.isatty():
        consolehandler = logging.StreamHandler(sys.stderr)
        consolehandler.setLevel(logging.INFO)       # -vv
        consolehandler.setFormatter(formatter)
        if options.verbosity > 3:
            consolehandler.setLevel(logging.DEBUG)  # -vvv

        logging.root.addHandler(consolehandler)

    if not sys.stdin.isatty():
        # Not running on a tty, log any sys.std[out,err].write() calls
        sys.stdout = STDOutWrapper(sys.__stdout__)
        sys.stderr = STDErrWrapper(sys.__stderr__)

    os.environ['DESTRUCTIVE_TESTS'] = str(options.run_destructive)

    if not any((options.module, options.client,
                options.shell, options.unit,
                options.state, options.runner,
                options.name)):
        options.module = True
        options.client = True
        options.shell = True
        options.unit = True
        options.runner = True
        options.state = True
    return options


def stop_coverage(opts):
    if opts.coverage:
        print_header(
            '  Stopping and saving coverage info  ',
            sep='=', inline=True, centered=True
        )
        code_coverage.stop()
        code_coverage.save()

    if opts.coverage and not opts.no_coverage_report:
        print(
            '  * Generating Coverage HTML Report(s) Under {0!r} ...'.format(
                opts.coverage_output
            )
        )
        if os.path.isdir(opts.coverage_output):
            shutil.rmtree(opts.coverage_output)

        coverage_files = sorted(glob.glob(COVERAGE_FILE + '*'))
        for cname in coverage_files:
            # The backup name needs to be like this so it does not get picked
            # up by the combine() call bellow.
            cname_backup = os.path.join(
                os.path.dirname(cname),
                '.bak.{0}'.format(os.path.basename(cname))
            )
            if os.path.isfile(cname_backup):
                os.remove(cname_backup)

            shutil.copyfile(cname, cname_backup)

            report_dir_name = os.path.basename(cname.lstrip(COVERAGE_FILE))
            if report_dir_name == '':
                # This is the test suite which gathers info from all running
                # vagrant machines
                report_dir_name = 'Starter Machine'

            print(
                '    * Generating coverage report for {0} ...'.format(cname)
            ),
            sys.stdout.flush()

            report_dir = os.path.join(opts.coverage_output, report_dir_name)

            try:
                partial_coverage = coverage.coverage(
                    branch=True,
                    data_file=cname,
                    source=[os.path.join(os.getcwd(), 'salt')],
                )
                partial_coverage.load()
                partial_coverage.html_report(
                    directory=report_dir
                )
            except CoverageException, err:
                print(
                    'Error while generating coverage report for '
                    '{0}: {1}'.format(
                        report_dir_name, err
                    )
                )
            else:
                print('OK')

        if os.path.exists(COVERAGE_FILE) and len(coverage_files) > 1:
            print('    * Generating the combined coverage report ...'),
            sys.stdout.flush()
            try:
                code_coverage.load()
                code_coverage.combine()
                code_coverage.html_report(
                    directory=os.path.join(
                        opts.coverage_output, 'Combined Coverage'
                    ),
                )
            except CoverageException, err:
                print('Error while generating the combined coverage '
                      'report: {0}'.format(err))
            else:
                print('OK')

        print('  * Done.')
        print_header('', sep='=')


if __name__ == '__main__':
    opts = parse_opts()

    print_header('Tests Starting!', bottom=False)
    print('Logging tests on {0}'.format(LOGFILE))
    print('Current directory: {0}'.format(os.getcwd()))

    if opts.coverage:
        code_coverage.start()

    overall_status = []
    status = run_integration_tests(opts)
    overall_status.extend(status)
    status = run_unit_tests(opts)
    overall_status.extend(status)
    false_count = overall_status.count(False)

    if opts.no_report:
        # Stop coverage and generate report
        stop_coverage(opts)
        print_header('Tests Finished!')

        if false_count > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    print
    print_header(
        u'  Overall Tests Report  ', sep=u'=', centered=True, inline=True
    )

    no_problems_found = True
    for (name, results) in TEST_RESULTS:
        if not results.failures and not results.errors and not results.skipped:
            continue

        no_problems_found = False

        print_header(
            u'\u22c6\u22c6\u22c6 {0}  '.format(unicode(name)),
            sep=u'\u22c6', inline=True
        )
        if results.skipped:
            print_header(u' --------  Skipped Tests  ', sep='-', inline=True)
            maxlen = len(
                max([tc.id() for (tc, reason) in results.skipped], key=len)
            )
            fmt = u'   \u2192 {0: <{maxlen}}  \u2192  {1}'
            for tc, reason in results.skipped:
                print(fmt.format(tc.id(), reason, maxlen=maxlen))
            print_header(u' ', sep='-', inline=True)

        if results.errors:
            print_header(
                u' --------  Tests with Errors  ', sep=u'-', inline=True
            )
            for tc, reason in results.errors:
                print_header(
                    u'   \u2192 {0}  '.format(tc.id()), sep=u'.', inline=True
                )
                for line in reason.rstrip().splitlines():
                    print('       {0}'.format(line.rstrip()))
                print_header(u'   ', sep=u'.', inline=True)
            print_header(u' ', sep='-', inline=True)

        if results.failures:
            print_header(u' --------  Failed Tests  ', sep=u'-', inline=True)
            for tc, reason in results.failures:
                print_header(
                    u'   \u2192 {0}  '.format(tc.id()), sep=u'.', inline=True
                )
                for line in reason.rstrip().splitlines():
                    print(u'       {0}'.format(line.rstrip()))
                print_header(u'   ', sep=u'.', inline=True)
            print_header(u' ', sep=u'-', inline=True)

        print_header(u'', sep=u'\u22c6', inline=True)

    if no_problems_found:
        print_header(
            u'\u22c6\u22c6\u22c6  No Problems Found While Running Tests  ',
            sep=u'\u22c6', inline=True
        )

    print_header(
        '  Overall Tests Report  ', sep='=', centered=True, inline=True
    )

    # Stop coverage and generate report
    stop_coverage(opts)

    print_header('Tests Finished!', top=False)

    if false_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)
