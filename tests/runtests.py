#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Discover all instances of unittest.TestCase in this directory.
'''
# Import python libs
import sys
import os
import glob
import logging
import optparse
import resource
import tempfile

try:
    import xmlrunner
except ImportError:
    xmlrunner = None

CWD = os.getcwd()
TEST_DIR = os.path.dirname(os.path.normpath(os.path.abspath(__file__)))
COVERAGE_FILE = os.path.join(tempfile.gettempdir(), '.coverage')
COVERAGE_REPORT = os.path.join(TEST_DIR, 'coverage-report')

try:
    import coverage
    # Cover any subprocess
    coverage.process_startup()
    try:
        salt_root = os.path.dirname(os.path.dirname(__file__))
        if salt_root:
            os.chdir(salt_root)
    except OSError, err:
        print 'Failed to change directory to salt\'s source: {0}'.format(err)

    # Setup coverage
    code_coverage = coverage.coverage(
        branch=True,
        data_file=COVERAGE_FILE,
        source=[os.getcwd()],
        include=[os.path.join(os.getcwd(), 'salt')]
    )
    code_coverage.erase()
except ImportError:
    code_coverage = None


# Import salt libs
import saltunittest
from integration import PNUM, print_header

REQUIRED_OPEN_FILES = 2048
TEST_RESULTS = []


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
        runner = xmlrunner.XMLTestRunner(output='test-reports').run(tests)
    else:
        runner = saltunittest.TextTestRunner(
            verbosity=opts.verbosity
        ).run(tests)
        TEST_RESULTS.append((header, runner))
    return runner.wasSuccessful()


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
        '--vagrant-test',
        default=False,
        action='store_true',
        help='Run the test suite within the testing vagrant machines'
    )
    vagrant_group.add_option(
        '--vagrant-no-stop',
        default=False,
        action='store_true',
        help='Do NOT stop the vagrant machines when done running the '
             'tests suite.'
    )
    parser.add_option_group(vagrant_group)

    options, _ = parser.parse_args()

    if options.xmlout and xmlrunner is None:
        parser.error('\'--xml\' is not available. The xmlrunner library '
                     'is not installed.')

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

        if not options.vagrant_test and any(
                        (options.module, options.client, options.shell,
                         options.unit, options.state, options.runner,
                         options.name,
                         os.geteuid() is not 0, not options.run_destructive)):
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
    logfile = os.path.join(tempfile.gettempdir(), 'salt-runtests.log')
    filehandler = logging.FileHandler(
        mode='w',           # Not preserved between re-runs
        filename=logfile
    )
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(formatter)
    logging.root.addHandler(filehandler)
    logging.root.setLevel(logging.DEBUG)

    print_header('Logging tests on {0}'.format(logfile), bottom=False)

    # With greater verbosity we can also log to the console
    if options.verbosity > 2 and sys.stdout.isatty():
        consolehandler = logging.StreamHandler(stream=sys.stderr)
        consolehandler.setLevel(logging.INFO)       # -vv
        consolehandler.setFormatter(formatter)
        if options.verbosity > 3:
            consolehandler.setLevel(logging.DEBUG)  # -vvv

        logging.root.addHandler(consolehandler)

    if not sys.stdout.isatty():
        # Not running on a tty, log any sys.stdout.write() calls
        sys.stdout = STDOutWrapper(sys.__stdout__)

    if not sys.stderr.isatty():
        # Not running on a tty, log any sys.stderr.write() calls
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
        print('Stopping and saving coverage info')
        code_coverage.stop()
        code_coverage.save()

    if opts.coverage and not opts.no_coverage_report:
        print(
            '\nGenerating Coverage HTML Report Under {0!r} ...'.format(
                opts.coverage_output
            )
        ),
        sys.stdout.flush()
        if os.path.isdir(opts.coverage_output):
            import shutil
            shutil.rmtree(opts.coverage_output)

        for cname in sorted(glob.glob(COVERAGE_FILE + '*')):
            cname_parts = cname.rsplit('.', 1)
            if cname_parts[-1] == 'coverage':
                # This is the test suite which gathers info from all running
                # vagrant machines
                cname_parts[-1] = 'Starter Machine'

            report_dir = os.path.join(opts.coverage_output, cname_parts[-1])

            partial_coverage = coverage.coverage(
                branch=True,
                data_file=cname,
                source=[os.getcwd()],
                include=[os.path.join(os.getcwd(), 'salt')]
            )
            partial_coverage.load()
            partial_coverage.html_report(
                directory=report_dir,
                #ignore_errors=True,
                #include=[os.path.join(os.getcwd(), 'salt')]
            )

        if os.path.exists(COVERAGE_FILE):
            code_coverage.load()
            #code_coverage.combine()
            code_coverage.html_report(
                directory=os.path.join(
                    opts.coverage_output, 'Combined Coverage'
                ),
                #ignore_errors=True,
                #include=[os.path.join(os.getcwd(), 'salt', '**')]
            )
        print('Done.\n')


if __name__ == '__main__':
    opts = parse_opts()
    logging.getLogger('salt.tests.runtests').warning('Tests Starting! {0}'.format(os.getcwd()))
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
        logging.getLogger('salt.tests.runtests').warning('Tests Finished!')

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
            u'\u22c6\u22c6\u22c6 {0}  '.format(name),
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
                u' --------  Tests with Errors  ', sep='-', inline=True
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
            print_header(u' --------  Failed Tests  ', sep='-', inline=True)
            for tc, reason in results.failures:
                print_header(
                    u'   \u2192 {0}  '.format(tc.id()), sep=u'.', inline=True
                )
                for line in reason.rstrip().splitlines():
                    print('       {0}'.format(line.rstrip()))
                print_header(u'   ', sep=u'.', inline=True)
            print_header(u' ', sep='-', inline=True)

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
    logging.getLogger('salt.tests.runtests').warning('Tests Finished!')

    if false_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)
