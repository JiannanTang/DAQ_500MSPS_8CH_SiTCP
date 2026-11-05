DAQ_500MSPS_8CH_SiTCP
=====================

Run:
  DAQ_500MSPS_8CH_SiTCP.exe

The default device address is 192.168.10.16.
RBCP uses UDP port 4660 by default.
The TCP acquisition port is editable in the real-time acquisition page and
defaults to 24.
Use the language selector in the title bar to switch between Chinese and
English without restarting the application.

Editable configuration:
  config\registers.toml

Raw capture files are written to:
  captures\

If Windows Firewall asks for network access, allow private-network access.
This package is a one-directory build: keep DAQ_500MSPS_8CH_SiTCP.exe, _internal, config,
and captures together. Do not move the exe out of this directory.

