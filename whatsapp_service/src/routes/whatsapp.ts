import { Router, Request, Response } from 'express';
import { getWhatsAppStatus, initWhatsApp, resetWhatsApp } from '../whatsapp.js';
import { MessageService } from '../services/message.service.js';
import { MediaService } from '../services/media.service.js';
import { authenticateInternalApi } from '../middleware/auth.middleware.js';

const router = Router();

// GET /whatsapp/status?sessionId=...
router.get('/status', (req: Request, res: Response) => {
  const sessionId = (req.query.sessionId as string) || 'default';
  const statusInfo = getWhatsAppStatus(sessionId);
  res.json({
    success: true,
    sessionId: statusInfo.sessionId,
    connected: statusInfo.connected,
    status: statusInfo.status,
    qrCode: statusInfo.qrCode
  });
});

// POST /whatsapp/start-session (Protected by internal API secret)
router.post('/start-session', authenticateInternalApi, async (req: Request, res: Response) => {
  try {
    const { sessionId = 'default', forceClean = false } = req.body || {};
    if (forceClean) {
      await resetWhatsApp(sessionId, true);
    } else {
      await initWhatsApp(sessionId);
    }
    res.json({
      success: true,
      message: `WhatsApp session initialization triggered for '${sessionId}'`
    });
  } catch (err: any) {
    res.status(500).json({
      success: false,
      error: err?.message || 'Failed to start session'
    });
  }
});

// POST /whatsapp/reset-session (Protected by internal API secret)
router.post('/reset-session', authenticateInternalApi, async (req: Request, res: Response) => {
  try {
    const { sessionId = 'default' } = req.body || {};
    await resetWhatsApp(sessionId, true);
    res.json({
      success: true,
      message: `WhatsApp session reset and auth folder cleaned for '${sessionId}'`
    });
  } catch (err: any) {
    res.status(500).json({
      success: false,
      error: err?.message || 'Failed to reset session'
    });
  }
});

// POST /whatsapp/send-message (Protected by internal API secret)
router.post('/send-message', authenticateInternalApi, async (req: Request, res: Response) => {
  try {
    const { sessionId = 'default', phone, message } = req.body || {};
    const result = await MessageService.sendMessage({ sessionId, phone, message });

    res.status(result.statusCode || (result.success ? 200 : 400)).json({
      success: result.success,
      message: result.message,
      ...(result.error ? { error: result.error } : {}),
      ...(result.data ? { data: result.data } : {})
    });
  } catch (err: any) {
    console.error('[whatsapp_service] Unhandled route error in /send-message:', err);
    res.status(500).json({
      success: false,
      message: 'Internal server error while processing send-message request',
      error: err?.message || 'Unknown error'
    });
  }
});

// POST /whatsapp/send-media (Protected by internal API secret)
router.post('/send-media', authenticateInternalApi, async (req: Request, res: Response) => {
  try {
    const {
      sessionId = 'default',
      phone,
      mediaType,
      mediaUrl,
      mediaBase64,
      caption,
      filename,
      mimeType
    } = req.body || {};

    const result = await MediaService.sendMedia({
      sessionId,
      phone,
      mediaType,
      mediaUrl,
      mediaBase64,
      caption,
      filename,
      mimeType
    });

    res.status(result.statusCode || (result.success ? 200 : 400)).json({
      success: result.success,
      message: result.message,
      ...(result.error ? { error: result.error } : {}),
      ...(result.data ? { data: result.data } : {})
    });
  } catch (err: any) {
    console.error('[whatsapp_service] Unhandled route error in /send-media:', err);
    res.status(500).json({
      success: false,
      message: 'Internal server error while processing send-media request',
      error: err?.message || 'Unknown error'
    });
  }
});

export default router;
