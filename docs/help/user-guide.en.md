---
doc_id: user-guide-en
language: en
title: AI Actuarial Info Search — User Guide
source_version: 1.0.0
---

# User Guide

This guide describes the current browsing, file, knowledge base, Chat, account, and feedback features. Available actions depend on your account permissions and deployment settings.

## Browsing and search {#browse-search}

Open **Database** to browse collected files. Search by title, filename, or source; use the category and source filters, sorting, and page controls to narrow the list. Select a row to open its file details. The list reflects files currently available to your account.

## Categories and sources {#categories-sources}

Open **Categories** to browse categories currently used by files. Open **Source Portals** to see monitored source sites and their summaries. A category view can link to matching files. Some deployments show an **Ask AI** link when a ready knowledge base is available for that category and your account can use Chat.

## File details and reading {#file-details}

Open a file from Database to see its title, source, category, summary, keywords, and available content. When a local file is available, **Preview** opens the readable file and **Download** appears only when your permissions allow it. Markdown content can be read on the detail page when available. Editing catalog metadata, changing Markdown, running processing tasks, and deleting files require separate permissions; controls are hidden or disabled when unavailable.

## Knowledge bases and current Chat {#knowledge-chat}

Open **Knowledge Bases** to see available knowledge bases and their readiness. Users with catalog management or task permissions may see additional setup and processing controls. Open **Chat** to ask a question after choosing an available knowledge base and response mode. A category's **Ask AI** link opens Chat with the category's dedicated knowledge base when one is ready. Chat results may include cited source documents. The new assistant question panel and its knowledge-base question feature are not shipped yet.

## Account and quota {#account-quota}

Sign in or register when the deployment offers those options. Open **Profile** while signed in to see your role, Chat quota usage, remaining quota, and recent activity. Anonymous visitors can use only the public features granted by the deployment. Chat limits vary by deployment and account; ask your administrator about the configured limits.

## Feedback entry {#feedback-entry}

When feedback is enabled by the deployment, use the floating **Help and feedback** button, then describe the issue or suggestion and submit it. The widget is hidden when feedback is disabled. Submission confirms with a receipt; feedback does not send a Chat question. The widget currently provides feedback only; it does not answer help questions.

## Common failures {#common-failures}

If a list or file does not appear, try clearing the search and filters, then reload the page. If a preview or Markdown view is unavailable, that file may not have a local copy or readable Markdown. If a knowledge base is unavailable, choose another ready base or ask an administrator to check its indexing status. If Chat reports a quota limit, wait for the quota period to reset or contact your administrator. If feedback cannot be submitted, retry when the service is available; keep the receipt if one was shown. A permission error means the action is not enabled for your account.
