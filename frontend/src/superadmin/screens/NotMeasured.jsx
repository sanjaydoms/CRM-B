/**
 * The screen for things this product does not measure.
 *
 * Jobs/Queues and API Monitoring are in the navigation because the
 * specification asks for them, and they render this because the honest answer
 * is that nothing in this codebase produces the data. There is no job runner
 * (no Celery, RQ, cron or scheduled management command anywhere), and no
 * middleware counts or times a request.
 *
 * The alternative was an empty chart, which reads as "everything is fine" --
 * the single most dangerous thing an operations console can say. This says what
 * is missing and what building it would take, which is the only useful content
 * available.
 */

import { Gauge, Info } from 'lucide-react';

import { SectionHead } from '../ui';

const CONTENT = {
  jobs: {
    title: 'Jobs & Queues',
    subtitle: 'Not measured — this product has no background job runner.',
    body: [
      'There is no Celery, RQ, Huey, django-q or Dramatiq in requirements.txt, no cron entry and no scheduled management command. Every operation in this product runs inline inside the request that triggered it.',
      'The one deferred call is the customer-message hook, which uses transaction.on_commit and still runs in the same process. It is disabled by default: CUSTOMER_MESSAGE_BACKEND is unset, so messages queue in the database for a person to send.',
      'The real backlog that exists today is that message queue, and it is on the Customer Messaging screen.',
    ],
    build: 'A queue dashboard needs a queue first. Adding one means a broker, a worker process on Render, and a result backend — none of which exist.',
  },
  api: {
    title: 'API Monitoring',
    subtitle: 'Not measured — nothing instruments requests.',
    body: [
      'No middleware records a request count, a response time or a status-code distribution. Gunicorn writes an access log to stdout, which Render captures but the application cannot read back.',
      'Any latency chart here would be invented. What IS captured is unhandled server exceptions — see the Error Center, which records every 500 with a fingerprint, a count and the first in-project stack frame.',
    ],
    build: 'Real numbers need either request-timing middleware writing to a table (cheap, coarse, and it costs a write per request) or an external APM. Both are decisions rather than screens.',
  },
};

export default function NotMeasured({ route }) {
  const content = CONTENT[route.head] || CONTENT.api;

  return (
    <>
      <SectionHead title={content.title} subtitle={content.subtitle} />
      <div className="sa-state muted" style={{ alignItems: 'flex-start', textAlign: 'left' }}>
        <Gauge size={22} />
        <h3>There is no data behind this screen, and that is the finding.</h3>
        {content.body.map((paragraph, i) => (
          <p key={i} style={{ maxWidth: 720 }}>{paragraph}</p>
        ))}
        <p style={{ maxWidth: 720, borderTop: '1px solid var(--border-color)', paddingTop: 12, marginTop: 6 }}>
          <Info size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
          {content.build}
        </p>
      </div>
    </>
  );
}
