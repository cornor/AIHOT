// One report in a feed. Desktop (≥ 961px): a white card beside the time rail. Mobile: a compact row
// with a divider, the reason in a grey box. One markup, two presentations, as on the original site.
import { memo } from "react";
import { Link } from "react-router";
import { IntentLink } from "../../components/ui/IntentLink";
import type { GroupInfo, FeedItemSummary, TimelineFilters } from "@aihot/contracts/site";
import { CATEGORY_LABELS } from "@aihot/contracts/taxonomy";
import { SelectedBadge } from "../../components/ui/Badge";
import { ScoreLabel } from "../../components/ui/Score";
import { MediaThumbs, SourceLine, StarButton } from "./parts";
import { GroupDevelopments, GroupSources, LatestDevelopment } from "./ReadingGroup";
import { QuotedLine } from "../item/QuotedPost";

export interface FeedItemProps {
  item: FeedItemSummary;
  group?: GroupInfo | null;
  filters?: TimelineFilters;
  read?: boolean;
  onOpen?: (id: string) => void;
  /** Show category and tags under the text (全部动态, topics, search). */
  showTags?: boolean;
}

export const FeedItem = memo(function FeedItem({ item, group, filters, read = false, onOpen, showTags = false }: FeedItemProps) {
  const isX = item.channel === "x" && !!item.x;
  const open = () => onOpen?.(item.id);
  const showSources = !!group && (group.additionalSourceCount > 0 || (group.developmentCount <= 1 && group.reportCount > 1));
  const showDevelopments = !!group?.story && group.developmentCount > 1;
  const tags = showTags ? [...new Set(item.tags)].filter(t => t !== (item.category ? CATEGORY_LABELS[item.category] : null)).slice(0, 3) : [];

  return (
    <article className="relative min-w-0 lg:card lg:card-hover lg:px-6 lg:py-5" data-item-id={item.id}>
      <header className="flex min-h-[18px] items-center gap-2 text-[12.5px] leading-[18px] text-ink-4">
        <SourceLine item={item} className="text-ink-4" />
        {read && <span className="text-[11px]">已读</span>}
        {item.selected && (
          <span className="hidden lg:inline-flex">
            <SelectedBadge />
          </span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-1.5 pl-2">
          <span className="hidden lg:inline-flex">
            <ScoreLabel score={item.score} />
          </span>
          <span className="lg:hidden">
            <ScoreLabel score={item.score} compact />
          </span>
          <span className="-my-1 hidden lg:inline-flex">
            <StarButton item={item} />
          </span>
        </span>
      </header>

      {isX ? (
        <p className={`mt-2 whitespace-pre-line text-[15px] leading-[1.75] line-clamp-5 lg:line-clamp-4 ${read ? "text-ink-4" : "text-ink"}`}>
          <IntentLink to={`/items/${item.id}`} onClick={open} className="after:absolute after:inset-0 after:content-['']">
            {item.summary ?? item.title}
          </IntentLink>
        </p>
      ) : (
        <>
          <h3 className="mt-2.5 line-clamp-3 text-[19px] font-bold leading-[1.5] text-ink lg:text-[21px]">
            <IntentLink to={`/items/${item.id}`} onClick={open} className="after:absolute after:inset-0 after:content-['']">
              {item.title}
            </IntentLink>
          </h3>
          {item.summary && <p className="mt-3 line-clamp-3 text-[14px] leading-[1.85] text-ink-3">{item.summary}</p>}
        </>
      )}

      {isX && item.x!.media.length > 0 && <MediaThumbs media={item.x!.media} className="mt-2.5" />}
      {isX && item.x!.quoted?.text && <QuotedLine quoted={item.x!.quoted} />}

      {(tags.length > 0 || (showTags && item.category)) && (
        <div className="relative z-10 mt-3 flex flex-wrap gap-x-2.5 gap-y-1 text-[12px] text-ink-4">
          {showTags && item.category && (
            <Link to={`/all?category=${item.category}`} className="hover:text-accent">
              {CATEGORY_LABELS[item.category]}
            </Link>
          )}
          {tags.map((t) => (
            <Link key={t} to={`/all?tag=${encodeURIComponent(t)}`} className="hover:text-accent">
              #{t}
            </Link>
          ))}
        </div>
      )}

      {group && <LatestDevelopment group={group} />}
      {(showSources || showDevelopments) && (
        <div className="mt-2 flex flex-wrap items-start gap-x-4 gap-y-1">
          {showSources && <GroupSources group={group!} filters={filters} parentId={item.id} />}
          {showDevelopments && <GroupDevelopments group={{ ...group!, story: group!.story! }} filters={filters} parentId={item.id} />}
        </div>
      )}

      {item.reason && (
        <div className="mt-2.5 rounded-control bg-bg-sunk px-3 py-2 dark:bg-bg-muted/60 lg:mt-3 lg:rounded-none lg:border-t lg:border-line-soft lg:bg-transparent lg:px-0 lg:pb-0 lg:pt-3 lg:dark:bg-transparent">
          <p className="line-clamp-2 text-[13px] leading-[1.65] text-ink-3 lg:line-clamp-none lg:leading-[1.75] lg:text-note">参考价值：{item.reason}</p>
        </div>
      )}
      {item.originalUrl && /^https?:\/\//i.test(item.originalUrl) && (
        <div className="mt-3 flex justify-end">
          <a href={item.originalUrl} target="_blank" rel="noopener noreferrer" onClick={open}
            className="relative z-10 inline-flex min-h-9 items-center gap-1 rounded-control px-2 text-[13px] font-medium text-accent hover:bg-accent-soft hover:underline focus-visible:outline-2 focus-visible:outline-accent">
            阅读原文 <span aria-hidden="true">↗</span>
          </a>
        </div>
      )}
    </article>
  );
});
