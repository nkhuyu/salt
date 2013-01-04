'''
Set up the Salt integration test suite
'''

# Import Python libs
import optparse
import multiprocessing
import os
import sys
import shutil
import tempfile
import time
import signal
from hashlib import md5
from subprocess import PIPE, Popen
from datetime import datetime, timedelta
try:
    import pwd
except ImportError:
    pass

# Import Salt libs
import salt
import salt.config
import salt.master
import salt.minion
import salt.runner
from salt.utils import fopen, get_colors, which
from salt.utils.verify import verify_env
from saltunittest import TestCase, RedirectStdStreams

try:
    import console
    width, height = console.getTerminalSize()
    PNUM = width
except:
    PNUM = 70
    # Default on console.py
    width, height = (80, 25)


INTEGRATION_TEST_DIR = os.path.dirname(
    os.path.normpath(os.path.abspath(__file__))
)
CODE_DIR = os.path.dirname(os.path.dirname(INTEGRATION_TEST_DIR))
SCRIPT_DIR = os.path.join(CODE_DIR, 'scripts')

PYEXEC = 'python{0}.{1}'.format(sys.version_info[0], sys.version_info[1])

if os.environ.has_key('TMPDIR'):
    # Gentoo Portage prefers ebuild tests are rooted in ${TMPDIR}
    SYS_TMP_DIR = os.environ['TMPDIR']
else:
    SYS_TMP_DIR = tempfile.gettempdir()

TMP = os.path.join(SYS_TMP_DIR, 'salt-tests-tmpdir')
FILES = os.path.join(INTEGRATION_TEST_DIR, 'files')
MOCKBIN = os.path.join(INTEGRATION_TEST_DIR, 'mockbin')
COVERAGE_FILE = os.path.join(tempfile.gettempdir(), '.coverage')
TESTING_SDIST_DIR = os.path.join(TMP, 'salt-source')
TMP_STATE_TREE = os.path.join(SYS_TMP_DIR, 'salt-temp-state-tree')

try:
    import console
    width, height = console.getTerminalSize()
    PNUM = width
except:
    PNUM = 70


def print_header(header, sep=u'~', top=True, bottom=True, inline=False,
                 centered=False):
    '''
    Allows some pretty printing of headers on the console, either with a
    "ruler" on bottom and/or top, inline, centered, etc.
    '''
    if top and not inline:
        print(sep * PNUM)

    if centered and not inline:
        fmt = u'{0:^{width}}'
    elif inline and not centered:
        fmt = u'{0:{sep}<{width}}'
    elif inline and centered:
        fmt = u'{0:{sep}^{width}}'
    else:
        fmt = u'{0}'
    print(fmt.format(header, sep=sep, width=PNUM))

    if bottom and not inline:
        print(sep * PNUM)


def run_tests(TestCase):
    '''
    Run integration tests for a chosen test case.

    Function uses optparse to set up test environment
    '''
    from saltunittest import TestLoader, TextTestRunner
    opts = parse_opts()
    loader = TestLoader()
    tests = loader.loadTestsFromTestCase(TestCase)
    print('Setting up Salt daemons to execute tests')
    with TestDaemon(clean=opts.clean):
        runner = TextTestRunner(verbosity=opts.verbosity).run(tests)
        sys.exit(runner.wasSuccessful())


def parse_opts():
    '''
    Parse command line options for running integration tests
    '''
    parser = optparse.OptionParser()
    parser.add_option('-v',
            '--verbose',
            dest='verbosity',
            default=1,
            action='count',
            help='Verbose test runner output')
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
    options, _ = parser.parse_args()
    return options


class TestDaemon(object):
    '''
    Set up the master and minion daemons, and run related cases
    '''
    MINIONS_CONNECT_TIMEOUT = MINIONS_SYNC_TIMEOUT = 120

    def __init__(self, opts):
        self.opts = opts
        self.colors = get_colors(opts.no_colors is False)

    def __enter__(self):
        '''
        Start a master and minion
        '''
        self.master_opts = salt.config.master_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
        )
        self.minion_opts = salt.config.minion_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'minion')
        )
        #if sys.version_info < (2, 7):
        #    self.minion_opts['multiprocessing'] = False
        self.sub_minion_opts = salt.config.minion_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'sub_minion')
        )
        #if sys.version_info < (2, 7):
        #    self.sub_minion_opts['multiprocessing'] = False
        self.smaster_opts = salt.config.master_config(
            os.path.join(
                INTEGRATION_TEST_DIR, 'files', 'conf', 'syndic_master'
            )
        )
        self.syndic_opts = salt.config.minion_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'syndic'))
        self.syndic_opts['_master_conf_file'] = os.path.join(
            INTEGRATION_TEST_DIR,
            'files/conf/master'
        )
        # Set up config options that require internal data
        self.master_opts['pillar_roots'] = {
            'base': [os.path.join(FILES, 'pillar', 'base')]
        }
        self.master_opts['file_roots'] = {
            'base': [
                os.path.join(FILES, 'file', 'base'),
                # Let's support runtime created files that can be used like:
                #   salt://my-temp-file.txt
                TMP_STATE_TREE,
                TESTING_SDIST_DIR
            ]
        }
        self.master_opts['ext_pillar'] = [
            {'cmd_yaml': 'cat {0}'.format(
                os.path.join(
                    FILES,
                    'ext.yaml'
                )
            )}
        ]
        # clean up the old files
        self._clean()

        # Even if not cleaned from the above call(because of --no-clean), wipe
        # all pki data between runs
        for odict in (self.master_opts, self.smaster_opts):
            for dname in (os.path.join(odict['pki_dir'], 'minions'),
                          os.path.join(odict['pki_dir'], 'minions_pre'),
                          os.path.join(odict['pki_dir'], 'minions_rejected')):
                if os.path.isdir(dname):
                    shutil.rmtree(dname)

        # Point the config values to the correct temporary paths
        for name in ('hosts', 'aliases'):
            optname = '{0}.file'.format(name)
            optname_path = os.path.join(TMP, name)
            self.master_opts[optname] = optname_path
            self.minion_opts[optname] = optname_path
            self.sub_minion_opts[optname] = optname_path

        verify_env([os.path.join(self.master_opts['pki_dir'], 'minions'),
                    os.path.join(self.master_opts['pki_dir'], 'minions_pre'),
                    os.path.join(self.master_opts['pki_dir'],
                                 'minions_rejected'),
                    os.path.join(self.master_opts['cachedir'], 'jobs'),
                    os.path.join(self.smaster_opts['pki_dir'], 'minions'),
                    os.path.join(self.smaster_opts['pki_dir'], 'minions_pre'),
                    os.path.join(self.smaster_opts['pki_dir'],
                                 'minions_rejected'),
                    os.path.join(self.smaster_opts['cachedir'], 'jobs'),
                    os.path.dirname(self.master_opts['log_file']),
                    self.minion_opts['extension_modules'],
                    self.sub_minion_opts['extension_modules'],
                    self.sub_minion_opts['pki_dir'],
                    self.master_opts['sock_dir'],
                    self.smaster_opts['sock_dir'],
                    self.sub_minion_opts['sock_dir'],
                    self.minion_opts['sock_dir'],
                    TESTING_SDIST_DIR,
                    TMP_STATE_TREE,
                    TMP
                    ],
                   pwd.getpwuid(os.getuid()).pw_name)

        # Set up PATH to mockbin
        self._enter_mockbin()

        master = salt.master.Master(self.master_opts)
        self.master_process = multiprocessing.Process(target=master.start)
        self.master_process.start()

        minion = salt.minion.Minion(self.minion_opts)
        self.minion_process = multiprocessing.Process(target=minion.tune_in)
        self.minion_process.start()

        sub_minion = salt.minion.Minion(self.sub_minion_opts)
        self.sub_minion_process = multiprocessing.Process(
            target=sub_minion.tune_in
        )
        self.sub_minion_process.start()

        smaster = salt.master.Master(self.smaster_opts)
        self.smaster_process = multiprocessing.Process(target=smaster.start)
        self.smaster_process.start()

        syndic = salt.minion.Syndic(self.syndic_opts)
        self.syndic_process = multiprocessing.Process(target=syndic.tune_in)
        self.syndic_process.start()

        if os.environ.get('DUMP_SALT_CONFIG', None) is not None:
            from copy import deepcopy
            try:
                import yaml
                os.makedirs('/tmp/salttest/conf')
            except OSError:
                pass
            master_opts = deepcopy(self.master_opts)
            minion_opts = deepcopy(self.minion_opts)
            master_opts.pop('conf_file', None)
            master_opts['user'] = pwd.getpwuid(os.getuid()).pw_name

            minion_opts['user'] = pwd.getpwuid(os.getuid()).pw_name
            minion_opts.pop('conf_file', None)
            minion_opts.pop('grains', None)
            minion_opts.pop('pillar', None)
            open('/tmp/salttest/conf/master', 'w').write(
                yaml.dump(master_opts)
            )
            open('/tmp/salttest/conf/minion', 'w').write(
                yaml.dump(minion_opts)
            )

        # Let's create a local client to ping and sync minions
        self.client = salt.client.LocalClient(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
        )

        self.minion_targets = set(['minion', 'sub_minion'])
        self.pre_setup_minions()
        self.setup_minions()

        if self.opts.sysinfo:
            from salt import version
            print_header('~~~~~~~ Versions Report ', inline=True)
            print('\n'.join(version.versions_report()))

            print_header(
                '~~~~~~~ Minion Grains Information ', inline=True,
            )
            grains = self.client.cmd('minion', 'grains.items')
            import pprint
            pprint.pprint(grains['minion'])

        #print_header('', sep='=', inline=True)

        try:
            return self
        finally:
            self.post_setup_minions()

    def __exit__(self, type, value, traceback):
        '''
        Kill the minion and master processes
        '''
        self.sub_minion_process.terminate()
        self.minion_process.terminate()
        self.master_process.terminate()
        self.syndic_process.terminate()
        self.smaster_process.terminate()
        self._exit_mockbin()
        self._clean()

    def enable_progress(self):
        """
        While running `VagrantTestDaemon` there's some informational `print`'s
        which will look pretty bad if they're being printed while the local
        tests are still running.

        `VagrantTestDaemon` makes use of this method to set a signal which,
        once set, will allow the information prints to be actually printed.
        """

    def pre_setup_minions(self):
        """
        `VagrantTestDaemon` will make use of this method for additional minion
        setup's like starting the vagrant machines, etc...
        """

    def setup_minions(self):
        # Wait for minions to connect back
        if self.minion_targets.difference(['minion', 'sub_minion']):
            # In this case, we're waiting for more than the local minions, let
            # us allow more time for connections to happen.
            self.MINIONS_CONNECT_TIMEOUT = self.MINIONS_SYNC_TIMEOUT = 5 * 60

        wait_minion_connections = multiprocessing.Process(
            target=self.wait_for_minion_connections,
            args=(self.minion_targets, self.MINIONS_CONNECT_TIMEOUT)
        )
        wait_minion_connections.start()
        wait_minion_connections.join()
        wait_minion_connections.terminate()
        if wait_minion_connections.exitcode > 0:
            print(
                '\n {RED_BOLD}*{ENDC} ERROR: Minions failed to connect'.format(
                **self.colors
                )
            )
            return False

        del(wait_minion_connections)

        sync_needed = self.opts.clean
        if self.minion_targets.difference(['minion', 'sub_minion']):
            sync_needed = True
        elif self.opts.clean is False:
            def sumfile(fpath):
                # Since we will be do'in this for small files, it should be ok
                fobj = fopen(fpath)
                m = md5()
                while True:
                    d = fobj.read(8096)
                    if not d:
                        break
                    m.update(d)
                return m.hexdigest()
            # Since we're not cleaning up, let's see if modules are already up
            # to date so we don't need to re-sync them
            modules_dir = os.path.join(FILES, 'file', 'base', '_modules')
            for fname in os.listdir(modules_dir):
                if not fname.endswith('.py'):
                    continue
                dfile = os.path.join(
                    '/tmp/salttest/cachedir/extmods/modules/', fname
                )

                if not os.path.exists(dfile):
                    sync_needed = True
                    break

                sfile = os.path.join(modules_dir, fname)
                if sumfile(sfile) != sumfile(dfile):
                    sync_needed = True
                    break

        if sync_needed:
            # Wait for minions to "sync_all"
            sync_minions = multiprocessing.Process(
                target=self.sync_minion_modules,
                args=(self.minion_targets, self.MINIONS_SYNC_TIMEOUT)
            )
            sync_minions.start()
            sync_minions.join()
            if sync_minions.exitcode > 0:
                return False
            sync_minions.terminate()
            del(sync_minions)

        return True

    def post_setup_minions(self):
        """
        `VagrantTestDaemon` will make use of this method to trigger the remote
        runtests to run.
        """

    def _enter_mockbin(self):
        path = os.environ.get('PATH', '')
        path_items = path.split(os.pathsep)
        if MOCKBIN not in path_items:
            path_items.insert(0, MOCKBIN)
        os.environ['PATH'] = os.pathsep.join(path_items)

    def _exit_mockbin(self):
        path = os.environ.get('PATH', '')
        path_items = path.split(os.pathsep)
        try:
            path_items.remove(MOCKBIN)
        except ValueError:
            pass
        os.environ['PATH'] = os.pathsep.join(path_items)

    def _clean(self):
        '''
        Clean out the tmp files
        '''
        if self.opts.clean is False:
            return
        if os.path.isdir(self.sub_minion_opts['root_dir']):
            shutil.rmtree(self.sub_minion_opts['root_dir'])
        if os.path.isdir(self.master_opts['root_dir']):
            shutil.rmtree(self.master_opts['root_dir'])
        if os.path.isdir(self.smaster_opts['root_dir']):
            shutil.rmtree(self.smaster_opts['root_dir'])
        if os.path.isdir(TMP):
            shutil.rmtree(TMP)

    def wait_for_jid(self, targets, jid, timeout=120, evt=None):
        time.sleep(1)  # Allow some time for minions to accept jobs
        now = datetime.now()
        expire = now + timedelta(seconds=timeout)
        job_finished = False
        while now <= expire:
            running = self.__client_job_running(targets, jid)
            if evt is None or (evt is not None and evt.is_set()):
                sys.stdout.write('\r' + ' ' * PNUM + '\r')
            if not running and job_finished is False:
                # Let's not have false positives and wait one more seconds
                job_finished = True
            elif not running and job_finished is True:
                return True
            elif running and job_finished is True:
                job_finished = False

            if (evt is None and job_finished is False) or (
                                            evt is not None and evt.is_set()
                                            and job_finished is False):
                sys.stdout.write(
                    '    * {YELLOW}[Quit in {0}]{ENDC} Waiting for {1}'.format(
                        '{0}'.format(expire - now).rsplit('.', 1)[0],
                        ', '.join(running),
                        **self.colors
                    )
                )
                sys.stdout.flush()
            time.sleep(1)
            now = datetime.now()
        else:
            if evt is None or (evt is not None and evt.is_set()):
                sys.stdout.write(
                    '\n    {RED_BOLD}*{ENDC} ERROR: Failed to get information '
                    'back\n'.format(**self.colors)
                )
                sys.stdout.flush()
        return False

    def __client_job_running(self, targets, jid):
        running = self.client.cmd(
            ','.join(targets), 'saltutil.running', expr_form='list'
        )
        return [
            k for (k, v) in running.iteritems() if v and v[0]['jid'] == jid
        ]

    def wait_for_minion_connections(self, targets, timeout):
        sys.stdout.write(
            '  {LIGHT_BLUE}*{ENDC} Waiting at most {0} for minions({1}) to '
            'connect back\n'.format(
                (timeout > 60 and
                 timedelta(seconds=timeout) or
                 '{0} secs'.format(timeout)),
                ', '.join(targets),
                **self.colors
            )
        )
        sys.stdout.flush()
        expected_connections = set(targets)
        now = datetime.now()
        expire = now + timedelta(seconds=timeout)
        while now <= expire:
            sys.stdout.write('\r' + ' ' * PNUM + '\r')
            sys.stdout.write(
                '  * {YELLOW}[Quit in {0}]{ENDC} Waiting for {1}'.format(
                    '{0}'.format(expire - now).rsplit('.', 1)[0],
                    ', '.join(expected_connections),
                    **self.colors
                )
            )
            sys.stdout.flush()

            responses = self.client.cmd(
                ','.join(expected_connections), 'test.ping', expr_form='list',
            )
            for target in responses:
                if target not in expected_connections:
                    # Someone(minion) else "listening"?
                    print target
                    continue
                expected_connections.remove(target)
                sys.stdout.write('\r' + ' ' * PNUM + '\r')
                sys.stdout.write(
                    '    {LIGHT_GREEN}*{ENDC} {0} connected.\n'.format(
                        target, **self.colors
                    )
                )
                sys.stdout.flush()

            if not expected_connections:
                return

            time.sleep(1)
            now = datetime.now()
        else:
            print(
                '\n  {RED_BOLD}*{ENDC} WARNING: Minions failed to connect '
                'back. Tests requiring them WILL fail'.format(**self.colors)
            )
            print_header('=', sep='=', inline=True)
            raise SystemExit()

    def sync_minion_modules(self, targets, timeout=120):
        # Let's sync all connected minions
        print(
            '  {LIGHT_BLUE}*{ENDC} Syncing minion\'s modules '
            '(saltutil.sync_modules)'.format(
                ', '.join(targets),
                **self.colors
            )
        )
        syncing = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'saltutil.sync_modules',
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid'], timeout) is False:
            print(
                '  {RED_BOLD}*{ENDC} WARNING: Minions failed to sync modules. '
                'Tests requiring these modules WILL fail'.format(**self.colors)
            )
            raise SystemExit()

        while syncing:
            rdata = self.client.get_returns(jid_info['jid'], syncing, 1)
            if rdata:
                for name, output in rdata.iteritems():
                    print(
                        '    {LIGHT_GREEN}*{ENDC} Synced {0} modules: '
                        '{1}'.format(name, ', '.join(output), **self.colors)
                    )
                    # Synced!
                    try:
                        syncing.remove(name)
                    except KeyError:
                        print(
                            '    {RED_BOLD}*{ENDC} {0} already synced???  '
                            '{1}'.format(name, output, **self.colors)
                        )
        return True


class VagrantMachineException(Exception):
    """
    Simple exception to catch some errors while starting the vagrant machines
    """


class VagrantTestDaemon(TestDaemon):
    # Max time, in seconds, that creating an sdist can take
    SDIST_COMPRESS_TIMEOUT = 10

    def __init__(self, opts):
        super(VagrantTestDaemon, self).__init__(opts)
        # Setup some events
        self.__evt_sdist = multiprocessing.Event()
        self.__evt_started = multiprocessing.Event()
        self.__evt_finished = multiprocessing.Event()
        self.__evt_shutdown = multiprocessing.Event()
        self.__evt_progress = multiprocessing.Event()
        self.__rvmrc_source = None

        # Gather the machines we're able to start ourselves
        self.__machines = {}
        vg_base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'vgm'
        )
        for dirname in os.listdir(vg_base_path):
            vg_path = os.path.join(vg_base_path, dirname)
            vagrantfile = os.path.join(vg_path, 'Vagrantfile')
            if not os.path.isfile(vagrantfile):
                continue
            self.__machines[dirname] = vg_path

    def __exit__(self, type, value, traceback):
        # Let's handle the vagrant stuff before running the TestDaemon.__exit__
        # code. Wait for the tests to complete.
        self.__evt_finished.wait()
        # Stop the machines
        self.__stop_machines()
        # Wait for the shutdown code to execute
        self.__evt_shutdown.wait()
        return super(VagrantTestDaemon, self).__exit__(
            type, value, traceback
        )

    def enable_progress(self):
        print
        print_header('', sep='=', inline=True)
        if not self.__evt_finished.is_set():
            sys.stdout.write(
                '  {LIGHT_BLUE}*{ENDC} Waiting for remote test results'.format(
                    **self.colors
                )
            )
            sys.stdout.flush()
        self.__evt_progress.set()

    def pre_setup_minions(self):
        super(VagrantTestDaemon, self).pre_setup_minions()
        self.__sdist_salt_source()
        if self.__evt_sdist.wait(self.SDIST_COMPRESS_TIMEOUT) is False:
            # Usually on the 2nd run it creates the compressed source file
            self.__sdist_salt_source_process.terminate()
            self.__sdist_salt_source()
            if self.__evt_sdist.wait(self.SDIST_COMPRESS_TIMEOUT) is False:
                sys.stdout.write('\r' + ' ' * PNUM + '\r')
                print(
                    '  {RED_BOLD}*{ENDC} WARNING: Failed to create an '
                    'sdist. Won\'t start vagrant machines.'.format(
                        **self.colors
                    )
                )
                self.__sdist_salt_source_process.terminate()
                self.__evt_sdist.set()
                return
        self.__start_machines()
        self.minion_targets.update(self.__machines.keys())

    def setup_minions(self):
        super(VagrantTestDaemon, self).setup_minions()
        self.__evt_sdist.wait()  # Should not be necessary
        self.__setup_minions_process = multiprocessing.Process(
            target=self.__setup_minions_target,
            args=(self.__evt_started, self.__evt_finished)
        )
        self.__setup_minions_process.start()
        self.__evt_started.wait()
        self.__setup_minions_process.terminate()
        del(self.__setup_minions_process)

    def post_setup_minions(self):
        super(VagrantTestDaemon, self).post_setup_minions()
        self.__tests_process = multiprocessing.Process(
            target=self.__run_tests_target,
            args=(self.__evt_finished, self.__evt_progress)
        )
        self.__tests_process.start()

    def __sdist_salt_source(self):
        #self.__sdist_salt_source_process = threading.Thread(
        self.__sdist_salt_source_process = multiprocessing.Process(
            target=self.__sdist_salt_source_bg, args=(self.__evt_sdist,)
        )
        sys.stdout.write('\r' + ' ' * PNUM + '\r')
        sys.stdout.write(
            '  {LIGHT_BLUE}*{ENDC} Creating source distribution to supply to '
            'vagrant machines '.format(**self.colors)
        )
        sys.stdout.flush()
        self.__sdist_salt_source_process.start()

    def __sdist_salt_source_bg(self, sdist_evt):
        popen = Popen(' '.join([
                'sleep 1;',
                #sys.executable,
                'python',
                'setup.py',
                'clean',
            ]),
            cwd=CODE_DIR,
            shell=True,
            #bufsize=-1,
            stdout=PIPE,
            stderr=PIPE
        )

        while True:
            time.sleep(1)
            finished = popen.poll()
            #print 123, finished
            if finished is not None:
                break

        if popen.returncode > 0:
            print popen.stderr.read()

        dname_path = os.path.join(TESTING_SDIST_DIR, 'saltsource.tar.bz2')
        if os.path.exists(dname_path):
            os.remove(dname_path)

        if not os.path.isdir(TESTING_SDIST_DIR):
            os.makedirs(TESTING_SDIST_DIR)

        os.chdir(CODE_DIR)

        popen = Popen(' '.join([
                'sleep 1;',
                #sys.executable,
                'python',
                'setup.py',
                'sdist',
                '--dist-dir={0}'.format(TESTING_SDIST_DIR),
                '--formats=bztar'   # smallest
            ]),
            cwd=CODE_DIR,
            shell=True,
            #bufsize=-1,
            stdout=PIPE,
            stderr=PIPE
        )

        while True:
            time.sleep(1)
            finished = popen.poll()
            #print 123, finished
            if finished is not None:
                break
            sys.stdout.write('.')
            sys.stdout.flush()

        sys.stdout.write('\n')
        sys.stdout.flush()

        if popen.returncode > 0:
            print popen.stderr.read()

        # There should be only one source file
        sname = os.listdir(TESTING_SDIST_DIR)[0]

        # Rename it to a known filename to be used in states
        os.rename(os.path.join(TESTING_SDIST_DIR, sname), dname_path)
        # We're done, set the signal
        sys.stdout.write('\r' + ' ' * PNUM + '\r')
        print(
            '    {LIGHT_GREEN}*{ENDC} Compressed salt\'s source: {0}'.format(
                dname_path, **self.colors
            )
        )
        sdist_evt.set()

    def __start_machines(self):
        print('  {LIGHT_BLUE}*{ENDC} Starting vagrant machine(s)'.format(
            **self.colors
        ))

        for machine, vg_path in self.__machines.copy().iteritems():
            header = '  Starting {0} Machine  '.format(machine)
            vagrant_skip = os.path.join(vg_path, 'Vagrantfile.skip')
            if os.path.exists(vagrant_skip):
                header += '~  SKIPPED  '.format(**self.colors)
            print_header(header, centered=True, inline=True)
            if os.path.exists(vagrant_skip):
                self.__machines.pop(machine)
                continue
            try:
                self.__start_machine(vg_path)
            except VagrantMachineException:
                print(
                    '  {RED_BOLD}*{ENDC} Failed to start machine: {0}'.format(
                        machine, **self.colors
                    )
                )
                self.__machines.pop(machine)
            print_header('~', inline=True)
            time.sleep(0.2)

    def __start_machine(self, machine_path):
        if self.__rvmrc_source is None:
            if which('vagrant') is None:
                self.__rvmrc_source = True
            else:
                # Let's check if we need to source .rvmrc
                try:
                    popen = Popen(
                        ['vagrant', '--help'], cwd=machine_path,
                        stdout=PIPE, stderr=PIPE
                    )
                    popen.wait()
                    self.__rvmrc_source = popen.returncode > 0
                except Exception:
                    # Yes, we need to source .rvmrc
                    self.__rvmrc_source = True

        cmd = 'vagrant up'
        executable = '/bin/sh'

        if self.__rvmrc_source is True:
            cmd = 'source .rvmrc && {0}'.format(cmd)
            executable = '/bin/bash'

        popen = Popen(cmd, cwd=machine_path, shell=True, executable=executable)
        popen.wait()
        if popen.returncode > 0:
            raise VagrantMachineException()

    def __run_step(self, step, sls, targets, timeout):
        print(
            '  {LIGHT_BLUE}*{ENDC} Running step {0!r} on the minion\'s'.format(
                step, **self.colors
            )
        )

        step_targets = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'state.sls', arg=['mods={0}'.format(sls)],
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid'], timeout) is False:
            print(
                '    {BOLD_RED}*{ENDC} Failed to run step {0!r}'.format(
                    step, **self.colors
                )
            )
            return False

        attemps = 3
        while step_targets:
            rdata = self.client.get_returns(jid_info['jid'], step_targets, 10)
            if not rdata:
                attemps -= 1
                if attemps < 0:
                    print(
                        '    {BOLD_RED}*{ENDC} Failed to get data back while '
                        'running step {0!r}'.format(
                            step, **self.colors
                        )
                    )
                    return False
                continue

            # Restore attempts if we reached here
            attemps = 3

            for name, output in rdata.items():
                if name in ('minion', 'sub_minion'):
                    # These should never appear here
                    continue

                if name not in step_targets:
                    # Previous error which is already skipped? Handle next!
                    continue

                if not isinstance(output, dict):
                    # This is an error:
                    print(
                        '    {RED_BOLD}*{ENDC} Error running step {0!r} '
                        'on {1}: {2}'.format(
                            step, name, '\n'.join(output), **self.colors
                        )
                    )
                    if name in targets:
                        print(
                            '        {LIGHT_GREEN}*{ENDC} Removing {0} from '
                            'overall targets'.format(name, **self.colors)
                        )
                        targets.remove(name)

                    if not targets:
                        # Every minion failed
                        print(
                            '    {RED_BOLD}*{ENDC} All minions failed to '
                            'run {0!r}'.format(
                                step, **self.colors
                            )
                        )
                        return False

                    if name in step_targets:
                        print(
                            '      {LIGHT_GREEN}*{ENDC} Removing minion {0} '
                            'from step {0!r}'.format(
                                name, step, **self.colors
                            )
                        )
                        step_targets.remove(name)
                    continue

                print(
                    '    {LIGHT_GREEN}*{ENDC} Minion {0} seems to '
                    'have completed step {1!r}'.format(
                        name, step, **self.colors
                    )
                )

                try:
                    failed = [
                        s for s in output.values() if s['result'] is False
                    ]
                    if failed:
                        print(
                            '      {RED_BOLD}*{ENDC} Failed to run step '
                            '{0!r} on minion {1}({3}). '
                            'Failing: {2}'.format(
                                step,
                                name,
                                '; '.join([s['comment'] for s in failed]),
                                step_targets,
                                **self.colors
                            )
                        )
                        if name in targets:
                            print(
                                '        {LIGHT_GREEN}*{ENDC} Removing {0} '
                                'from overall targets'.format(
                                    name, **self.colors
                                )
                            )
                            targets.remove(name)
                        if name in step_targets:
                            print(
                                '      {LIGHT_GREEN}*{ENDC} Removing minion '
                                '{0} from step {0!r}'.format(
                                    name, step, **self.colors
                                )
                            )
                        step_targets.remove(name)
                except AttributeError:
                    print(
                        '    {RED_BOLD}*****{ENDC} Error running step '
                        '{0!r} on {0}: {1}'.format(
                            name, output, **self.colors
                        )
                    )
                # code execution reached here, minion completed step
                if name in step_targets:
                    print(
                        '      {LIGHT_GREEN}*{ENDC} Removing minion {0} from '
                        'step {0!r}'.format(
                            name, step, **self.colors
                        )
                    )
                    step_targets.remove(name)
        return True

    def __check_available_targets(self, start_evt, finish_evt):
        targets = set(self.__machines.keys())
        if not targets:
            print_header(
                'There aren\'t any minions running to run remote tests '
                'against', sep='=', centered=True
            )

            start_evt.set()
            finish_evt.set()
            return False
        return True

    def __setup_minions_target(self, start_evt, finish_evt):
        targets = set(self.__machines.keys())
        # Install dependencies
        self.__run_step(
            'install dependencies', 'runtests.pkgs', targets, 10 * 60
        )

        if not self.__check_available_targets(start_evt, finish_evt):
            return

        # Setup salt source
        self.__run_step(
            'setup salt\'s source', 'runtests.setup', targets, 10 * 60
        )

        if not self.__check_available_targets(start_evt, finish_evt):
            return

        # Create virtualenv
        self.__run_step(
            'create virtualenv', 'runtests', targets, 15 * 60
        )

        if not self.__check_available_targets(start_evt, finish_evt):
            return

        #print_header('=', sep='=', inline=True)

        # Local tests can start
        start_evt.set()

    def __run_tests_target(self, finish_evt, progress_evt):
        targets = set(self.__machines.keys())
        # Now let's run the tests remotely
        running = set(targets)
        time.sleep(1)

        run_tests_kwargs = dict(
            clean=True,
            #no_clean=True,
            coverage=True,
            run_destructive=True,
            no_coverage_report=True,
            verbose=self.opts.verbosity,
            screen_width=width,
            screen_height=height,
            cwd=os.getcwd()
        )
        if self.opts.xmlout:
            run_tests_kwargs['xml'] = True

        if self.opts.vagrant_same_tests:
            run_tests_kwargs.update(
                module=self.opts.module,
                state=self.opts.state,
                client=self.opts.client,
                shell=self.opts.shell,
                runner=self.opts.runner,
                unit=self.opts.unit,
                name=(':'.join(self.opts.name) if self.opts.name else ''),
            )

        run_tests_arg = [
            '{0}={1}'.format(k, v) for (k, v) in run_tests_kwargs.iteritems()
        ]
        jid_info = self.client.run_job(
            ','.join(targets), 'runtests.run_tests',
            expr_form='list',
            cwd='/tmp',
            #verbose=True,
            timeout=9999999999999999,
            arg=run_tests_arg
        )

        if self.wait_for_jid(targets, jid_info['jid'], 45*60, evt=progress_evt) is False:
            # Let's signal anyone waiting for the event that we're done
            finish_evt.set()
            raise SystemExit('Failed to runtests.....')

        data = {}

        while running:
            rdata = self.client.get_returns(jid_info['jid'], running, 1)
            #import pprint
            #print('\n\n{0}\n\n'.format(pprint.pformat(rdata)))
            #print rdata.keys()
            if rdata:
                #for idx, (name, output) in enumerate(rdata.iteritems()):
                for idx, name in enumerate(rdata.keys()):
                    if name in ('minion', 'sub_minion'):
                        continue
                    output = rdata[name]
                    # Got back the test results from the minion.
                    # It's no longer running tests
                    try:
                        running.remove(name)
                    except KeyError:
                        print 6, name, running, output

                    # Returned data is expected to be a dictionary, if it's
                    # not, the something wrong happened
                    if not isinstance(output, dict):
                        if '"runtests.run_tests" is not available' in output:
                            print(
                                '\n  {RED_BOLD}*{ENDC} The minion {0} is not '
                                'able to run the test suite because the '
                                '\'runtests\' module wasn\'t uploaded to it. '
                                'Removing it from the testing targets.'.format(
                                    name, **self.colors
                                )
                            )
                            targets.remove(name)
                        else:
                            print(
                                '\n  {RED_BOLD}*{ENDC} An error occurred on '
                                '{0}: {1}'.format(
                                    name, output, **self.colors
                                )
                            )
                        continue

                    print
                    if idx % 2:
                        rcolor = self.colors['LIGHT_BLUE']
                    else:
                        rcolor = self.colors['BROWN']

                    print('{0}'.format(
                        (output['retcode'] > 0 and
                        '{RED_BOLD}' or '{LIGHT_GREEN}').format(**self.colors)
                    ))
                    print_header(
                        '  {0} ~ Remote Test Results ~ {1}  '.format(
                            name,
                            output['retcode'] > 0 and 'FAILED' or 'PASSED'
                        ), inline=True, centered=True
                    )
                    print(rcolor)

                    if output['retcode'] > 0:
                        print(output['stderr'])
                    print(output['stdout'])

                    print_header('~', inline=True)
                    #if idx + 1 % 2:
                    print(self.colors['ENDC'])

            if not running:
                # All remote tests have finished. Exit the loop
                print
                print_header('', sep='=', inline=True)
                break

            #elif steps <= 0:
            #    # We're still waiting for results from the remote vagrant
            #    # minions running the test suite.
            #    steps = 3
            #    if progress_evt.is_set():
            #        sys.stdout.write('\r' + ' ' * PNUM + '\r')
            #        sys.stdout.write(
            #            '  * Waiting for test results from {0} '.format(
            #                ', '.join(running)
            #            )
            #        )
            #else:
            #    steps -= 1
            #    if progress_evt.is_set():
            #        sys.stdout.write('.')
            #sys.stdout.flush()

        if self.opts.coverage is False:
            # There's nothing else to do here.
            # Let's signal anyone waiting for the event that we're done
            finish_evt.set()
            return

        # All finished, gather coverage data back from the vagrant minions
        coverage_data = self.client.cmd(
            ','.join(targets),
            'runtests.get_coverage', cwd='/tmp', expr_form='list'
        )

        if coverage_data:
            print_header(
                '  Checking for remote coverage data  ',
                sep='=', centered=True, bottom=False
            )
            for name, data in coverage_data.iteritems():
                if name in ('minion', 'sub_minion'):
                    continue
                if not data:
                    # No coverage data was created
                    continue
                coverage_file = '{0}.{1}'.format(COVERAGE_FILE, name)
                print(
                    '  * Saving remote coverage data from {0}: {1}'.format(
                        name, coverage_file
                    )
                )
                open(coverage_file, 'wb').write(
                    data.decode('base64')
                )
            print_header('', sep='=', inline=True)

        # Let's signal anyone waiting for the event that we're done
        finish_evt.set()

    def __stop_machines(self):
        if self.opts.vagrant_no_stop:
            self.__evt_shutdown.set()
            return

        for machine, vg_path in self.__machines.iteritems():
            header = '  Stopping {0} Machine  '.format(machine)
            print_header(header, centered=True, inline=True)
            try:
                self.__stop_machine(vg_path)
            except VagrantMachineException:
                print('  * Failed to stop machine: {0}'.format(machine))
            print_header('', sep='=', inline=True)

        self.__evt_shutdown.set()

    def __stop_machine(self, machine_path):
        cmd = 'vagrant destroy --force'
        executable = '/bin/sh'

        if self.__rvmrc_source is True:
            cmd = 'source .rvmrc && {0}'.format(cmd)
            executable = '/bin/bash'

        popen = Popen(cmd, cwd=machine_path, shell=True, executable=executable)
        popen.wait()
        if popen.returncode > 0:
            raise VagrantMachineException()


class SaltClientTestCaseMixIn(object):

    _salt_client_config_file_name_ = 'master'
    __slots__ = ('client', '_salt_client_config_file_name_')

    @property
    def client(self):
        return salt.client.LocalClient(
            os.path.join(
                INTEGRATION_TEST_DIR, 'files', 'conf',
                self._salt_client_config_file_name_
            )
        )


class ModuleCase(TestCase, SaltClientTestCaseMixIn):
    '''
    Execute a module function
    '''

    def minion_run(self, _function, *args, **kw):
        '''
        Run a single salt function on the 'minion' target and condition
        the return down to match the behavior of the raw function call
        '''
        return self.run_function(_function, args, **kw)

    def run_function(self, function, arg=(), minion_tgt='minion', **kwargs):
        '''
        Run a single salt function and condition the return down to match the
        behavior of the raw function call
        '''
        know_to_return_none = ('file.chown', 'file.chgrp')
        orig = self.client.cmd(
            minion_tgt, function, arg, timeout=500, kwarg=kwargs
        )

        if minion_tgt not in orig:
            self.skipTest(
                'WARNING(SHOULD NOT HAPPEN #1935): Failed to get a reply '
                'from the minion \'{0}\'. Command output: {1}'.format(
                    minion_tgt, orig
                )
            )
        elif orig[minion_tgt] is None and function not in know_to_return_none:
            self.skipTest(
                'WARNING(SHOULD NOT HAPPEN #1935): Failed to get \'{0}\' from '
                'the minion \'{1}\'. Command output: {2}'.format(
                    function, minion_tgt, orig
                )
            )
        return orig[minion_tgt]

    def run_state(self, function, **kwargs):
        '''
        Run the state.single command and return the state return structure
        '''
        return self.run_function('state.single', [function], **kwargs)

    @property
    def minion_opts(self):
        '''
        Return the options used for the minion
        '''
        return salt.config.minion_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'minion')
        )

    @property
    def sub_minion_opts(self):
        '''
        Return the options used for the minion
        '''
        return salt.config.minion_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'sub_minion')
        )

    @property
    def master_opts(self):
        '''
        Return the options used for the minion
        '''
        return salt.config.master_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
        )


class SyndicCase(TestCase, SaltClientTestCaseMixIn):
    '''
    Execute a syndic based execution test
    '''
    _salt_client_config_file_name_ = 'syndic_master'

    def run_function(self, function, arg=()):
        '''
        Run a single salt function and condition the return down to match the
        behavior of the raw function call
        '''
        orig = self.client.cmd('minion', function, arg, timeout=500)
        if 'minion' not in orig:
            self.skipTest(
                'WARNING(SHOULD NOT HAPPEN #1935): Failed to get a reply '
                'from the minion. Command output: {0}'.format(orig)
            )
        return orig['minion']


class ShellCase(TestCase):
    '''
    Execute a test for a shell command
    '''
    def run_script(self, script, arg_str, catch_stderr=False, timeout=None):
        '''
        Execute a script with the given argument string
        '''
        path = os.path.join(SCRIPT_DIR, script)
        if not os.path.isfile(path):
            return False
        ppath = 'PYTHONPATH={0}:{1}'.format(CODE_DIR, ':'.join(sys.path[1:]))
        cmd = '{0} {1} {2} {3}'.format(ppath, PYEXEC, path, arg_str)

        popen_kwargs = {
            'shell': True,
            'stdout': PIPE
        }

        if catch_stderr is True:
            popen_kwargs['stderr'] = PIPE

        if not sys.platform.lower().startswith('win'):
            popen_kwargs['close_fds'] = True

            def detach_from_parent_group():
                # detach from parent group (no more inherited signals!)
                os.setpgrp()

            popen_kwargs['preexec_fn'] = detach_from_parent_group

        elif sys.platform.lower().startswith('win') and timeout is not None:
            raise RuntimeError('Timeout is not supported under windows')

        process = Popen(cmd, **popen_kwargs)

        if timeout is not None:
            stop_at = datetime.now() + timedelta(seconds=timeout)
            term_sent = False
            while True:
                process.poll()
                if process.returncode is not None:
                    break

                if datetime.now() > stop_at:
                    if term_sent is False:
                        # Kill the process group since sending the term signal
                        # would only terminate the shell, not the command
                        # executed in the shell
                        os.killpg(os.getpgid(process.pid), signal.SIGINT)
                        term_sent = True
                        continue

                    # As a last resort, kill the process group
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)

                    out = [
                        'Process took more than {0} seconds to complete. '
                        'Process Killed!'.format(timeout)
                    ]
                    if catch_stderr:
                        return out, [
                            'Process killed, unable to catch stderr output'
                        ]
                    return out

        if catch_stderr:
            if sys.version_info < (2, 7):
                # On python 2.6, the subprocess'es communicate() method uses
                # select which, is limited by the OS to 1024 file descriptors
                # We need more available descriptors to run the tests which
                # need the stderr output.
                # So instead of .communicate() we wait for the process to
                # finish, but, as the python docs state "This will deadlock
                # when using stdout=PIPE and/or stderr=PIPE and the child
                # process generates enough output to a pipe such that it
                # blocks waiting for the OS pipe buffer to accept more data.
                # Use communicate() to avoid that." <- a catch, catch situation
                #
                # Use this work around were it's needed only, python 2.6
                process.wait()
                out = process.stdout.read()
                err = process.stderr.read()
            else:
                out, err = process.communicate()
            # Force closing stderr/stdout to release file descriptors
            process.stdout.close()
            process.stderr.close()
            try:
                return out.splitlines(), err.splitlines()
            finally:
                try:
                    process.terminate()
                except OSError, err:
                    # process already terminated
                    pass

        data = process.communicate()
        process.stdout.close()

        try:
            return data[0].splitlines()
        finally:
            try:
                process.terminate()
            except OSError, err:
                # process already terminated
                pass

    def run_salt(self, arg_str):
        '''
        Execute salt
        '''
        mconf = os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf')
        arg_str = '-c {0} {1}'.format(mconf, arg_str)
        return self.run_script('salt', arg_str)

    def run_run(self, arg_str):
        '''
        Execute salt-run
        '''
        mconf = os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf')
        arg_str = '-c {0} {1}'.format(mconf, arg_str)
        return self.run_script('salt-run', arg_str)

    def run_run_plus(self, fun, options='', *arg):
        '''
        Execute Salt run and the salt run function and return the data from
        each in a dict
        '''
        ret = {}
        ret['out'] = self.run_run(
            '{0} {1} {2}'.format(options, fun, ' '.join(arg))
        )
        opts = salt.config.master_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
        )
        opts.update({'doc': False, 'fun': fun, 'arg': arg})
        with RedirectStdStreams():
            runner = salt.runner.Runner(opts)
            ret['fun'] = runner.run()
        return ret

    def run_key(self, arg_str, catch_stderr=False):
        '''
        Execute salt-key
        '''
        mconf = os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf')
        arg_str = '-c {0} {1}'.format(mconf, arg_str)
        return self.run_script('salt-key', arg_str, catch_stderr=catch_stderr)

    def run_cp(self, arg_str):
        '''
        Execute salt-cp
        '''
        mconf = os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf')
        arg_str = '--config-dir {0} {1}'.format(mconf, arg_str)
        return self.run_script('salt-cp', arg_str)

    def run_call(self, arg_str):
        mconf = os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf')
        arg_str = '--config-dir {0} {1}'.format(mconf, arg_str)
        return self.run_script('salt-call', arg_str)


class ShellCaseCommonTestsMixIn(object):

    def test_deprecated_config(self):
        """
        test for the --config deprecation warning

        Once --config is fully deprecated, this test can be removed

        """

        if getattr(self, '_call_binary_', None) is None:
            self.skipTest("'_call_binary_' not defined.")

        cfgfile = os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
        out, err = self.run_script(
            self._call_binary_,
            '--config {0}'.format(cfgfile),
            catch_stderr=True
        )
        self.assertIn('Usage: {0}'.format(self._call_binary_), '\n'.join(err))
        self.assertIn('deprecated', '\n'.join(err))

    def test_version_includes_binary_name(self):
        if getattr(self, '_call_binary_', None) is None:
            self.skipTest("'_call_binary_' not defined.")

        out = '\n'.join(self.run_script(self._call_binary_, "--version"))
        self.assertIn(self._call_binary_, out)
        self.assertIn(salt.__version__, out)


class QueryRunningMinionsMixIn(object):
    __running_minions = None

    def get_running_minions(self):
        if self.__running_minions is None:
            client = salt.client.LocalClient(
                os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
            )
            targets = client.cmd('*', 'test.ping', timeout=5)
            if 'minion' in targets and 'sub_minion' in targets:
                # We need at least minion and sub_minion which are local
                self.__running_minions = salt.utils.isorted([
                    name for (name, running) in targets.iteritems()
                    if running is True
                ])
        return self.__running_minions or []


class SaltReturnAssertsMixIn(object):

    def assertReturnSaltType(self, ret):
        try:
            self.assertTrue(isinstance(ret, dict))
        except AssertionError:
            raise AssertionError(
                '{0} is not dict. Salt returned: {1}'.format(
                    type(ret).__name__, ret
                )
            )

    def assertReturnNonEmptySaltType(self, ret):
        self.assertReturnSaltType(ret)
        try:
            self.assertNotEqual(ret, {})
        except AssertionError:
            raise AssertionError(
                '{} is equal to {}. Salt returned an empty dictionary.'
            )

    def __return_valid_keys(self, keys):
        if isinstance(keys, tuple):
            # If it's a tuple, turn it into a list
            keys = list(keys)
        elif isinstance(keys, basestring):
            # If it's a basestring , make it a one item list
            keys = [keys]
        elif not isinstance(keys, list):
            # If we've reached here, it's a bad type passed to keys
            raise RuntimeError('The passed keys need to be a list')
        return keys

    def __getWithinSaltReturn(self, ret, keys):
        self.assertReturnNonEmptySaltType(ret)
        keys = self.__return_valid_keys(keys)
        okeys = keys[:]
        for part in ret.itervalues():
            try:
                ret_item = part[okeys.pop(0)]
            except (KeyError, TypeError):
                raise AssertionError(
                    'Could not get ret{0} from salt\'s return: {1}'.format(
                        ''.join(['[{0!r}]'.format(k) for k in keys]), part
                    )
                )
            while okeys:
                try:
                    ret_item = ret_item[okeys.pop(0)]
                except (KeyError, TypeError):
                    raise AssertionError(
                        'Could not get ret{0} from salt\'s return: {1}'.format(
                            ''.join(['[{0!r}]'.format(k) for k in keys]), part
                        )
                    )
            return ret_item

    def assertSaltTrueReturn(self, ret):
        try:
            self.assertTrue(self.__getWithinSaltReturn(ret, 'result'))
        except AssertionError:
            raise AssertionError(
                '{result} is not True. Salt Comment:\n{comment}'.format(
                    **(ret.values()[0])
                )
            )

    def assertSaltFalseReturn(self, ret):
        try:
            self.assertFalse(self.__getWithinSaltReturn(ret, 'result'))
        except AssertionError:
            raise AssertionError(
                '{result} is not False. Salt Comment:\n{comment}'.format(
                    **(ret.values()[0])
                )
            )

    def assertSaltNoneReturn(self, ret):
        try:
            self.assertIsNone(self.__getWithinSaltReturn(ret, 'result'))
        except AssertionError:
            raise AssertionError(
                '{result} is not None. Salt Comment:\n{comment}'.format(
                    **(ret.values()[0])
                )
            )

    def assertInSaltComment(self, ret, in_comment):
        return self.assertIn(
            in_comment, self.__getWithinSaltReturn(ret, 'comment')
        )

    def assertNotInSaltComment(self, ret, not_in_comment):
        return self.assertNotIn(
            not_in_comment, self.__getWithinSaltReturn(ret, 'comment')
        )

    def assertSaltCommentRegexpMatches(self, ret, pattern):
        return self.assertInSaltReturnRegexpMatches(ret, pattern, 'comment')

    def assertInSaltReturn(self, ret, item_to_check, keys):
        return self.assertIn(
            item_to_check, self.__getWithinSaltReturn(ret, keys)
        )

    def assertNotInSaltReturn(self, ret, item_to_check, keys):
        return self.assertNotIn(
            item_to_check, self.__getWithinSaltReturn(ret, keys)
        )

    def assertInSaltReturnRegexpMatches(self, ret, pattern, keys=()):
        return self.assertRegexpMatches(
            self.__getWithinSaltReturn(ret, keys), pattern
        )

    def assertSaltStateChangesEqual(self, ret, comparison, keys=()):
        keys = ['changes'] + self.__return_valid_keys(keys)
        return self.assertEqual(
            self.__getWithinSaltReturn(ret, keys), comparison
        )

    def assertSaltStateChangesNotEqual(self, ret, comparison, keys=()):
        keys = ['changes'] + self.__return_valid_keys(keys)
        return self.assertNotEqual(
            self.__getWithinSaltReturn(ret, keys), comparison
        )
