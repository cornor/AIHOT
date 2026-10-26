import { Link } from "react-router";
import type { RecentReadingEntry } from "@aihot/contracts/site";
import { CATEGORY_LABELS, isCategoryKey } from "@aihot/contracts/taxonomy";
import { IconArrowRight } from "../../components/icons";
import { monthDayTime } from "../../lib/format";

export function RecentReading({ entries }: { entries: RecentReadingEntry[] }) {
  if (!entries.length) return null;
  return (
    <section aria-labelledby="recent-reading" className="card mb-6 overflow-hidden px-4 py-4 lg:px-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <h2 id="recent-reading" className="text-[16px] font-bold text-ink">近期值得看</h2>
          <span className="text-[12px] text-ink-4">近 7 天精选</span>
        </div>
        <Link to="/hot" className="inline-flex items-center gap-1 text-[12px] text-ink-3 hover:text-accent">
          热点榜 <IconArrowRight size={13} />
        </Link>
      </div>
      <ol className="divide-y divide-line">
        {entries.map((entry, index) => (
          <li key={entry.id}>
            <Link to={`/items/${entry.id}`} className="group -mx-2 flex gap-3 rounded-tile px-2 py-3 transition-colors hover:bg-bg-sunk/70">
              <span className="num mt-0.5 w-5 shrink-0 text-center text-[14px] font-bold text-accent" aria-hidden="true">{index + 1}</span>
              <div className="min-w-0 flex-1">
                <h3 className="line-clamp-2 text-[16px] font-semibold leading-relaxed text-ink group-hover:text-accent">{entry.title}</h3>
                {entry.reason && <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-ink-3"><span className="text-accent">推荐理由：</span>{entry.reason}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-ink-4">
                  {entry.category && <span>{isCategoryKey(entry.category) ? CATEGORY_LABELS[entry.category] : entry.category}</span>}
                  <span>{entry.sourceName}</span>
                  <time dateTime={entry.publishedAt}>{monthDayTime(entry.publishedAt)}</time>
                  {entry.sourceCount > 1 && <span className="text-accent">{entry.sourceCount} 个来源关注</span>}
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
