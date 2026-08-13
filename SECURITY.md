# Security policy

## Supported scope

The current repository is a paper-trading and replay harness. It contains no real venue credentials, wallet signer, withdrawal path, or live order endpoint.

## Secrets

Never commit `.env`, private keys, API secrets, seed phrases, exported browser sessions, or account identifiers. Test fixtures must use synthetic values only.

## Operational controls

- Keep the file kill switch enabled as an independent approval gate.
- Treat every order acknowledgement as non-terminal until a fill or rejection is recorded.
- A failed compensation leaves residual exposure and must halt new entries.
- Do not publish sensitive account details in issues or logs.

## Reporting

Report security defects privately to the repository owner with the affected commit and a minimal reproduction. Do not include real credentials.
