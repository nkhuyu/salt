{% if salt['runtests.saltsource_on_shared_folders']()==False %}
clean-previous:
  cmd.run:
    - name: rm -rf /salt


create-salt-dir:
  file.directory:
    - name: /salt
    - makedirs: True
    - user: vagrant
    - group: vagrant
    - require:
      - cmd: clean-previous



clean-previous-temp-source:
  cmd.run:
    - name: rm -rf /tmp/salt-source


create-temp-source-dir:
  file.directory:
    - name: /tmp/salt-source
    - makedirs: True
    - user: vagrant
    - group: vagrant
    - require:
      - cmd: clean-previous-temp-source


download-saltsource:
  file.managed:
    - name: /tmp/saltsource.tar.bz2
    - source: salt://saltsource.tar.bz2
    - replace: True
    - require:
      - cmd: clean-previous
      - cmd: clean-previous-temp-source


decompress-saltsource:
  cmd.run:
    - cwd: /tmp/salt-source
    - name: tar jxvf /tmp/saltsource.tar.bz2
    - runas: vagrant
    - require:
      - file: download-saltsource
      - file: create-temp-source-dir


move-saltsource:
  cmd.run:
    - cwd: /tmp
    - name: mv /tmp/salt-source/salt-*/ /salt/source
    - require:
      - file: create-salt-dir
      - cmd: decompress-saltsource

{% endif %}
