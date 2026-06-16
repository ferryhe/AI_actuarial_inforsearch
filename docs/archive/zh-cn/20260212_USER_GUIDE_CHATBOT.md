# AI Chatbot - User Guide

**Product**: AI Actuarial Info Search - AI Chatbot  
**Version**: 1.0  
**Date**: 2026-02-12  
**For**: End Users

---

## 📚 Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Using the Chat Interface](#using-the-chat-interface)
4. [Chatbot Modes](#chatbot-modes)
5. [Knowledge Base Selection](#knowledge-base-selection)
6. [Citations and Sources](#citations-and-sources)
7. [Conversation Management](#conversation-management)
8. [Tips and Best Practices](#tips-and-best-practices)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)

---

## Introduction

The AI Chatbot is an intelligent assistant that answers questions about actuarial topics using your organization's knowledge bases. It provides accurate, cited answers by searching through indexed documents and using advanced AI to generate responses.

### Key Features

✨ **Multiple Modes**: Expert, Summary, Tutorial, and Comparison modes  
✨ **Smart Search**: Automatically finds relevant information from knowledge bases  
✨ **Citations**: Every answer includes source references  
✨ **Conversation History**: All conversations are saved automatically  
✨ **Multi-KB Search**: Search across multiple knowledge bases simultaneously  

---

## Getting Started

### Accessing the Chat

1. **Log in** to the AI Actuarial Info Search system
2. Click **"Chat"** in the navigation menu
3. The chat interface will open with:
   - Message input area
   - KB (Knowledge Base) selector
   - Mode selector
   - Conversation history sidebar

### Your First Question

1. Leave settings at default (Auto KB, Expert mode)
2. Type a question in the message box
3. Press **Enter** or click **Send**
4. Wait 2-5 seconds for the response
5. Read the response with citations

**Example First Question**:
```
"What are the main capital requirements under Solvency II?"
```

---

## Using the Chat Interface

### Interface Layout

```
┌────────────────────────────────────────────────────┐
│  [Navigation Bar]                                   │
├──────────────┬─────────────────────────────────────┤
│              │  Knowledge Base: [Dropdown ▼]       │
│              │  Mode: [Dropdown ▼]                 │
│ Conversation │  [New Conversation]                 │
│ History      │                                     │
│ Sidebar      │  ┌─────────────────────────────┐   │
│              │  │                             │   │
│ • Conv 1     │  │    Chat Messages            │   │
│ • Conv 2     │  │    Display Area             │   │
│ • Conv 3     │  │                             │   │
│              │  └─────────────────────────────┘   │
│              │                                     │
│              │  [Type your message here...]        │
│              │  [Send]                             │
└──────────────┴─────────────────────────────────────┘
```

### Sending Messages

**Method 1: Enter Key**
- Type your question
- Press **Enter** to send
- Shift+Enter for new line (if needed)

**Method 2: Send Button**
- Type your question
- Click **Send** button

### Reading Responses

Responses appear as message bubbles with:
- **User messages**: Right side, blue background
- **Assistant messages**: Left side, gray background
- **Citations**: Clickable links in format [Source: filename.pdf]
- **Loading indicator**: Shows "Thinking..." while generating response

---

## Chatbot Modes

The chatbot offers four different modes to suit your needs:

### 🎓 Expert Mode (Default)

**Best for**: Detailed research, technical analysis, regulatory compliance

**Characteristics**:
- Comprehensive, detailed answers
- Full technical terminology
- Multiple citations per response
- Explains context and background
- Highlights edge cases

**When to Use**:
- Researching complex regulations
- Need accurate technical details
- Want comprehensive understanding
- Preparing formal documents

**Example Response Style**:
```
Under Solvency II, the capital requirement consists of two key 
components [Source: regulation_2023.pdf]:

1. Solvency Capital Requirement (SCR): Calculated to ensure a 
   99.5% probability of meeting obligations over one year, using 
   either the standard formula or an approved internal model 
   [Source: technical_guide.pdf]

2. Minimum Capital Requirement (MCR): The absolute regulatory 
   minimum, typically 25-45% of the SCR [Source: regulation_2023.pdf]

The SCR calculation considers market risk, credit risk, operational 
risk, and insurance-specific risks through a series of stress 
scenarios...
```

---

### 📊 Summary Mode

**Best for**: Quick overviews, time-constrained situations, executive summaries

**Characteristics**:
- Concise responses (<200 words)
- Bullet point format
- Key takeaways only
- 1-2 main citations
- Minimal technical jargon

**When to Use**:
- Need quick answer
- Want only key points
- Preparing executive summary
- Time-sensitive queries

**Example Response Style**:
```
Solvency II capital requirements [Source: regulation_2023.pdf]:

• **SCR**: 99.5% confidence level over 1 year
• **MCR**: Minimum threshold (25-45% of SCR)
• **Calculation**: Standard formula or internal model
• **Purpose**: Ensure insurers can meet policyholder obligations

Key point: SCR represents economic capital needed; MCR is 
regulatory floor.
```

---

### 📖 Tutorial Mode

**Best for**: Learning new concepts, training materials, educational purposes

**Characteristics**:
- Step-by-step explanations
- Builds from basics to advanced
- Uses examples and analogies
- Defines technical terms
- Progressive learning

**When to Use**:
- Learning unfamiliar topics
- Training new team members
- Need concept clarification
- Want deeper understanding

**Example Response Style**:
```
Let me explain Solvency II capital requirements step by step:

**Step 1: Understanding Capital Requirements**
Think of capital requirements like an emergency fund. Just as you 
keep savings for unexpected expenses, insurance companies must 
maintain capital cushions to protect policyholders 
[Source: intro_guide.pdf].

**Step 2: The Two Levels**
Solvency II defines two thresholds [Source: regulation_2023.pdf]:

1. **MCR (Minimum Capital)**: Like your absolute minimum bank 
   balance - if you go below this, serious consequences follow

2. **SCR (Solvency Capital)**: Your target savings goal - 
   maintains a healthy financial position

**Step 3: The 99.5% Confidence Level**
The SCR ensures a 99.5% probability of meeting obligations over 
the next year. In simpler terms: only 1 in 200 times would the 
capital be insufficient [Source: technical_guide.pdf]...
```

---

### ⚖️ Comparison Mode

**Best for**: Comparing options, analyzing differences, side-by-side analysis

**Characteristics**:
- Structured comparisons
- Highlights similarities and differences
- Uses tables when possible
- Balanced and objective
- Multiple citations

**When to Use**:
- Comparing regulations
- Analyzing product options
- Understanding changes over time
- Evaluating alternatives

**Example Response Style**:
```
Comparison of Solvency II (EU) vs US RBC:

**SIMILARITIES**
• Both require risk-based capital cushions [Source: comparison.pdf]
• Both have minimum thresholds for regulatory action
• Both use mathematical models for calculation

**KEY DIFFERENCES**

| Aspect | Solvency II | US RBC |
|--------|-------------|---------|
| Confidence | 99.5% [Source: sii.pdf] | 95% [Source: rbc.pdf] |
| Approach | Economic balance sheet | Statutory accounting |
| Flexibility | Standard or internal model | Factor-based formula |
| Complexity | High | Moderate |

**CONTEXT**
Solvency II is more sophisticated but requires more resources 
[Source: comparison.pdf]. US RBC is simpler to implement but 
less sensitive to actual risk profiles [Source: rbc.pdf].

**RECOMMENDATION**
Choose based on jurisdiction and available expertise...
```

---

## Knowledge Base Selection

### Available Options

**Auto (Recommended)**:
- System automatically selects the most relevant KB
- Based on query keywords and context
- Best for general use

**All Knowledge Bases**:
- Searches across all available KBs
- Best for comprehensive research
- May take slightly longer
- Shows diverse sources

**Specific KB**:
- Select individual KB from dropdown
- Best when you know which source to use
- Faster than "All KBs"

### How to Select

1. **Click KB dropdown** at top of chat
2. **Choose option**:
   - Auto (let system decide)
   - All Knowledge Bases
   - Specific KB name
3. **Send your query**
4. **System uses selected KB(s)** for that question

### When to Use Each

**Use Auto When**:
- You're not sure which KB to use
- First time asking about a topic
- Want system to be smart
- General queries

**Use All KBs When**:
- Need comprehensive answer
- Topic spans multiple sources
- Comparing information across sources
- Research requires broad coverage

**Use Specific KB When**:
- You know exactly which source needed
- Want faster response
- Focused on specific regulation/topic
- Previous queries identified the right KB

---

## Citations and Sources

### Understanding Citations

Every answer includes citations in this format:
```
[Source: filename.pdf]
```

**What Citations Mean**:
- Information came from that specific document
- You can verify the answer
- Document is in the knowledge base
- Link goes to full document

### Clicking Citations

1. **Click any [Source: ...] link** in the response
2. **Opens file detail page** with:
   - Full document information
   - File metadata
   - Option to view/download
3. **Use browser back button** to return to chat

### Multi-KB Citations

When using "All Knowledge Bases", citations show the KB name:
```
[Source: regulation_2023.pdf (General KB)]
[Source: technical_guide.pdf (Technical Docs KB)]
```

**Color Badges**:
- Each KB may have a different color
- Helps identify source at a glance
- Visual distinction between sources

### Why Citations Matter

✅ **Verify Information**: Check the source yourself  
✅ **Build Trust**: Know where answers come from  
✅ **Further Reading**: Explore topic in depth  
✅ **Compliance**: Document your research sources  

---

## Conversation Management

### Auto-Save

**Good news**: All conversations save automatically!

- No "Save" button needed
- Happens in real-time
- Never lose your work
- Access from any device (same account)

### Conversation Titles

**Auto-Generated**:
- Title created from your first question
- Format: "{Topic} - {Date}"
- Example: "Solvency II Questions - Feb 12"

**Manual Titles** (if available):
- Click conversation to rename (implementation dependent)
- Give it a meaningful name
- Easier to find later

### Conversation Sidebar

**Shows**:
- List of all your conversations
- Most recent at top
- Title and date
- Number of messages (if shown)

**Actions**:
- **Click conversation** to load it
- **Scroll** to see older conversations
- **Delete** (if button shown) to remove

### Starting New Conversations

**Why Start New**:
- Different topic from current conversation
- Want clean slate
- Keep conversations organized

**How to Start**:
1. Click **"New Conversation"** button
2. Previous conversation stays in sidebar
3. Start typing your new question
4. Title generates from first question

### Managing Old Conversations

**Finding Old Conversations**:
- Scroll conversation sidebar
- Look at dates
- Read conversation titles

**Deleting Conversations**:
1. Select conversation
2. Find "Delete" button (if available)
3. Confirm deletion
4. Conversation removed permanently

**Best Practice**:
- Keep related questions in same conversation
- Start new conversation for new topics
- Delete old test conversations periodically

---

## Tips and Best Practices

### Writing Good Questions

**✅ DO**:
- Be specific and clear
- Use relevant keywords
- Ask one thing at a time
- Provide context if needed

**❌ DON'T**:
- Be too vague
- Ask multiple unrelated questions
- Use ambiguous pronouns without context
- Expect mind-reading

**Examples**:

**Bad**: "What are the requirements?"  
**Good**: "What are the capital requirements for life insurance under Solvency II?"

**Bad**: "Tell me about that thing we discussed"  
**Good**: "What is the Solvency Capital Requirement (SCR) calculation method?"

---

### Following Up

**Context Awareness**:
- Chatbot remembers recent conversation
- Can reference previous answers
- Use "it", "this", "that" in follow-ups

**Good Follow-up Pattern**:
```
You: "What is Solvency II?"
Bot: [explains Solvency II]

You: "How is the SCR calculated under it?"
Bot: [explains SCR calculation, remembers "it" = Solvency II]

You: "What are the main risk categories?"
Bot: [knows we're still talking about Solvency II]
```

---

### Verifying Information

**Always Verify Critical Information**:
1. **Check citations**: Click source links
2. **Read full documents**: Don't rely solely on summary
3. **Cross-reference**: Ask in multiple ways
4. **Consult experts**: For critical decisions

**When to Double-Check**:
- Legal or regulatory decisions
- Financial calculations
- Contract language
- Compliance matters

---

### Getting Better Results

**Try Different Modes**:
- Start with Expert for detailed answer
- Use Summary if Expert too long
- Try Tutorial if Expert too technical
- Use Comparison when choosing between options

**Refine Your Query**:
- If results not relevant, rephrase
- Add more specific keywords
- Try different KB
- Break complex questions into parts

**Use Multi-KB**:
- For comprehensive research
- When topic spans sources
- To see different perspectives
- To find all relevant regulations

---

## Troubleshooting

### No Response or Error

**Possible Causes**:
- Network issue
- API timeout
- Server problem

**Solutions**:
1. **Wait 30 seconds** and try again
2. **Check internet connection**
3. **Refresh page** (F5 or Ctrl+R)
4. **Check if server is running**
5. **Contact support** if persistent

---

### "I don't have enough information"

**What It Means**:
- Topic not in knowledge bases
- Query too vague
- Different KB might be better

**Solutions**:
1. **Rephrase query**: Use different keywords
2. **Try different KB**: Select specific or "All KBs"
3. **Check if documents indexed**: Go to `/rag` page
4. **Ask simpler question**: Break down complex query

---

### Irrelevant Responses

**Possible Causes**:
- Wrong KB selected
- Query ambiguous
- Need different mode

**Solutions**:
1. **Select correct KB**: Check which KB has your topic
2. **Be more specific**: Add details to query
3. **Try different mode**: Maybe Summary too brief
4. **Rephrase**: Use exact terms from documents

---

### Citations Don't Work

**Possible Causes**:
- Document not in system
- Broken link
- Permission issue

**Solutions**:
1. **Try another citation**: See if others work
2. **Go to /database**: Search for file manually
3. **Report to admin**: If consistent problem
4. **Use file name**: Search for document separately

---

## FAQ

### Q: How accurate are the answers?

**A**: Very accurate for information in the knowledge bases. The chatbot:
- Only uses indexed documents
- Provides citations for verification
- Admits when it doesn't know
- Doesn't make up information

**However**: Always verify critical information by checking sources.

---

### Q: Can I trust the citations?

**A**: Yes. Citations are:
- Automatically generated from search results
- Link to actual documents in system
- Validated before display
- Traceable to source

**Best Practice**: Click citations to verify context.

---

### Q: How long is information stored?

**A**: 
- **Conversations**: Stored indefinitely (until deleted)
- **Knowledge bases**: Updated when documents change
- **Your queries**: Metadata only, no content logged for privacy

---

### Q: Can others see my conversations?

**A**: No. Conversations are:
- Private to your account
- Not shared with other users
- Visible only to you (and admins if needed for support)

---

### Q: How fast should responses be?

**A**: 
- **Target**: 2-5 seconds
- **Maximum**: Up to 10 seconds for complex queries
- **Factors**: KB size, query complexity, server load

**If slower**: Network or server issue - report to admin.

---

### Q: Can I use this for production decisions?

**A**: Use as **research tool**, not sole decision-maker:
- ✅ Background research
- ✅ Finding relevant documents
- ✅ Understanding concepts
- ✅ Comparing options

- ❌ Sole basis for legal decisions
- ❌ Replacement for expert consultation
- ❌ Unverified compliance determinations

**Always consult qualified professionals for critical decisions.**

---

### Q: What if I get contradictory information?

**A**: When using multi-KB search:
- Different sources may have different information
- Chatbot will flag contradictions
- Check which KB each citation comes from
- Consider context (dates, jurisdictions, etc.)

**Resolution**: Consult most recent/authoritative source or expert.

---

### Q: Can I share responses?

**A**: Currently:
- **Copy/paste**: ✅ Copy text and citations
- **Screenshot**: ✅ Take screenshot
- **Export**: Check if available (may be future feature)
- **Link sharing**: Not currently available

---

### Q: What happens if API is down?

**A**: If OpenAI API is unavailable:
- You'll see error message
- Try again in few minutes
- Check status: https://status.openai.com/
- Contact support if extended outage

---

## Getting Help

### Support Channels

**Technical Issues**:
- Contact IT support
- Email: [support email]
- Include: Screenshot, error message, steps to reproduce

**Questions About Answers**:
- Check citations first
- Consult domain experts
- Rephrase and ask again

**Feature Requests**:
- Submit via feedback form
- Describe desired feature
- Explain use case

---

### Additional Resources

- **RAG System Guide**: `/rag` page for managing knowledge bases
- **Admin Documentation**: For administrators managing system
- **API Documentation**: For developers integrating with system

---

**Last Updated**: 2026-02-12  
**Version**: 1.0  
**Feedback**: Please report any issues or suggestions to the development team

---

**End of User Guide**
