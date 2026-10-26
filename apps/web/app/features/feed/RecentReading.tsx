import { Link } from "react-router";
import type { RecentReadingEntry } from "@aihot/contracts/site";
import { markRead } from "../../lib/local-state";

export function RecentReading({ entries }: { entries: RecentReadingEntry[] }) {
  if (!entries.length) return null;
  return (
    <section aria-labelledby="recent-reading" className="card mb-6 overflow-hidden px-4 py-4 lg:px-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <h2 id="recent-reading" className="text-[16px] font-bold text-ink">近期值得看</h2>
          <span className="text-[12px] text-ink-4">近 7 天精选</span>
        </div>
      </div>
      <ol className="divide-y divide-line">
        {entries.map((entry, index) => (
          <li key={entry.id}>
            <div className="-mx-2 flex gap-3 rounded-tile px-2 py-3 transition-colors hover:bg-bg-sunk/70">
              <span className="num mt-0.5 w-5 shrink-0 text-center text-[14px] font-bold text-accent" aria-hidden="true">{index + 1}</span>
              <div className="min-w-0 flex-1">
                <Link to={`/items/${entry.id}`} className="group block">
                  <h3 className="line-clamp-2 text-[16px] font-semibold leading-relaxed text-ink group-hover:text-accent">{entry.title}</h3>
                  {entry.reason && <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-ink-3"><span className="text-accent">推荐理由：</span>{entry.reason}</p>}
                </Link>
                <div className="mt-2 flex justify-end">
                  {entry.originalUrl && /^https?:\/\//i.test(entry.originalUrl) && (
                    <a href={entry.originalUrl} target="_blank" rel="noopener noreferrer" onClick={() => { void markRead(entry.id); }}
                      className="ml-auto inline-flex min-h-9 shrink-0 items-center gap-1 rounded-control px-2 text-[13px] font-medium text-accent hover:bg-accent-soft hover:underline focus-visible:outline-2 focus-visible:outline-accent">
                      阅读原文 <span aria-hidden="true">↗</span>
                    </a>
                  )}
                </div>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
