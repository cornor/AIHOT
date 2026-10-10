import { tag } from "./setup.ts";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { closeDb, sql } from "@aihot/backend/db";
import { loadPool } from "@aihot/backend/publication/pool";

const T = tag();
const SOURCE = `pool-time-${T}`;
const now = new Date("2026-10-10T04:00:00Z");
const filters = { channel: "all" as const, category: null, tag: T, now };
after(async () => {
  await sql`DELETE FROM articles WHERE source_id=${SOURCE}`;
  await sql`DELETE FROM sources WHERE id=${SOURCE}`;
  await closeDb();
});

test("pool rail, paging, search and today count use publication time instead of ingestion time", async () => {
  await sql`INSERT INTO sources(id,name,kind) VALUES(${SOURCE},'Publication-time test','rss')`;
  const expected: { id: string; at: string }[] = [];
  // Reverse ingestion order across a full page; include equal dates and a Beijing midnight boundary.
  for (let i = 0; i < 43; i++) {
    const id = `${T}-${String(i).padStart(2, '0')}`;
    const published = i === 42 ? null : new Date(Date.parse('2026-10-09T15:40:00Z') + Math.floor(i / 2) * 60_000);
    const discovered = new Date(now.getTime() - i * 1000);
    const url = `https://example.test/${id}`;
    await sql`INSERT INTO articles(id,source_id,identity_key,url,title,published_at,discovered_at,timeline_at)
      VALUES(${id},${SOURCE},${id},${url},'game time',${published},${discovered},${discovered})`;
    await sql`INSERT INTO publications(article_id,title,summary,source_id,channel,url,published_at,discovered_at,timeline_at,sort_at,eligible,tags,search_text)
      VALUES(${id},'game time','same summary',${SOURCE},'news',${url},${published},${discovered},${discovered},${discovered},true,${[T]},'game time same summary')`;
    await sql`INSERT INTO pool_search(article_id,direct,body) VALUES(${id},'game time same summary','body')`;
    expected.push({ id, at: (published ?? discovered).toISOString() });
  }
  expected.sort((a, b) => b.at.localeCompare(a.at) || b.id.localeCompare(a.id));
  for (const query of [{}, { q: 'game' }, { q: 'game', tab: 'relevance' as const }]) {
    const first = await loadPool({ ...filters, ...query });
    const second = await loadPool({ ...filters, ...query, page: 2 });
    assert.equal(first.total, 43);
    assert.equal(first.todayCount, 3, 'only two midnight publications plus the missing-date fallback belong to today');
    assert.equal(first.items.length, 40);
    assert.equal(second.items.length, 3);
    assert.deepEqual([...first.items, ...second.items].map(i => ({ id: i.id, at: i.timelineAt })), expected);
  }
  const [stored] = await sql`SELECT published_at,discovered_at,timeline_at FROM publications WHERE article_id=${`${T}-00`}`;
  assert.notEqual(stored!.published_at.toISOString(), stored!.discovered_at.toISOString());
  assert.equal(stored!.timeline_at.toISOString(), stored!.discovered_at.toISOString(), 'reading must not rewrite ingestion history');
});
