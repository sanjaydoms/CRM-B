import { Request, Response, NextFunction } from 'express';
import { config } from '../config.js';

/**
 * Middleware to authenticate requests between Django backend and WhatsApp service.
 * Compares X-Internal-API-Secret header with configured secret key.
 */
export function authenticateInternalApi(req: Request, res: Response, next: NextFunction): void {
  const secretHeader = req.headers['x-internal-api-secret'];

  if (!secretHeader || secretHeader !== config.INTERNAL_API_SECRET) {
    res.status(401).json({
      success: false,
      error: 'Unauthorized: Invalid or missing internal API secret'
    });
    return;
  }

  next();
}
