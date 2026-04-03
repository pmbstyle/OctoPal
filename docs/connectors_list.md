# Supported Connectors

This document lists the connectors that are currently supported in Octopal.

## Google

Current supported services:
- Gmail
- Calendar
- Drive

What it can do today:
- list recent emails
- search emails with Gmail query syntax
- read a message by ID
- read a thread by ID
- count unread emails
- inspect labels
- inspect the connected mailbox profile
- list calendars
- list events
- search events
- read an event by ID
- create an event
- update an event
- delete an event
- run free/busy lookup for one or more calendars
- list recent Drive files
- search Drive files
- inspect Drive file metadata
- list files inside Drive folders
- create Drive folders
- download Drive file contents
- export Google Docs-native files
- upload new files to Drive
- update existing Drive files
- move Drive files to trash
- move files between Drive and workspace
- upload a workspace file and return its Drive link
- read and write text files without manual base64 handling

What it does not do yet:
- send email
- archive or delete email
- mark messages read or unread
- move messages between labels/folders
- download attachment contents
- attendee response management

Setup guide:
- [google_connector_setup.md](google_connector_setup.md)

CLI flow:
1. Run `octopal configure`
2. Enable any needed Google services such as `Gmail`, `Calendar`, and/or `Drive`
3. Run `octopal connector auth google`
4. Run `octopal connector status`
5. Restart Octopal if needed
