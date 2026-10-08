import dns from 'node:dns/promises';
import { isIP } from 'node:net';
import ipaddr from 'ipaddr.js';
import * as cheerio from 'cheerio';
import { Agent, request } from 'undici';

const MAX_PAGE_BYTES = 2_000_000;
const MAX_PAGE_TEXT = 50_000;
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

function assertPublicAddress(address: string) {
  try {
    const parsed = ipaddr.parse(address);
    if (parsed.range() !== 'unicast') throw new Error('The website address is not public.');
  } catch {
    throw new Error('The website address is not public.');
  }
}

async function validateAndPin(url: URL) {
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported URL protocol.');
  if (url.username || url.password) throw new Error('URLs with embedded credentials are not supported.');
  if (url.port && !['80', '443'].includes(url.port)) throw new Error('Non-standard website ports are not supported.');
  const hostname = url.hostname.replace(/^\[|\]$/g, '').toLowerCase();
  if (!hostname || hostname === 'localhost' || hostname.endsWith('.localhost') || hostname.endsWith('.local') || hostname.endsWith('.internal') || hostname.endsWith('.test')) {
    throw new Error('The website address is not public.');
  }
  let addresses: Array<{ address: string; family: number }>;
  if (isIP(hostname)) {
    assertPublicAddress(hostname);
    addresses = [{ address: hostname, family: isIP(hostname) }];
  } else {
    addresses = await dns.lookup(hostname, { all: true, verbatim: true });
    if (!addresses.length || addresses.length > 32) throw new Error('The website did not resolve to a usable address.');
    for (const entry of addresses) assertPublicAddress(entry.address);
  }

  const lookup = ((_: string, options: { all?: boolean }, callback: (...args: unknown[]) => void) => {
    if (options?.all) callback(null, addresses);
    else callback(null, addresses[0]!.address, addresses[0]!.family);
  }) as never;
  return new Agent({ connect: { lookup } });
}

async function readBounded(response: Awaited<ReturnType<typeof request>>) {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of response.body) {
    const buffer = Buffer.from(chunk);
    size += buffer.byteLength;
    if (size > MAX_PAGE_BYTES) {
      response.body.destroy();
      throw new Error('Page is too large to extract.');
    }
    chunks.push(buffer);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function fetchHtml(start: URL) {
  let current = start;
  for (let redirect = 0; redirect <= 4; redirect += 1) {
    const dispatcher = await validateAndPin(current);
    try {
      const response = await request(current, {
        method: 'GET',
        dispatcher,
        headersTimeout: 7000,
        bodyTimeout: 7000,
        signal: AbortSignal.timeout(8000),
        headers: {
          'user-agent': 'TroveLinkPreview/0.1 (+https://trove.app; public-page metadata requested by a user)',
          accept: 'text/html,application/xhtml+xml,text/plain;q=0.9',
          'accept-encoding': 'identity',
        },
      });
      if (REDIRECT_STATUSES.has(response.statusCode)) {
        const location = response.headers.location;
        response.body.destroy();
        if (typeof location !== 'string' || redirect === 4) throw new Error('The page redirected too many times.');
        current = new URL(location, current);
        continue;
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        response.body.destroy();
        throw new Error('The page did not return a successful response.');
      }
      const contentType = String(response.headers['content-type'] ?? '').toLowerCase();
      if (!contentType.includes('text/html') && !contentType.includes('application/xhtml+xml') && !contentType.includes('text/plain')) {
        response.body.destroy();
        throw new Error('The page content type is not supported.');
      }
      const contentLength = Number(response.headers['content-length'] ?? 0);
      if (contentLength > MAX_PAGE_BYTES) {
        response.body.destroy();
        throw new Error('Page is too large to extract.');
      }
      return { body: await readBounded(response), contentType, finalUrl: current.href };
    } finally {
      await dispatcher.close();
    }
  }
  throw new Error('Page redirect limit reached.');
}

export async function extractPublicPage(rawUrl: string) {
  const start = new URL(rawUrl);
  const { body, contentType, finalUrl } = await fetchHtml(start);
  if (contentType.includes('text/plain')) return { title: null, description: null, text: body.slice(0, MAX_PAGE_TEXT), finalUrl };

  const $ = cheerio.load(body);
  const meta = (selector: string) => $(selector).attr('content')?.trim() || null;
  const title = meta('meta[property="og:title"]') || meta('meta[name="twitter:title"]') || $('title').first().text().trim() || null;
  const description = meta('meta[property="og:description"]') || meta('meta[name="description"]') || meta('meta[name="twitter:description"]') || null;
  $('script,style,noscript,svg,iframe,canvas,nav,footer,header,form,button,aside,[aria-hidden="true"]').remove();
  const article = $('article').first().text().trim() || $('[role="main"]').first().text().trim() || $('main').first().text().trim() || $('body').text();
  const text = article.replace(/\s+/g, ' ').trim().slice(0, MAX_PAGE_TEXT);
  return { title: title?.slice(0, 500) ?? null, description: description?.slice(0, 4000) ?? null, text: text || null, finalUrl };
}
