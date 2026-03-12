"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import "katex/dist/katex.min.css";
import { Mermaid } from "../Mermaid";

interface ReportMarkdownProps {
  content: string;
  scrollContainerId?: string;
  className?: string;
}

export default function ReportMarkdown({
  content,
  scrollContainerId,
  className = "",
}: ReportMarkdownProps) {
  return (
    <article
      className={`prose prose-slate dark:prose-invert max-w-none prose-headings:text-slate-800 dark:prose-headings:text-slate-100 prose-p:text-slate-600 dark:prose-p:text-slate-300 prose-a:text-indigo-600 dark:prose-a:text-indigo-400 prose-img:rounded-xl prose-table:border-collapse prose-th:border prose-th:border-slate-300 dark:prose-th:border-slate-600 prose-th:bg-slate-50 dark:prose-th:bg-slate-700 prose-th:p-2 prose-td:border prose-td:border-slate-200 dark:prose-td:border-slate-600 prose-td:p-2 ${className}`}
    >
      <style>{`
        [id^="ref-"] { scroll-margin-top: 20px; }
      `}</style>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeRaw]}
        components={{
          h1: ({ node, ...props }) => (
            <h1
              className="text-3xl font-bold mb-6 pb-2 border-b border-slate-200 dark:border-slate-700"
              {...props}
            />
          ),
          h2: ({ node, ...props }) => (
            <h2
              className="text-2xl font-bold mt-8 mb-4 text-indigo-900 dark:text-indigo-300"
              {...props}
            />
          ),
          h3: ({ node, ...props }) => (
            <h3
              className="text-xl font-semibold mt-6 mb-3 text-slate-800 dark:text-slate-200"
              {...props}
            />
          ),
          p: ({ node, ...props }) => (
            <p
              className="leading-relaxed mb-4 text-slate-600 dark:text-slate-300"
              {...props}
            />
          ),
          li: ({ node, ...props }) => <li className="mb-2" {...props} />,
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-6">
              <table
                className="min-w-full border-collapse border border-slate-300 dark:border-slate-600 text-sm"
                {...props}
              />
            </div>
          ),
          thead: ({ node, ...props }) => (
            <thead className="bg-slate-50 dark:bg-slate-700" {...props} />
          ),
          th: ({ node, ...props }) => (
            <th
              className="border border-slate-300 dark:border-slate-600 px-4 py-2 text-left font-semibold text-slate-700 dark:text-slate-200"
              {...props}
            />
          ),
          td: ({ node, ...props }) => (
            <td
              className="border border-slate-200 dark:border-slate-600 px-4 py-2 text-slate-600 dark:text-slate-300"
              {...props}
            />
          ),
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="border-l-4 border-indigo-300 dark:border-indigo-600 pl-4 py-2 my-4 bg-indigo-50/50 dark:bg-indigo-900/30 text-slate-600 dark:text-slate-300 italic"
              {...props}
            />
          ),
          a: ({ node, href, ...props }) => {
            const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
              if (!scrollContainerId || !href?.startsWith("#")) return;
              e.preventDefault();
              const targetId = href.slice(1);
              const targetElement = document.getElementById(targetId);
              const scrollContainer = document.getElementById(scrollContainerId);
              if (targetElement && scrollContainer) {
                const containerRect = scrollContainer.getBoundingClientRect();
                const targetRect = targetElement.getBoundingClientRect();
                const offset =
                  targetRect.top - containerRect.top + scrollContainer.scrollTop - 20;
                scrollContainer.scrollTo({ top: offset, behavior: "smooth" });
              }
            };
            return (
              <a
                href={href}
                onClick={handleClick}
                className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 underline decoration-indigo-300 dark:decoration-indigo-600 hover:decoration-indigo-500 dark:hover:decoration-indigo-400"
                {...props}
              />
            );
          },
          code: ({ node, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || "");
            const language = match ? match[1] : "";
            const isInline = !match;

            if (language === "mermaid") {
              const chartCode = String(children).replace(/\n$/, "");
              return <Mermaid chart={chartCode} />;
            }

            return isInline ? (
              <code
                className="bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-200 px-1.5 py-0.5 rounded text-sm font-mono"
                {...props}
              >
                {children}
              </code>
            ) : (
              <code
                className={`${className} block bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm`}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ node, children, ...props }) => {
            const child = React.Children.toArray(children)[0] as React.ReactElement<{
              className?: string;
            }>;
            if (child?.props?.className?.includes("language-mermaid")) {
              return <>{children}</>;
            }
            return (
              <pre
                className="bg-slate-900 rounded-lg overflow-hidden my-4"
                {...props}
              >
                {children}
              </pre>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </article>
  );
}
