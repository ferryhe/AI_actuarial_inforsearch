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
            'common.cancel':  'Cancel',
            'common.ok':      'OK',
            'common.confirm': 'Confirm',
            'common.edit':    'Edit',
            'common.reset':   'Reset',
            'common.refresh': 'Refresh',
            'common.create':  'Create',
            'common.close':   'Close',
            'common.dismiss': 'Dismiss',
            'common.actions': 'Actions',
            'common.name':    'Name',
            'common.mode':    'Mode',
            'common.status':  'Status',
            'common.updated': 'Updated',
            'common.prev':    'Previous',
            'common.next':    'Next',
            'common.files':   'Files',
            'common.error_loading': 'Error loading data',
            'common.no_data': 'No data found',

            // Error page
            'error.heading':          'Error',
            'error.msg_default':      'An error occurred',
            'error.return_dashboard': 'Return to Dashboard',

            // Login page
            'login.page_title': 'Token Login',
            'login.subtitle':   'Paste your API token to access the web UI.',
            'login.api_token':  'API Token',
            'login.show':       'Show',
            'login.hide':       'Hide',
            'login.paste':      'Paste',
            'login.submit':     'Login',
            'login.home':       'Home',
            'login.return_to':  'After login you will return to:',

            // Database page
            'db.title':           'Database Management',
            'db.subtitle':        'Search and manage collected files',
            'db.search_ph':       'Search by title, filename, or site...',
            'db.search':          'Search',
            'db.all_sources':     'All Sources',
            'db.all_categories':  'All Categories',
            'db.uncategorized':   'Uncategorized',
            'db.include_deleted': 'Include deleted',
            'db.reset':           'Reset',
            'db.files_heading':   'Files',
            'db.sort_new':        'Date (Newest First)',
            'db.sort_old':        'Date (Oldest First)',
            'db.sort_title':      'Title (A-Z)',
            'db.sort_source':     'Source Site (A-Z)',
            'db.sort_size':       'Size (Largest First)',
            'db.loading':         'Loading files...',
            'db.no_files':        'No files found',
            'db.error_loading':   'Error loading files',
            'db.col_title':       'Title / Summary',
            'db.col_source':      'Source',
            'db.col_category':    'Category',
            'db.col_markdown':    'Markdown',
            'db.col_size':        'Size',
            'db.col_last_seen':   'Last Seen',
            'db.col_actions':     'Actions',
            'db.col_num':         '#',
            'db.preview':         'Preview',
            'db.md_available':    'Markdown available',
            'db.no_markdown':     'No markdown',
            'db.common_term':     'Common search term',
            'db.n_files':         'files',
            'db.page_of':         'Page {0} of {1}',

            // File Preview page
            'fp.title':           'File Preview',
            'fp.back':            'Back to Database',
            'fp.original':        'Original File',
            'fp.loading_orig':    'Loading original file...',
            'fp.chunks':          'Chunks',
            'fp.loading_chunks':  'Loading chunks...',
            'fp.error_no_file':   'Error: No file specified',
            'fp.no_url':          'No file URL provided',

            // Collection (URL) page
            'col_url.title':        'URL Collection',
            'col_url.subtitle':     'Download files from specific URLs',
            'col_url.urls_label':   'URLs (one per line):',
            'col_url.name_label':   'Collection Name:',
            'col_url.check_dup':    'Check for duplicates in database',
            'col_url.start':        'Start Collection',
            'col_url.cancel':       'Cancel',
            'col_url.progress':     'Collection Progress',
            'col_url.alert_no_url': 'Please enter at least one URL',
            'col_url.alert_found':  'Found:',
            'col_url.alert_dl':     'Downloaded:',
            'col_url.completed':    'Collection completed!',

            // Collection (File) page
            'col_file.title':        'File Import',
            'col_file.subtitle':     'Import files from local filesystem',
            'col_file.dir_label':    'Directory Path:',
            'col_file.browse':       'Browse...',
            'col_file.dir_help':     'Select a folder from your computer to import files from.',
            'col_file.ext_label':    'File Extensions (comma separated, empty for all):',
            'col_file.name_label':   'Collection Name:',
            'col_file.recursive':    'Recursive Scan (include subdirectories)',
            'col_file.start':        'Start Import',
            'col_file.back':         'Back',
            'col_file.importing':    'Importing Files...',
            'col_file.scanning':     'Scanning directory...',
            'col_file.found':        'Files Found:',
            'col_file.cataloged':    'Successfully Cataloged:',
            'col_file.skipped':      'Duplicates Skipped:',
            'col_file.failed':       'Failures:',
            'col_file.ok':           'OK',
            'col_file.completed':    'Import Completed',
            'col_file.done_ok':      'Files processed successfully.',
            'col_file.done_warn':    'Import finished with errors.',
            'col_file.alert_no_dir': 'Please enter a directory path',

            // RAG Management page
            'rag.title':            'Knowledge Bases',
            'rag.subtitle':         'Manage category-based and manual RAG knowledge bases.',
            'rag.refresh':          'Refresh',
            'rag.chunk_profiles':   'Chunk Profiles',
            'rag.create_kb':        'Create KB',
            'rag.categories_no_kb': 'categories do not have a knowledge base yet.',
            'rag.create_kbs':       'Create KBs',
            'rag.dismiss':          'Dismiss',
            'rag.search_ph':        'Search by name, description, or ID',
            'rag.all_modes':        'All Modes',
            'rag.mode_category':    'Category',
            'rag.mode_manual':      'Manual',
            'rag.col_name':         'Name',
            'rag.col_mode':         'Mode',
            'rag.col_files':        'Files',
            'rag.col_chunks':       'Chunks',
            'rag.col_updated':      'Updated',
            'rag.loading_kbs':      'Loading knowledge bases...',

            // RAG Detail page
            'rag_d.back':             'Back to Knowledge Bases',
            'rag_d.title':            'Knowledge Base',
            'rag_d.refresh':          'Refresh',
            'rag_d.edit':             'Edit',
            'rag_d.export':           'Export File List',
            'rag_d.reindex':          'Reindex',
            'rag_d.delete':           'Delete',
            'rag_d.metadata':         'Metadata',
            'rag_d.kb_id':            'KB ID:',
            'rag_d.mode':             'Mode:',
            'rag_d.embedding':        'Embedding:',
            'rag_d.chunk_profile':    'Chunk Profile:',
            'rag_d.chunk_size':       'Chunk Size:',
            'rag_d.chunk_overlap':    'Chunk Overlap:',
            'rag_d.updated':          'Updated:',
            'rag_d.chunk_maint':      'Chunk Maintenance',
            'rag_d.loading_sync':     'Loading sync state...',
            'rag_d.cleanup_btn':      'Cleanup Unbound Chunks (>30d)',
            'rag_d.cleanup_preview':  'Preview Cleanup',
            'rag_d.cleanup_hint':     'Deletes chunk sets not bound to any KB and older than 30 days.',
            'rag_d.tab_files':        'Files',
            'rag_d.tab_categories':   'Categories',
            'rag_d.tab_tasks':        'Indexing Tasks',
            'rag_d.add_files':        'Add Files',
            'rag_d.bulk_remove':      'Bulk Remove',
            'rag_d.search_files_ph':  'Search files',
            'rag_d.col_filename':     'Filename',
            'rag_d.col_chunks':       'Chunks',
            'rag_d.col_versions':     'No. of Versions',
            'rag_d.col_chunk_time':   'Chunk Time',
            'rag_d.col_md_time':      'Markdown Time',
            'rag_d.col_idx_status':   'Index Status',
            'rag_d.col_idx_time':     'Index Time',
            'rag_d.col_actions':      'Actions',
            'rag_d.loading_files':    'Loading files...',
            'rag_d.select_category':  'Select category',
            'rag_d.link_category':    'Link Category',
            'rag_d.col_task':         'Task',
            'rag_d.col_status':       'Status',
            'rag_d.col_started':      'Started',
            'rag_d.col_processed':    'Processed',
            'rag_d.col_task_chunks':  'Chunks',
            'rag_d.loading_tasks':    'Loading tasks...',

            // KB Stats card (partial)
            'kb_stats.total_files':   'Total Files',
            'kb_stats.indexed_files': 'Indexed Files',
            'kb_stats.pending_files': 'Pending Files',
            'kb_stats.total_chunks':  'Total Chunks',

            // Category sidebar (partial)
            'cat_sidebar.title':   'Categories',
            'cat_sidebar.clear':   'Clear',
            'cat_sidebar.loading': 'Loading categories...',

            // File selector (partial)
            'file_sel.title':      'Select Files',
            'file_sel.hint':       'Only files with markdown content are shown.',
            'file_sel.all_cats':   'All Categories',
            'file_sel.refresh':    'Refresh',
            'file_sel.col_name':   'Filename',
            'file_sel.col_cat':    'Category',
            'file_sel.col_source': 'Source',
            'file_sel.col_size':   'Size',
            'file_sel.col_upd':    'Updated',
            'file_sel.loading':    'Loading...',
            'file_sel.prev':       'Prev',
            'file_sel.next':       'Next',
            'file_sel.clear':      'Clear',
            'file_sel.apply':      'Apply',

            // Create KB Modal
            'kb_create.title':       'Create Knowledge Base',
            'kb_create.kb_id':       'KB ID (Auto Generated)',
            'kb_create.name':        'Name',
            'kb_create.desc':        'Description',
            'kb_create.mode':        'Mode',
            'kb_create.cat_mode':    'Category Mode',
            'kb_create.manual_mode': 'Manual Mode',
            'kb_create.categories':  'Categories',
            'kb_create.cats_hint':   'Hold Ctrl/Cmd to select multiple categories.',
            'kb_create.cats_stats':  'Select categories to view unique file and markdown counts.',
            'kb_create.sel_files':   'Selected Files',
            'kb_create.sel_btn':     'Select Files',
            'kb_create.advanced':    'Advanced Settings',
            'kb_create.chunk_prof':  'Chunk Profile',
            'kb_create.chunk_ph':    'Select existing chunk profile',
            'kb_create.embed_model': 'Embedding Model',
            'kb_create.embed_hint':  'Index model (for vector embedding), independent of chunk profile model.',
            'kb_create.cancel':      'Cancel',
            'kb_create.create':      'Create',
            'kb_create.create_idx':  'Create & Index',
            'kb_create.n_selected':  'files selected',

            // Edit KB Modal
            'kb_edit.title':     'Edit Knowledge Base',
            'kb_edit.name':      'Name',
            'kb_edit.desc':      'Description',
            'kb_edit.mode':      'KB Mode',
            'kb_edit.embedding': 'Embedding Model',
            'kb_edit.immutable': 'kb_id, mode, and embedding model are immutable for existing KBs.',
            'kb_edit.cancel':    'Cancel',
            'kb_edit.save':      'Save',

            // Chunk Profile Modal
            'cp.title':         'Chunk Profile Management',
            'cp.hint':          'Chunk profile controls chunk generation settings (model/splitter/tokenizer/size/overlap).',
            'cp.existing':      'Existing Profiles',
            'cp.col_name':      'Name',
            'cp.col_model':     'Chunk Model',
            'cp.col_size':      'Chunk Size',
            'cp.col_overlap':   'Overlap',
            'cp.col_splitter':  'Splitter',
            'cp.col_tok':       'Tokenizer',
            'cp.col_updated':   'Updated',
            'cp.loading':       'Loading profiles...',
            'cp.create_upsert': 'Create/Upsert Profile',
            'cp.name':          'Name',
            'cp.version':       'Version',
            'cp.model':         'Chunk Model',
            'cp.model_hint':    'Used for token counting behavior during chunking (not embedding model).',
            'cp.splitter':      'Splitter',
            'cp.splitter_opt':  'semantic (section/paragraph-aware)',
            'cp.size':          'Chunk Size',
            'cp.overlap':       'Chunk Overlap',
            'cp.tokenizer':     'Tokenizer',
            'cp.tok_hint':      'Controls token counting granularity for chunk size/overlap.',
            'cp.close':         'Close',
            'cp.save':          'Save Profile',

            // Scheduled Tasks page
            'sched.title':           'Scheduled Task Management',
            'sched.tab_sites':       'Configured Sites',
            'sched.tab_upcoming':    'Upcoming Runs',
            'sched.tab_manual':      'Manual Trigger',
            'sched.read_only':       'Read-only (operator/admin required to edit sites)',
            'sched.loading_sites':   'Loading configured sites...',
            'sched.loading_sched':   'Loading schedule status...',
            'sched.run_now':         'Run Collection Immediately',
            'sched.site_label':      'Select Site:',
            'sched.all_sites':       'All Sites',
            'sched.max_pages':       'Max Pages',
            'sched.max_depth':       'Max Depth',
            'sched.start':           'Start Collection',
            'sched.add_site':        'Add New Site',
            'sched.site_name':       'Site Name:',
            'sched.url':             'URL:',
            'sched.max_pages_opt':   'Max Pages (optional)',
            'sched.max_depth_opt':   'Max Depth (optional)',
            'sched.keywords':        'Keywords (comma separated)',
            'sched.excl_keywords':   'Exclude Keywords (comma separated)',
            'sched.excl_prefixes':   'Exclude Prefixes (comma separated)',
            'sched.save_site':       'Save Site',

            // Settings page
            'stg.tab_categories':  'Categories',
            'stg.tab_ai':          'AI Configuration',
            'stg.tab_other':       'Other Settings',
            'stg.tab_tokens':      'Tokens',
            'stg.tab_history':     'Task History',
            'stg.tab_backend':     'Backend Settings',
            'stg.cat_rules':       'Category Rules',
            'stg.cat_list':        'Category List',
            'stg.del_selected':    'Delete Selected',
            'stg.cat_keywords':    'Category Keywords',
            'stg.apply_selected':  'Apply to Selected',
            'stg.ai_filter':       'AI Filter Keywords',
            'stg.providers':       'Model Providers',
            'stg.add_provider':    'Add / Update Provider',
            'stg.provider':        'Provider',
            'stg.base_url':        'Base URL',
            'stg.api_key':         'API Key',
            'stg.loading_prov':    'Loading providers...',
            'stg.ai_model':        'AI Model Selection',
            'stg.catalog_model':   'Cataloging Model',
            'stg.chat_model':      'Chat Model',
            'stg.chunk_model':     'Chunk (Embedding) Model',
            'stg.loading_models':  'Loading models...',

            // Tasks page
            'tasks.title':             'Task Center',
            'tasks.url_col':           'URL Collection',
            'tasks.url_col_desc':      'Crawl specific URLs',
            'tasks.file_import':       'File Import',
            'tasks.file_import_desc':  'Import local files',
            'tasks.web_search':        'Web Search',
            'tasks.web_search_desc':   'Search & Collect',
            'tasks.quick_check':       'Quick Site Check',
            'tasks.quick_check_desc':  'Ad-hoc Site Scan',
            'tasks.scheduled':         'Scheduled',
            'tasks.scheduled_desc':    'Manage Schedules',
            'tasks.cataloging':        'Cataloging',
            'tasks.cataloging_desc':   'AI Categorization',
            'tasks.md_convert':        'Convert to Markdown',
            'tasks.md_convert_desc':   'Convert files to MD',
            'tasks.gen_chunks':        'Generate Chunks',
            'tasks.gen_chunks_desc':   'Build/reuse chunk sets',
            'tasks.create_kb':         'Create KB',
            'tasks.create_kb_desc':    'Create Knowledge Base',
            'tasks.build_idx':         'Build KB Index',
            'tasks.build_idx_desc':    'Run KB index task',
            'tasks.active':            'Active Tasks',
            'tasks.loading_active':    'Loading active tasks...',
            'tasks.history':           'Task History',
            'tasks.loading_history':   'Loading task history...',
            'tasks.no_active':         'No active tasks',
            'tasks.no_history':        'No task history',

            // File View page
            'fv.title':          'File Details',
            'fv.back':           'Back',
            'fv.source_site':    'Source Site',
            'fv.orig_url':       'Original URL',
            'fv.source_page':    'Source Page',
            'fv.content_type':   'Content Type',
            'fv.file_size':      'File Size',
            'fv.local_path':     'Local Path',
            'fv.collected_date': 'Collected Date',
            'fv.category':       'Category',
            'fv.choose_cat':     'Choose Categories',
            'fv.cat_hint':       'Category options are managed in the Settings page.',
            'fv.status':         'Status',
            'fv.deleted':        'Deleted',
            'fv.deletion_time':  'Deletion Time',
            'fv.summary':        'Summary',
            'fv.no_summary':     'No summary available',
            'fv.keywords':       'Keywords',
            'fv.no_keywords':    'No keywords available',
            'fv.edit':           'Edit Details',
            'fv.save':           'Save Changes',
            'fv.cancel':         'Cancel',
            'fv.catalog':        'Catalog (AI)',
            'fv.download':       'Download File',
            'fv.download_na':    'Download Unavailable',
            'fv.delete':         'Delete File',
            'fv.ai_explain':     'AI Explain Document',
            'fv.preview':        'File Preview',
            'fv.modify_chunk':   'Modify Chunk',
            'fv.md_content':     'Markdown Content',
            'fv.view':           'View',
            'fv.md_edit':        'Edit',
            'fv.expand':         'Expand',
            'fv.no_md':          'No markdown content available',
            'fv.convert_engine': 'Convert engine',

            // Chat page
            'chat.title':         'AI Chat Assistant',
            'chat.subtitle':      'Ask questions about your knowledge bases',
            'chat.filter_cat':    'Filter by Category',
            'chat.all_cats':      'All Categories',
            'chat.search_kw':     'Search Keywords',
            'chat.select_doc':    'Select Document',
            'chat.load_docs':     'Load Documents',
            'chat.click_load':    'Click "Load Documents" to start',
            'chat.click_load2':   'Click load button above',
            'chat.explain_sel':   'Explain Selected',
            'chat.conversations': 'Conversations',
            'chat.loading_convs': 'Loading conversations...',
            'chat.new_conv':      'New Conversation',
            'chat.kb_select':     'KB Selection',
            'chat.auto_smart':    'Auto (Smart Selection)',
            'chat.all_kbs':       'All Knowledge Bases',
            'chat.model_sel':     'Model Selection',
            'chat.expert_mode':   'Expert Mode',
            'chat.summary_mode':  'Summary Mode',
            'chat.tutorial_mode': 'Tutorial Mode',
            'chat.compare_mode':  'Comparison Mode',
            'chat.start_title':   'Start a Conversation',
            'chat.start_hint':    'Type a message below to begin chatting with the AI assistant',
            'chat.send':          'Send',
            'chat.explain_doc':   'Explain Document',
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
            'common.cancel':  '取消',
            'common.ok':      '确定',
            'common.confirm': '确认',
            'common.edit':    '编辑',
            'common.reset':   '重置',
            'common.refresh': '刷新',
            'common.create':  '创建',
            'common.close':   '关闭',
            'common.dismiss': '取消提示',
            'common.actions': '操作',
            'common.name':    '名称',
            'common.mode':    '模式',
            'common.status':  '状态',
            'common.updated': '更新时间',
            'common.prev':    '上一页',
            'common.next':    '下一页',
            'common.files':   '文件',
            'common.error_loading': '加载数据出错',
            'common.no_data': '未找到数据',

            // Error page
            'error.heading':          '错误',
            'error.msg_default':      '发生错误',
            'error.return_dashboard': '返回仪表板',

            // Login page
            'login.page_title': 'Token 登录',
            'login.subtitle':   '粘贴 API Token 以访问管理界面。',
            'login.api_token':  'API Token',
            'login.show':       '显示',
            'login.hide':       '隐藏',
            'login.paste':      '粘贴',
            'login.submit':     '登录',
            'login.home':       '首页',
            'login.return_to':  '登录后将返回至：',

            // Database page
            'db.title':           '数据库管理',
            'db.subtitle':        '搜索和管理已收集的文件',
            'db.search_ph':       '按标题、文件名或站点搜索…',
            'db.search':          '搜索',
            'db.all_sources':     '所有来源',
            'db.all_categories':  '所有分类',
            'db.uncategorized':   '未分类',
            'db.include_deleted': '包含已删除',
            'db.reset':           '重置',
            'db.files_heading':   '文件列表',
            'db.sort_new':        '日期（最新优先）',
            'db.sort_old':        '日期（最早优先）',
            'db.sort_title':      '标题 (A-Z)',
            'db.sort_source':     '来源站点 (A-Z)',
            'db.sort_size':       '大小（最大优先）',
            'db.loading':         '加载文件…',
            'db.no_files':        '未找到文件',
            'db.error_loading':   '加载文件出错',
            'db.col_title':       '标题 / 摘要',
            'db.col_source':      '来源',
            'db.col_category':    '分类',
            'db.col_markdown':    'Markdown',
            'db.col_size':        '大小',
            'db.col_last_seen':   '最近访问',
            'db.col_actions':     '操作',
            'db.col_num':         '#',
            'db.preview':         '预览',
            'db.md_available':    '已有 Markdown',
            'db.no_markdown':     '无 Markdown',
            'db.common_term':     '常用搜索词',
            'db.n_files':         '个文件',
            'db.page_of':         '第 {0} 页，共 {1} 页',

            // File Preview page
            'fp.title':           '文件预览',
            'fp.back':            '返回数据库',
            'fp.original':        '原始文件',
            'fp.loading_orig':    '加载原始文件…',
            'fp.chunks':          '文本块',
            'fp.loading_chunks':  '加载文本块…',
            'fp.error_no_file':   '错误：未指定文件',
            'fp.no_url':          '未提供文件 URL',

            // Collection (URL) page
            'col_url.title':        'URL 收集',
            'col_url.subtitle':     '从指定 URL 下载文件',
            'col_url.urls_label':   'URL（每行一个）：',
            'col_url.name_label':   '收集名称：',
            'col_url.check_dup':    '检查数据库中的重复项',
            'col_url.start':        '开始收集',
            'col_url.cancel':       '取消',
            'col_url.progress':     '收集进度',
            'col_url.alert_no_url': '请至少输入一个 URL',
            'col_url.alert_found':  '发现：',
            'col_url.alert_dl':     '已下载：',
            'col_url.completed':    '收集完成！',

            // Collection (File) page
            'col_file.title':        '文件导入',
            'col_file.subtitle':     '从本地文件系统导入文件',
            'col_file.dir_label':    '目录路径：',
            'col_file.browse':       '浏览…',
            'col_file.dir_help':     '从您的电脑选择文件夹以导入文件。',
            'col_file.ext_label':    '文件扩展名（逗号分隔，留空则全部）：',
            'col_file.name_label':   '收集名称：',
            'col_file.recursive':    '递归扫描（含子目录）',
            'col_file.start':        '开始导入',
            'col_file.back':         '返回',
            'col_file.importing':    '正在导入文件…',
            'col_file.scanning':     '正在扫描目录…',
            'col_file.found':        '发现文件：',
            'col_file.cataloged':    '成功录入：',
            'col_file.skipped':      '跳过重复：',
            'col_file.failed':       '失败：',
            'col_file.ok':           '确定',
            'col_file.completed':    '导入完成',
            'col_file.done_ok':      '文件处理成功。',
            'col_file.done_warn':    '导入完成，存在错误。',
            'col_file.alert_no_dir': '请输入目录路径',

            // RAG Management page
            'rag.title':            '知识库',
            'rag.subtitle':         '管理分类模式和手动模式的 RAG 知识库。',
            'rag.refresh':          '刷新',
            'rag.chunk_profiles':   '分块配置',
            'rag.create_kb':        '创建知识库',
            'rag.categories_no_kb': '个分类尚未创建知识库。',
            'rag.create_kbs':       '批量创建',
            'rag.dismiss':          '取消提示',
            'rag.search_ph':        '按名称、描述或 ID 搜索',
            'rag.all_modes':        '所有模式',
            'rag.mode_category':    '分类模式',
            'rag.mode_manual':      '手动模式',
            'rag.col_name':         '名称',
            'rag.col_mode':         '模式',
            'rag.col_files':        '文件数',
            'rag.col_chunks':       '文本块数',
            'rag.col_updated':      '更新时间',
            'rag.loading_kbs':      '加载知识库…',

            // RAG Detail page
            'rag_d.back':             '返回知识库列表',
            'rag_d.title':            '知识库',
            'rag_d.refresh':          '刷新',
            'rag_d.edit':             '编辑',
            'rag_d.export':           '导出文件列表',
            'rag_d.reindex':          '重新索引',
            'rag_d.delete':           '删除',
            'rag_d.metadata':         '元数据',
            'rag_d.kb_id':            '知识库 ID：',
            'rag_d.mode':             '模式：',
            'rag_d.embedding':        '向量模型：',
            'rag_d.chunk_profile':    '分块配置：',
            'rag_d.chunk_size':       '分块大小：',
            'rag_d.chunk_overlap':    '分块重叠：',
            'rag_d.updated':          '更新时间：',
            'rag_d.chunk_maint':      '分块维护',
            'rag_d.loading_sync':     '加载同步状态…',
            'rag_d.cleanup_btn':      '清理未绑定分块（>30天）',
            'rag_d.cleanup_preview':  '预览清理',
            'rag_d.cleanup_hint':     '删除未绑定到任何知识库且已超过 30 天的分块集。',
            'rag_d.tab_files':        '文件',
            'rag_d.tab_categories':   '分类',
            'rag_d.tab_tasks':        '索引任务',
            'rag_d.add_files':        '添加文件',
            'rag_d.bulk_remove':      '批量移除',
            'rag_d.search_files_ph':  '搜索文件',
            'rag_d.col_filename':     '文件名',
            'rag_d.col_chunks':       '文本块数',
            'rag_d.col_versions':     '版本数',
            'rag_d.col_chunk_time':   '分块时间',
            'rag_d.col_md_time':      'Markdown 时间',
            'rag_d.col_idx_status':   '索引状态',
            'rag_d.col_idx_time':     '索引时间',
            'rag_d.col_actions':      '操作',
            'rag_d.loading_files':    '加载文件…',
            'rag_d.select_category':  '选择分类',
            'rag_d.link_category':    '关联分类',
            'rag_d.col_task':         '任务',
            'rag_d.col_status':       '状态',
            'rag_d.col_started':      '开始时间',
            'rag_d.col_processed':    '已处理',
            'rag_d.col_task_chunks':  '文本块数',
            'rag_d.loading_tasks':    '加载任务…',

            // KB Stats card (partial)
            'kb_stats.total_files':   '总文件数',
            'kb_stats.indexed_files': '已索引文件',
            'kb_stats.pending_files': '待索引文件',
            'kb_stats.total_chunks':  '总文本块数',

            // Category sidebar (partial)
            'cat_sidebar.title':   '分类',
            'cat_sidebar.clear':   '清除',
            'cat_sidebar.loading': '加载分类…',

            // File selector (partial)
            'file_sel.title':      '选择文件',
            'file_sel.hint':       '仅显示含 Markdown 内容的文件。',
            'file_sel.all_cats':   '所有分类',
            'file_sel.refresh':    '刷新',
            'file_sel.col_name':   '文件名',
            'file_sel.col_cat':    '分类',
            'file_sel.col_source': '来源',
            'file_sel.col_size':   '大小',
            'file_sel.col_upd':    '更新时间',
            'file_sel.loading':    '加载中…',
            'file_sel.prev':       '上一页',
            'file_sel.next':       '下一页',
            'file_sel.clear':      '清除',
            'file_sel.apply':      '应用',

            // Create KB Modal
            'kb_create.title':       '创建知识库',
            'kb_create.kb_id':       '知识库 ID（自动生成）',
            'kb_create.name':        '名称',
            'kb_create.desc':        '描述',
            'kb_create.mode':        '模式',
            'kb_create.cat_mode':    '分类模式',
            'kb_create.manual_mode': '手动模式',
            'kb_create.categories':  '分类',
            'kb_create.cats_hint':   '按住 Ctrl/Cmd 可多选。',
            'kb_create.cats_stats':  '选择分类后可查看唯一文件数和 Markdown 数。',
            'kb_create.sel_files':   '已选文件',
            'kb_create.sel_btn':     '选择文件',
            'kb_create.advanced':    '高级设置',
            'kb_create.chunk_prof':  '分块配置',
            'kb_create.chunk_ph':    '选择现有分块配置',
            'kb_create.embed_model': '向量模型',
            'kb_create.embed_hint':  '索引模型（用于向量嵌入），与分块配置模型无关。',
            'kb_create.cancel':      '取消',
            'kb_create.create':      '创建',
            'kb_create.create_idx':  '创建并索引',
            'kb_create.n_selected':  '个文件已选',

            // Edit KB Modal
            'kb_edit.title':     '编辑知识库',
            'kb_edit.name':      '名称',
            'kb_edit.desc':      '描述',
            'kb_edit.mode':      '知识库模式',
            'kb_edit.embedding': '向量模型',
            'kb_edit.immutable': 'kb_id、模式和向量模型在创建后不可修改。',
            'kb_edit.cancel':    '取消',
            'kb_edit.save':      '保存',

            // Chunk Profile Modal
            'cp.title':         '分块配置管理',
            'cp.hint':          '分块配置控制分块生成设置（模型/分割器/分词器/大小/重叠）。',
            'cp.existing':      '现有配置',
            'cp.col_name':      '名称',
            'cp.col_model':     '分块模型',
            'cp.col_size':      '分块大小',
            'cp.col_overlap':   '重叠',
            'cp.col_splitter':  '分割器',
            'cp.col_tok':       '分词器',
            'cp.col_updated':   '更新时间',
            'cp.loading':       '加载配置…',
            'cp.create_upsert': '创建/更新配置',
            'cp.name':          '名称',
            'cp.version':       '版本',
            'cp.model':         '分块模型',
            'cp.model_hint':    '用于分块时的 Token 计数行为（非向量嵌入模型）。',
            'cp.splitter':      '分割器',
            'cp.splitter_opt':  'semantic（段落/章节感知）',
            'cp.size':          '分块大小',
            'cp.overlap':       '分块重叠',
            'cp.tokenizer':     '分词器',
            'cp.tok_hint':      '控制分块大小/重叠的 Token 计数粒度。',
            'cp.close':         '关闭',
            'cp.save':          '保存配置',

            // Scheduled Tasks page
            'sched.title':           '定时任务管理',
            'sched.tab_sites':       '已配置站点',
            'sched.tab_upcoming':    '即将执行',
            'sched.tab_manual':      '手动触发',
            'sched.read_only':       '只读（需要 operator/admin 权限才能编辑站点）',
            'sched.loading_sites':   '加载已配置站点…',
            'sched.loading_sched':   '加载调度状态…',
            'sched.run_now':         '立即运行收集',
            'sched.site_label':      '选择站点：',
            'sched.all_sites':       '所有站点',
            'sched.max_pages':       '最大页数',
            'sched.max_depth':       '最大深度',
            'sched.start':           '开始收集',
            'sched.add_site':        '添加新站点',
            'sched.site_name':       '站点名称：',
            'sched.url':             'URL：',
            'sched.max_pages_opt':   '最大页数（可选）',
            'sched.max_depth_opt':   '最大深度（可选）',
            'sched.keywords':        '关键词（逗号分隔）',
            'sched.excl_keywords':   '排除关键词（逗号分隔）',
            'sched.excl_prefixes':   '排除前缀（逗号分隔）',
            'sched.save_site':       '保存站点',

            // Settings page
            'stg.tab_categories':  '分类',
            'stg.tab_ai':          'AI 配置',
            'stg.tab_other':       '其他设置',
            'stg.tab_tokens':      'Token 管理',
            'stg.tab_history':     '任务历史',
            'stg.tab_backend':     '后端设置',
            'stg.cat_rules':       '分类规则',
            'stg.cat_list':        '分类列表',
            'stg.del_selected':    '删除所选',
            'stg.cat_keywords':    '分类关键词',
            'stg.apply_selected':  '应用到所选',
            'stg.ai_filter':       'AI 过滤关键词',
            'stg.providers':       '模型提供商',
            'stg.add_provider':    '添加 / 更新提供商',
            'stg.provider':        '提供商',
            'stg.base_url':        '基础 URL',
            'stg.api_key':         'API Key',
            'stg.loading_prov':    '加载提供商…',
            'stg.ai_model':        'AI 模型选择',
            'stg.catalog_model':   '目录模型',
            'stg.chat_model':      '对话模型',
            'stg.chunk_model':     '分块（向量）模型',
            'stg.loading_models':  '加载模型…',

            // Tasks page
            'tasks.title':             '任务中心',
            'tasks.url_col':           'URL 收集',
            'tasks.url_col_desc':      '爬取指定 URL',
            'tasks.file_import':       '文件导入',
            'tasks.file_import_desc':  '导入本地文件',
            'tasks.web_search':        '网络搜索',
            'tasks.web_search_desc':   '搜索并收集',
            'tasks.quick_check':       '快速站点检查',
            'tasks.quick_check_desc':  '临时站点扫描',
            'tasks.scheduled':         '定时任务',
            'tasks.scheduled_desc':    '管理定时计划',
            'tasks.cataloging':        '目录分类',
            'tasks.cataloging_desc':   'AI 自动分类',
            'tasks.md_convert':        '转换为 Markdown',
            'tasks.md_convert_desc':   '批量转换文件',
            'tasks.gen_chunks':        '生成文本块',
            'tasks.gen_chunks_desc':   '构建/重用分块集',
            'tasks.create_kb':         '创建知识库',
            'tasks.create_kb_desc':    '新建知识库',
            'tasks.build_idx':         '构建索引',
            'tasks.build_idx_desc':    '运行知识库索引任务',
            'tasks.active':            '活跃任务',
            'tasks.loading_active':    '加载活跃任务…',
            'tasks.history':           '任务历史',
            'tasks.loading_history':   '加载任务历史…',
            'tasks.no_active':         '无活跃任务',
            'tasks.no_history':        '无任务历史',

            // File View page
            'fv.title':          '文件详情',
            'fv.back':           '返回',
            'fv.source_site':    '来源站点',
            'fv.orig_url':       '原始 URL',
            'fv.source_page':    '来源页面',
            'fv.content_type':   '内容类型',
            'fv.file_size':      '文件大小',
            'fv.local_path':     '本地路径',
            'fv.collected_date': '收集日期',
            'fv.category':       '分类',
            'fv.choose_cat':     '选择分类',
            'fv.cat_hint':       '分类选项在"设置"页面管理。',
            'fv.status':         '状态',
            'fv.deleted':        '已删除',
            'fv.deletion_time':  '删除时间',
            'fv.summary':        '摘要',
            'fv.no_summary':     '暂无摘要',
            'fv.keywords':       '关键词',
            'fv.no_keywords':    '暂无关键词',
            'fv.edit':           '编辑详情',
            'fv.save':           '保存更改',
            'fv.cancel':         '取消',
            'fv.catalog':        '目录分类（AI）',
            'fv.download':       '下载文件',
            'fv.download_na':    '无法下载',
            'fv.delete':         '删除文件',
            'fv.ai_explain':     'AI 文档解析',
            'fv.preview':        '文件预览',
            'fv.modify_chunk':   '修改分块',
            'fv.md_content':     'Markdown 内容',
            'fv.view':           '查看',
            'fv.md_edit':        '编辑',
            'fv.expand':         '展开',
            'fv.no_md':          '暂无 Markdown 内容',
            'fv.convert_engine': '转换引擎',

            // Chat page
            'chat.title':         'AI 智能问答',
            'chat.subtitle':      '基于知识库提问',
            'chat.filter_cat':    '按分类筛选',
            'chat.all_cats':      '所有分类',
            'chat.search_kw':     '搜索关键词',
            'chat.select_doc':    '选择文档',
            'chat.load_docs':     '加载文档',
            'chat.click_load':    '点击"加载文档"开始',
            'chat.click_load2':   '点击上方的加载按钮',
            'chat.explain_sel':   '解析已选文档',
            'chat.conversations': '对话记录',
            'chat.loading_convs': '加载对话记录…',
            'chat.new_conv':      '新建对话',
            'chat.kb_select':     '知识库选择',
            'chat.auto_smart':    '自动（智能选择）',
            'chat.all_kbs':       '所有知识库',
            'chat.model_sel':     '模型选择',
            'chat.expert_mode':   '专家模式',
            'chat.summary_mode':  '摘要模式',
            'chat.tutorial_mode': '教程模式',
            'chat.compare_mode':  '对比模式',
            'chat.start_title':   '开始对话',
            'chat.start_hint':    '在下方输入消息，开始与 AI 助手对话',
            'chat.send':          '发送',
            'chat.explain_doc':   '解析文档',
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
