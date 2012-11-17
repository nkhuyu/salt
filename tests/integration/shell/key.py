# Import python libs
import os
import sys
import shutil
import tempfile

# Import salt libs
from salt import version
from saltunittest import TestLoader, TextTestRunner
import integration
from integration import TestDaemon


class KeyTest(integration.ShellCase,
              integration.QueryRunningMinionsMixIn,
              integration.ShellCaseCommonTestsMixIn):
    '''
    Test salt-key script
    '''

    _call_binary_ = 'salt-key'

    def test_list(self):
        '''
        test salt-key -L
        '''
        data = self.run_key('-L')
        expect = [
            'Accepted Keys:',
            ] + self.get_running_minions() + [
            'Unaccepted Keys:',
            'Rejected Keys:'
        ]
        self.assertEqual(data, expect)

    def test_list_json_out(self):
        '''
        test salt-key -L --json-out
        '''
        data = self.run_key('-L --json-out')
        if version.__version_info__ < (0, 10, 8):
            self.assertEqual(
                "WARNING: The option --json-out is deprecated. Please "
                "consider using '--out json' instead.",
                data[0]
            )

        data = self.run_key('-L --out json')

        expect = [
            '{',
            '    "minions_rejected": [], ',
            '    "minions_pre": [], ',
            '    "minions": ['] + ', \n'.join([
            '        "{0}"'.format(m) for m in self.get_running_minions()
            ]).split('\n') + [
            '    ]',
            '}',
        ]
        self.assertEqual(data, expect)

    def test_list_yaml_out(self):
        '''
        test salt-key -L --yaml-out
        '''
        data = self.run_key('-L --yaml-out')
        if version.__version_info__ < (0, 10, 8):
            self.assertEqual(
                "WARNING: The option --yaml-out is deprecated. Please "
                "consider using '--out yaml' instead.",
                data[0]
            )

        data = self.run_key('-L --out yaml')

        expect = ['minions:'] + [
            '- {0}'.format(m) for m in self.get_running_minions()] + [
            'minions_pre: []',
            'minions_rejected: []',
        ]
        self.assertEqual(data, expect)

    def test_list_raw_out(self):
        '''
        test salt-key -L --raw-out
        '''
        data = self.run_key('-L --raw-out')
        if version.__version_info__ < (0, 10, 8):
            self.assertEqual(
                "WARNING: The option --raw-out is deprecated. Please "
                "consider using '--out raw' instead.",
                data[0]
            )

        data = self.run_key('-L --out raw')

        running = self.get_running_minions()
        expect = [
            "{'minions_rejected': [], 'minions_pre': [], "
            "'minions': [" + ', '.join('{0!r}'.format(m) for m in running) +
            "]}"
        ]
        self.assertEqual(data, expect)

    def test_list_acc(self):
        '''
        test salt-key -l
        '''
        data = self.run_key('-l acc')
        self.assertEqual(
            data,
            ['Accepted Keys:'] + self.get_running_minions()
        )

    def test_list_un(self):
        '''
        test salt-key -l
        '''
        data = self.run_key('-l un')
        self.assertEqual(
            data,
            ['Unaccepted Keys:']
        )

    def test_keys_generation(self):
        tempdir = tempfile.mkdtemp()
        arg_str = '--gen-keys minibar --gen-keys-dir {0}'.format(tempdir)
        self.run_key(arg_str)
        try:
            for fname in ('minibar.pub', 'minibar.pem'):
                self.assertTrue(os.path.isfile(os.path.join(tempdir, fname)))
        finally:
            shutil.rmtree(tempdir)

    def test_keys_generation_no_configdir(self):
        tempdir = tempfile.mkdtemp()
        arg_str = '--gen-keys minibar --gen-keys-dir {0}'.format(tempdir)
        self.run_script('salt-key', arg_str)
        try:
            for fname in ('minibar.pub', 'minibar.pem'):
                self.assertTrue(os.path.isfile(os.path.join(tempdir, fname)))
        finally:
            shutil.rmtree(tempdir)

    def test_keys_generation_keysize_minmax(self):
        tempdir = tempfile.mkdtemp()
        arg_str = '--gen-keys minion --gen-keys-dir {0}'.format(tempdir)
        try:
            data, error = self.run_key(
                arg_str + ' --keysize=1024', catch_stderr=True
            )
            self.assertIn(
                'salt-key: error: The minimum value for keysize is 2048', error
            )

            data, error = self.run_key(
                arg_str + ' --keysize=32769', catch_stderr=True
            )
            self.assertIn(
                'salt-key: error: The maximum value for keysize is 32768',
                error
            )
        finally:
            shutil.rmtree(tempdir)


if __name__ == "__main__":
    loader = TestLoader()
    tests = loader.loadTestsFromTestCase(KeyTest)
    print('Setting up Salt daemons to execute tests')
    with TestDaemon():
        runner = TextTestRunner(verbosity=1).run(tests)
        sys.exit(runner.wasSuccessful())
