screen:
  pkg:
    - installed

screen-startup-message:
  # Disable the startup message
  cmd.run:
    - name: sudo sed -i 's/^#startup_message off/startup_message off/g' /etc/screenrc
    - unless: grep '^startup_message off' /etc/screenrc
    - require:
      - pkg: screen

screen-auto-detach:
  # Auto detach screens when closing ssh connection
  cmd.run:
    - name: sudo sed -i 's/^#autodetach off/autodetach on/g' /etc/screenrc
    - unless: grep '^autodetach on' /etc/screenrc
    - require:
      - pkg: screen

screen-termcapinfo:
  # add lines to xterm's scrollback buffer
  cmd.run:
    - name: sudo sed -i 's/^#termcapinfo xterm|xterms|xs|rxvt ti@:te@/termcapinfo xterm|xterms|xs|rxvt ti@:te@/g' /etc/screenrc
    - unless: grep '^termcapinfo xterm|xterms|xs|rxvt ti@:te@' /etc/screenrc
    - require:
      - pkg: screen