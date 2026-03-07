import fs from "node:fs/promises";
import path from "node:path";
import http from "node:http";
import { URL } from "node:url";
import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import pino from "pino";
import QRCode from "qrcode-terminal";

const host = process.env.BROODMIND_WHATSAPP_BRIDGE_HOST || "127.0.0.1";
const port = Number(process.env.BROODMIND_WHATSAPP_BRIDGE_PORT || "8765");
const authDir = process.env.BROODMIND_WHATSAPP_AUTH_DIR || path.resolve("auth");
const callbackUrl = (process.env.BROODMIND_WHATSAPP_CALLBACK_URL || "").trim();
const callbackToken = (process.env.BROODMIND_WHATSAPP_CALLBACK_TOKEN || "").trim();

let sock = null;
let latestQr = "";
let latestQrTerminal = "";
let connected = false;
let linked = false;
let selfId = "";
let reconnectTimer = null;

async function ensureAuthDir() {
  await fs.mkdir(authDir, { recursive: true });
}

function renderQrTerminal(qr) {
  return new Promise((resolve) => {
    QRCode.generate(qr, { small: true }, (output) => resolve(output || ""));
  });
}

function normalizeDirectJid(raw) {
  if (!raw) return "";
  if (raw.includes("@g.us") || raw.includes("@broadcast") || raw === "status@broadcast") {
    return "";
  }
  if (raw.includes("@")) {
    return raw;
  }
  const digits = String(raw).replace(/\D+/g, "");
  return digits ? `${digits}@s.whatsapp.net` : raw;
}

function senderFromJid(jid) {
  const digits = String(jid || "").split("@", 1)[0].replace(/\D+/g, "");
  return digits ? `+${digits}` : "";
}

async function postInbound(payload) {
  if (!callbackUrl) return;
  try {
    const headers = { "content-type": "application/json" };
    if (callbackToken) {
      headers["x-broodmind-whatsapp-token"] = callbackToken;
    }
    await fetch(callbackUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error("failed to forward inbound whatsapp payload", error);
  }
}

function extractText(message) {
  if (!message) return "";
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    ""
  );
}

async function bootstrapSocket() {
  await ensureAuthDir();
  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const { version } = await fetchLatestBaileysVersion();
  sock = makeWASocket({
    auth: state,
    version,
    printQRInTerminal: false,
    logger: pino({ level: "silent" }),
    browser: ["BroodMind", "Chrome", "1.0"],
    markOnlineOnConnect: false,
    syncFullHistory: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    if (update.qr) {
      latestQr = update.qr;
      latestQrTerminal = await renderQrTerminal(update.qr);
    }
    if (update.connection === "open") {
      connected = true;
      linked = true;
      latestQr = "";
      latestQrTerminal = "";
      selfId = sock.user?.id || "";
      console.log("whatsapp bridge connected", selfId);
    }
    if (update.connection === "close") {
      connected = false;
      const reason = update.lastDisconnect?.error?.output?.statusCode;
      if (reason === DisconnectReason.loggedOut) {
        linked = false;
        selfId = "";
        latestQr = "";
        latestQrTerminal = "";
        return;
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      reconnectTimer = setTimeout(() => {
        bootstrapSocket().catch((error) => console.error("failed to reconnect whatsapp socket", error));
      }, 2000);
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const item of messages || []) {
      if (!item?.message || item?.key?.fromMe) continue;
      const remoteJid = item?.key?.remoteJid || "";
      if (remoteJid.includes("@g.us") || remoteJid.includes("@broadcast") || remoteJid === "status@broadcast") {
        continue;
      }
      const sender = senderFromJid(remoteJid);
      const text = extractText(item.message).trim();
      if (!sender || !text) continue;
      await postInbound({
        sender,
        text,
        messageId: item?.key?.id || "",
      });
    }
  });
}

async function clearAuth() {
  await fs.rm(authDir, { recursive: true, force: true });
  await ensureAuthDir();
}

async function jsonResponse(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

async function readJson(req) {
  let body = "";
  for await (const chunk of req) {
    body += chunk;
  }
  if (!body) return {};
  return JSON.parse(body);
}

await bootstrapSocket();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${host}:${port}`);
  if (req.method === "GET" && url.pathname === "/health") {
    return await jsonResponse(res, 200, { ok: true, connected, linked });
  }
  if (req.method === "GET" && url.pathname === "/status") {
    return await jsonResponse(res, 200, {
      connected,
      linked,
      self: selfId,
      authDir,
    });
  }
  if (req.method === "GET" && url.pathname === "/qr") {
    return await jsonResponse(res, 200, { qr: latestQr, connected, linked });
  }
  if (req.method === "GET" && url.pathname === "/qr-terminal") {
    return await jsonResponse(res, 200, {
      qr: latestQr,
      terminal: latestQrTerminal,
      connected,
      linked,
    });
  }
  if (req.method === "POST" && url.pathname === "/send") {
    const payload = await readJson(req);
    const to = normalizeDirectJid(payload.to || "");
    const text = String(payload.text || "").trim();
    if (!sock || !to || !text) {
      return await jsonResponse(res, 400, { ok: false, error: "missing_to_or_text" });
    }
    await sock.sendMessage(to, { text });
    return await jsonResponse(res, 200, { ok: true, to, length: text.length });
  }
  if (req.method === "POST" && url.pathname === "/logout") {
    try {
      if (sock) {
        try {
          await sock.logout();
        } catch {
          // fall through to local auth cleanup
        }
      }
      await clearAuth();
      connected = false;
      linked = false;
      selfId = "";
      latestQr = "";
      latestQrTerminal = "";
      await bootstrapSocket();
      return await jsonResponse(res, 200, { ok: true });
    } catch (error) {
      return await jsonResponse(res, 500, { ok: false, error: String(error) });
    }
  }
  return await jsonResponse(res, 404, { ok: false, error: "not_found" });
});

server.listen(port, host, () => {
  console.log(`whatsapp bridge listening on http://${host}:${port}`);
});
