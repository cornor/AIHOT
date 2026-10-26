import { tag } from "./setup.ts";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { closeDb, sql } from "@aihot/backend/db";
import { chooseRecentReading, loadRecentReading, type ReadingCandidate } from "@aihot/backend/publication/recent-reading";

after(closeDb);
const now = new Date("2040-10-26T04:00:00Z");
const DAY = 86_400_000;
const row = (id: string, extra: Partial<ReadingCandidate> = {}): ReadingCandidate => ({
  id, title: `文章 ${id}`, reason: "提供可供研发团队参考的产品复盘", summary: "摘要", source_id: id,
  source_name: id, published_at: now, category: "game-tech", score: 80,
  story_id: null, fact_id: null, body_length: 1000, ...extra,
});

test("recent reading ranks value with a modest freshness bonus and uses a strict publication window", () => {
  const result = chooseRecentReading([
    row("old", { score: 90, published_at: new Date(+now - 6 * DAY) }),
    row("fresh"), row("expired", { published_at: new Date(+now - 7 * DAY - 1), score: 100 }),
    row("future", { published_at: new Date(+now + 1), score: 100 }),
    row("boundary", { published_at: new Date(+now - 7 * DAY), score: 100 }),
  ], now);
  assert.deepEqual(result.map(r => r.id), ["boundary", "fresh", "old"]);
  assert.deepEqual(chooseRecentReading([], now), []);
});

test("recent reading covers available categories, limits each source to two and never fills below the candidate set", () => {
  const result = chooseRecentReading([
    ...[1, 2, 3, 4].map(n => row(`tech-${n}`, { source_id: "same", score: 99 - n })),
    row("product", { category: "game-products", score: 70 }),
    row("market", { category: "game-market", score: 65 }),
    row("policy", { category: "industry", score: 60 }),
  ], now);
  assert.equal(result.length, 5);
  assert.equal(result.filter(r => r.id.startsWith("tech")).length, 2);
  assert.equal(new Set(result.map(r => r.category)).size, 4);
  assert.equal(chooseRecentReading([row("only")], now).length, 1);
});

test("known events and duplicate titles share one recommendation with distinct source counts", () => {
  const result = chooseRecentReading([
    row("brief", { story_id: 1, body_length: 100, score: 99 }),
    row("complete", { story_id: 1, body_length: 3000 }),
    row("same-source", { story_id: 1, source_id: "complete", body_length: 500 }),
    row("title-a", { title: "游戏更新：新玩法！", score: 90 }),
    row("title-b", { title: "游戏更新 新玩法", score: 70 }),
    row("fact-a", { fact_id: 8 }), row("fact-b", { fact_id: 8, body_length: 50 }),
  ], now);
  assert.equal(result.length, 3);
  assert.equal(result.find(r => r.id === "complete")?.sourceCount, 2);
  assert.equal(result.find(r => r.id === "title-a")?.sourceCount, 2);
  assert.equal(result.find(r => r.id === "fact-a")?.sourceCount, 2);
  assert.ok(!result.some(r => r.id === "brief"));
});

test("publication scope excludes hidden, withdrawn, unselected, gated, undated and stale articles on every read", async () => {
  const T = tag(); const source = `reading-${T}`; const ids: string[] = [];
  try {
    await sql`INSERT INTO sources(id,name,kind,tier) VALUES(${source},'游戏测试源','external','T2')`;
    const add = async (suffix: string, selected: boolean, visibility: string, date: Date | null, gate = now) => {
      const id = `${T}-${suffix}`; ids.push(id);
      await sql`INSERT INTO articles(id,source_id,identity_key,url,title,discovered_at,timeline_at)
        VALUES(${id},${source},${id},'https://example.test/reading',${id},${now},${now})`;
      await sql`INSERT INTO publications(article_id,title,reason,source_id,channel,url,published_at,discovered_at,timeline_at,sort_at,eligible,selected,visible_after,visibility,score)
        VALUES(${id},${id},'已生成的推荐理由',${source},'news','https://example.test/reading',${date},${now},${now},${now},true,${selected},${gate},${visibility},80)`;
      return id;
    };
    const visible = await add("visible", true, "public", now);
    await add("hidden", true, "summary-only", now);
    await add("unselected", false, "public", now);
    await add("gated", true, "public", now, new Date(+now + 1000));
    await add("stale", true, "public", new Date(+now - 8 * DAY));
    await add("undated", true, "public", null);
    const result = await loadRecentReading(now);
    assert.deepEqual(result.map(r => r.id), [visible]);
    assert.equal(result[0]?.reason, "已生成的推荐理由");
    assert.equal(result[0]?.sourceCount, 1);
    await sql`UPDATE publications SET visibility='withdrawn' WHERE article_id=${visible}`;
    assert.deepEqual(await loadRecentReading(now), []);
  } finally {
    if (ids.length) await sql`DELETE FROM articles WHERE id IN ${sql(ids)}`;
    await sql`DELETE FROM sources WHERE id=${source}`;
  }
});
