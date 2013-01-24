# -*- coding: utf-8 -*-
'''
    tests.integration.states.pkg
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    :codeauthor: :email:`Pedro Algarvio (pedro@algarvio.me)`
    :copyright: © 2013 by the SaltStack Team, see AUTHORS for more details.
    :license: Apache 2.0, see LICENSE for more details.
'''

# Import python linbs
import os

# Import salt libs
import integration
from saltunittest import skipIf


class PkgStateTest(integration.ModuleCase, integration.SaltReturnAssertsMixIn):

    @skipIf(os.geteuid() is not 0, 'you must be root to run this test')
    def test_issue_3420_pkg_installed_and_cmdmod_is_windows(self):
        template_lines = [
            'testcase-packages:',
            '  pkg.latest:',
            '    - pkgs:',
            '      - screen'
        ]
        template = '\n'.join(template_lines)
        try:
            ret = self.run_function('state.template_str', [template])
            self.assertSaltFalseReturn(ret)
        except AssertionError:
            raise
