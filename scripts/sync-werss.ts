// Local WeRSS bridge: reads only the pinned loopback service. Public collectors keep their SSRF guard.
// Configure .data/werss/feeds.json with [{sourceId, feedId, name, tier, firstParty?}].
// node --env-file=.env scripts/sync-werss.ts [--watch]
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { z } from 'zod';
import { XMLParser, XMLValidator } from 'fast-xml-parser';
import { REPO_ROOT } from '@aihot/backend/config';
import { sql, closeDb } from '@aihot/backend/db';
import { upsertMaterial, type MaterialInput } from '@aihot/backend/content/materials';
import { sanitizeBody } from '@aihot/backend/content/sanitize';
import { stripTags } from '@aihot/backend/lib/text';
import { queueProcessing } from '@aihot/backend/jobs/content';
import { stopBoss } from '@aihot/backend/jobs/queue';

const Feed = z.object({
  sourceId: z.string().regex(/^werss-[a-z0-9-]+$/).max(120),
  feedId: z.string().min(1).max(200), name: z.string().min(1).max(200),
  tier: z.enum(['T1', 'T1_5', 'T2']).default('T2'), firstParty: z.boolean().default(false),
});
const Payload = z.object({ items: z.array(z.object({
  title: z.string(), link: z.string(), updated: z.string(),
  content: z.string().optional(), description: z.string().optional(),
})).max(50) });

export function parseWerssRss(xml: string): unknown {
  if (/<!DOCTYPE/i.test(xml) || XMLValidator.validate(xml) !== true) throw new Error('Invalid WeRSS XML');
  const doc = new XMLParser({ parseTagValue: false, trimValues: true }).parse(xml);
  if (!doc.rss?.channel) throw new Error('WeRSS response is not an RSS feed');
  const entries = doc.rss.channel.item;
  const items = entries == null ? [] : Array.isArray(entries) ? entries : [entries];
  return { items: items.map(item => ({ title: item.title, link: item.link, updated: item.pubDate,
    description: item.description || '', content: item['content:encoded'] || '' })) };
}

export function werssMaterials(payload: unknown, sourceId: string): MaterialInput[] {
  const seen = new Set<string>();
  return Payload.parse(payload).items.flatMap(item => {
    let url: URL;
    try { url = new URL(item.link); } catch { return []; }
    const publishedAt = new Date(item.updated);
    // Never accept local reader links, arbitrary external URLs, or invented publication dates.
    if (url.protocol !== 'https:' || url.hostname !== 'mp.weixin.qq.com' || url.username || url.password || url.port
      || !/^\/s(?:\/|$)/.test(url.pathname) || !item.title.trim() || !Number.isFinite(publishedAt.getTime()) || seen.has(url.href)) return [];
    seen.add(url.href);
    const bodyHtml = item.content ? sanitizeBody(item.content, url.href) : null;
    const bodyText = bodyHtml ? stripTags(bodyHtml.replace(/<\/p>|<br\s*\/?>/gi, '\n')).trim() : null;
    return [{ sourceId, url: url.href, title: stripTags(item.title).trim(), publishedAt,
      language: 'zh', excerpt: item.description ? stripTags(item.description) : null,
      bodyHtml, bodyText, bodyStatus: bodyText ? 'ok' : 'none', via: 'ingest',
      raw: { collector: 'local-werss' } } satisfies MaterialInput];
  });
}

async function sync() {
  if (process.env.COLLECT_ENABLED !== 'true') throw new Error('COLLECT_ENABLED is off; no WeRSS collection performed');
  const feeds = z.array(Feed).parse(JSON.parse(await readFile(path.join(REPO_ROOT, '.data/werss/feeds.json'), 'utf8')));
  if (!feeds.length) { console.log('No WeRSS subscriptions configured; waiting for login and source selection.'); return; }
  for (const feed of feeds) {
    try {
      const [source] = await sql<{ enabled: boolean; kind: string; cursor: Record<string, unknown> | null }[]>`SELECT enabled,kind,cursor FROM sources WHERE id=${feed.sourceId}`;
      if (source && (!source.enabled || source.kind !== 'external')) continue;
      const response = await fetch(`http://127.0.0.1:8001/feed/${encodeURIComponent(feed.feedId)}.rss?limit=50`, {
        redirect: 'error', signal: AbortSignal.timeout(30_000), headers: { accept: 'application/rss+xml' },
      });
      if (!response.ok) throw new Error(`WeRSS HTTP ${response.status}`);
      const reader = response.body!.getReader();
      const chunks: Uint8Array[] = []; let bytes = 0;
      try { for (;;) { const { done, value } = await reader.read(); if (done) break;
        bytes += value.length; if (bytes > 8 * 1024 * 1024) throw new Error('WeRSS response exceeds 8 MiB'); chunks.push(value);
      } } finally { await reader.cancel(); }
      const materials = werssMaterials(parseWerssRss(Buffer.concat(chunks).toString('utf8')), feed.sourceId);
      await sql`INSERT INTO sources(id,name,kind,config,tier,first_party,participation_mode,interval_minutes,enabled,site_fulltext,syndicate_fulltext)
        VALUES(${feed.sourceId},${feed.name},'external','{}',${feed.tier},${feed.firstParty},'editorial',120,true,false,false)
        ON CONFLICT(id) DO NOTHING`;
      let created = 0, revised = 0;
      for (const material of materials) {
        const result = await upsertMaterial({ ...material, backfill: source?.cursor?.werssInitialized ? null : 'first-import' });
        if (result.created) created++;
        if (result.revised) revised++;
        if (result.created || result.revised) await queueProcessing(result.articleId);
      }
      await sql`UPDATE sources SET cursor=COALESCE(cursor,'{}'::jsonb)||'{"werssInitialized":true}'::jsonb,
        last_fetch_at=now(),last_ok_at=now(),health='ok',fail_count=0,last_error=NULL WHERE id=${feed.sourceId}`;
      console.log(JSON.stringify({ source: feed.name, received: materials.length, created, revised }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(JSON.stringify({ source: feed.name, error: message }));
      await sql`UPDATE sources SET last_fetch_at=now(),last_error=${message.slice(0,500)},fail_count=fail_count+1,health='degraded' WHERE id=${feed.sourceId}`;
      if (!process.argv.includes('--watch')) process.exitCode = 1;
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    await sync();
    if (process.argv.includes('--watch')) {
      const timer = setInterval(() => { void run(); }, 30 * 60_000);
      let busy = false;
      async function run() { if (busy) return; busy = true; try { await sync(); } catch (e) { console.error(String(e)); } finally { busy = false; } }
      await new Promise<void>(resolve => { for (const signal of ['SIGINT', 'SIGTERM'] as const) process.once(signal, () => { clearInterval(timer); resolve(); }); });
      while (busy) await new Promise(resolve => setTimeout(resolve, 100));
    }
  } finally { await stopBoss(); await closeDb(); }
}
