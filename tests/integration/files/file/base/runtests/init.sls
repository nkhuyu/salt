runtests-pkg-deps:
  pkg.installed:
    - names:
      - {{ pillar['pkg']['git'] }}
      - {{ pillar['pkg']['supervisor'] }}
      - {{ pillar['pkg']['python-mock'] }}
      - {{ pillar['pkg']['python-virtualenv'] }}
{% if grains['os'] not in ('Arch',) %}
      - {{ pillar['pkg']['python-dev'] }}
{% endif %}


/tmp/ve:
  virtualenv.manage:
    - runas: vagrant
    - distribute: True
    - no_site_packages: False
    #- system_site_packages: True
    - mirrors: http://testpypi.python.org/pypi
    - require:
      - pkg: {{ pillar['pkg']['python-virtualenv'] }}

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
      - pkg: {{ pillar['pkg']['supervisor'] }}
      - pkg: {{ pillar['pkg']['python-mock'] }}

#/home/vagrant/.bashrc:
#  file.append:
#    - text: export PATH=/tmp/ve/bin:$PATH
#    - require:
#      - virtualenv: /tmp/ve

coverage:
  pip.installed:
    - name: coverage
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - pkg: {{ pillar['pkg']['git'] }}
      - pkg: {{ pillar['pkg']['python-dev'] }}
      - virtualenv: /tmp/ve

{% if (grains['pythonversion'][0]|int, grains['pythonversion'][1]|int) < (2, 7) %}
unittest2:
  pip.installed:
    - name: unittest2
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

