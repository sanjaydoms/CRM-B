import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  WASocket
} from 'baileys';
import pino from 'pino';
import qrcode from 'qrcode';
import path from 'path';
import fs from 'fs';
import { IncomingMessageService } from './services/incoming.service.js';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

interface SessionData {
  sock: WASocket | null;
  status: ConnectionStatus;
  isInitializing: boolean;
  qrCode: string | null;
}

const sessions = new Map<string, SessionData>();
const logger = pino({ level: 'silent' });

function getSessionData(sessionId: string): SessionData {
  if (!sessions.has(sessionId)) {
    sessions.set(sessionId, {
      sock: null,
      status: 'disconnected',
      isInitializing: false,
      qrCode: null
    });
  }
  return sessions.get(sessionId)!;
}

/**
 * Initializes a WhatsApp Baileys socket instance for a given session ID.
 * Keeps auth state files strictly isolated under auth_info/<sessionId>.
 */
export async function initWhatsApp(sessionId: string = 'default'): Promise<void> {
  const session = getSessionData(sessionId);
  if (session.isInitializing) return;
  session.isInitializing = true;

  try {
    session.status = 'connecting';
    const authFolder = sessionId === 'default'
      ? path.resolve(process.cwd(), 'auth_info')
      : path.resolve(process.cwd(), 'auth_info', sessionId);

    if (!fs.existsSync(authFolder)) {
      fs.mkdirSync(authFolder, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(authFolder);

    const sock = makeWASocket({
      auth: state,
      logger,
      printQRInTerminal: false,
      browser: ['Scaleezy CRM', 'Chrome', '1.0.0']
    });

    session.sock = sock;

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async (m) => {
      try {
        if (m.type === 'notify') {
          IncomingMessageService.handleIncomingMessages(m.messages, sessionId);
        }
      } catch (err) {
        console.error(`[whatsapp_service] [Session: ${sessionId}] Error handling messages.upsert event:`, err);
      }
    });

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        session.status = 'connecting';
        try {
          session.qrCode = await qrcode.toDataURL(qr);
          console.log(`[whatsapp_service] [Session: ${sessionId}] New QR code generated for dashboard display.`);
        } catch (err) {
          console.error(`[whatsapp_service] [Session: ${sessionId}] Error generating QR Data URL:`, err);
        }
      }

      if (connection === 'open') {
        session.status = 'connected';
        session.isInitializing = false;
        session.qrCode = null;
        console.log(`[whatsapp_service] [Session: ${sessionId}] Connection established and OPEN!`);
      } else if (connection === 'close') {
        session.status = 'disconnected';
        session.isInitializing = false;
        session.qrCode = null;
        session.sock = null;

        const statusCode = (lastDisconnect?.error as any)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut && statusCode !== 401 && statusCode !== 403;

        console.log(
          `[whatsapp_service] [Session: ${sessionId}] Connection closed (status code: ${statusCode || 'unknown'}). Reconnecting: ${shouldReconnect}`
        );

        if (!shouldReconnect) {
          console.log(`[whatsapp_service] [Session: ${sessionId}] Session logged out or auth invalid. Cleaning auth folder.`);
          try {
            if (fs.existsSync(authFolder)) {
              fs.rmSync(authFolder, { recursive: true, force: true });
            }
          } catch (e) {
            console.error(`[whatsapp_service] Failed to remove auth folder:`, e);
          }
        }

        if (shouldReconnect) {
          setTimeout(() => {
            initWhatsApp(sessionId);
          }, 3000);
        }
      } else if (connection === 'connecting') {
        session.status = 'connecting';
      }
    });
  } catch (err) {
    session.status = 'disconnected';
    session.isInitializing = false;
    session.qrCode = null;
    session.sock = null;
    console.error(`[whatsapp_service] [Session: ${sessionId}] Failed to initialize socket:`, err);
  }
}

export async function resetWhatsApp(sessionId: string = 'default', forceClean: boolean = true): Promise<void> {
  const session = getSessionData(sessionId);
  try {
    if (session.sock) {
      try {
        session.sock.end(undefined);
      } catch (e) {}
    }
  } catch (e) {}

  session.sock = null;
  session.status = 'disconnected';
  session.isInitializing = false;
  session.qrCode = null;

  if (forceClean) {
    const authFolder = sessionId === 'default'
      ? path.resolve(process.cwd(), 'auth_info')
      : path.resolve(process.cwd(), 'auth_info', sessionId);
    if (fs.existsSync(authFolder)) {
      try {
        fs.rmSync(authFolder, { recursive: true, force: true });
        console.log(`[whatsapp_service] [Session: ${sessionId}] Force cleaned auth folder: ${authFolder}`);
      } catch (e) {
        console.error(`[whatsapp_service] Failed to force clean auth folder:`, e);
      }
    }
  }

  await initWhatsApp(sessionId);
}

export function getWhatsAppStatus(sessionId: string = 'default'): { status: ConnectionStatus; connected: boolean; sessionId: string; qrCode: string | null } {
  const session = getSessionData(sessionId);
  if (session.status === 'disconnected' && !session.isInitializing && !session.sock) {
    initWhatsApp(sessionId).catch((err) => {
      console.error(`[whatsapp_service] Failed to auto-init session '${sessionId}':`, err);
    });
  }
  return {
    sessionId,
    status: session.status,
    connected: session.status === 'connected',
    qrCode: session.qrCode
  };
}

export function getSocket(sessionId: string = 'default'): WASocket | null {
  const session = getSessionData(sessionId);
  return session.sock;
}

/**
 * Gracefully closes all active Baileys WhatsApp sessions during service shutdown.
 */
export async function closeAllWhatsAppSessions(): Promise<void> {
  console.log('[whatsapp_service] Closing active WhatsApp Baileys socket connections...');
  for (const [sessionId, session] of sessions.entries()) {
    try {
      if (session.sock) {
        session.sock.end(undefined);
        session.status = 'disconnected';
        console.log(`[whatsapp_service] [Session: ${sessionId}] Socket closed gracefully.`);
      }
    } catch (err: any) {
      console.warn(`[whatsapp_service] Error closing socket for session ${sessionId}:`, err?.message || err);
    }
  }
}
