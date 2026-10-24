// Apply the user-requested lower T2 threshold to complete stored scores, without model calls.
// Preview by default; --apply appends rule analyses and republishes through the shared read model.
import { SELECTION } from '@aihot/industry/selection';
import { sql, closeDb } from '@aihot/backend/db';
import { publishArticleTx } from '@aihot/backend/publication/publish';

const apply = process.argv.includes('--apply');
const threshold = SELECTION.thresholds.T2!;
let eligible = 0;
let promoted = 0;
try {
  const rows = await sql<{ id: string }[]>`
    SELECT p.article_id AS id FROM publications p JOIN sources s ON s.id=p.source_id
    WHERE s.enabled AND s.tier='T2' AND s.participation_mode='editorial'
      AND p.eligible AND p.visibility='public' AND NOT p.selected ORDER BY p.article_id`;
  for (const row of rows) await sql.begin(async tx => {
    const [article] = await tx`SELECT revision FROM articles WHERE id=${row.id} FOR UPDATE`;
    const [an] = await tx`SELECT * FROM analyses WHERE article_id=${row.id} ORDER BY input_revision DESC,id DESC LIMIT 1`;
    const [override] = await tx`SELECT fields FROM editorial_overrides WHERE article_id=${row.id}`;
    const scores = an?.output?.scores;
    if (!an || an.input_revision !== article?.revision || an.relevance !== 'pass' || an.selected
      || an.output?.scoreRefused || typeof override?.fields?.selected === 'boolean'
      || !Array.isArray(scores) || scores.length !== 2
      || !scores.every(s => Number.isInteger(s) && s >= 0 && s <= 100)
      || scores[0] + scores[1] < threshold * 2) return;
    eligible++;
    if (!apply) return;
    // Preserve the original model judgement; the new record documents only the threshold change.
    const output = { ...an.output, threshold, thresholdChange: { previousAnalysisId: an.id, previousThreshold: an.output?.threshold } };
    await tx`
      INSERT INTO analyses (article_id,input_revision,origin,model,prompt_version,receipt_ids,relevance,
        category,tags,subjects,title_zh,summary_zh,reason_zh,score,selected,output)
      SELECT article_id,input_revision,'rule',model,prompt_version,receipt_ids,relevance,
        category,tags,subjects,title_zh,summary_zh,reason_zh,score,true,${tx.json(output)}
      FROM analyses WHERE id=${an.id}`;
    // These are already published articles: do not enqueue a burst of content notifications.
    const result = await publishArticleTx(tx, row.id, { releasedAt: new Date() });
    if (result?.selected) promoted++;
  });
  console.log(JSON.stringify({ apply, threshold, eligible, promoted }));
} finally {
  await closeDb();
}
