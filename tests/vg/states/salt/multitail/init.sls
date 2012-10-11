
multitail:
  pkg:
    - installed
  cmd.run:
    - name: sudo sed -i 's/^check_mail:\([0-9]*\)/#check_mail:\1/g' /etc/multitail.conf
    - unless: grep '^#check_mail:' /etc/multitail.conf
    - require:
      - pkg: multitail