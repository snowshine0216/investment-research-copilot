# Handoff Document
*Last updated: 2026-05-07 12:17:20 CST*

---

## Session: May 7 — Investment Research Copilot Planning + Repo Analysis

### Goal
Design a new investment-research project for a beginner finance user who wants a thorough, explainable system for gold plus domestic/international fund and ETF allocation analysis. The system should combine data, research, scoring, and multi-factor reasoning, not rely only on autoregressive price forecasts.

### Current Progress
- Used the `repo-analysis` skill to analyze 9 repositories and saved structured markdown reports:
  - `ai-engineering/kronos.md`
  - `claude/financial-services.md`
  - `rag-and-knowledge/local-deep-research.md`
  - `agent-frameworks/dexter.md`
  - `agent-frameworks/tradingagents.md`
  - `dev-tools/insforge.md`
  - `dev-tools/ladybird.md`
  - `dev-tools/scrapling.md`
  - `dev-tools/openbb.md`
- Verified all 9 reports include required frontmatter and the fixed section structure: Repo Snapshot, Primary Use Cases, When To Use, Benefits, Limitations and Risks, Practical Insights.
- Ran `git diff --check`; no whitespace errors.
- Began `superpowers:brainstorming` for the actual project design. The hard gate from that skill is active: do not scaffold or implement until the design is approved and written as a spec.
- Decided the investment project should be a separate repo, not a subfolder of `snow-knowledge-database`.
- Approved project-start approach: **Option 1, minimal research system**.
- Approved first design section, Project Boundary:
  - New repo name: `investment-research-copilot`.
  - First version focuses on gold plus domestic/international funds and ETFs.
  - No auto-trading, no broker integration, no high-frequency trading, no dashboard at first.
  - First outputs are Markdown reports plus CSV/JSON data.

### User Decisions Captured
- MVP scope: **A — gold plus domestic/international fund allocation analysis**.
- Investable universe: **B — Mainland China products plus HK/US ETFs**.
- Decision cadence: **D — long-term allocation as core, medium-term rotation as support, no high-frequency short-term trading**.
- Risk profile: **B — steady, accepts roughly 10%-20% max drawdown**.
- Input mode: **C — analyze real holdings and maintain a watchlist/candidate pool**.
- Holding privacy: **C — anonymized holdings; normalize total assets to 100 or 1,000,000**.
- Interface path: **D — start with Markdown reports and CSV/JSON, later upgrade to dashboard**.
- Data-source assumption: **D — free/public data first, pluggable paid/data-vendor sources later**.

### What Worked
- GitHub CLI (`gh repo view`, `gh api`) worked well for repository metadata, README, and selected key docs.
- Repo classification used the knowledge database's six-topic rule; OpenBB stayed under `dev-tools`, Kronos under `ai-engineering`, TradingAgents/Dexter under `agent-frameworks`, Local Deep Research under `rag-and-knowledge`, and Anthropic financial-services under `claude`.
- The most useful architecture mapping from repo analysis:
  - OpenBB = primary financial data layer.
  - Scrapling = missing public web/fund factsheet collector.
  - Local Deep Research = cited research and knowledge-memory layer.
  - Kronos = auxiliary market-sequence signal generator, not final decision maker.
  - TradingAgents = multi-role decision chamber for technical, macro, news, risk, and portfolio views.
  - Dexter = interactive financial research agent pattern, useful later for stock/tool orchestration.
  - Anthropic financial-services = process templates for idea generation, thesis tracking, catalyst calendar, and portfolio rebalance.
  - InsForge = possible later backend platform, not first MVP.
  - Ladybird = no near-term role for investment analysis.

### What Didn't Work
- `gh repo view --json readme` failed because this GitHub CLI version does not expose `readme` as a JSON field. The working fallback was `gh api repos/<owner>/<repo>/readme -H 'Accept: application/vnd.github.raw'`.
- `qgithub.com/shiyu-coder/Kronos` is not a normal GitHub URL; analysis used the intended repo `https://github.com/shiyu-coder/Kronos`.
- Starting with dashboard or database platform was ruled out as too heavy before validating the finance logic.
- Using Kronos or any autoregressive model as the final buy/sell engine was explicitly ruled out.
- Putting the runnable project inside this knowledge database was ruled out because this repo is mainly an Obsidian/content system.

### Next Steps
1. Continue `superpowers:brainstorming` from **Design Section 2**. Present the next section for approval, likely:
   - data model and input files (`portfolio.csv`, `watchlist.csv`, `risk-profile.yaml`)
   - asset classes and required fields
   - free/public source strategy
2. Then present and approve later design sections:
   - scoring framework
   - report/memo format
   - system architecture and data flow
   - error handling and data-quality rules
   - testing approach
   - future dashboard path
3. After all design sections are approved, write the spec to:
   - `docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md`
4. Self-review the spec for placeholders, contradictions, scope creep, and ambiguity.
5. Ask user to review the written spec before moving to implementation planning.
6. Only after user approval, invoke `superpowers:writing-plans` and create the implementation plan. Do not scaffold the new repo before this approval.

### Key Files & Locations
| File | Purpose |
| :--- | :--- |
| `ai-engineering/kronos.md` | Repo analysis for financial K-line foundation model |
| `claude/financial-services.md` | Repo analysis for Claude financial-services workflows and skills |
| `rag-and-knowledge/local-deep-research.md` | Repo analysis for research and knowledge-memory layer |
| `agent-frameworks/dexter.md` | Repo analysis for autonomous financial research agent |
| `agent-frameworks/tradingagents.md` | Repo analysis for multi-agent trading/research framework |
| `dev-tools/openbb.md` | Repo analysis for financial data platform; updated existing file |
| `dev-tools/scrapling.md` | Repo analysis for scraping/data extraction layer |
| `dev-tools/insforge.md` | Repo analysis for possible later backend platform |
| `dev-tools/ladybird.md` | Repo analysis; concluded no first-version role |
| `HANDOFF.md` | This handoff file |

### Context & Notes
- Current workspace: `/Users/snow/Documents/Repository/snow-knowledge-database`.
- At handoff time, `git status --short --untracked-files=all` returned clean.
- The user prefers Chinese explanations for the investment-project discussion.
- The user has explicitly chosen a cautious MVP. Keep scope focused on an explainable weekly/monthly research system for gold and funds/ETFs.
- Avoid implying financial advice. The product should output research memos and recommendations for human review, not automatic trade execution.
- The design should preserve future extension points for individual-stock analysis, Kronos, TradingAgents, InsForge, and dashboard UI, but these should not dominate the first implementation.

---

## Session: April 19 — Answer Guide Rendering Fix + Course Transcription

### Goal
Fix the broken Answer Guide rendering in all course notes (Obsidian was displaying them as walls of text), update the template so future notes are generated correctly, and continue the EVC pipeline for the RAG and Agentic AI courses.

### What Was Done

#### Answer Guide Format Fix
- **Root cause identified**: `<details>/<summary>` HTML blocks suppress all markdown rendering inside them in Obsidian — bullets, tables, bold, code all collapse into unstyled prose.
- **Fix**: Replaced with Obsidian-native collapsible callout `> [!example]-` syntax. Markdown inside callouts renders fully.
- **New format**: Each answer now gets its own `#### Qn — Short Title` heading for navigation; complex answers use tables.

#### Files Changed
- ✅ `courses/zero-to-hero/01-the-spelled-out-intro-to-neural-networks-and-backpropagation-building-micrograd_VMj-3S1tku0.md` — reformatted answer guide + added new Q4 (why tanh?)
- ✅ `.claude/skills/content-summarizer/references/template-lecture-text.md` — updated canonical template: replaced all `<details>` references with callout syntax, added explicit "Forbidden Patterns" entry banning `<details>/<summary>`, updated Required Structure list and rules section
- ✅ `scripts/enhance-answer-guides.py` — new batch script: finds all `courses/**/*.md` with old `<details>` answer guides, calls Claude Haiku API to reformat each one, writes in-place

#### New Q4 Added to Micrograd Course
Pre-test Q4: *"In micrograd's neuron formula `output = tanh(sum(w_i * x_i) + b)`, why is `tanh` applied after the weighted sum? What would happen if you removed it?"*

Answer guide covers: non-linearity (layers collapse without it), bounded output (−1 to 1), zero-centering vs Sigmoid, and cheap gradient $1 - y^2$. Includes a reasons table and a linear-vs-tanh comparison table.

### What Worked
- **Obsidian callout syntax** (`> [!example]-`): fully renders markdown, tables, math, code inside the collapsed block
- **`#### Qn — Title` pattern**: gives each answer a navigable heading; Q3 table format is especially clean for the training-loop answer

### What Didn't Work
- **`<details>/<summary>` HTML**: never use this for answer guides in Obsidian — markdown does not render inside HTML blocks regardless of Obsidian version

### Next Steps
1. **Run the batch script** to fix all remaining course files with old `<details>` answer guides:
   ```bash
   python3 scripts/enhance-answer-guides.py --dry-run  # preview
   python3 scripts/enhance-answer-guides.py            # apply
   ```
2. **RAG course**: lessons 046 and 047 were dispatched for write-up; ~15 lessons still need audio download + transcription.
3. **Agentic AI course**: transcription in progress (17+ of 29 files done as of ~noon); write-up agents need to run for newly transcribed lessons.
4. **Wiki index**: verify `wiki/_index.md` has rows for all newly written lessons.

### Key Files
| File | Purpose |
| :--- | :--- |
| `scripts/enhance-answer-guides.py` | Batch-convert old `<details>` answer guides to callout format |
| `.claude/skills/content-summarizer/references/template-lecture-text.md` | Canonical template for EVC lecture write-ups — updated |
| `courses/zero-to-hero/01-*-micrograd_VMj-3S1tku0.md` | Reference file with new callout format + Q4 |

---

## Session: April 18 — yt-video-summarizer + EVC Pipeline Setup

### Goal
Extend the yt-video-summarizer skill to automatically extract all video URLs from course pages (DeepLearning.AI, Coursera, Udemy) and process them systematically with progress tracking.

### What Was Done
- ✅ Extended yt-video-summarizer with Playwright-based course enumeration and adapter system
- ✅ Progress tracking (JSON-based, resume-capable)
- ✅ Cookie support via yt-dlp browser export
- ✅ Demo structure for `courses/fine-tuning-large-language-models/`
- ✅ Playwright browsers installed (Chromium v1217)

### What Worked
- Adapter pattern for platform-specific enumeration
- Leveraging existing yt-video-summarizer pipeline
- Browser cookie export/import (mirrors encrypted-video-capture approach)

### What Didn't Work
- **DeepLearning.AI headless access**: bot protection blocks headless Playwright; needs visible browser or alternative auth
- **Simple cookie persistence**: required more sophisticated parsing for Chrome's microsecond timestamps

### Next Steps (from Apr 18, may already be done)
1. Try persistent browser context with manual login for DeepLearning.AI
2. Test Coursera/Udemy adapters
3. Connect course processor to content-summarizer for markdown generation
4. Add wiki compilation for processed courses

### Key Files
- **Skill**: `.claude/skills/yt-video-summarizer/`
- **Course processor**: `scripts/process_course.py`
- **Playwright enumerator**: `playwright/course-enumerator.mjs`
- **Platform adapters**: `playwright/adapters/`
- **Target course dir**: `courses/fine-tuning-large-language-models/`

### Quick Start
```bash
cd .claude/skills/yt-video-summarizer/
yt-dlp --cookies-from-browser chrome --cookies /tmp/course-cookies.txt --skip-download <course-url>
node playwright/course-enumerator.mjs "<course-url>" --cookies /tmp/course-cookies.txt --no-headless
python3 scripts/process_course.py "<course-url>" --course-name course-name --dry-run
```
