'''
Tests for the salt-run command
'''
# Import python libs
import sys

# Import Salt Modules
from saltunittest import TestLoader, TextTestRunner
import integration
from integration import TestDaemon


class ManageTest(integration.ShellCase):
    '''
    Test the manage runner
    '''
    def test_active(self):
        '''
        jobs.active
        '''
        ret = self.run_run_plus('jobs.active')

        if ret['fun']:
            # We have some running jobs, make sure we remove the remote
            # runtests job from the list
            for job_id, job_data in ret['fun'].copy().iteritems():
                if job_data['Function'] == 'runtests.run_tests':
                    ret['fun'].pop(job_id)

        self.assertEqual(ret['fun'], {})
        self.assertEqual(ret['out'], ['{}'])

    def test_lookup_jid(self):
        '''
        jobs.lookup_jid
        '''
        ret = self.run_run_plus('jobs.lookup_jid', '', '23974239742394')
        self.assertEqual(ret['fun'], {})
        self.assertEqual(ret['out'], [])

    def test_list_jobs(self):
        '''
        jobs.list_jobs
        '''
        ret = self.run_run_plus('jobs.list_jobs')
        self.assertIsInstance(ret['fun'], dict)

if __name__ == "__main__":
    loader = TestLoader()
    tests = loader.loadTestsFromTestCase(ManageTest)
    print('Setting up Salt daemons to execute tests')
    with TestDaemon():
        runner = TextTestRunner(verbosity=1).run(tests)
        sys.exit(runner.wasSuccessful())
