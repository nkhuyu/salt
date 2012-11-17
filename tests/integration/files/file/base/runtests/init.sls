/tmp/ve:
  virtualenv.manage:
    - runas: vagrant
    - distribute: True
    - no_site_packages: False
    {% if salt['runtests.virtualenv_has_system_site_packages']()==True -%}
    - system_site_packages: True
    {%- endif %}
    - mirrors: http://testpypi.python.org/pypi


ve-saltdevel-install:
  cmd.run:
    - cwd: /salt/source/
    - env: USE_SETUPTOOLS=1
    - mirrors: http://testpypi.python.org/pypi
    - name: sudo USE_SETUPTOOLS=1 /tmp/ve/bin/python setup.py develop
    - runas: vagrant
    - unless: test -d /tmp/ve/bin
    - require:
      - virtualenv: /tmp/ve


coverage:
  pip.installed:
    - name: coverage
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - virtualenv: /tmp/ve


{% if salt['runtests.unittest2_required']() %}
# Because we're on python 2.6
unittest2:
  pip.installed:
    - name: unittest2
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - virtualenv: /tmp/ve
{% endif %}


{% if salt['runtests.ordereddict_required']() %}
# Because we're on python 2.6
OrderedDict:
  pip.installed:
    - name: ordereddict
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - virtualenv: /tmp/ve
{% endif %}


unittest-xml-reporting:
  pip.installed:
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - virtualenv: /tmp/ve

