# Security policy

## Supported version

Security fixes target the current `main` branch. The supported runtime is Windows with Python 3.11 or newer. Keep Windows, Python and Ollama updated independently.

## Report a vulnerability

Use the repository's [Security Advisories page](https://github.com/Lovekach/ai-news/security/advisories) and select **Report a vulnerability** to send a private report. Private vulnerability reporting is enabled for this repository.

Include the affected commit, component, expected behavior and a minimal reproduction using fabricated inputs. Do not submit live bot tokens, personal files, private news databases or channel archives. Do not post exploit details or credentials in a public issue. If a credential was exposed, its owner must revoke or rotate it; deleting a file does not undo exposure.

This is a maintained personal project without a guaranteed response time. Please allow time for investigation before public disclosure.

## Boundaries

The repository contains code and safe examples, not production settings or data. CI runs on hosted runners with read-only contents permissions and no production credentials. Source access and content permissions are the responsibility of each installation. URL guards are not a complete DNS/network sandbox; local Windows account compromise is outside DPAPI's protection.
