/**
 * i18n.js — Lightweight bilingual (English / Chinese) module
 *
 * Usage:
 *   - Add `data-i18n="key"` to any element whose textContent should be translated.
 *   - Add `data-i18n-placeholder="key"` for <input> placeholder attributes.
 *   - Add `data-i18n-title="key"` for title attributes.
 *   - Add `data-i18n-aria-label="key"` for aria-label attributes.
 *   - Call `window.I18n.toggleLang()` to flip between 'en' and 'zh'.
 *   - Call `window.I18n.t(key)` to get a translation string imperatively.
 *
 * Language detection priority:
 *   1. localStorage item 'lang'  (manual user choice, remembered)
 *   2. navigator.language        (browser setting, zh-* → 'zh', else 'en')
 *   3. Fallback: 'en'
 */
(function (global) {
    'use strict';

    // ─── Translation dictionaries ────────────────────────────────────────────
    const translations = {
        en: {
            // Navigation
            'nav.brand':           'AI Actuarial Info Search',
            'nav.dashboard':       'Dashboard',
            'nav.database':        'Database',
            'nav.chat':            'Chat',
            'nav.tasks':           'Tasks',
            'nav.knowledge_bases': 'Knowledge Bases',
            'nav.settings':        'Settings',
            'nav.login':           'Login',
            'nav.logout':          'Logout',
            'nav.lang_toggle':     '中文',   // label shown when current lang is EN

            // Theme button
            'theme.toggle_title':  'Toggle dark mode',

            // Footer
            'footer.copyright':    '© 2024 AI Actuarial Info Search. All rights reserved.',

            // Confirm modal
            'modal.confirm_title': 'Confirm Action',
            'modal.cancel':        'Cancel',
            'modal.confirm_ok':    'Confirm',

            // Auth-required modal
            'modal.auth_title':    'Login Required',
            'modal.auth_message':  'You must log in to access this page.',
            'modal.auth_back':     'Back',
            'modal.auth_login':    'Login',

            // Index / Dashboard
            'index.welcome_title':    'Welcome to AI Actuarial Info Search',
            'index.welcome_subtitle': 'Discover, download, and catalog AI-related documents from actuarial organizations worldwide',
            'index.total_files':      'Total Files',
            'index.cataloged_files':  'Cataloged Files',
            'index.sources':          'Sources',
            'index.active_tasks':     'Active Tasks',
            'index.quick_actions':    'Quick Actions',
            'index.browse_db':        'Browse Database',
            'index.browse_db_desc':   'Search and manage collected files',
            'index.task_center':      'Task Center',
            'index.task_center_desc': 'Run collections and manage tasks',
            'index.kb':               'Knowledge Bases',
            'index.kb_desc':          'Manage RAG knowledge bases',
            'index.chat':             'Chat',
            'index.chat_desc':        'Ask questions with indexed knowledge',
            'index.recent_files':     'Recent Files',
            'index.loading':          'Loading...',
            'index.no_files':         'No files found',
            'index.load_error':       'Error loading files',

            // Table headers (shared)
            'table.title':  'Title',
            'table.source': 'Source',
            'table.date':   'Date',

            // Common
            'common.back':    'Back',
            'common.save':    'Save',
            'common.delete':  'Delete',
            'common.search':  'Search',
            'common.loading': 'Loading...',
            'common.error':   'An error occurred',
        },

        zh: {
            // Navigation
            'nav.brand':           'AI 精算信息搜索',
            'nav.dashboard':       '仪表板',
            'nav.database':        '数据库',
            'nav.chat':            '智能问答',
            'nav.tasks':           '任务中心',
            'nav.knowledge_bases': '知识库',
            'nav.settings':        '设置',
            'nav.login':           '登录',
            'nav.logout':          '退出',
            'nav.lang_toggle':     'EN',   // label shown when current lang is ZH

            // Theme button
            'theme.toggle_title':  '切换深色模式',

            // Footer
            'footer.copyright':    '© 2024 AI 精算信息搜索。保留所有权利。',

            // Confirm modal
            'modal.confirm_title': '确认操作',
            'modal.cancel':        '取消',
            'modal.confirm_ok':    '确认',

            // Auth-required modal
            'modal.auth_title':    '需要登录',
            'modal.auth_message':  '您必须登录才能访问此页面。',
            'modal.auth_back':     '返回',
            'modal.auth_login':    '登录',

            // Index / Dashboard
            'index.welcome_title':    '欢迎使用 AI 精算信息搜索',
            'index.welcome_subtitle': '发现、下载并整理全球精算组织的 AI 相关文档',
            'index.total_files':      '文件总数',
            'index.cataloged_files':  '已分类文件',
            'index.sources':          '来源数',
            'index.active_tasks':     '活跃任务',
            'index.quick_actions':    '快速操作',
            'index.browse_db':        '浏览数据库',
            'index.browse_db_desc':   '搜索和管理收集的文件',
            'index.task_center':      '任务中心',
            'index.task_center_desc': '运行收集任务和管理工作流',
            'index.kb':               '知识库',
            'index.kb_desc':          '管理 RAG 知识库',
            'index.chat':             '智能问答',
            'index.chat_desc':        '基于索引知识进行智能对话',
            'index.recent_files':     '最近文件',
            'index.loading':          '加载中…',
            'index.no_files':         '未找到文件',
            'index.load_error':       '加载文件时出错',

            // Table headers (shared)
            'table.title':  '标题',
            'table.source': '来源',
            'table.date':   '日期',

            // Common
            'common.back':    '返回',
            'common.save':    '保存',
            'common.delete':  '删除',
            'common.search':  '搜索',
            'common.loading': '加载中…',
            'common.error':   '发生错误',
        },
    };

    // ─── Internal state ──────────────────────────────────────────────────────
    const STORAGE_KEY = 'lang';
    let currentLang = 'en';

    // ─── Language detection ──────────────────────────────────────────────────
    /**
     * Resolve initial language:
     *   1. Stored user preference in localStorage
     *   2. Browser navigator.language  (zh-* → 'zh')
     *   3. Fallback 'en'
     */
    function detectLang() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'zh' || stored === 'en') return stored;

        const nav = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
        return nav.startsWith('zh') ? 'zh' : 'en';
    }

    // ─── Translation lookup ──────────────────────────────────────────────────
    /**
     * Get the translation for `key` in the current language.
     * Falls back to the English value, then to the key itself.
     * @param {string} key
     * @returns {string}
     */
    function t(key) {
        const dict = translations[currentLang] || translations.en;
        return dict[key] !== undefined ? dict[key] : (translations.en[key] !== undefined ? translations.en[key] : key);
    }

    // ─── DOM application ─────────────────────────────────────────────────────
    /**
     * Walk the document and apply translations to all elements
     * that carry a `data-i18n*` attribute.
     */
    function applyTranslations() {
        // textContent
        document.querySelectorAll('[data-i18n]').forEach(function (el) {
            const key = el.getAttribute('data-i18n');
            el.textContent = t(key);
        });

        // placeholder attribute
        document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
            const key = el.getAttribute('data-i18n-placeholder');
            el.setAttribute('placeholder', t(key));
        });

        // title attribute
        document.querySelectorAll('[data-i18n-title]').forEach(function (el) {
            const key = el.getAttribute('data-i18n-title');
            el.setAttribute('title', t(key));
        });

        // aria-label attribute
        document.querySelectorAll('[data-i18n-aria-label]').forEach(function (el) {
            const key = el.getAttribute('data-i18n-aria-label');
            el.setAttribute('aria-label', t(key));
        });

        // Update <html lang="…">
        document.documentElement.setAttribute('lang', currentLang === 'zh' ? 'zh-CN' : 'en');
    }

    // ─── Language switching ───────────────────────────────────────────────────
    /**
     * Switch to a specific language and persist the choice.
     * @param {'en'|'zh'} lang
     */
    function setLang(lang) {
        if (lang !== 'en' && lang !== 'zh') return;
        currentLang = lang;
        localStorage.setItem(STORAGE_KEY, lang);
        applyTranslations();
        // Notify other scripts that may listen
        try {
            document.dispatchEvent(new CustomEvent('langchange', { detail: { lang: lang } }));
        } catch (e) { /* IE11 guard */ }
    }

    /**
     * Toggle between 'en' and 'zh'.
     */
    function toggleLang() {
        setLang(currentLang === 'en' ? 'zh' : 'en');
    }

    /**
     * Return the currently active language code ('en' or 'zh').
     * @returns {'en'|'zh'}
     */
    function getCurrentLang() {
        return currentLang;
    }

    // ─── Initialisation ───────────────────────────────────────────────────────
    function init() {
        currentLang = detectLang();
        applyTranslations();
    }

    // Run as soon as the DOM is ready (may fire before or after DOMContentLoaded)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ─── Public API ───────────────────────────────────────────────────────────
    global.I18n = {
        t:              t,
        setLang:        setLang,
        toggleLang:     toggleLang,
        getCurrentLang: getCurrentLang,
        applyTranslations: applyTranslations,
    };

}(window));
