# Google Gmail Connector Setup

This guide explains how a self-hosted Octopal user can create the Google OAuth
credentials needed for the Gmail connector.

For a higher-level overview of connectors, see
[connectors.md](connectors.md).

For the current list of supported connectors, see
[connectors_list.md](connectors_list.md).

## What you need

For the current Gmail connector flow, each user should bring their own Google
OAuth credentials.

You need:
- A Google account
- A Google Cloud project you control
- An OAuth client of type `Desktop app`
- The `client_id` and `client_secret` from that OAuth client

## Step 1: Open Google Cloud Console

Open:

`https://console.cloud.google.com/apis/credentials`

If needed, create a new project first.

## Step 2: Enable the Gmail API

In your project:
- Open `APIs & Services`
- Open `Library`
- Search for `Gmail API`
- Click `Enable`

Direct link:

`https://console.cloud.google.com/apis/api/gmail.googleapis.com`

Wait a minute or two after enabling the API before retrying auth or Gmail tool
calls.

## Step 3: Configure the OAuth consent screen

Google may ask you to configure the OAuth consent screen before you can create
 credentials.

Typical fields:
- App name: `Octopal`
- User support email: your email
- Audience: usually `External`
- Developer contact email: your email

For a personal self-hosted setup, `Testing` mode is usually fine.

If Google blocks sign-in with `access_denied`, make sure the Google account you
are using is listed in `Test users`.

## Step 4: Create OAuth credentials

In `APIs & Services -> Credentials`:
- Click `Create credentials`
- Choose `OAuth client ID`
- Application type: `Desktop app`
- Give it a name like `Octopal Gmail`

Then copy:
- `Client ID`
- `Client secret`

Do not use:
- Service accounts
- Web application credentials

The current Octopal CLI flow expects a `Desktop app` OAuth client.

## Step 5: Run Octopal auth

Use:

```bash
uv run octopal connector auth google
```

When prompted, paste:
- your Google OAuth Desktop App `client_id`
- your Google OAuth Desktop App `client_secret`

## Step 6: Complete browser authorization

If you are on a local machine, Octopal will try to open a browser.

If you are on a VPS or another headless machine:
- Octopal will print an authorization URL
- Open that URL on your own computer
- Sign in and approve access
- Copy the full localhost redirect URL from your browser address bar
- Paste that URL back into the terminal

## After auth

Check status:

```bash
uv run octopal connector status
```

If needed, restart Octopal:

```bash
uv run octopal restart
```

## Notes

- Current scope: Gmail only
- Current model: user-provided OAuth credentials
- A shared verified Octopal Google app is not required for this self-hosted flow
- Current Gmail connector is read-focused: search, list, and read mailbox data
