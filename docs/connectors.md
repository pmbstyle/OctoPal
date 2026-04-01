# Connectors

Connectors are the integration layer between Octopal and external services.

They let a user explicitly choose which third-party services Octopal may use,
authorize those services through CLI flows, and then expose only the supported
capabilities to Octo and workers.

## How connectors work

The current connector pipeline is CLI-first:

1. Run `octopal configure`
2. Open the `Connectors` section
3. Enable a connector and choose its supported services
4. Save the config
5. Run the connector auth command shown by the CLI
6. Restart Octopal if needed

After that, Octopal checks connector readiness during startup and only starts
the connector-backed MCP servers that are actually authorized and supported.

## Current model

- Connector enablement is controlled in `octopal configure`
- Authentication is handled through CLI commands, not through chat
- Octo and workers can inspect connector availability, but they cannot grant
  themselves new access
- The current Google flow uses user-provided OAuth credentials for self-hosted
  setups

## Supported connectors

See [connectors_list.md](connectors_list.md) for
the current list of supported connectors and setup links.
