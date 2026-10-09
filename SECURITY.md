# Security

The scripts read local design and fabrication files and write reports / images; they make no network requests.
`gerber_check.py` evaluates aperture-macro arithmetic from Gerber files with a whitelist of digits and operators only.
`placement_from_easyeda.js` runs inside EasyEDA Pro and only reads the open board.

Report a vulnerability through GitHub's private vulnerability reporting on this repository (Security tab), not in a
public issue.
