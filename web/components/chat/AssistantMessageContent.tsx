"use client";

import { Loader2, BookOpen, Globe, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import MarkdownRenderer from "@/components/common/MarkdownRenderer";
import type { HomeChatMessage } from "@/types/chat";
import ThinkingBlock from "./ThinkingBlock";

interface AssistantMessageContentProps {
  message: HomeChatMessage;
  showSources?: boolean;
  className?: string;
}

export default function AssistantMessageContent({
  message,
  showSources = true,
  className = "",
}: AssistantMessageContentProps) {
  const { t } = useTranslation();

  return (
    <div className={`flex-1 space-y-3 ${className}`}>
      <div className="bg-white dark:bg-slate-800 px-5 py-4 rounded-2xl rounded-tl-none border border-slate-200 dark:border-slate-700 shadow-sm space-y-3">
        {message.thinking && (
          <ThinkingBlock
            content={message.thinking}
            isStreaming={!!message.isStreaming}
            hasMainContent={!!message.content?.trim()}
            defaultExpanded={!!message.isStreaming && !message.content?.trim()}
          />
        )}

        {message.content && (
          <MarkdownRenderer content={message.content} variant="default" />
        )}

        {message.isStreaming && (
          <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{t("Generating response...")}</span>
          </div>
        )}
      </div>

      {showSources &&
        message.sources &&
        (message.sources.rag?.length ?? 0) + (message.sources.web?.length ?? 0) >
          0 && (
          <div className="flex flex-wrap gap-2">
            {message.sources.rag?.map((source, i) => (
              <div
                key={`rag-${i}`}
                className="flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg text-xs"
              >
                <BookOpen className="w-3 h-3" />
                <span>{source.kb_name}</span>
              </div>
            ))}
            {message.sources.web?.slice(0, 3).map((source, i) => (
              <a
                key={`web-${i}`}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-lg text-xs hover:bg-emerald-100 dark:hover:bg-emerald-900/50 transition-colors"
              >
                <Globe className="w-3 h-3" />
                <span className="max-w-[150px] truncate">{source.title || source.url}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            ))}
          </div>
        )}
    </div>
  );
}
