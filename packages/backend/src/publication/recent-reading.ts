import type { RecentReadingEntry } from "@aihot/contracts/site";
import { RECENT_READING } from "@aihot/industry/selection";
import { sql } from "../db.ts";
import { selectedCondition } from "./scope.ts";

export interface ReadingCandidate {
  id: string;
  url: string;
  title: string;
  reason: string | null;
  summary: string | null;
  source_id: string;
  source_name: string;
  published_at: Date;
  category: string | null;
  score: number;
  story_id: number | null;
  fact_id: number | null;
  body_length: number;
}

const DAY = 86_400_000;
const normalizedTitle = (title: string) => title.normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
const groupKey = (row: ReadingCandidate) => row.story_id ? `s:${row.story_id}` : row.fact_id ? `f:${row.fact_id}` : `a:${row.id}`;

/** Reuse existing grouping; title equality catches obvious duplicates not grouped yet. */
export function chooseRecentReading(candidates: ReadingCandidate[], now: Date): RecentReadingEntry[] {
  const recent = candidates.filter(row => row.published_at.getTime() <= now.getTime()
    && row.published_at.getTime() >= now.getTime() - RECENT_READING.days * DAY);
  const rank = (row: ReadingCandidate) => row.score
    - (now.getTime() - row.published_at.getTime()) / DAY * RECENT_READING.freshnessPointsPerDay;
  const order = (a: ReadingCandidate, b: ReadingCandidate) => rank(b) - rank(a)
    || b.published_at.getTime() - a.published_at.getTime() || a.id.localeCompare(b.id);
  // Keep the most complete representative of each known event, then rank the resulting articles.
  const groups = new Map<string, ReadingCandidate[]>();
  for (const row of recent) {
    const key = groupKey(row);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const representatives = [...groups.values()].map(rows => [...rows].sort((a, b) =>
    b.body_length - a.body_length || order(a, b))[0]!).sort(order);
  const picked: ReadingCandidate[] = [];
  const sources = new Map<string, number>();
  const categories = new Set<string>();
  const titles = new Set<string>();
  const add = (row: ReadingCandidate) => {
    const title = normalizedTitle(row.title);
    if (picked.length >= RECENT_READING.limit || picked.includes(row) || titles.has(title)
      || (sources.get(row.source_id) ?? 0) >= RECENT_READING.perSource) return;
    picked.push(row);
    titles.add(title);
    sources.set(row.source_id, (sources.get(row.source_id) ?? 0) + 1);
    if (row.category) categories.add(row.category);
  };
  for (const row of representatives) if (row.category && !categories.has(row.category)) add(row);
  for (const row of representatives) add(row);
  return picked.sort(order).map(row => ({
    id: row.id, title: row.title, originalUrl: row.url,
    // Existing editorial text only: never generate recommendations in a reader request.
    reason: (row.reason?.trim() || row.summary?.trim() || "").replace(/\s+/g, " "),
    sourceName: row.source_name, publishedAt: row.published_at.toISOString(), category: row.category,
    sourceCount: new Set(recent.filter(other => groupKey(other) === groupKey(row)
      || normalizedTitle(other.title) === normalizedTitle(row.title)).map(other => other.source_id)).size,
  }));
}

export async function loadRecentReading(now = new Date()): Promise<RecentReadingEntry[]> {
  const since = new Date(now.getTime() - RECENT_READING.days * DAY);
  const rows = await sql<ReadingCandidate[]>`
    SELECT p.article_id AS id, p.url, p.title, p.reason, p.summary, p.source_id, s.name AS source_name,
      p.published_at, p.category, p.score, p.story_id, p.fact_id,
      coalesce(length(a.body_text), 0) AS body_length
    FROM publications p JOIN sources s ON s.id = p.source_id JOIN articles a ON a.id = p.article_id
    WHERE ${selectedCondition(now)} AND p.published_at >= ${since} AND p.published_at <= ${now}
      AND p.score IS NOT NULL`;
  return chooseRecentReading(rows, now);
}
