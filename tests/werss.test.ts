import './setup.ts';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWerssRss, werssMaterials } from '../scripts/sync-werss.ts';
const item = { title: '游戏研发案例', link: 'https://mp.weixin.qq.com/s/article-id', updated: '2026-10-08T10:00:00+08:00', description: '摘要', content: '<p>实际正文</p><script>alert(1)</script>' };
test('WeRSS XML ingestion preserves source dates and decodes encoded article bodies', () => {
  const xml = '<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>游戏研发案例</title><link>https://mp.weixin.qq.com/s/article-id</link><pubDate>Thu, 08 Oct 2026 10:00:00 +0800</pubDate><description>摘要</description><content:encoded>&lt;p&gt;实际正文&lt;/p&gt;</content:encoded></item></channel></rss>';
  const [article] = werssMaterials(parseWerssRss(xml), 'werss-games');
  assert.equal(article!.bodyText, '实际正文');
  assert.equal(article!.publishedAt!.toISOString(), '2026-10-08T02:00:00.000Z');
  assert.deepEqual(werssMaterials(parseWerssRss('<rss><channel><title>空源</title></channel></rss>'), 'werss-games'), []);
  assert.throws(() => parseWerssRss('<html>Login required</html>'));
  assert.throws(() => parseWerssRss('<!DOCTYPE rss><rss><channel/></rss>'));
});
test('WeRSS preserves original URLs, source times and cleaned body without executing source markup', () => {
  const [result] = werssMaterials({ items: [item, item] }, 'werss-games');
  assert.equal(werssMaterials({ items: [item, item] }, 'werss-games').length, 1);
  assert.equal(result!.url, item.link);
  assert.equal(result!.publishedAt!.toISOString(), '2026-10-08T02:00:00.000Z');
  assert.equal(result!.bodyText, '实际正文');
  assert.equal(result!.bodyStatus, 'ok');
});
test('WeRSS rejects local reader links, non-WeChat URLs and missing dates', () => {
  const links = ['http://127.0.0.1:8001/views/article/1', 'https://example.com/s/a', 'https://mp.weixin.qq.com.evil.com/s/a', 'https://user:pass@mp.weixin.qq.com/s/a', 'https://mp.weixin.qq.com/cgi-bin/home'];
  assert.equal(werssMaterials({ items: links.map(link => ({ ...item, link })) }, 'werss-games').length, 0);
  assert.equal(werssMaterials({ items: [{ ...item, updated: 'invalid' }] }, 'werss-games').length, 0);
});
test('WeRSS does not mistake a summary for a complete article body', () => {
  const [result] = werssMaterials({ items: [{ ...item, content: '' }] }, 'werss-games');
  assert.equal(result!.bodyStatus, 'none');
  assert.equal(result!.bodyText, null);
  assert.equal(result!.excerpt, '摘要');
  assert.throws(() => werssMaterials({ error: 'login expired' }, 'werss-games'));
});
