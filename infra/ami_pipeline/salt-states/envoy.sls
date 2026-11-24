# SaltStack state to provision and harden Sovereign Envoy edge node

envoy_user:
  user.present:
    - name: envoy
    - system: True
    - shell: /usr/sbin/nologin

envoy_directories:
  file.directory:
    - names:
      - /etc/envoy
      - /var/log/envoy
    - user: envoy
    - group: envoy
    - mode: 755

apply_sysctl_tuning:
  file.managed:
    - name: /etc/sysctl.d/99-envoy-edge.conf
    - source: salt://sysctl.conf
    - mode: 644
  cmd.run:
    - name: sysctl --system
    - onchanges:
      - file: apply_sysctl_tuning

install_systemd_service:
  file.managed:
    - name: /etc/systemd/system/envoy.service
    - source: salt://systemd.service
    - mode: 644
  cmd.run:
    - name: systemctl daemon-reload
    - onchanges:
      - file: install_systemd_service

enable_envoy_service:
  service.running:
    - name: envoy
    - enable: True
    - watch:
      - file: install_systemd_service
