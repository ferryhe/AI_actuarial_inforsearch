import { useState, useCallback, useEffect } from "react";

const translations: Record<string, Record<string, string>> = {
  en: {
    "nav.brand": "AI Actuarial Info Search",
    "nav.dashboard": "Dashboard",
    "nav.database": "Database",
    "nav.chat": "Chat",
    "nav.tasks": "Tasks",
    "nav.knowledge": "Knowledge Bases",
    "nav.settings": "Settings",
    "dashboard.welcome": "Welcome to AI Actuarial Info Search",
    "dashboard.subtitle": "Discover, download, and catalog AI-related documents from actuarial organizations worldwide",
    "dashboard.total_files": "Total Files",
    "dashboard.cataloged": "Cataloged",
    "dashboard.sources": "Sources",
    "dashboard.active_tasks": "Active Tasks",
    "dashboard.quick_actions": "Quick Actions",
    "dashboard.browse_db": "Browse Database",
    "dashboard.browse_db_desc": "Search and manage collected files",
    "dashboard.task_center": "Task Center",
    "dashboard.task_center_desc": "Run collections and manage tasks",
    "dashboard.knowledge_bases": "Knowledge Bases",
    "dashboard.knowledge_bases_desc": "Manage RAG knowledge bases",
    "dashboard.chat": "AI Chat",
    "dashboard.chat_desc": "Ask questions with indexed knowledge",
    "dashboard.recent_files": "Recent Files",
    "dashboard.no_files": "No files collected yet",
    "dashboard.no_files_desc": "Start by crawling actuarial sites or importing files",
    "table.title": "Title",
    "table.source": "Source",
    "table.type": "Type",
    "table.date": "Date",
    "theme.toggle": "Toggle dark mode",
    "lang.toggle": "中文",
  },
  zh: {
    "nav.brand": "AI精算信息搜索",
    "nav.dashboard": "仪表盘",
    "nav.database": "数据库",
    "nav.chat": "聊天",
    "nav.tasks": "任务",
    "nav.knowledge": "知识库",
    "nav.settings": "设置",
    "dashboard.welcome": "欢迎使用 AI 精算信息搜索",
    "dashboard.subtitle": "发现、下载和编目全球精算组织的 AI 相关文档",
    "dashboard.total_files": "总文件数",
    "dashboard.cataloged": "已编目",
    "dashboard.sources": "来源",
    "dashboard.active_tasks": "活动任务",
    "dashboard.quick_actions": "快捷操作",
    "dashboard.browse_db": "浏览数据库",
    "dashboard.browse_db_desc": "搜索和管理已收集的文件",
    "dashboard.task_center": "任务中心",
    "dashboard.task_center_desc": "运行采集和管理任务",
    "dashboard.knowledge_bases": "知识库",
    "dashboard.knowledge_bases_desc": "管理 RAG 知识库",
    "dashboard.chat": "AI 聊天",
    "dashboard.chat_desc": "通过索引知识提问",
    "dashboard.recent_files": "最近文件",
    "dashboard.no_files": "暂无已采集的文件",
    "dashboard.no_files_desc": "开始爬取精算网站或导入文件",
    "table.title": "标题",
    "table.source": "来源",
    "table.type": "类型",
    "table.date": "日期",
    "theme.toggle": "切换深色模式",
    "lang.toggle": "EN",
  },
};

function detectLang(): string {
  const saved = localStorage.getItem("lang");
  if (saved) return saved;
  return navigator.language.startsWith("zh") ? "zh" : "en";
}

export function useI18n() {
  const [lang, setLang] = useState(detectLang);

  useEffect(() => {
    localStorage.setItem("lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);

  const t = useCallback(
    (key: string) => translations[lang]?.[key] || translations.en[key] || key,
    [lang]
  );

  const toggleLang = useCallback(() => {
    setLang((prev) => (prev === "en" ? "zh" : "en"));
  }, []);

  return { lang, t, toggleLang };
}
