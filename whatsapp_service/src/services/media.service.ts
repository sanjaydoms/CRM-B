import fs from 'fs';
import path from 'path';
import os from 'os';
import { pipeline } from 'stream/promises';
import { downloadContentFromMessage, WASocket } from 'baileys';
import { getSocket, getWhatsAppStatus } from '../whatsapp.js';
import { formatToWhatsAppJid } from '../utils/phone.js';

export type SupportedMediaType = 'image' | 'document' | 'audio' | 'video';

export interface SendMediaPayload {
  sessionId?: string;
  phone: string;
  mediaType: SupportedMediaType;
  mediaUrl?: string;
  mediaBase64?: string;
  caption?: string;
  filename?: string;
  mimeType?: string;
}

export interface SendMediaResult {
  success: boolean;
  message: string;
  data?: any;
  error?: string;
  statusCode?: number;
}

// Strict allowed MIME types mapping per media type
const ALLOWED_MIME_TYPES: Record<SupportedMediaType, string[]> = {
  image: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
  document: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/csv',
    'application/zip',
    'application/x-zip-compressed'
  ],
  audio: ['audio/ogg', 'audio/mp3', 'audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/wav', 'audio/m4a'],
  video: ['video/mp4', 'video/3gpp', 'video/quicktime', 'video/webm']
};

const MAX_FILE_SIZE_BYTES = 64 * 1024 * 1024; // 64MB hard limit

export class MediaService {
  /**
   * Sanitizes filename to prevent directory/path traversal vulnerabilities.
   */
  public static sanitizeFilename(inputName?: string, defaultExt: string = 'bin'): string {
    if (!inputName || typeof inputName !== 'string') {
      return `file_${Date.now()}.${defaultExt}`;
    }
    const safeBase = path.basename(inputName).replace(/[^a-zA-Z0-9._-]/g, '_');
    return safeBase || `file_${Date.now()}.${defaultExt}`;
  }

  /**
   * Validates MIME type against allowed list for media type.
   */
  public static isValidMimeType(mediaType: SupportedMediaType, mimeType?: string): boolean {
    if (!mimeType) return true; // Allow fallback if undetectable
    const cleanMime = mimeType.split(';')[0].trim().toLowerCase();
    const allowed = ALLOWED_MIME_TYPES[mediaType] || [];
    return allowed.some((valid) => cleanMime.startsWith(valid));
  }

  /**
   * Downloads incoming WhatsApp media message into a temporary file.
   * Streaming pipeline is used to prevent loading full file into RAM.
   */
  public static async downloadIncomingMediaToTemp(
    msg: any,
    mediaType: SupportedMediaType
  ): Promise<{ tempFilePath: string; mimeType: string; filename: string } | null> {
    try {
      const messageNode =
        msg.message?.imageMessage ||
        msg.message?.documentMessage ||
        msg.message?.audioMessage ||
        msg.message?.videoMessage;

      if (!messageNode) return null;

      const stream = await downloadContentFromMessage(messageNode, mediaType as any);
      const ext = mediaType === 'image' ? 'jpg' : mediaType === 'video' ? 'mp4' : mediaType === 'audio' ? 'ogg' : 'pdf';
      const safeName = MediaService.sanitizeFilename(messageNode.fileName || messageNode.title, ext);
      const tempPath = path.join(os.tmpdir(), `scaleezy_in_${Date.now()}_${safeName}`);

      const writeStream = fs.createWriteStream(tempPath);
      for await (const chunk of stream) {
        writeStream.write(chunk);
      }
      writeStream.end();

      const mimeType = messageNode.mimetype || 'application/octet-stream';
      return {
        tempFilePath: tempPath,
        mimeType,
        filename: safeName
      };
    } catch (err: any) {
      console.error('[whatsapp_service] Error downloading incoming media:', err?.message || err);
      return null;
    }
  }

  /**
   * Sends an outgoing media message (image, document, audio, video) via Baileys socket.
   */
  public static async sendMedia(payload: SendMediaPayload): Promise<SendMediaResult> {
    const { sessionId = 'default', phone, mediaType, mediaUrl, mediaBase64, caption, filename, mimeType } = payload;
    let tempPathCreated: string | null = null;

    try {
      // 1. Validation
      if (!phone || typeof phone !== 'string' || !phone.trim()) {
        return { success: false, message: 'Phone number is required', statusCode: 400 };
      }
      if (!['image', 'document', 'audio', 'video'].includes(mediaType)) {
        return { success: false, message: "Invalid mediaType. Must be 'image', 'document', 'audio', or 'video'", statusCode: 400 };
      }
      if (!mediaUrl && !mediaBase64) {
        return { success: false, message: 'Either mediaUrl or mediaBase64 must be provided', statusCode: 400 };
      }

      // Validate MIME type
      if (mimeType && !MediaService.isValidMimeType(mediaType, mimeType)) {
        return {
          success: false,
          message: `MIME type '${mimeType}' is not allowed for media type '${mediaType}'`,
          statusCode: 400
        };
      }

      const jid = formatToWhatsAppJid(phone);
      if (!jid) {
        return { success: false, message: 'Invalid phone number format', statusCode: 400 };
      }

      const statusInfo = getWhatsAppStatus(sessionId);
      const socket = getSocket(sessionId);

      if (!statusInfo.connected || !socket) {
        return {
          success: false,
          message: `WhatsApp client for session '${sessionId}' is not connected (current status: ${statusInfo.status})`,
          statusCode: 503
        };
      }

      let mediaBuffer: Buffer;
      const safeFilename = MediaService.sanitizeFilename(filename, mediaType === 'image' ? 'jpg' : 'pdf');

      // 2. Fetch media from URL or decode base64 into buffer / temp stream
      if (mediaUrl) {
        const response = await fetch(mediaUrl);
        if (!response.ok) {
          return {
            success: false,
            message: `Failed to download media from URL (HTTP ${response.status})`,
            statusCode: 400
          };
        }

        const arrayBuf = await response.arrayBuffer();
        if (arrayBuf.byteLength > MAX_FILE_SIZE_BYTES) {
          return {
            success: false,
            message: `Media file exceeds maximum allowed size of 64MB`,
            statusCode: 400
          };
        }
        mediaBuffer = Buffer.from(arrayBuf);
      } else if (mediaBase64) {
        const cleanBase64 = mediaBase64.replace(/^data:[^;]+;base64,/, '');
        mediaBuffer = Buffer.from(cleanBase64, 'base64');
        if (mediaBuffer.length > MAX_FILE_SIZE_BYTES) {
          return {
            success: false,
            message: `Media file exceeds maximum allowed size of 64MB`,
            statusCode: 400
          };
        }
      } else {
        return { success: false, message: 'No media content supplied', statusCode: 400 };
      }

      // 3. Construct Baileys payload based on media type
      let content: any = {};
      const finalMime = mimeType || (mediaType === 'image' ? 'image/jpeg' : mediaType === 'video' ? 'video/mp4' : mediaType === 'audio' ? 'audio/ogg' : 'application/pdf');

      if (mediaType === 'image') {
        content = {
          image: mediaBuffer,
          caption: caption ? caption.trim() : undefined,
          mimetype: finalMime
        };
      } else if (mediaType === 'video') {
        content = {
          video: mediaBuffer,
          caption: caption ? caption.trim() : undefined,
          mimetype: finalMime
        };
      } else if (mediaType === 'audio') {
        content = {
          audio: mediaBuffer,
          mimetype: finalMime,
          ptt: false
        };
      } else if (mediaType === 'document') {
        content = {
          document: mediaBuffer,
          fileName: safeFilename,
          caption: caption ? caption.trim() : undefined,
          mimetype: finalMime
        };
      }

      // 4. Send via Baileys socket
      const sentMsg = await socket.sendMessage(jid, content);

      return {
        success: true,
        message: `WhatsApp ${mediaType} sent successfully`,
        data: {
          messageId: sentMsg?.key?.id,
          timestamp: sentMsg?.messageTimestamp,
          mediaType,
          filename: safeFilename
        },
        statusCode: 200
      };
    } catch (err: any) {
      console.error('[whatsapp_service] Error sending media message:', err?.message || err);
      return {
        success: false,
        message: `Failed to send WhatsApp ${mediaType}`,
        error: err?.message || 'Media delivery failed',
        statusCode: 500
      };
    } finally {
      // 5. Clean up any temporary files
      if (tempPathCreated && fs.existsSync(tempPathCreated)) {
        try {
          fs.unlinkSync(tempPathCreated);
        } catch (_) {}
      }
    }
  }

  /**
   * Safely deletes a temporary file if it exists.
   */
  public static removeTempFile(filePath?: string): void {
    if (filePath && fs.existsSync(filePath)) {
      try {
        fs.unlinkSync(filePath);
      } catch (err) {
        console.warn(`[whatsapp_service] Failed to remove temp file ${filePath}:`, err);
      }
    }
  }
}
