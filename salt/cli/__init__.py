'''
The management of salt command line utilities are stored in here
'''

# Import python libs
import os
import sys

# Import salt libs
import salt.cli.caller
import salt.cli.cp
import salt.cli.batch
import salt.client
import salt.output
import salt.runner
import salt.auth
import salt.key

from salt.utils import migrations, parsers
from salt.utils.verify import (
    check_user,
    verify_env,
    verify_files,
    verify_socket
)
from salt.exceptions import (
    SaltInvocationError,
    SaltClientError,
    EauthAuthenticationError
)


class Master(parsers.MasterOptionParser):
    '''
    Creates a master server
    '''

    def prepare(self):
        '''
        Run the preparation sequence required to start a salt master server.

        If sub-classed, don't **ever** forget to run:

            super(YourSubClass, self).prepare()
        '''
        self.parse_args()

        try:
            if self.config['verify_env']:
                verify_env(
                    [
                        self.config['pki_dir'],
                        os.path.join(self.config['pki_dir'], 'minions'),
                        os.path.join(self.config['pki_dir'], 'minions_pre'),
                        os.path.join(self.config['pki_dir'],
                                     'minions_rejected'),
                        self.config['cachedir'],
                        os.path.join(self.config['cachedir'], 'jobs'),
                        os.path.join(self.config['cachedir'], 'proc'),
                        self.config['sock_dir'],
                        self.config['token_dir'],
                    ],
                    self.config['user'],
                    permissive=self.config['permissive_pki_access'],
                    pki_dir=self.config['pki_dir'],
                )
                if (not self.config['log_file'].startswith('tcp://') or
                    not self.config['log_file'].startswith('udp://') or
                    not self.config['log_file'].startswith('file://')):
                    # Logfile is not using Syslog, verify
                    verify_files(
                        [self.config['log_file']],
                        self.config['user']
                    )
        except OSError as err:
            sys.exit(err.errno)

        self.setup_logfile_logger()
        logger.warn('Setting up the Salt Master')

        if not verify_socket(self.config['interface'],
                             self.config['publish_port'],
                             self.config['ret_port']):
            self.exit(4, 'The ports are not available to bind\n')
        migrations.migrate_paths(self.config)

        # Late import so logging works correctly
        import salt.master
        self.master = salt.master.Master(self.config)
        self.daemonize_if_required()
        self.set_pidfile()

    def start(self):
        '''
        Start the actual master.

        If sub-classed, don't **ever** forget to run:

            super(YourSubClass, self).start()

        NOTE: Run any required code before calling `super()`.
        '''
        self.prepare()
        if check_user(self.config['user']):
            try:
                self.master.start()
            except salt.master.MasterExit:
                self.shutdown()
            finally:
                sys.exit()

    def shutdown(self):
        '''
        If sub-classed, run any shutdown operations on this method.
        '''


class Minion(parsers.MinionOptionParser):
    '''
    Create a minion server
    '''

    def prepare(self):
        '''
        Run the preparation sequence required to start a salt minion.

        If sub-classed, don't **ever** forget to run:

            super(YourSubClass, self).prepare()
        '''
        self.parse_args()

        try:
            if self.config['verify_env']:
                confd = os.path.join(
                    os.path.dirname(self.config['conf_file']),
                    'minion.d'
                )
                verify_env(
                    [
                        self.config['pki_dir'],
                        self.config['cachedir'],
                        self.config['sock_dir'],
                        self.config['extension_modules'],
                        confd,
                    ],
                    self.config['user'],
                    permissive=self.config['permissive_pki_access'],
                    pki_dir=self.config['pki_dir'],
                )
                if (not self.config['log_file'].startswith('tcp://') or
                    not self.config['log_file'].startswith('udp://') or
                    not self.config['log_file'].startswith('file://')):
                    # Logfile is not using Syslog, verify
                    verify_files(
                        [self.config['log_file']],
                        self.config['user']
                    )
                verify_files(
                    [self.config['log_file']],
                    self.config['user'])
        except OSError as err:
            sys.exit(err.errno)

        self.setup_logfile_logger()
        logger.warn(
            'Setting up the Salt Minion "{0}"'.format(
                self.config['id']
            )
        )
        migrations.migrate_paths(self.config)
        # Late import so logging works correctly
        import salt.minion
        # If the minion key has not been accepted, then Salt enters a loop
        # waiting for it, if we daemonize later then the minion could halt
        # the boot process waiting for a key to be accepted on the master.
        # This is the latest safe place to daemonize
        self.daemonize_if_required()
        self.minion = salt.minion.Minion(self.config)
        self.set_pidfile()

    def start(self):
        '''
        Start the actual minion.

        If sub-classed, don't **ever** forget to run:

            super(YourSubClass, self).start()

        NOTE: Run any required code before calling `super()`.
        '''
        self.prepare()
        try:
            if check_user(self.config['user']):
                self.minion.tune_in()
        except KeyboardInterrupt:
            logger.warn('Stopping the Salt Minion')
            self.shutdown()
        finally:
            raise SystemExit('\nExiting on Ctrl-c')

    def shutdown(self):
        '''
        If sub-classed, run any shutdown operations on this method.
        '''


class Syndic(parsers.SyndicOptionParser):
    '''
    Create a syndic server
    '''

    def prepare(self):
        '''
        Run the preparation sequence required to start a salt syndic minion.

        If sub-classed, don't **ever** forget to run:

            super(YourSubClass, self).prepare()
        '''
        self.parse_args()
        try:
            if self.config['verify_env']:
                verify_env(
                    [
                        self.config['pki_dir'],
                        self.config['cachedir'],
                        self.config['sock_dir'],
                        self.config['extension_modules'],
                    ],
                    self.config['user'],
                    permissive=self.config['permissive_pki_access'],
                    pki_dir=self.config['pki_dir'],
                )
                if (not self.config['log_file'].startswith('tcp://') or
                    not self.config['log_file'].startswith('udp://') or
                    not self.config['log_file'].startswith('file://')):
                    # Logfile is not using Syslog, verify
                    verify_files(
                        [self.config['log_file']],
                        self.config['user']
                    )
        except OSError as err:
            sys.exit(err.errno)

        self.setup_logfile_logger()
        logger.warn(
            'Setting up the Salt Syndic Minion "{0}"'.format(
                self.config['id']
            )
        )

        # Late import so logging works correctly
        import salt.minion
        self.daemonize_if_required()
        self.syndic = salt.minion.Syndic(self.config)
        self.set_pidfile()

    def start(self):
        '''
        Start the actual syndic.

        If sub-classed, don't **ever** forget to run:

            super(YourSubClass, self).start()

        NOTE: Run any required code before calling `super()`.
        '''
        self.prepare()
        if check_user(self.config['user']):
            try:
                self.syndic.tune_in()
            except KeyboardInterrupt:
                logger.warn('Stopping the Salt Syndic Minion')
                self.shutdown()
            finally:
                raise SystemExit('\nExiting on Ctrl-c')

    def shutdown(self):
        '''
        If sub-classed, run any shutdown operations on this method.
        '''


class SaltCMD(parsers.SaltCMDOptionParser):
    '''
    The execution of a salt command happens here
    '''

    def run(self):
        '''
        Execute the salt command line
        '''
        self.parse_args()

        try:
            local = salt.client.LocalClient(
                self.get_config_file_path('master')
            )
        except SaltClientError as exc:
            self.exit(2, '{0}\n'.format(exc))
            return

        if self.options.batch:
            batch = salt.cli.batch.Batch(self.config)
            # Printing the output is already taken care of in run() itself
            for res in batch.run():
                pass
        else:
            if self.options.timeout <= 0:
                self.options.timeout = local.opts['timeout']

            kwargs = {
                'tgt': self.config['tgt'],
                'fun': self.config['fun'],
                'arg': self.config['arg'],
                'timeout': self.options.timeout}

            if 'token' in self.config:
                kwargs['token'] = self.config['token']

            if self.selected_target_option:
                kwargs['expr_form'] = self.selected_target_option
            else:
                kwargs['expr_form'] = 'glob'

            if getattr(self.options, 'return'):
                kwargs['ret'] = getattr(self.options, 'return')

            if self.options.eauth:
                resolver = salt.auth.Resolver(self.config)
                res = resolver.cli(self.options.eauth)
                if self.options.mktoken and res:
                    tok = resolver.token_cli(
                            self.options.eauth,
                            res
                            )
                    if tok:
                        kwargs['token'] = tok.get('token', '')
                if not res:
                    sys.exit(2)
                kwargs.update(res)
                kwargs['eauth'] = self.options.eauth

            try:
                # local will be None when there was an error
                if local:
                    if self.options.static:
                        if self.options.verbose:
                            kwargs['verbose'] = True
                        full_ret = local.cmd_full_return(**kwargs)
                        ret, out = self._format_ret(full_ret)
                        self._output_ret(ret, out)
                    elif self.config['fun'] == 'sys.doc':
                        ret = {}
                        out = ''
                        for full_ret in local.cmd_cli(**kwargs):
                            ret_, out = self._format_ret(full_ret)
                            ret.update(ret_)
                        self._output_ret(ret, out)
                    else:
                        if self.options.verbose:
                            kwargs['verbose'] = True
                        for full_ret in local.cmd_cli(**kwargs):
                            ret, out = self._format_ret(full_ret)
                            self._output_ret(ret, out)
            except (SaltInvocationError, EauthAuthenticationError) as exc:
                ret = exc
                out = ''
                self._output_ret(ret, out)

    def _output_ret(self, ret, out):
        '''
        Print the output from a single return to the terminal
        '''
        # Handle special case commands
        if self.config['fun'] == 'sys.doc' and not isinstance(ret, Exception):
            self._print_docs(ret)
        else:
            # Determine the proper output method and run it
            salt.output.display_output(ret, out, self.config)

    def _format_ret(self, full_ret):
        '''
        Take the full return data and format it to simple output
        '''
        ret = {}
        out = ''
        for key, data in full_ret.items():
            ret[key] = data['ret']
            if 'out' in data:
                out = data['out']
        return ret, out

    def _print_docs(self, ret):
        '''
        Print out the docstrings for all of the functions on the minions
        '''
        docs = {}
        if not ret:
            self.exit(2, 'No minions found to gather docs from\n')

        for host in ret:
            for fun in ret[host]:
                if fun not in docs:
                    if ret[host][fun]:
                        docs[fun] = ret[host][fun]
        for fun in sorted(docs):
            print(fun + ':')
            print(docs[fun])
            print('')


class SaltCP(parsers.SaltCPOptionParser):
    '''
    Run the salt-cp command line client
    '''

    def run(self):
        '''
        Execute salt-cp
        '''
        self.parse_args()
        cp_ = salt.cli.cp.SaltCP(self.config)
        cp_.run()


class SaltKey(parsers.SaltKeyOptionParser):
    '''
    Initialize the Salt key manager
    '''

    def run(self):
        '''
        Execute salt-key
        '''
        self.parse_args()

        if self.config['verify_env']:
            verify_env_dirs = []
            if not self.config['gen_keys']:
                verify_env_dirs.extend([
                    self.config['pki_dir'],
                    os.path.join(self.config['pki_dir'], 'minions'),
                    os.path.join(self.config['pki_dir'], 'minions_pre'),
                    os.path.join(self.config['pki_dir'], 'minions_rejected'),
                    os.path.dirname(self.config['key_logfile'])
                ])

            verify_env(
                verify_env_dirs,
                self.config['user'],
                permissive=self.config['permissive_pki_access'],
                pki_dir=self.config['pki_dir'],
            )

        self.setup_logfile_logger()

        key = salt.key.KeyCLI(self.config)
        key.run()


class SaltCall(parsers.SaltCallOptionParser):
    '''
    Used to locally execute a salt command
    '''

    def run(self):
        '''
        Execute the salt call!
        '''
        self.parse_args()

        if self.config['verify_env']:
            verify_env([
                    self.config['pki_dir'],
                    self.config['cachedir'],
                ],
                self.config['user'],
                permissive=self.config['permissive_pki_access'],
                pki_dir=self.config['pki_dir'],
            )
            if (not self.config['log_file'].startswith('tcp://') or
                not self.config['log_file'].startswith('udp://') or
                not self.config['log_file'].startswith('file://')):
                # Logfile is not using Syslog, verify
                verify_files(
                    [self.config['log_file']],
                    self.config['user']
                )

        if self.options.local:
            self.config['file_client'] = 'local'

        # Setup file logging!
        self.setup_logfile_logger()

        caller = salt.cli.caller.Caller(self.config)

        if self.options.doc:
            caller.print_docs()
            self.exit(0)

        if self.options.grains_run:
            caller.print_grains()
            self.exit(0)

        caller.run()


class SaltRun(parsers.SaltRunOptionParser):

    def run(self):
        '''
        Execute salt-run
        '''
        self.parse_args()

        runner = salt.runner.Runner(self.config)
        if self.options.doc:
            runner._print_docs()
        else:
            # Run this here so SystemExit isn't raised anywhere else when
            # someone tries to use the runners via the python api
            try:
                runner.run()
            except SaltClientError as exc:
                raise SystemExit(str(exc))
