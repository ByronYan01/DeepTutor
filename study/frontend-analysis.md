# DeepTutor 前端架构分析

## 概述

DeepTutor 前端基于 **Next.js 16 + React 19** 构建，采用现代化的 App Router 架构，支持服务端渲染和客户端交互。

---

## 1. 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 16.1.1 | React 框架 |
| React | 19.0.0 | UI 库 |
| TypeScript | 5.x | 类型安全 |
| TailwindCSS | 3.4.17 | 样式框架 |
| Lucide React | 0.562.0 | 图标库 |
| Framer Motion | 12.24.0 | 动画库 |
| i18next | 25.8.0 | 国际化 |

---

## 2. 项目结构

```
web/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # 根布局
│   ├── page.tsx           # 首页 (23KB)
│   ├── globals.css        # 全局样式
│   ├── solver/            # 问题求解页
│   ├── guide/             # 引导学习页 (13 items)
│   ├── research/          # 深度研究页
│   ├── question/          # 题目生成页
│   ├── knowledge/         # 知识库管理页
│   ├── co_writer/         # 协作写作页
│   ├── ideagen/           # 创意生成页
│   ├── notebook/          # 笔记本页
│   ├── history/           # 历史记录页
│   └── settings/          # 设置页 (7 items)
├── components/            # 组件目录
│   ├── Sidebar.tsx        # 侧边栏导航 (19KB)
│   ├── CoWriterEditor.tsx # 协作编辑器 (82KB)
│   ├── CoMarkerEditor.tsx # 标注编辑器 (77KB)
│   ├── SystemStatus.tsx   # 系统状态 (15KB)
│   ├── common/            # 通用组件
│   ├── knowledge/         # 知识库组件
│   ├── question/          # 题目相关组件
│   ├── research/          # 研究相关组件
│   └── ui/                # UI 基础组件
├── context/               # 状态管理
│   ├── GlobalContext.tsx  # 全局上下文
│   ├── CompositeProvider.tsx # 复合 Provider
│   ├── solver/            # Solver 状态
│   ├── question/          # Question 状态
│   ├── research/          # Research 状态
│   ├── chat/              # Chat 状态
│   ├── ideagen/           # IdeaGen 状态
│   └── settings/          # Settings 状态
├── i18n/                  # 国际化配置
├── public/                # 静态资源
└── scripts/               # 构建脚本
```

---

## 3. 页面路由

### 3.1 App Router 结构

| 路径 | 页面 | 功能 |
|------|------|------|
| `/` | page.tsx | 首页 - 问题求解入口 |
| `/solver` | solver/page.tsx | 问题求解详情 |
| `/guide` | guide/page.tsx | 引导学习 |
| `/research` | research/page.tsx | 深度研究 |
| `/question` | question/page.tsx | 题目生成 |
| `/knowledge` | knowledge/page.tsx | 知识库管理 |
| `/co_writer` | co_writer/page.tsx | 协作写作 |
| `/ideagen` | ideagen/page.tsx | 创意生成 |
| `/notebook` | notebook/page.tsx | 笔记本 |
| `/history` | history/page.tsx | 历史记录 |
| `/settings` | settings/page.tsx | 系统设置 |

### 3.2 布局系统

```tsx
// app/layout.tsx
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <GlobalProvider>
          <I18nClientBridge>
            <LayoutWrapper>
              <div className="flex h-screen">
                <Sidebar />
                <main className="flex-1">{children}</main>
              </div>
            </LayoutWrapper>
          </I18nClientBridge>
        </GlobalProvider>
      </body>
    </html>
  );
}
```

---

## 4. 组件架构

### 4.1 核心组件

| 组件 | 大小 | 功能 |
|------|------|------|
| `Sidebar.tsx` | 19KB | 侧边导航栏，支持折叠 |
| `CoWriterEditor.tsx` | 82KB | Markdown 协作编辑器 |
| `CoMarkerEditor.tsx` | 77KB | 文本标注编辑器 |
| `SystemStatus.tsx` | 15KB | 系统健康状态显示 |
| `ActivityDetail.tsx` | 12KB | 活动详情展示 |
| `SolverSessionDetail.tsx` | 12KB | 求解会话详情 |
| `ChatSessionDetail.tsx` | 11KB | 聊天会话详情 |
| `Mermaid.tsx` | 2.5KB | Mermaid 图表渲染 |

### 4.2 组件分类

```
components/
├── common/           # 通用组件
│   ├── Button
│   ├── Modal
│   └── Loading
├── knowledge/        # 知识库相关
│   └── KnowledgeCard
├── question/         # 题目相关
│   ├── QuestionCard
│   └── QuestionList
├── research/         # 研究相关
│   ├── ResearchProgress
│   └── ReportViewer
└── ui/               # UI 基础
    ├── Input
    ├── Select
    └── Tabs
```

---

## 5. 状态管理

### 5.1 Context 架构

```tsx
// context/index.ts
export { CompositeProvider } from "./CompositeProvider";
export { useSolver, SolverProvider } from "./solver";
export { useQuestion, QuestionProvider } from "./question";
export { useResearch, ResearchProvider } from "./research";
export { useChat, ChatProvider } from "./chat";
export { useUISettings, UISettingsProvider } from "./settings";
export { useSidebar, SidebarProvider } from "./settings";
export { useIdeaGen, IdeaGenProvider } from "./ideagen";
export { useGlobal, GlobalProvider } from "./GlobalContext";
```

### 5.2 Provider 嵌套

```tsx
// CompositeProvider.tsx
export function CompositeProvider({ children }) {
  return (
    <SolverProvider>
      <QuestionProvider>
        <ResearchProvider>
          <ChatProvider>
            <IdeaGenProvider>
              <UISettingsProvider>
                <SidebarProvider>
                  {children}
                </SidebarProvider>
              </UISettingsProvider>
            </IdeaGenProvider>
          </ChatProvider>
        </ResearchProvider>
      </QuestionProvider>
    </SolverProvider>
  );
}
```

### 5.3 主要 Hooks

| Hook | 用途 |
|------|------|
| `useSolver()` | 问题求解状态 |
| `useQuestion()` | 题目生成状态 |
| `useResearch()` | 深度研究状态 |
| `useChat()` | 聊天会话状态 |
| `useIdeaGen()` | 创意生成状态 |
| `useUISettings()` | UI 设置 |
| `useSidebar()` | 侧边栏状态 |
| `useGlobal()` | 全局状态 (兼容) |

---

## 6. 样式系统

### 6.1 TailwindCSS 配置

```javascript
// tailwind.config.js
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",  // 暗黑模式
  theme: {
    extend: {
      colors: {
        // 自定义颜色
      }
    }
  }
}
```

### 6.2 全局样式

```css
/* app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* 自定义组件样式 */
/* Markdown 渲染样式 */
/* 代码高亮样式 */
```

### 6.3 暗黑模式

```tsx
// components/ThemeScript.tsx
// 在 head 中注入主题脚本，避免闪烁
export default function ThemeScript() {
  return (
    <script dangerouslySetInnerHTML={{
      __html: `
        if (localStorage.theme === 'dark') {
          document.documentElement.classList.add('dark')
        }
      `
    }} />
  );
}
```

---

## 7. 国际化 (i18n)

### 7.1 配置

```tsx
// i18n/I18nClientBridge.tsx
import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

i18next.use(initReactI18next).init({
  lng: 'en',
  fallbackLng: 'en',
  resources: {
    en: { translation: {...} },
    zh: { translation: {...} }
  }
});
```

### 7.2 使用

```tsx
import { useTranslation } from 'react-i18next';

function MyComponent() {
  const { t } = useTranslation();
  return <h1>{t('welcome')}</h1>;
}
```

---

## 8. API 通信

### 8.1 API 基础配置

```tsx
// 从环境变量获取 API 地址
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8001';

async function fetchAPI(endpoint: string, options?: RequestInit) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  return response.json();
}
```

### 8.2 WebSocket 连接

```tsx
// Solver 页面 WebSocket 连接
const ws = new WebSocket(`ws://${API_HOST}/api/v1/ws/solve/${sessionId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // 处理流式响应
  handleStreamEvent(data);
};
```

---

## 9. 关键功能

### 9.1 Markdown 渲染

```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

<ReactMarkdown
  remarkPlugins={[remarkGfm, remarkMath]}
  rehypePlugins={[rehypeKatex]}
>
  {content}
</ReactMarkdown>
```

### 9.2 图表渲染

```tsx
// components/Mermaid.tsx
import mermaid from 'mermaid';

mermaid.initialize({ startOnLoad: true, theme: 'default' });

export function Mermaid({ chart }) {
  useEffect(() => {
    mermaid.contentLoaded();
  }, [chart]);
  
  return <div className="mermaid">{chart}</div>;
}
```

### 9.3 PDF 导出

```tsx
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';

async function exportToPDF(element: HTMLElement) {
  const canvas = await html2canvas(element);
  const pdf = new jsPDF();
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0);
  pdf.save('document.pdf');
}
```

---

## 10. 依赖清单

### 10.1 生产依赖

| 包名 | 用途 |
|------|------|
| `next` | React 框架 |
| `react` | UI 库 |
| `react-dom` | DOM 渲染 |
| `react-markdown` | Markdown 渲染 |
| `react-i18next` | 国际化 |
| `framer-motion` | 动画 |
| `lucide-react` | 图标 |
| `mermaid` | 流程图 |
| `cytoscape` | 网络图 |
| `html2canvas` | 截图 |
| `jspdf` | PDF 生成 |
| `tailwind-merge` | 样式合并 |
| `clsx` | 类名工具 |

### 10.2 开发依赖

| 包名 | 用途 |
|------|------|
| `typescript` | 类型检查 |
| `tailwindcss` | CSS 框架 |
| `eslint` | 代码检查 |
| `@playwright/test` | E2E 测试 |

---

## 总结

DeepTutor 前端采用 **Next.js App Router + React Context** 的架构设计:

1. **路由层** - App Router 文件系统路由，12个功能页面
2. **组件层** - 模块化组件设计，大型编辑器组件
3. **状态层** - 多 Provider 分离关注点
4. **样式层** - TailwindCSS + 暗黑模式支持
5. **国际化** - i18next 多语言支持

这种架构实现了**模块化开发**和**渐进式迁移**，便于团队协作和功能扩展。
