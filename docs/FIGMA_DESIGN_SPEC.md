# Nidin BOS — Figma Design Spec

Use this document to set up your Figma design system and redesign pages.

---

## 1. Color Styles (Create in Figma)

### Light Mode

| Style Name | Hex | Usage |
|------------|-----|-------|
| bg | `#F5F5F7` | Page background |
| surface | `#FFFFFF` | Cards, panels |
| surface-alt | `#FBFBFD` | Agent chat bubbles, alt backgrounds |
| line | `#D2D2D7` | Borders |
| line-soft | `#E8E8ED` | Subtle dividers |
| text | `#1D1D1F` | Primary text |
| text-secondary | `#424245` | Secondary text |
| text-muted | `#6E6E73` | Labels, hints |
| text-faint | `#86868B` | Disabled, captions |
| brand | `#007AFF` | Primary action, links |
| brand-hover | `#0062CC` | Button hover |
| brand-soft | `#007AFF` 8% | Selected backgrounds |
| ok | `#34C759` | Success |
| ok-soft | `#34C759` 8% | Success background |
| warn | `#FF9F0A` | Warning |
| warn-soft | `#FF9F0A` 8% | Warning background |
| danger | `#FF3B30` | Error |
| danger-soft | `#FF3B30` 8% | Error background |
| info | `#5856D6` | Info/purple |
| info-soft | `#5856D6` 8% | Info background |

### Dark Mode

| Style Name | Hex | Usage |
|------------|-----|-------|
| bg | `#000000` | Page background |
| surface | `#1C1C1E` | Cards, panels |
| surface-alt | `#2C2C2E` | Agent chat bubbles |
| line | `#38383A` | Borders |
| line-soft | `#2C2C2E` | Subtle dividers |
| text | `#F5F5F7` | Primary text |
| text-secondary | `#A1A1A6` | Secondary text |
| text-muted | `#8E8E93` | Labels |
| text-faint | `#636366` | Disabled |
| brand | `#0A84FF` | Primary action |
| brand-hover | `#409CFF` | Button hover |
| ok | `#30D158` | Success |
| warn | `#FF9F0A` | Warning |
| danger | `#FF453A` | Error |
| info | `#5E5CE6` | Info |

### Sidebar Colors

| Style Name | Light | Dark |
|------------|-------|------|
| sb-bg | `#FFFFFF` 72% | `#1C1C1E` 88% |
| sb-text | `#86868B` | `#98989D` |
| sb-text-hover | `#1D1D1F` | `#F5F5F7` |
| sb-active-bg | `#007AFF` 8% | `#007AFF` 15% |
| sb-active-text | `#007AFF` | `#0A84FF` |

---

## 2. Typography (Create as Text Styles)

**Font:** Inter (Google Fonts) — fallback: SF Pro Display, system-ui

| Style Name | Size | Weight | Case | Tracking | Usage |
|------------|------|--------|------|----------|-------|
| Page Title | 18px (1.15rem) | 700 | Normal | 0 | Page headings |
| Card Header | 11px (0.68rem) | 600 | UPPERCASE | 0.08em | Card/section titles |
| Tab Label | 12px (0.76rem) | 600 | Normal | 0 | Tabs |
| Body | 13px (0.8rem) | 400 | Normal | 0 | Table cells, general |
| Chat Message | 13px (0.84rem) | 400 | Normal | 0 | Chat bubbles |
| Button | 12px (0.78rem) | 600 | Normal | 0 | All buttons |
| Input | 12px (0.78rem) | 400 | Normal | 0 | Form inputs |
| Label | 11px (0.72rem) | 600 | UPPERCASE | 0.04em | Form labels |
| KPI Value | 19px (1.2rem) | 700 | Normal | 0 | Big numbers (tabular nums) |
| KPI Label | 10px (0.62rem) | 600 | UPPERCASE | 0.08em | Metric captions |
| Table Header | 10px (0.65rem) | 600 | UPPERCASE | 0.05em | Column headers |
| Toast | 12px (0.78rem) | 500 | Normal | 0 | Notifications |
| Badge | 10px (0.6rem) | 600 | UPPERCASE | 0.04em | Tags, pills |

---

## 3. Spacing Scale

| Token | Value | Figma |
|-------|-------|-------|
| sp-1 | 4px | Use for tight gaps |
| sp-2 | 8px | Icon padding, small gaps |
| sp-3 | 12px | Card internal padding |
| sp-4 | 16px | Standard padding |
| sp-5 | 20px | Section spacing |
| sp-6 | 24px | Panel padding |
| sp-7 | 32px | Large gaps |
| sp-8 | 40px | Page margins |

---

## 4. Elevation (Drop Shadows)

| Token | Shadow | Usage |
|-------|--------|-------|
| shadow-sm | `Y:1 B:3 #000 4%` + `Y:1 B:2 #000 2%` | Cards, inputs |
| shadow | `Y:2 B:8 #000 6%` | Elevated cards |
| shadow-md | `Y:4 B:16 #000 8%` | Dropdowns, popovers |
| shadow-lg | `Y:12 B:40 #000 12%` | Modals |

---

## 5. Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| radius-sm | 8px | Buttons, inputs, badges |
| radius | 12px | Cards, panels, modals |
| radius-lg | 16px | Large containers |
| radius-full | 999px | Pills, avatars |

---

## 6. Components to Build in Figma

### 6a. Sidebar (Icon Rail)

```
┌──────┐
│  N   │  ← Brand icon (gradient: #007aff → #5856d6, 28px circle)
├──────┤
│  ⊞   │  Dashboard
│  💬  │  Agent Chat
│  💡  │  Strategy
│  ☑   │  Tasks
│  📁  │  Projects
│  👤  │  Contacts
│  💰  │  Finance
│  🔌  │  Integrations
│  🔔  │  Notifications
├──────┤
│  📖  │  Docs
│  🌙  │  Theme
│  A   │  Avatar (user initial)
│  →   │  Logout
└──────┘

Width: 64px
Icon size: 18px
Item size: 40x40px
Active: brand-soft bg + brand text
Hover: bg + text
Tooltip: appears right on hover
```

**Variants:** Default, Hover, Active

### 6b. Card

```
┌─────────────────────────┐
│ CARD HEADER              │  ← 11px, uppercase, text-faint
├─────────────────────────┤
│                         │
│  Card content here      │  ← 13px, text
│                         │
└─────────────────────────┘

Background: surface
Border: none (use shadow-sm)
Radius: 12px
Padding: 12-16px
```

**Variants:** Stat Card, Widget Card, Panel Card (full height), Chat Card

### 6c. Stat Card

```
┌─────────────────────────┐
│ REVENUE          ▲ 12%  │
│ $24,500                 │
│ ██ ██ ▓▓ ▒▒ ▒▒ ░░ ░░   │  ← mini bar chart
└─────────────────────────┘
```

### 6d. Health Ring

```
    ╭───╮
   │ 84 │   ← Large number center
    ╰───╯
   ◠◡◠◡◠    ← SVG circle progress (ok color)
```

### 6e. Button

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Primary   │   │  Secondary  │   │    Ghost    │
└─────────────┘   └─────────────┘   └─────────────┘
  brand bg          surface bg        transparent
  white text        text-muted        text-muted
  no border         line border       no border
```

**Sizes:** Default (padding 6px 14px), Small (padding 4px 8px)
**States:** Default, Hover, Disabled
**Special:** Danger (red bg), Success (green bg)

### 6f. Input

```
┌─────────────────────────────┐
│ Placeholder text...         │
└─────────────────────────────┘

Background: bg
Border: 1px line
Radius: 12px
Padding: 6px 10px
Focus: border → brand, ring → focus-ring
```

**Variants:** Text, Textarea, Select, Search (with Ctrl+K badge)

### 6g. Tabs

```
  Dashboard    Agent Chat    Tasks    Finance
  ─────────    ──────────
  (active)     (default)
```

**Active:** brand color text + brand bottom border (2px)
**Default:** text-muted, transparent border

### 6h. Chat Bubble

```
User message (right-aligned):
                    ┌──────────────────┐
                    │ How are sales?   │  ← brand bg, white text
                    └──────────────────┘

Agent message (left-aligned):
┌──────────────────────────────┐
│ Revenue is up 12% this week  │  ← surface-alt bg, text color
└──────────────────────────────┘
```

Radius: 16px (+ 4px on sender corner)
Padding: 10px 14px
Max-width: 75%

### 6i. Toast

```
┌─────────────────────────────────┐
│ ✓  Rule saved successfully.     │  ← ok-soft bg, ok-border
└─────────────────────────────────┘
```

**Variants:** info (brand), success (ok), error (danger), warn (warn)
Position: top-right, stacked
Animation: slide from right

### 6j. Badge / Tag

```
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│  OK    │  │  WARN  │  │  ERR   │  │  INFO  │
└────────┘  └────────┘  └────────┘  └────────┘
 ok-soft     warn-soft   danger-soft  info-soft
 ok text     warn text   danger text  info text
```

Radius: 4px
Padding: 2px 6px
Font: 10px uppercase 600

### 6k. Modal

```
┌──────────────────────────────────┐
│ Modal Title                   ✕  │
├──────────────────────────────────┤
│                                  │
│  Form content / message here     │
│                                  │
├──────────────────────────────────┤
│              Cancel    ■ Save    │
└──────────────────────────────────┘

Width: 420px
Radius: 12px
Shadow: shadow-lg
Overlay: #000 35%
```

### 6l. KPI Row

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ OPEN     │ │ CLOSED   │ │ REVENUE  │ │ HEALTH   │
│ 23       │ │ 156      │ │ $45.2K   │ │ 91%      │
└──────────┘ └──────────┘ └──────────┘ └──────────┘

Grid: repeat(4, 1fr), gap 12px
```

### 6m. Empty State

```
         ┌─────────────────┐
         │   No data yet   │  ← text-faint, centered
         └─────────────────┘
```

### 6n. Mini Trend Chart

```
┌─────────────────────────────┐
│ REVENUE TREND    7D 30D 90D │
│ $24,500  ▲ 12%              │
│  ╱╲    ╱╲                   │
│ ╱  ╲  ╱  ╲  ╱              │  ← SVG polyline (brand stroke)
│╱    ╲╱    ╲╱                │
└─────────────────────────────┘
```

---

## 7. Page Layouts (Frames to Create)

### Frame Sizes
- **Desktop:** 1440 x 900
- **Tablet:** 1024 x 768
- **Mobile:** 375 x 812

### 7a. Dashboard

```
Desktop (1440x900):
┌──┬──────────────────────────────────────────────┐
│  │ ◉ Nidin BOS   Dashboard  Chat  Tasks  Finance│
│  ├──────────────────────────────────────────────┤
│S │  ┌─────────────────────┐  ┌──────────────┐  │
│I │  │    REVENUE    ▲12%  │  │   NEXT UP    │  │
│D │  │    $24,500          │  │  Meeting 2pm │  │
│E │  │    ██ ▓▓ ▒▒ ░░     │  └──────────────┘  │
│B │  ├─────────────────────┤  ┌──────────────┐  │
│A │  │ HEALTH RING   84   │  │  QUICK TASKS │  │
│R │  └─────────────────────┘  │  ☐ Task 1    │  │
│  │  ┌─────────────────────┐  │  ☐ Task 2    │  │
│  │  │ COMPACT CHAT        │  │  ☐ Task 3    │  │
│  │  │ Welcome! Ask me...  │  │  + Add task   │  │
│  │  │ ┌────────────────┐  │  └──────────────┘  │
│  │  │ │ Type here...   │  │                     │
│  │  └─────────────────────┘                     │
└──┴──────────────────────────────────────────────┘
     64px                2fr                  1fr
```

### 7b. Agent Chat (Talk)

```
Desktop (1440x900):
┌──┬──────────────────────────────────────────────┐
│  │ Talk to Agent                                │
│  │ ● Professional  ○ Personal  ○ Entertainment  │
│  ├────────────────────────────┬─────────────────┤
│S │ LIVE CONVERSATION          │ TODAY SNAPSHOT   │
│I │                            │ ┌─────┬─────┐   │
│D │  How are sales today?   →  │ │ 12  │  3  │   │
│E │                            │ │Tasks│Appvl│   │
│B │  ← Sales are up 12%...    │ └─────┴─────┘   │
│A │                            │                 │
│R │                            │ LEARNED ABOUT   │
│  │                            │ • Prefers email │
│  │ Provider: [Default ▾]      │                 │
│  │ ┌──────────────────────┐   │ SUGGESTED       │
│  │ │ Tell agent what to..│   │ • Check inbox   │
│  │ └──────────────────────┘   │ • Review tasks  │
└──┴────────────────────────────┴─────────────────┘
```

### 7c. Strategy Workspace

```
Desktop (1440x900):
┌──┬──────────────────────────────────────────────┐
│  │ Strategy Workspace        [Powered by ChatGPT]│
│  │ Deep thinking with ChatGPT...                 │
│  ├──────────────────────────┬───────────────────┤
│S │ STRATEGY DISCUSSION       │ PUSH DECISION     │
│I │                           │ ┌───────────────┐ │
│D │  What's our Q2 plan?  →  │ │ Decision text │ │
│E │                           │ └───────────────┘ │
│B │  ← Here's my analysis... │ [Push Decision]   │
│A │                           │                   │
│R │                           │ STRATEGY RULES    │
│  │                           │ • Rule 1: ...     │
│  │                           │ • Rule 2: ...     │
│  │ ┌────────────────────┐    │ [+ Add Rule]      │
│  │ │ Think out loud...  │    │                   │
│  │ └────────────────────┘    │ WHAT I REMEMBER   │
│  │                           │ • Memory 1        │
│  │                           │                   │
│  │                           │ STRATEGY PROMPTS  │
│  │                           │ [Chip] [Chip]     │
└──┴──────────────────────────┴───────────────────┘
            2fr                       1fr
```

### 7d. Tasks

```
Desktop (1440x900):
┌──┬──────────────────────────────────────────────┐
│  │ Task Inbox                                    │
│  │ ┌──────┐ ┌──────────┐ ┌─────────┐            │
│S │ │ OPEN │ │ HIGH PRI │ │ SOURCES │            │
│I │ │  23  │ │    5     │ │    4    │            │
│D │ └──────┘ └──────────┘ └─────────┘            │
│E │                                               │
│B │ [All] [ClickUp] [GitHub PR] [Issues] [High]  │
│A │                                               │
│R │ ☐ Fix login bug              HIGH  ClickUp   │
│  │ ☐ Review PR #123                   GitHub    │
│  │ ☐ Update docs                      Internal  │
│  │ ☐ Deploy v2.1               HIGH  Internal   │
│  │ ☐ Review email campaign            ClickUp   │
└──┴──────────────────────────────────────────────┘
```

### 7e. Login

```
Desktop (1440x900):
┌─────────────────────────────────────────────────┐
│                                                 │
│                                                 │
│              ┌───────────────────┐              │
│              │       ◉          │              │
│              │    Nidin BOS      │              │
│              │  AI Agent Factory │              │
│              │                   │              │
│              │  Email            │              │
│              │  ┌─────────────┐  │              │
│              │  │             │  │              │
│              │  └─────────────┘  │              │
│              │  Password         │              │
│              │  ┌─────────────┐  │              │
│              │  │             │  │              │
│              │  └─────────────┘  │              │
│              │  ┌─────────────┐  │              │
│              │  │   Sign in   │  │              │
│              │  └─────────────┘  │              │
│              └───────────────────┘              │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 8. Figma Setup Checklist

1. **Create a new Figma file** → "Nidin BOS Design System"
2. **Page 1: Tokens**
   - Add all Color Styles (light + dark)
   - Add all Text Styles
   - Add spacing grid reference
3. **Page 2: Components**
   - Build each component from Section 6 as a Figma Component
   - Add variants (states, sizes, themes)
4. **Page 3: Desktop Layouts**
   - Create frames at 1440x900
   - Assemble pages using your components
5. **Page 4: Mobile Layouts**
   - Create frames at 375x812
   - Stacked single-column layouts
   - Hamburger menu replaces sidebar

---

## 9. Icons

Using **Lucide Icons** — install the Figma plugin "Lucide Icons" to drag and drop the same icons used in production.

Key icons used:
- `layout-dashboard` — Dashboard
- `message-circle` — Agent Chat
- `lightbulb` — Strategy
- `check-square` — Tasks
- `folder-kanban` — Projects
- `contact` — Contacts
- `wallet` — Finance
- `plug` — Integrations
- `bell` — Notifications
- `book-open` — Docs
- `moon` / `sun` — Theme toggle
- `log-out` — Logout
- `send` — Chat send
- `bot` — Agent avatar
- `sparkles` — AI indicator
- `brain` — Strategy panel
- `plus` — Add actions
- `arrow-up` — Trend up

---

## 10. Motion & Animation Reference

| Animation | Duration | Easing | Usage |
|-----------|----------|--------|-------|
| Page enter | 350ms | cubic-bezier(0.4, 0, 0.2, 1) | Fade + slide up |
| Hover | 120ms | ease | Buttons, cards |
| Transition | 200ms | ease | Color changes, borders |
| Toast in | 400ms | ease-out | Slide from right |
| Toast out | 300ms | ease-in | Fade + slide right |
| Spinner | 600ms | linear | Loading indicator |
| Skeleton | 1800ms | ease-in-out | Shimmer gradient |

---

## 11. Responsive Breakpoints

| Breakpoint | Behavior |
|------------|----------|
| > 1024px | Full sidebar + multi-column grids |
| 769-1024px | Sidebar icon rail + reduced columns |
| < 768px | Hidden sidebar + hamburger + stacked layout + 2-col KPI grid |

---

## 12. Redesign Priorities

### Tier 1 — Core Experience
1. **Dashboard** — First impression, KPIs, quick chat
2. **Agent Chat** — Primary interaction surface
3. **Strategy** — New feature, premium feel
4. **Tasks** — Daily workflow
5. **Login** — Brand identity

### Tier 2 — Business Pages
6. Projects, Contacts, Finance, Integrations, Notifications

### Tier 3 — Admin/System
7. Admin, Security, Webhooks, Activity, API Keys, etc.

Start with Tier 1, iterate, then cascade the patterns to Tier 2 and 3.
