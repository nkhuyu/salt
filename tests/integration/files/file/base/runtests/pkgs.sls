runtests-pkg-deps:
  pkg.installed:
    - names:
      - {{ pillar['pkg']['git'] }}
      - {{ pillar['pkg']['supervisor'] }}
      - {{ pillar['pkg']['python-mock'] }}
      - {{ pillar['pkg']['python-virtualenv'] }}
      - {{ pillar['pkg']['rabbitmq-server'] }}
{% if grains['os'] not in ('Arch',) %}
      - {{ pillar['pkg']['python-dev'] }}
{% endif %}
