# Security policy

## Supported versions

FloppyCase is in **public beta**. Security fixes are applied on the latest
released version on the default branch.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Use GitHub's
[private vulnerability reporting](https://github.com/pblasone/floppycase/security/advisories/new)
for this repository instead. Include:

- a description of the issue and its impact
- steps to reproduce, or a proof of concept if you have one
- affected version / commit if known

You should receive an acknowledgement within a few days. Please give us a
reasonable window to investigate and ship a fix before any public disclosure.

If the private reporting form is unavailable, open a minimal public issue that
says only that you need to share a security report (no technical details), and
a maintainer will follow up privately.

## Scope notes

FloppyCase installs and launches third-party software (Amiberry, WHDLoad).
Vulnerabilities in those projects should be reported upstream to their
maintainers. Reports about FloppyCase itself should focus on our installer,
launcher, ROM handling, or desktop integration.
