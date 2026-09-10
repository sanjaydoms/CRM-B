import { getSocket, getWhatsAppStatus } from '../whatsapp.js';
import { formatToWhatsAppJid } from '../utils/phone.js';

export interface SendMessagePayload {
  sessionId?: string;
  phone: string;
  message: string;
}

export interface SendMessageResult {
  success: boolean;
  message: string;
  data?: any;
  error?: string;
  statusCode?: number;
}

export class MessageService {
  public static async sendMessage(payload: SendMessagePayload): Promise<SendMessageResult> {
    const { sessionId = 'default', phone, message } = payload;

    // 1. Validate phone parameter
    if (!phone || typeof phone !== 'string' || !phone.trim()) {
      return {
        success: false,
        message: 'Phone number is required and must be a non-empty string',
        statusCode: 400
      };
    }

    // 2. Validate message parameter
    if (!message || typeof message !== 'string' || !message.trim()) {
      return {
        success: false,
        message: 'Message content is required and cannot be empty',
        statusCode: 400
      };
    }

    // 3. Normalize WhatsApp JID
    const jid = formatToWhatsAppJid(phone);
    if (!jid) {
      return {
        success: false,
        message: 'Invalid phone number format. Could not normalize WhatsApp JID.',
        statusCode: 400
      };
    }

    // 4. Verify WhatsApp connection availability for the target session
    const statusInfo = getWhatsAppStatus(sessionId);
    const socket = getSocket(sessionId);

    if (!statusInfo.connected || !socket) {
      return {
        success: false,
        message: `WhatsApp client for session '${sessionId}' is not connected (current status: ${statusInfo.status})`,
        statusCode: 503
      };
    }

    // 5. Send text message through Baileys
    try {
      const sentMsg = await socket.sendMessage(jid, { text: message.trim() });
      return {
        success: true,
        message: 'WhatsApp message sent successfully',
        data: {
          messageId: sentMsg?.key?.id,
          timestamp: sentMsg?.messageTimestamp
        },
        statusCode: 200
      };
    } catch (err: any) {
      console.error('[whatsapp_service] Error sending message via Baileys:', err?.message || err);
      return {
        success: false,
        message: 'Failed to send WhatsApp message',
        error: err?.message || 'Internal Baileys error',
        statusCode: 500
      };
    }
  }
}
