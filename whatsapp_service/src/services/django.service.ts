import { config } from '../config.js';
import { NormalizedMessage } from './incoming.service.js';

export class DjangoService {
  /**
   * Sends an incoming normalized WhatsApp message payload to Django webhook endpoint.
   * Includes retry mechanism so Django being temporarily down does not crash whatsapp_service.
   */
  public static async sendIncomingWebhook(message: NormalizedMessage, maxRetries = 3): Promise<boolean> {
    const webhookUrl = `${config.DJANGO_BACKEND_URL.replace(/\/$/, '')}/api/whatsapp/webhook/`;
    let attempt = 0;

    while (attempt < maxRetries) {
      attempt++;
      try {
        const response = await fetch(webhookUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Internal-API-Secret': config.INTERNAL_API_SECRET
          },
          body: JSON.stringify(message)
        });

        if (response.ok) {
          console.log(`[whatsapp_service] Webhook delivered to Django successfully (HTTP ${response.status})`);
          return true;
        } else {
          console.warn(
            `[whatsapp_service] Django webhook returned HTTP ${response.status} on attempt ${attempt}/${maxRetries}`
          );
        }
      } catch (err: any) {
        console.warn(
          `[whatsapp_service] Failed to reach Django webhook on attempt ${attempt}/${maxRetries}: ${err.message}`
        );
      }

      // Wait 1 second before retrying if attempts remain
      if (attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }

    console.error(`[whatsapp_service] Unable to deliver message ${message.messageId} to Django after ${maxRetries} attempts.`);
    return false;
  }
}
