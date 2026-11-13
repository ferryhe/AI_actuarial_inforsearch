---
doc_id: user-guide-en
language: en
title: AI Actuarial Info Search — User Guide
source_version: 1.1.3
---

# User Guide

This guide describes the current browsing, file, knowledge base, Chat, account, and feedback features. Available actions depend on your account permissions and deployment settings.

## Features and Dashboard {#features-dashboard}

What features are available? The Dashboard at **/** shows current file, catalog and source counts, active tasks, and the latest published weekly additions when available. Use **Database** for search, **Source Portals** for source information, **Categories** for topics, **Knowledge Bases** for index status, **Chat** for questions, **Weekly** for the published update reader, **Profile** for your account and quota, and **Help and feedback** for help or suggestions. The navigation shows only entries your account can use.

## Browsing and search {#browse-search}

Open **Database** to browse collected files. Use text search to find files; the separate category and source filters, sorting, and page controls narrow the list. Select a row to open its file details. The list reflects files currently available to your account.

## Categories and sources {#categories-sources}

Open **Categories** to browse categories currently used by files. Open **Source Portals** to browse reviewed source entries, their overviews, and recent updates. Some entries are historical or on hold. A category view can link to matching files. Some deployments show an **Ask AI** link when a ready knowledge base is available for that category and your account can use Chat.

## Weekly reports {#weekly-reports}

How do I view weekly updates?

How do I use the weekly report or find this week's new files? With permission to read files, open **/weekly** directly. If the Dashboard shows the weekly card, its **View all** link also opens Weekly. The reader opens the latest complete **published** snapshot and says when none is available. The current week appears once it is complete and published. Select an older published period to inspect its historical list. Open an included file to read its details, source link, preview, or Markdown when available. The snapshot counts files first collected by this system during its period (`first_seen`). An empty published period has no new files by that definition.

## Dates and updates {#dates-updates}

A file's publication date (`files.published_time`) is different from the system's first collection date (`files.first_seen`) and the date it joined a knowledge base (`rag_kb_files.added_at`). Source Portal update entries describe source activity. Content revision lineage is currently not recorded, so this site cannot tell when a document's content changed from `last_seen`, a scheduled refresh, an HTTP status, or one current hash. Ask for a publication date, newly collected files, or weekly additions separately.

## File details and reading {#file-details}

Open a file from Database to see its title, source, category, summary, keywords, and available content. When a local file exists, **Preview** is enabled. The **Download** button remains visible but is enabled only when a local file exists and your account has download permission. Markdown content can be read on the detail page when available. Editing catalog metadata, changing Markdown, running processing tasks, and deleting files require separate permissions; controls are hidden or disabled when unavailable.

## Knowledge bases and current Chat {#knowledge-chat}

Open **Knowledge Bases** to see available knowledge bases and their readiness. Users with catalog management or task permissions may see additional setup and processing controls. Open **Chat** to ask a question after choosing an available knowledge base and response mode. A category's **Ask AI** link opens Chat with the category's dedicated knowledge base when one is ready. Chat results may include cited source documents. When enabled, the floating website assistant answers usage questions, searches public directory metadata and summaries, and reads only KBs allowed by the server for your identity. Seeing a KB in the list does not grant assistant access. Staff KBs require an authenticated operator or administrator. Directory summaries do not establish body conclusions. KB answers cite actual body excerpts and the version being served; an earlier serving version is labeled. Missing evidence or unavailable indexes are reported explicitly.

## Account and quota {#account-quota}

Sign in or register when the deployment offers those options. Open **Profile** while signed in to see your role, Chat quota usage, remaining quota, and recent activity. Anonymous visitors can use only the public features granted by the deployment. Chat and the website assistant share one daily AI quota. Guests have 20 queries per IP address, and registered users have 40 queries per account. The quota resets at midnight UTC. Manual feedback and opening help do not call AI or consume the allowance.

## Feedback entry {#feedback-entry}

Feedback and assistant are separate, off by default. **Help and feedback** appears when either is on. Feedback alone opens an editable form. With both on, **Send a suggestion** opens it without AI. Review before submitting. A server receipt confirms success. With the assistant on, ask your question directly in the single input. It chooses the tools. A short conversation stays in this tab's memory across in-site navigation and out of Chat history. Use **Clear conversation** or refresh the page to reset it. Guide citations open the exact current section and version. Directory and KB citations open source file details. Missing help is reported, not invented. If it detects feedback, it makes an editable draft from your original text. Canceling does not submit it. Turning feedback off hides submission. **Read user guide (no AI)** and manual feedback remain available if the model fails.

## Common failures {#common-failures}

If a list or file does not appear, try clearing the search and filters, then reload the page. If a preview or Markdown view is unavailable, that file may not have a local copy or readable Markdown. If a knowledge base is unavailable, choose another ready base or ask an administrator to check its indexing status. If Chat reports a quota limit, wait for the quota period to reset or contact your administrator. If feedback cannot be submitted, retry when the service is available; keep the receipt if one was shown. A permission error means the action is not enabled for your account.
