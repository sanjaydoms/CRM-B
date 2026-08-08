/**
 * Assembles the marketing site into dist/ as plain static HTML.
 *
 * Every page is layout.html + a content file, so the nav and footer exist once
 * rather than in twelve files that drift apart. Output is finished HTML with
 * real <a href> links -- the whole point is that a crawler which does not run
 * JavaScript can read the site, so nothing here may depend on the client.
 *
 * Run after `vite build`: vite writes the React workspace into dist/ and copies
 * public/ verbatim, then this overwrites/adds the marketing pages and the
 * sitemap. See the "build" script in package.json.
 */
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const SITE = join(root, 'site')
const OUT = join(root, 'dist')
const ORIGIN = 'https://boutique.scaleezy.com'

// The demo form posts here. VITE_API_URL is the same variable the React app
// reads (src/services/api.js), so there is one source of truth for where the
// API lives rather than two that can drift apart.
//
// It carries an /api suffix; the leading slash below drops it, because the
// intake route sits outside /api/ for the same reason /track/ does -- see
// boutique_crm/urls.py. Falling back to localhost keeps a developer's build
// working, but on Vercel an unset variable is a form that posts into the void,
// so it fails the build loudly instead of shipping one.
const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000/api'
if (!process.env.VITE_API_URL && process.env.VERCEL) {
  throw new Error('VITE_API_URL is not set: the demo form would post nowhere. Set it on the Vercel project.')
}
const DEMO_ENDPOINT = new URL('/demo-request/', API_BASE).href

const read = (...p) => readFileSync(join(SITE, ...p), 'utf8')

/** Splits a source file's leading `<!--{ ... }-->` metadata from its body. */
function parse(src, name) {
  const m = src.match(/^\s*<!--(\{[\s\S]*?\})-->/)
  if (!m) throw new Error(`${name}: missing leading <!--{...}--> metadata block`)
  try {
    return { meta: JSON.parse(m[1]), body: src.slice(m[0].length).trim() }
  } catch (e) {
    throw new Error(`${name}: metadata is not valid JSON -- ${e.message}`)
  }
}

const layout = read('layout.html')
const navHtml = read('partials', 'nav.html')
const footerHtml = read('partials', 'footer.html')

const load = (dir) =>
  readdirSync(join(SITE, dir))
    .filter((f) => f.endsWith('.html'))
    .map((f) => ({ file: f, ...parse(read(dir, f), `${dir}/${f}`) }))

const pages = load('pages')
const posts = load('posts').sort((a, b) => (a.meta.date < b.meta.date ? 1 : -1))

const fmtDate = (iso) =>
  new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  })

/** The blog index list, injected wherever {{POST_LIST}} appears. */
const postList = posts
  .map(
    (p) => `        <a class="post-card" href="/blog/${p.meta.slug}">
          <span class="post-meta"><time datetime="${p.meta.date}">${fmtDate(p.meta.date)}</time> · ${p.meta.readingTime}</span>
          <h3>${p.meta.title}</h3>
          <p>${p.meta.description}</p>
          <span class="post-more">Read the article →</span>
        </a>`
  )
  .join('\n')

/** The three most recent posts, for the teaser strip on the home page. */
const postTeasers = posts
  .slice(0, 3)
  .map(
    (p) => `        <a class="post-card" href="/blog/${p.meta.slug}">
          <span class="post-meta">${p.meta.readingTime}</span>
          <h3>${p.meta.title}</h3>
          <p>${p.meta.description}</p>
        </a>`
  )
  .join('\n')

function render({ meta, body }, { isPost = false } = {}) {
  const path = meta.slug === '' ? '/' : isPost ? `/blog/${meta.slug}` : `/${meta.slug}`
  const url = ORIGIN + path

  // Marking the current nav item with aria-current gives screen readers the
  // same signal the highlight gives everyone else, and needs no extra class.
  const nav = navHtml.replace(`data-nav="${meta.nav}"`, `data-nav="${meta.nav}" aria-current="page"`)

  const jsonld = meta.jsonld
    ? `\n<script type="application/ld+json">\n${JSON.stringify(meta.jsonld, null, 1)}\n</script>\n`
    : ''

  const breadcrumb = isPost
    ? {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Home', item: ORIGIN + '/' },
          { '@type': 'ListItem', position: 2, name: 'Blog', item: ORIGIN + '/blog' },
          { '@type': 'ListItem', position: 3, name: meta.title, item: url },
        ],
      }
    : null

  const article = isPost
    ? {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: meta.title,
        description: meta.description,
        datePublished: meta.date,
        dateModified: meta.date,
        author: { '@type': 'Organization', name: 'Scaleezy', url: 'https://www.scaleezy.com/' },
        publisher: { '@type': 'Organization', name: 'Scaleezy', url: 'https://www.scaleezy.com/' },
        mainEntityOfPage: url,
        image: ORIGIN + '/og.png',
      }
    : null

  const extraLd = [breadcrumb, article]
    .filter(Boolean)
    .map((o) => `\n<script type="application/ld+json">\n${JSON.stringify(o, null, 1)}\n</script>\n`)
    .join('')

  // Every replacement passes a FUNCTION rather than a string. String.replace
  // expands $&, $`, $' and $$ inside a string replacement, so any page or post
  // containing those would be silently corrupted -- and the demo page now
  // carries a <script>. A function replacer is inserted verbatim.
  //
  // {{API}} is replaced after {{CONTENT}}: the placeholder lives in the page
  // body, so it does not exist in the layout until the body is in.
  return layout
    .replaceAll('{{TITLE}}', () => meta.title)
    .replaceAll('{{DESCRIPTION}}', () => meta.description)
    .replaceAll('{{CANONICAL}}', () => url)
    .replaceAll('{{OG_TYPE}}', () => (isPost ? 'article' : 'website'))
    .replace('{{NAV}}', () => nav)
    .replace('{{FOOTER}}', () => footerHtml)
    .replace('{{JSONLD}}', () => jsonld + extraLd)
    .replace('{{CONTENT}}', () => body)
    .replace('{{POST_LIST}}', () => postList)
    .replace('{{POST_TEASERS}}', () => postTeasers)
    .replaceAll('{{API}}', () => DEMO_ENDPOINT)
}

writeFileSync(join(OUT, 'styles.css'), read('styles.css'))

/**
 * Every page is written as <path>/index.html rather than <path>.html.
 *
 * The blog forces the issue -- `blog.html` next to a `blog/` directory is a
 * collision that different static hosts resolve differently, and Vite's preview
 * server disagrees with Vercel about it. Directory indexes have one obvious
 * answer everywhere, so clean URLs stop depending on host configuration.
 */
function emit(page, path, opts) {
  const dir = path === '/' ? OUT : join(OUT, path)
  const html = render(page, opts)
  // A leftover {{PLACEHOLDER}} is a page that silently ships broken -- a form
  // posting to the literal string "{{API}}", say. Cheaper to fail the build.
  const leftover = html.match(/\{\{[A-Z_]+\}\}/)
  if (leftover) throw new Error(`${path}: unsubstituted ${leftover[0]}`)
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'index.html'), html)
  return path
}

const written = []
for (const p of pages) written.push(emit(p, p.meta.slug === '' ? '/' : `/${p.meta.slug}`))
for (const p of posts) written.push(emit(p, `/blog/${p.meta.slug}`, { isPost: true }))

// The sitemap is generated from what was actually written, so a new page cannot
// be published without being listed -- the failure mode of a hand-kept sitemap.
const urls = written
  .map((path) => {
    const isPost = path.startsWith('/blog/')
    const post = isPost && posts.find((p) => `/blog/${p.meta.slug}` === path)
    return `  <url>
    <loc>${ORIGIN}${path}</loc>${post ? `\n    <lastmod>${post.meta.date}</lastmod>` : ''}
    <changefreq>${isPost ? 'yearly' : 'monthly'}</changefreq>
    <priority>${path === '/' ? '1.0' : isPost ? '0.6' : '0.8'}</priority>
  </url>`
  })
  .join('\n')

writeFileSync(
  join(OUT, 'sitemap.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
)

console.log(`site: ${pages.length} pages, ${posts.length} posts, sitemap with ${written.length} URLs`)
