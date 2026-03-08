"use client";

import { useEffect, useRef, useState } from "react";
import { Brain, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import MarkdownRenderer from "@/components/common/MarkdownRenderer";

interface ThinkingBlockProps {
  content: string;
  isStreaming?: boolean;
  hasMainContent?: boolean;
  defaultExpanded?: boolean;
  className?: string;
}

export default function ThinkingBlock({
  content,
  isStreaming = false,
  hasMainContent = false,
  defaultExpanded = false,
  className = "",
}: ThinkingBlockProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded || isStreaming);
  const prevMainContentRef = useRef(hasMainContent);

  useEffect(() => {
    if (isStreaming && !hasMainContent) {
      setExpanded(true);
    }

    if (!prevMainContentRef.current && hasMainContent) {
      setExpanded(false);
    }

    prevMainContentRef.current = hasMainContent;
  }, [isStreaming, hasMainContent]);

  if (!content?.trim()) {
    return null;
  }

  return (
    <div
      className={`rounded-xl border border-indigo-200/70 dark:border-indigo-700/50 bg-indigo-50/60 dark:bg-indigo-900/20 ${className}`}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-indigo-100/60 dark:hover:bg-indigo-900/30 transition-colors rounded-xl"
      >
        <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
          <Brain className="w-4 h-4" />
          <span className="text-xs font-semibold tracking-wide uppercase">
            {t("Thinking Process")}
          </span>
          {isStreaming && (
            <span className="inline-flex items-center gap-1 text-[11px] text-indigo-600 dark:text-indigo-300">
              <Loader2 className="w-3 h-3 animate-spin" />
              {t("Thinking...")}
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-indigo-600 dark:text-indigo-300" />
        ) : (
          <ChevronRight className="w-4 h-4 text-indigo-600 dark:text-indigo-300" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3">
          <MarkdownRenderer
            content={content}
            variant="compact"
            className="text-slate-700 dark:text-slate-200"
          />
        </div>
      )}
    </div>
  );
}
