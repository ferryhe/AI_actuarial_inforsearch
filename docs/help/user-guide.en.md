---
doc_id: user-guide-en
language: en
title: AI Actuarial Info Search — User Guide
source_version: 1.0.0
---

# User Guide

This guide describes the current browsing, file, knowledge base, Chat, account, and feedback features. Available actions depend on your account permissions and deployment settings.

## Browsing and search {#browse-search}

Open **Database** to browse collected files. Use text search to find files; the separate category and source filters, sorting, and page controls narrow the list. Select a row to open its file details. The list reflects files currently available to your account.

## Categories and sources {#categories-sources}

Open **Categories** to browse categories currently used by files. Open **Source Portals** to browse reviewed source entries, their overviews, and recent updates. Some entries are historical or on hold. A category view can link to matching files. Some deployments show an **Ask AI** link when a ready knowledge base is available for that category and your account can use Chat.

## File details and reading {#file-details}

Open a file from Database to see its title, source, category, summary, keywords, and available content. When a local file exists, **Preview** is enabled. The **Download** button remains visible but is enabled only when a local file exists and your account has download permission. Markdown content can be read on the detail page when available. Editing catalog metadata, changing Markdown, running processing tasks, and deleting files require separate permissions; controls are hidden or disabled when unavailable.

## Knowledge bases and current Chat {#knowledge-chat}

Open **Knowledge Bases** to see available knowledge bases and their readiness. Users with catalog management or task permissions may see additional setup and processing controls. Open **Chat** to ask a question after choosing an available knowledge base and response mode. A category's **Ask AI** link opens Chat with the category's dedicated knowledge base when one is ready. Chat results may include cited source documents. When enabled, the floating website assistant answers usage questions, searches public directory metadata and summaries, and reads only KBs allowed by the server for your identity. Seeing a KB in the list does not grant assistant access. Staff KBs require an authenticated operator or administrator. Directory summaries do not establish body conclusions. KB answers cite actual body excerpts and the version being served; an earlier serving version is labeled. Missing evidence or unavailable indexes are reported explicitly.

## Account and quota {#account-quota}

Sign in or register when the deployment offers those options. Open **Profile** while signed in to see your role, Chat quota usage, remaining quota, and recent activity. Anonymous visitors can use only the public features granted by the deployment. Chat and the website assistant share one daily AI quota: guests have 5 queries and registered users have 20 queries per UTC day; other roles follow the existing Chat allowance. Manual feedback and opening help do not call AI or consume the allowance.

## Feedback entry {#feedback-entry}

Feedback and assistant are independent switches, both off by default. The floating **Help and feedback** entry appears when either is enabled. If only feedback is enabled, the entry opens the ordinary editable form. When the assistant is also enabled, choose **Send a suggestion** to open that form without calling AI. Submit only after reviewing the text; success requires a server receipt. With the assistant enabled, select Auto, Website usage, Directory / summaries, or KB body evidence. Usage answers cite the current guide; open a citation to read that exact section/version. Directory and KB citations link to the source file details. Missing help is reported rather than invented. Auto feedback only prepares your original text as an editable draft: canceling does not submit it. If feedback is disabled, no submission action is shown. Each question is independent; history stays on the current page, clears on navigation or refresh, and is not saved to Chat. **Read user guide (no AI)** and manual feedback remain available when the model fails.

## Common failures {#common-failures}

If a list or file does not appear, try clearing the search and filters, then reload the page. If a preview or Markdown view is unavailable, that file may not have a local copy or readable Markdown. If a knowledge base is unavailable, choose another ready base or ask an administrator to check its indexing status. If Chat reports a quota limit, wait for the quota period to reset or contact your administrator. If feedback cannot be submitted, retry when the service is available; keep the receipt if one was shown. A permission error means the action is not enabled for your account.
