# Supported Connectors

This document lists the connectors that are currently supported in Octopal.

## Google

Current supported service:
- Gmail

What it can do today:
- list recent emails
- search emails with Gmail query syntax
- read a message by ID
- read a thread by ID
- count unread emails
- inspect labels
- inspect the connected mailbox profile

What it does not do yet:
- send email
- archive or delete email
- mark messages read or unread
- move messages between labels/folders
- download attachment contents

Setup guide:
- [google_gmail_connector_setup.md](google_gmail_connector_setup.md)

CLI flow:
1. Run `octopal configure`
2. Enable `Google -> Gmail`
3. Run `octopal connector auth google`
4. Run `octopal connector status`
5. Restart Octopal if needed
