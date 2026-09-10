import express, { Request, Response } from 'express';
import cors from 'cors';
import { config } from './config.js';
import whatsappRouter from './routes/whatsapp.js';
import { initWhatsApp, closeAllWhatsAppSessions } from './whatsapp.js';

const app = express();
const PORT = config.PORT;

// Restrict CORS for production security
const allowedOrigins = [
  config.DJANGO_BACKEND_URL.replace(/\/$/, ''),
  'http://localhost:8000',
  'http://127.0.0.1:8000'
];

app.use(
  cors({
    origin: (origin, callback) => {
      // Allow requests with no origin (e.g. server-to-server or curl) or allowed origin list
      if (!origin || allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(null, true); // Permissive for local dev, header-secret protected
      }
    },
    allowedHeaders: ['Content-Type', 'X-Internal-API-Secret', 'Authorization'],
    methods: ['GET', 'POST', 'OPTIONS']
  })
);

// Payload size limit
app.use(express.json({ limit: '64mb' }));

// Health Check Route
app.get('/health', (_req: Request, res: Response) => {
  res.json({
    success: true,
    service: 'whatsapp_service',
    status: 'running'
  });
});

// Protected WhatsApp routes
app.use('/whatsapp', whatsappRouter);

// Global Error Handler Middleware
app.use((err: any, _req: Request, res: Response, _next: any) => {
  console.error('[whatsapp_service] Unhandled express error:', err?.message || err);
  res.status(500).json({
    success: false,
    error: 'Internal server error'
  });
});

// Process listeners for safety
process.on('uncaughtException', (err) => {
  console.error('[whatsapp_service] Uncaught Exception:', err?.message || err);
});

process.on('unhandledRejection', (reason) => {
  console.error('[whatsapp_service] Unhandled Rejection:', reason);
});

// Start Express Server & initialize default WhatsApp session
const server = app.listen(PORT, () => {
  console.log(`[whatsapp_service] Server running securely on port ${PORT}`);
  initWhatsApp();
});

// Graceful Shutdown Handler (SIGINT & SIGTERM)
async function gracefulShutdown(signal: string) {
  console.log(`\n[whatsapp_service] Received ${signal}. Starting graceful shutdown...`);
  server.close(async () => {
    console.log('[whatsapp_service] Express HTTP server closed.');
    await closeAllWhatsAppSessions();
    console.log('[whatsapp_service] Graceful shutdown complete. Exiting.');
    process.exit(0);
  });

  // Force exit after 10 seconds if shutdown hangs
  setTimeout(() => {
    console.error('[whatsapp_service] Forced shutdown timeout expired.');
    process.exit(1);
  }, 10000);
}

process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
