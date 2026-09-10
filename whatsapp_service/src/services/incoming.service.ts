import { DjangoService } from './django.service.js';

export interface MediaInfo {
  mediaType: 'image' | 'document' | 'audio' | 'video';
  mimeType: string;
  filename?: string;
  caption?: string;
  fileSize?: number;
}

export interface NormalizedMessage {
  sessionId: string;
  messageId: string;
  phone: string;
  jid: string;
  text: string;
  timestamp: number;
  type: 'text' | 'media' | 'unknown';
  media?: MediaInfo;
  direction: 'incoming' | 'outgoing';
  isFromMe: boolean;
}

// Deduplication Cache (LRU / TTL)
const processedMessageIds = new Map<string, number>();
const MAX_DEDUPE_CACHE_SIZE = 2000;
const DEDUPE_TTL_MS = 10 * 60 * 1000; // 10 minutes

function isDuplicateMessage(messageId: string): boolean {
  if (!messageId) return false;
  const now = Date.now();

  // Prune expired entries if cache reaches maximum limit
  if (processedMessageIds.size > MAX_DEDUPE_CACHE_SIZE) {
    for (const [id, time] of processedMessageIds.entries()) {
      if (now - time > DEDUPE_TTL_MS) {
        processedMessageIds.delete(id);
      }
    }
  }

  if (processedMessageIds.has(messageId)) {
    return true;
  }

  processedMessageIds.set(messageId, now);
  return false;
}

export class IncomingMessageService {
  /**
   * Normalizes a raw Baileys WAMessage object into a safe, clean internal structure.
   */
  public static processRawMessage(msg: any, sessionId: string = 'default'): NormalizedMessage | null {
    try {
      if (!msg || !msg.key || !msg.message) return null;

      // Ignore protocol messages, reactions, or system stubs
      if (
        msg.message.protocolMessage ||
        msg.message.senderKeyDistributionMessage ||
        msg.message.reactionMessage
      ) {
        return null;
      }

      const isFromMe = Boolean(msg.key.fromMe);
      const jid = msg.key.remoteJid || '';

      // Ignore status/broadcast updates or group chats
      if (!jid || jid.endsWith('@status.whatsapp.net') || jid.endsWith('@g.us')) {
        return null;
      }

      const messageId = msg.key.id || '';
      const rawPhone = jid.split('@')[0] || '';
      const phone = rawPhone.replace(/\D/g, '');

      // Extract message text content safely
      let text = '';
      if (msg.message.conversation) {
        text = msg.message.conversation;
      } else if (msg.message.extendedTextMessage?.text) {
        text = msg.message.extendedTextMessage.text;
      } else if (msg.message.imageMessage?.caption) {
        text = msg.message.imageMessage.caption;
      } else if (msg.message.videoMessage?.caption) {
        text = msg.message.videoMessage.caption;
      } else if (msg.message.documentMessage?.caption) {
        text = msg.message.documentMessage.caption;
      }

      // Extract media information if present
      let type: 'text' | 'media' | 'unknown' = 'unknown';
      let media: MediaInfo | undefined;

      if (msg.message.conversation || msg.message.extendedTextMessage) {
        type = 'text';
      } else if (msg.message.imageMessage) {
        type = 'media';
        const mNode = msg.message.imageMessage;
        media = {
          mediaType: 'image',
          mimeType: mNode.mimetype || 'image/jpeg',
          caption: mNode.caption || undefined,
          fileSize: typeof mNode.fileLength === 'number' ? mNode.fileLength : Number(mNode.fileLength?.low || 0)
        };
      } else if (msg.message.documentMessage) {
        type = 'media';
        const mNode = msg.message.documentMessage;
        media = {
          mediaType: 'document',
          mimeType: mNode.mimetype || 'application/pdf',
          filename: mNode.fileName || mNode.title || undefined,
          caption: mNode.caption || undefined,
          fileSize: typeof mNode.fileLength === 'number' ? mNode.fileLength : Number(mNode.fileLength?.low || 0)
        };
      } else if (msg.message.audioMessage) {
        type = 'media';
        const mNode = msg.message.audioMessage;
        media = {
          mediaType: 'audio',
          mimeType: mNode.mimetype || 'audio/ogg',
          fileSize: typeof mNode.fileLength === 'number' ? mNode.fileLength : Number(mNode.fileLength?.low || 0)
        };
      } else if (msg.message.videoMessage) {
        type = 'media';
        const mNode = msg.message.videoMessage;
        media = {
          mediaType: 'video',
          mimeType: mNode.mimetype || 'video/mp4',
          caption: mNode.caption || undefined,
          fileSize: typeof mNode.fileLength === 'number' ? mNode.fileLength : Number(mNode.fileLength?.low || 0)
        };
      }

      // Safe timestamp conversion (handling protobuf Long or number)
      let timestamp: number;
      if (typeof msg.messageTimestamp === 'number') {
        timestamp = msg.messageTimestamp;
      } else if (msg.messageTimestamp?.low) {
        timestamp = msg.messageTimestamp.low;
      } else if (typeof msg.messageTimestamp === 'string') {
        timestamp = parseInt(msg.messageTimestamp, 10);
      } else {
        timestamp = Math.floor(Date.now() / 1000);
      }

      const direction: 'incoming' | 'outgoing' = isFromMe ? 'outgoing' : 'incoming';

      return {
        sessionId,
        messageId,
        phone,
        jid,
        text,
        timestamp,
        type,
        ...(media ? { media } : {}),
        direction,
        isFromMe
      };
    } catch (err) {
      console.error('[whatsapp_service] Error processing raw message:', err);
      return null;
    }
  }

  /**
   * Processes a list of raw incoming/upserted WAMessages from Baileys for a given session.
   */
  public static handleIncomingMessages(messages: any[], sessionId: string = 'default'): void {
    if (!Array.isArray(messages)) return;

    for (const rawMsg of messages) {
      const messageId = rawMsg?.key?.id;

      // Skip duplicate message processing
      if (messageId && isDuplicateMessage(messageId)) {
        console.log(`[whatsapp_service] [Session: ${sessionId}] Skipping duplicate messageId: ${messageId}`);
        continue;
      }

      const normalized = IncomingMessageService.processRawMessage(rawMsg, sessionId);
      if (!normalized) continue;

      // Safe logging for development without printing auth or sensitive keys
      console.log(`[whatsapp_service] [Session: ${sessionId}] Processed Message Event:`);
      console.log(JSON.stringify(normalized, null, 2));

      // Notify Django backend via webhook for customer incoming messages
      if (normalized.direction === 'incoming') {
        DjangoService.sendIncomingWebhook(normalized).catch((err) => {
          console.error('[whatsapp_service] Async error sending webhook to Django:', err);
        });
      }
    }
  }
}
