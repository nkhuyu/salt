'''
Set up the Salt integration test suite
'''

# Import Python libs
import optparse
import multiprocessing
import os
import sys
import shutil
import subprocess
import tempfile
import time
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
from salt.utils import get_colors, which
from salt.utils.verify import verify_env
from saltunittest import TestCase

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

SYS_TMP_DIR = tempfile.gettempdir()
TMP = os.path.join(SYS_TMP_DIR, 'salt-tests-tmpdir')
FILES = os.path.join(INTEGRATION_TEST_DIR, 'files')
MOCKBIN = os.path.join(INTEGRATION_TEST_DIR, 'mockbin')
COVERAGE_FILE = os.path.join(tempfile.gettempdir(), '.coverage')
TESTING_SDIST_DIR = os.path.join(TMP, 'salt-source')

MINIONS_CONNECT_TIMEOUT = MINIONS_SYNC_TIMEOUT = 60
# Max time, in seconds, that creating an sdist can take
SDIST_COMPRESS_TIMEOUT = 10

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

    def __init__(self, opts):
        self.opts = opts

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
        self.sub_minion_opts = salt.config.minion_config(
            os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'sub_minion')
        )
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
            'base': [os.path.join(FILES, 'file', 'base'), TESTING_SDIST_DIR],
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

        evt_minions_connect = multiprocessing.Event()
        evt_minions_sync = multiprocessing.Event()
        minion_targets = set(['minion', 'sub_minion'])

        # Wait for minions to connect back
        wait_minions_connection = multiprocessing.Process(
            target=self.__wait_for_minions_connections,
            args=(evt_minions_connect, minion_targets)
        )
        wait_minions_connection.start()
        if evt_minions_connect.wait(MINIONS_CONNECT_TIMEOUT) is False:
            print('WARNING: Minions failed to connect back. Tests requiring '
                  'them WILL fail')
        wait_minions_connection.terminate()
        del(evt_minions_connect, wait_minions_connection)

        # Wait for minions to "sync_all"
        sync_minions = multiprocessing.Process(
            target=self.__sync_minions,
            args=(evt_minions_sync, minion_targets)
        )
        sync_minions.start()
        if evt_minions_sync.wait(MINIONS_SYNC_TIMEOUT) is False:
            print('WARNING: Minions failed to sync. Tests requiring the '
                  'testing `runtests_helper` module WILL fail')
        sync_minions.terminate()
        del(evt_minions_sync, sync_minions)

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

        print_header('', sep='=', inline=True)

        return self

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
        # overridden in the VagrantTestDaemon
        pass

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
        now = datetime.now()
        expire = now + timedelta(seconds=timeout)
        while now <= expire:
            running = self.__client_job_running(targets, jid)
            if evt is None or (evt is not None and evt.is_set()):
                sys.stdout.write('\r' + ' ' * PNUM + '\r')
            if not running:
                #if evt is None or (evt is not None and evt.is_set()):
                #    print
                return True
            if evt is None or (evt is not None and evt.is_set()):
                sys.stdout.write(
                    '    * [Quit in {0}] Waiting for {1}'.format(
                        '{0}'.format(expire - now).rsplit('.', 1)[0],
                        ', '.join(running)
                    )
                )
                sys.stdout.flush()
            time.sleep(1)
            now = datetime.now()
        else:
            if evt is None or (evt is not None and evt.is_set()):
                sys.stdout.write(
                    '\n    * ERROR: Failed to get information back\n'
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

    def __wait_for_minions_connections(self, evt, targets):
        print_header(
            'Waiting at most {0} secs for local minions to connect '
            'back and another {1} secs for them to '
            '"saltutil.sync_all()"'.format(
                MINIONS_CONNECT_TIMEOUT, MINIONS_SYNC_TIMEOUT
            ), sep='=', centered=True
        )
        targets = set(['minion', 'sub_minion'])
        expected_connections = set(targets)
        while True:
            # If enough time passes, a timeout will be triggered by
            # multiprocessing.Event, so, we can have this while True here
            targets = self.client.cmd('*', 'test.ping')
            for target in targets:
                if target not in expected_connections:
                    # Someone(minion) else "listening"?
                    continue
                expected_connections.remove(target)
                print('  * {0} minion connected'.format(target))
            if not expected_connections:
                # All expected connections have connected
                break
            time.sleep(1)
        evt.set()

    def __client_job_running(self, targets, jid):
        running = self.client.cmd(
            ','.join(targets), 'saltutil.running', expr_form='list'
        )
        return [
            k for (k, v) in running.iteritems() if v and v[0]['jid'] == jid
        ]

    def __sync_minions(self, evt, targets):
        # Let's sync all connected minions
        print('  * Syncing local minion\'s dynamic data(saltutil.sync_all)')
        syncing = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'saltutil.sync_all',
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid']) is False:
            raise Exception('foo')

        while syncing:
            rdata = self.client.get_returns(jid_info['jid'], syncing, 1)
            if rdata:
                for idx, (name, output) in enumerate(rdata.iteritems()):
                    print('    * Synced {0}: {1}'.format(name, output))
                    # Synced!
                    try:
                        syncing.remove(name)
                    except KeyError:
                        print('    * {0} already synced???  {1}'.format(
                            name, output
                        ))
        evt.set()


class VagrantMachineException(Exception):
    """
    Simple exception to catch some errors while starting the vagrant machines
    """


class VagrantTestDaemon(TestDaemon):
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

    def __enter__(self):
        # Run the __enter__ code from TestDaemon
        ret = super(VagrantTestDaemon, self).__enter__()
        # Wait for the vagrant stuff to start before returning the code
        # execution back
        # Start the vagrant machines
        self.__sdist_salt_source()
        if self.__evt_sdist.wait(SDIST_COMPRESS_TIMEOUT) is False:
            # Usually on the 2nd run it creates the compressed source file
            self.__sdist_salt_source_process.terminate()
            self.__sdist_salt_source()
            if self.__evt_sdist.wait(SDIST_COMPRESS_TIMEOUT) is False:
                sys.stdout.write('\r' + ' ' * PNUM + '\r')
                print(
                    'WARNING: Failed to create an sdist. Won\'t start vagrant '
                    'machines.'
                )
                self.__sdist_salt_source_process.terminate()
                return ret
        self.__start_machines()
        self.__evt_started.wait()
        return ret

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
            sys.stdout.write('  * Waiting for test results from ...')
            sys.stdout.flush()
        self.__evt_progress.set()

    def __sdist_salt_source(self):
        #self.__sdist_salt_source_process = threading.Thread(
        self.__sdist_salt_source_process = multiprocessing.Process(
            target=self.__sdist_salt_source_bg, args=(self.__evt_sdist,)
        )
        sys.stdout.write('\r' + ' ' * PNUM + '\r')
        sys.stdout.write(
            ' * Creating source distribution to supply to vagrant machines '
        )
        sys.stdout.flush()
        self.__sdist_salt_source_process.start()

    def __sdist_salt_source_bg(self, sdist_evt):
        popen = subprocess.Popen(' '.join([
                'sleep 1;',
                #sys.executable,
                'python',
                'setup.py',
                'clean',
            ]),
            cwd=CODE_DIR,
            shell=True,
            #bufsize=-1,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
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

        popen = subprocess.Popen(' '.join([
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
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
        print('   * Compressed salt\'s source: {0}'.format(dname_path))
        sdist_evt.set()

    def __start_machines(self):
        for machine, vg_path in self.__machines.copy().iteritems():
            header = '  Starting {0} Machine  '.format(machine)
            vagrant_skip = os.path.join(vg_path, 'Vagrantfile.skip')
            if os.path.exists(vagrant_skip):
                header += '~  SKIPPED  '
            print_header(header, centered=True, inline=True)
            if os.path.exists(vagrant_skip):
                self.__machines.pop(machine)
                continue
            try:
                self.__start_machine(vg_path)
            except VagrantMachineException:
                print('  * Failed to start machine: {0}'.format(machine))
                self.__machines.pop(machine)
            print_header('~', inline=True)
            time.sleep(0.2)
        self.__run_tests()

    def __start_machine(self, machine_path):
        if self.__rvmrc_source is None:
            if which('vagrant') is None:
                self.__rvmrc_source = True
            else:
                # Let's check if we need to source .rvmrc
                try:
                    popen = subprocess.Popen(
                        ['vagrant', '--help'], cwd=machine_path,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
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

        popen = subprocess.Popen(
            cmd, cwd=machine_path, shell=True, executable=executable
        )
        popen.wait()
        if popen.returncode > 0:
            raise VagrantMachineException()

    def __run_tests(self):
        self.__evt_sdist.wait()
        self.__tests_process = multiprocessing.Process(
            target=self.__run_tests_target,
            args=(self.__evt_started, self.__evt_finished, self.__evt_progress)
        )
        self.__tests_process.start()

    def __run_tests_target(self, start_evt, finish_evt, progress_evt):
        sleep = 60
        print_header(
            'Waiting at most {0} secs for remote minions to connect '
            'back'.format(sleep), sep='=', centered=True
        )
        expected_connection = set(self.__machines.keys())
        while sleep > 0:
            # Let's get the minions who are responding back
            targets = filter(
                lambda x: x not in ('minion', 'sub_minion'),
                self.client.cmd('*', 'test.ping')
            )
            for target in targets:
                if target not in expected_connection:
                    continue
                print('  * {0} minion connected'.format(target))
                expected_connection.remove(target)

            if not expected_connection:
                time.sleep(1)
                break
            time.sleep(1)
            sleep -= 1
        else:
            if expected_connection:
                print(
                    '  * Failed to get a connection back from: {0}'.format(
                        ', '.join(expected_connection)
                    )
                )

        def check_available_targets():
            if not targets:
                print_header(
                    'There aren\'t any minions running to run remote tests '
                    'against', sep='=', centered=True
                )

                start_evt.set()
                finish_evt.set()
                return False
            return True

        if not check_available_targets():
            return

        targets = set(targets)

        # Let's sync all connected minions
        print('  * Syncing minion\'s dynamic data(saltutil.sync_all)')
        syncing = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'saltutil.sync_all',
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid'], 5*60) is False:
            raise Exception('foo')

        while syncing:
            rdata = self.client.get_returns(jid_info['jid'], syncing, 10)
            if rdata:
                for idx, (name, output) in enumerate(rdata.iteritems()):
                    if name in ('minion', 'sub_minion'):
                        continue
                    print('    * Synced {0}: {1}'.format(name, output))
                    # Synced!
                    try:
                        syncing.remove(name)
                    except KeyError:
                        print('    * {0} already synced???  {1}'.format(
                            name, output
                        ))

        # Let's install required packages
        # I need to do this as a separate step because I need to use a
        # grain which depends on a package. Having it all in the same state
        # file would create circular dependencies.
        print('  * Installing runtests dependencies on the minion\'s')
        runtests_pkgs_sls = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'state.sls', arg=['mods=runtests.pkgs'],
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid'], 10*60) is False:
            raise Exception('foo')

        while runtests_pkgs_sls:
            rdata = self.client.get_returns(
                jid_info['jid'], runtests_pkgs_sls, 10
            )
            if rdata:
                for idx, (name, output) in enumerate(rdata.iteritems()):
                    if name in ('minion', 'sub_minion'):
                        # These should never appear here
                        continue

                    print(
                        '    * Minion {0} seems to have completed installing '
                        'salt\'s package dependencies .'.format(name)
                    )
                    try:
                        failed = [
                            s for s in output.values() if s['result'] is False
                        ]
                        if failed:
                            print(
                                '      * Failed to install salt\'s '
                                'dependencies on minion {0}. '
                                'Failing: {1}'.format(
                                    name,
                                    '; '.join([s['comment'] for s in failed])
                                )
                            )
                            print(
                                '      * Removing {0} from overall '
                                'targets'.format(name)
                            )
                            try:
                                targets.remove(name)
                            except KeyError:
                                print(
                                    '      * Failed to remove {0} from overall'
                                    'targets. Previously removed!?!?!?'.format(
                                        name
                                    )
                                )
                            break
                        try:
                            print('    * Removing {0} from salt\'s packages '
                                  'dependencies install targets.'.format(name))
                            runtests_pkgs_sls.remove(name)
                        except KeyError:
                            print('      * Failed to remove {0} from salt\'s '
                                  'packages install targets. Previously '
                                  'removed!?!?!?'.format(name))
                            print output
                    except AttributeError:
                        print(
                            '    * Error installing salt\'s package '
                            'dependencies on {0}: {1}'.format(name, output)
                        )

        if not check_available_targets():
            return

        # Let's run the setup states
        print('  * Setting up the salt source on the minion\'s')
        runtests_setup_sls = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'state.sls', arg=['mods=runtests.setup'],
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid'], 10*60) is False:
            raise Exception('foo')

        while runtests_setup_sls:
            rdata = self.client.get_returns(
                jid_info['jid'], runtests_setup_sls, 10
            )
            if rdata:
                for idx, (name, output) in enumerate(rdata.iteritems()):
                    if name in ('minion', 'sub_minion'):
                        # These should never appear here
                        continue

                    print('    * Minion {0} seems to have completed setting '
                          'up salt\'s source.'.format(name))
                    try:
                        failed = [
                            s for s in output.values() if s['result'] is False
                        ]
                        if failed:
                            print(
                                '      * Failed to setup salt\'s source on '
                                'minion {0}. Failing: {1}'.format(
                                    name,
                                    '; '.join([s['comment'] for s in failed])
                                )
                            )
                            print(
                                '      * Removing {0} from overall '
                                'targets'.format(name)
                            )
                            try:
                                targets.remove(name)
                            except KeyError:
                                print(
                                    '      * Failed to remove {0} from overall'
                                    'targets. Previously removed!?!?!?'.format(
                                        name
                                    )
                                )
                            break
                        try:
                            print('    * Removing {0} from salt\'s source '
                                  'setup targets.'.format(name))
                            runtests_setup_sls.remove(name)
                        except KeyError:
                            print('      * Failed to remove {0} from salt\'s '
                                  'source setup targets. Previously '
                                  'removed!?!?!?'.format(name))
                    except AttributeError:
                        print('    * Error setting up salt\'s source on '
                              '{0}: {1}'.format(name, output))

        if not check_available_targets():
            return

        # Let's run the setup states
        print('  * Creating runtests virtualenv on the minion\'s')
        runtests_sls = set(targets)
        jid_info = self.client.run_job(
            ','.join(targets), 'state.sls', arg=['mods=runtests'],
            expr_form='list',
            timeout=9999999999999999,
        )

        if self.wait_for_jid(targets, jid_info['jid'], 10*60) is False:
            raise Exception('foo')

        while runtests_sls:
            rdata = self.client.get_returns(jid_info['jid'], runtests_sls, 10)
            if rdata:
                for idx, (name, output) in enumerate(rdata.iteritems()):
                    if name in ('minion', 'sub_minion'):
                        # These should never appear here
                        continue

                    print('  * Minion {0} seems to have completed setting up '
                          'salt\'s virtualenv.'.format(name))
                    try:
                        failed = [
                            s for s in output.values() if s['result'] is False
                        ]
                        if failed:
                            print(
                                '  * Failed to setup salt\'s virtualenv on '
                                'minion {0}. Failing: {1}'.format(
                                    name,
                                    '; '.join([s['comment'] for s in failed])
                                )
                            )
                            print(
                                '    * Removing {0} from overall '
                                'targets'.format(name)
                            )
                            try:
                                targets.remove(name)
                            except KeyError:
                                print(
                                    '    * Failed to remove {0} from overall'
                                    'targets. Previously removed!?!?!?'.format(
                                        name
                                    )
                                )
                            break

                        try:
                            print('    * Removing {0} from salt\'s virtualenv '
                                  'setup targets.'.format(name))
                            runtests_sls.remove(name)
                        except KeyError:
                            print('    * Failed to remove {0} from salt\'s '
                                  'virtualenv setup targets. Previously '
                                  'removed!?!?!?'.format(name))
                    except AttributeError:
                        print('    * Error setting up salt\'s virtualenv on '
                              '{0}: {1}'.format(name, output))

        if not check_available_targets():
            return

        print_header('=', sep='=', inline=True)
        start_evt.set()

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
            name=(':'.join(self.opts.name) if self.opts.name else None),
            #unit=True,
            #shell=True,
            #module=True,
            #states=True,
            screen_width=width,
            screen_height=height,
            cwd=os.getcwd()
        )
        if self.opts.xmlout:
            run_tests_kwargs['xml'] = True

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

        if self.wait_for_jid(targets, jid_info['jid'], 60*60, evt=progress_evt) is False:
            raise Exception('foo')

        data = {}
        steps = 3

        while running:
            rdata = self.client.get_returns(jid_info['jid'], running, 1)
            if rdata:
                for idx, (name, output) in enumerate(rdata.iteritems()):
                    if name in ('minion', 'sub_minion'):
                        continue
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
                                '\n  * The minion {0} is not able to run the '
                                'test suite because the \'runtests\' module '
                                'wasn\'t uploaded to it. Removing it from the '
                                'testing targets.'.format(name)
                            )
                            targets.remove(name)
                        else:
                            print(
                                '\n  * An error occurred on {0}: {1}'.format(
                                    name, output
                                )
                            )
                        continue

                    print
                    if idx + 1 % 2:
                        print(get_colors(True)['LIGHT_BLUE'])
                    print_header(
                        '  {0} ~ Remote Test Results ~ {1}  '.format(
                            name,
                            (output['retcode'] > 0 and 'FAILED' or 'PASSED')
                        ), inline=True, centered=True
                    )
                    if output['retcode'] > 0:
                        print(output['stderr'])
                    print(output['stdout'])

                    print_header('~', inline=True)
                    if idx + 1 % 2:
                        print(get_colors(True)['ENDC'])

            if not running:
                # All remote tests have finished. Exit the loop
                print
                print_header('', sep='=', inline=True)
                break

            elif steps <= 0:
                # We're still waiting for results from the remote vagrant
                # minions running the test suite.
                steps = 3
                if progress_evt.is_set():
                    sys.stdout.write('\r' + ' ' * PNUM + '\r')
                    sys.stdout.write(
                        '  * Waiting for test results from {0} '.format(
                            ', '.join(running)
                        )
                    )
            else:
                steps -= 1
                if progress_evt.is_set():
                    sys.stdout.write('.')
            sys.stdout.flush()

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

        popen = subprocess.Popen(
            cmd, cwd=machine_path, shell=True, executable=executable
        )
        popen.wait()
        if popen.returncode > 0:
            raise VagrantMachineException()


class ModuleCase(TestCase):
    '''
    Execute a module function
    '''

    _client = None

    @property
    def client(self):
        if self._client is None:
            self._client = salt.client.LocalClient(
                os.path.join(INTEGRATION_TEST_DIR, 'files', 'conf', 'master')
            )
        return self._client

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

    def state_result(self, ret, raw=False):
        '''
        Return the result data from a single state return
        '''
        res = ret[next(iter(ret))]
        if raw:
            return res
        return res['result']

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

    def assert_success(self, ret):
        try:
            res = self.state_result(ret, raw=True)
        except TypeError:
            pass
        else:
            if isinstance(res, dict):
                if res['result'] is True:
                    return
                if 'comment' in res:
                    raise AssertionError(res['comment'])
                ret = res
        raise AssertionError('bad result: %r' % (ret))


class SyndicCase(TestCase):
    '''
    Execute a syndic based execution test
    '''
    def setUp(self):
        '''
        Generate the tools to test a module
        '''
        super(SyndicCase, self).setUp()
        self.client = salt.client.LocalClient(
            os.path.join(
                INTEGRATION_TEST_DIR,
                'files', 'conf', 'syndic_master'
            )
        )

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
    def run_script(self, script, arg_str, catch_stderr=False):
        '''
        Execute a script with the given argument string
        '''
        path = os.path.join(SCRIPT_DIR, script)
        if not os.path.isfile(path):
            return False
        ppath = 'PYTHONPATH={0}:{1}'.format(CODE_DIR, ':'.join(sys.path[1:]))
        cmd = '{0} {1} {2} {3}'.format(ppath, PYEXEC, path, arg_str)

        if catch_stderr:
            process = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if sys.version_info[0:2] < (2, 7):
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

        process = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE
        )
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
        print 777, self.__running_minions
        return self.__running_minions or []
