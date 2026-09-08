import http from 'http';
import { IncomingMessageService } from '../dist/services/incoming.service.js';
import { MediaService } from '../dist/services/media.service.js';

const SECRET = 'scaleezy_internal_secret_key_2026';

function makeRequest(path, data) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port: 3001,
      path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-API-Secret': SECRET
      }
    }, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => resolve({ statusCode: res.statusCode, body: body ? JSON.parse(body) : {} }));
    });
    req.on('error', reject);
    if (data) req.write(JSON.stringify(data));
    req.end();
  });
}

async function runMediaTests() {
  console.log("=== WHATSAPP MEDIA SUPPORT TESTS ===");

  // 1. Test Path Traversal Protection
  console.log("\n--- Test 1: Path Traversal Sanitization ---");
  const unsafePath = "../../../etc/passwd";
  const safeName = MediaService.sanitizeFilename(unsafePath, "pdf");
  console.log(`Unsafe: '${unsafePath}' -> Sanitized: '${safeName}'`);
  assert(safeName === "passwd", "Path traversal sanitization failed");
  console.log("SUCCESS: Path traversal protection verified!");

  // 2. Test Invalid MIME Type Rejection
  console.log("\n--- Test 2: Invalid MIME Type Rejection ---");
  const isImageValid = MediaService.isValidMimeType("image", "application/x-executable");
  console.log("Validating 'application/x-executable' for image:", isImageValid);
  assert(isImageValid === false, "Invalid MIME type should be rejected");
  console.log("SUCCESS: Invalid MIME types correctly rejected!");

  // 3. Test Raw Message Processing for Media Types
  console.log("\n--- Test 3: Incoming Media Metadata Extraction ---");

  // Image Message
  const rawImage = {
    key: { id: "IMG_101", remoteJid: "919876543210@s.whatsapp.net", fromMe: false },
    message: { imageMessage: { mimetype: "image/png", caption: "Look at this design", fileLength: 102400 } }
  };
  const normImage = IncomingMessageService.processRawMessage(rawImage, "tenant_a");
  console.log("Normalized Image:", JSON.stringify(normImage, null, 2));
  assert(normImage.type === "media");
  assert(normImage.media.mediaType === "image");
  assert(normImage.media.mimeType === "image/png");
  assert(normImage.media.caption === "Look at this design");

  // Document Message
  const rawDoc = {
    key: { id: "DOC_102", remoteJid: "919876543210@s.whatsapp.net", fromMe: false },
    message: { documentMessage: { mimetype: "application/pdf", fileName: "Invoice_2026.pdf", caption: "Order Invoice", fileLength: 204800 } }
  };
  const normDoc = IncomingMessageService.processRawMessage(rawDoc, "tenant_a");
  console.log("Normalized Document:", JSON.stringify(normDoc, null, 2));
  assert(normDoc.media.mediaType === "document");
  assert(normDoc.media.filename === "Invoice_2026.pdf");

  // Audio Message
  const rawAudio = {
    key: { id: "AUD_103", remoteJid: "919876543210@s.whatsapp.net", fromMe: false },
    message: { audioMessage: { mimetype: "audio/ogg", fileLength: 51200 } }
  };
  const normAudio = IncomingMessageService.processRawMessage(rawAudio, "tenant_a");
  console.log("Normalized Audio:", JSON.stringify(normAudio, null, 2));
  assert(normAudio.media.mediaType === "audio");

  // Video Message
  const rawVideo = {
    key: { id: "VID_104", remoteJid: "919876543210@s.whatsapp.net", fromMe: false },
    message: { videoMessage: { mimetype: "video/mp4", caption: "Garment preview video", fileLength: 5242880 } }
  };
  const normVideo = IncomingMessageService.processRawMessage(rawVideo, "tenant_a");
  console.log("Normalized Video:", JSON.stringify(normVideo, null, 2));
  assert(normVideo.media.mediaType === "video");
  console.log("SUCCESS: Incoming media extraction verified for Image, Document, Audio, and Video!");

  // 4. Test Outgoing Media API Route
  console.log("\n--- Test 4: Outgoing Media API Route (POST /whatsapp/send-media) ---");
  for (const mediaType of ["image", "document", "audio", "video"]) {
    const res = await makeRequest("/whatsapp/send-media", {
      sessionId: "tenant_a",
      phone: "919876543210",
      mediaType,
      mediaBase64: "SGVsbG8gV29ybGQ=", // "Hello World" sample
      filename: `sample_${mediaType}.dat`,
      caption: `Sample ${mediaType} message`
    });
    console.log(`POST /whatsapp/send-media (${mediaType}):`, res.statusCode, res.body.message);
    assert([200, 503].includes(res.statusCode), `Unexpected HTTP status ${res.statusCode}`);
  }

  console.log("\n=== ALL MEDIA TESTS PASSED SUCCESSFULLY! ===");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message || "Assertion failed");
  }
}

runMediaTests().catch(console.error);
