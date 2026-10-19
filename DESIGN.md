---
name: Pulse
description: A monochrome pixel widget for macOS and Windows, and the one-page site that runs it live.
colors:
  ground: "#090909"
  ground-raised: "#0e0e0e"
  well: "#0f0f0e"
  wallpaper: "#121211"
  pixel-on: "#f2f2ed"
  pixel-mid: "#b3b3ad"
  text-dim: "#8c8c88"
  pixel-dim: "#757573"
  edge-strong: "#4a4a47"
  rule-dotted: "#3a3a37"
  rule: "#303030"
  edge: "#2a2a28"
  pixel-off: "#262626"
typography:
  display-pixel:
    fontFamily: "Pulse 5x7 glyph table (rendered as SVG/canvas squares)"
    fontSize: "84px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "1 empty column per glyph (6-column advance)"
  headline-pixel:
    fontFamily: "Pulse 5x7 glyph table (rendered as SVG/canvas squares)"
    fontSize: "42px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "1 empty column per glyph (6-column advance)"
  lede:
    fontFamily: "Schibsted Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(20px, 2.1vw, 24px)"
    fontWeight: 400
    lineHeight: 1.45
  title:
    fontFamily: "Schibsted Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.005em"
  body:
    fontFamily: "Schibsted Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Schibsted Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.4
  mono:
    fontFamily: "ui-monospace, SF Mono, Cascadia Mono, Menlo, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.7
rounded:
  hair: "2px"
  key: "3px"
  button: "4px"
  control: "6px"
  panel: "8px"
  mini: "10px"
  screen: "12px"
  widget: "14px"
spacing:
  gutter: "clamp(16px, 4vw, 40px)"
  section: "clamp(96px, 13vw, 176px)"
  wrap: "1180px"
  wrap-wide: "1320px"
  widget-pad: "18px"
  widget-width: "320px"
  tile-pad: "10px"
  row-gap: "14px"
components:
  button-primary:
    backgroundColor: "{colors.pixel-on}"
    textColor: "{colors.ground}"
    rounded: "{rounded.button}"
    padding: "0 22px"
    height: "52px"
    typography: "600 15px/1 Schibsted Grotesk"
  button-primary-hover:
    backgroundColor: "#ffffff"
    textColor: "{colors.ground}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.pixel-on}"
    rounded: "{rounded.button}"
    padding: "0 22px"
    height: "52px"
  button-small:
    rounded: "{rounded.button}"
    padding: "0 14px"
    height: "40px"
  segmented-control:
    backgroundColor: "transparent"
    textColor: "{colors.pixel-mid}"
    rounded: "{rounded.control}"
    padding: "3px"
  segmented-control-active:
    backgroundColor: "{colors.pixel-on}"
    textColor: "{colors.ground}"
    rounded: "{rounded.key}"
    height: "40px"
  widget-panel:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.pixel-on}"
    rounded: "{rounded.widget}"
    padding: "{spacing.widget-pad}"
    width: "{spacing.widget-width}"
  widget-panel-mini:
    backgroundColor: "{colors.ground}"
    rounded: "{rounded.mini}"
    padding: "9px 12px"
  widget-tile:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.pixel-on}"
    rounded: "0"
    padding: "{spacing.tile-pad}"
  claude-board:
    backgroundColor: "{colors.ground-raised}"
    rounded: "{rounded.widget}"
    padding: "clamp(24px, 3vw, 40px)"
  command-well:
    backgroundColor: "{colors.well}"
    textColor: "{colors.pixel-on}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  context-menu:
    backgroundColor: "#181817"
    textColor: "{colors.pixel-on}"
    rounded: "{rounded.panel}"
    padding: "6px"
  context-menu-item-hover:
    backgroundColor: "{colors.pixel-on}"
    textColor: "{colors.ground}"
    rounded: "{rounded.button}"
    height: "34px"
---

# Design System: Pulse

## Overview

**Creative North Star: "Lit Pixels on a Dark Panel"**

Pulse is one object drawn the same way everywhere: a near-black panel where information exists only as lit squares. The widget (SwiftUI on macOS, WPF on Windows, canvas on the site) and the marketing page share one palette, one 5×7 glyph table and one set of pixel instruments. A value is either lit, dim or off; there is no colour, no gradient fill, no icon set. Hierarchy comes from pixel scale and brightness, not hue.

The site treats the widget as the hero and the page as its desktop. Display type is the widget's own font, set at large dot sizes; the real reading text is a quiet grotesk in grey so the pixels stay the loudest thing on screen. Density is generous on the page (big section gaps, one idea per section) and tight inside the widget (18px padding, 14px row rhythm, 1px rules).

Motion is ambient and small: a scanner stepping across the header, a breathing live pixel, a faint CRT band sweeping down, bars tweening a segment at a time. All of it stops under reduced motion, and the Mini size has none at all.

**Key Characteristics:**
- Monochrome: one warm off-white for "on", greys for everything else, near-black ground.
- The 5×7 glyph table is the display face on both the widget and the site.
- Segmented bars, pixel sparklines, per-core meters, week charts and dotted rules are the only data marks.
- 3px scanlines over every dark surface.
- Real text for content, pixel rendering for display and data.

## Colors

A strictly achromatic, faintly warm palette: every value is a step on one grey line from #090909 to #f2f2ed.

### Primary
- **Phosphor White** (pixel-on): the lit pixel. Glyphs, lit bar segments, headings, links, the primary button fill, the active segment of a toggle, focus rings and text selection. Anything that is "on".

### Neutral
- **Panel Black** (ground): the page background and the widget panel. Also `theme-color`.
- **Raised Black** (ground-raised): the one raised card on the page (the Claude Code board).
- **Well Black** (well): recessed code and command wells.
- **Dither Grey** (wallpaper): the base of the simulated desktops and the size stage, under a 4×4 ordered-dither dot pattern at 9% white.
- **Steel Grey** (pixel-mid): body copy on the site; secondary pixel text in the widget (clock, network up-rate, tile subtitles, past days in the week chart at 75%).
- **Caption Grey** (text-dim): small real text only (meta lines, captions, figcaptions, metric descriptions, footer). 5.9:1 on ground.
- **Ash** (pixel-dim): pixel ink only: widget labels, detail lines, the half-lit leading segment of a bar. Never used for real text.
- **Strong Edge** (edge-strong): ghost-button and star-button borders, step-number boxes, the source-disclosure box.
- **Rule Grey** (rule): hairline dividers on the site, the widget's dotted rule and tile borders.
- **Dotted Edge** (rule-dotted): the site's 1px dotted rules (gestures) and the context-menu border.
- **Chrome Edge** (edge): 1px borders on the simulated screens, windows and stage.
- **Unlit** (pixel-off): unlit bar segments, sparkline baselines, core-meter tracks, star-count chips on dark buttons.

### Named Rules
**The Lit-or-Not Rule.** State is expressed by brightness alone: on, mid, dim, off. Hot temperature is shown by the last lit segment blinking to off, never by a warning colour.

**The Two Dims Rule.** Ash (pixel-dim) is for pixel ink; Caption Grey (text-dim) is for real small text. Ash fails body-text contrast and must not be promoted to prose.

## Typography

**Display Font:** the Pulse 5×7 glyph table (`site/glyphs.js`, generated from `macos/Pulse.swift`), rendered as crisp SVG rects on the site and as filled squares on canvas/SwiftUI/WPF.
**Body Font:** Schibsted Grotesk (variable 400 to 900, self-hosted woff2, with ui-sans-serif, system-ui fallback)
**Label/Mono Font:** system monospace stack, for code, commands, counts and step numbers.

**Character:** a hand-made bitmap face doing all the shouting, set against a calm, slightly condensed grotesk that reads like documentation.

### Hierarchy
- **Display pixel** (dot 12px, 7 rows = 84px cap height): the hero headline only, two lines, uppercase. The closing headline uses dot 11px.
- **Headline pixel** (dot 6px = 42px): every section heading. Big numbers on the Claude board use dot 9px; stats dot 3px; nav wordmark and metric keys dot 2.5px.
- **Lede** (400, clamp(20px, 2.1vw, 24px), 1.45): the hero pitch, max 34ch. Section intros are 20px/1.5 at 46ch.
- **Title** (600, 18px, 1.35): metric names and gesture leads. Fact headings 20px, install column headings 24px.
- **Body** (400, 18px, 1.6, Steel Grey): prose, max 52 to 58ch.
- **Label** (400, 13 to 15px, Caption Grey): meta lines, captions, fine print, board labels.
- **Mono** (12.5px/1.7): JSON excerpt; commands 13px/1.5; counts 600 12px with tabular numerals.

Pixel scale inside the widget: scale 1 for labels and details, 1.5 for clock, stats and Mini values, 2 for section titles and tile values, 3 for hero numbers. At scale 3 and above each dot shrinks by 0.75 so the gaps show; on the site, dots of 6px and up get a gap of 12% of the dot. Glyph advance is always 6 columns (5 lit + 1 blank); line gap is 3 dots.

### Named Rules
**The Real-Text-Behind-Pixels Rule.** Every pixel heading carries a visually hidden real-text twin, and the pixel SVG is `aria-hidden`. Pixels are display and data; prose is always real text.

**The Uppercase-Only-In-Pixels Rule.** The glyph table is uppercase; real text is sentence case. Do not uppercase the grotesk to imitate it.

## Layout

Single column of sections inside a 1180px wrap with a fluid gutter (16px to 40px); the hero desktops break out to a 1320px wide wrap. Sections are separated by one large fluid gap (96px to 176px) and no background bands: the ground never changes, only hairline rules and the occasional raised board divide space.

Section patterns, as built:
- **Hero:** full-width two-line pixel headline; below it a two-column row of lede (left) and CTAs (right, bottom-aligned); then two simulated desktops at 50/50 with a gap of 16px to 32px.
- **Vitals:** sticky widget column (max 400px, sticky at 96px) beside a ruled list; each list row is a 64px key column plus text.
- **Sizes:** heading and intro side by side, then a full-width stage (clamp(520px, 62vw, 760px) tall) that is itself a desktop, then controls, then a three-column gesture list with dotted top rules.
- **Claude Code:** sticky board (1.05fr) beside facts and a code figure (1fr).
- **Install:** two equal columns with a top rule each, numbered steps.
- **Close:** centred pixel headline, sentence and CTA row.

Responsive behaviour:
- 900px: vitals, sizes head and Claude grid collapse to one column; sticky elements become static; the vitals widget moves below the list and centres.
- 860px: hero copy stacks; the two desktops become one desktop with a macOS/Windows tab toggle above it; the screen aspect changes from 16:11 to 4:5 and the widget centres in it; install collapses.
- 760px: nav section links hide (brand and Star remain); gestures stack.
- 640px: footer stacks.
- 520px: closing CTAs go full-width and stacked; the JSON block keeps its real shape and scrolls sideways with a right-edge fade.
- Pixel headings fit their container: the dot size is reduced in 0.25px steps (minimum 1.5px) so a line never overflows.

Widget layout: 320px wide with 18px padding in Full and Compact; vertical stack at 14px (Full) or 12px (Compact) with a dotted rule between every group; hero rows put label and detail left, a sparkline and a 70px right-aligned number right, and the meter full-width below; tiles sit in a 2×2 grid with 8px gaps. Mini is a single line, 9px by 12px padding, with fixed-width value slots so digits never shift the window.

## Elevation & Depth

Flat, dark and tonal. Depth on the page comes from the ground stepping a few points lighter (ground, raised, well, wallpaper) and from 1px edges, not from shadows on content. Shadows exist only on things that are objects on a desktop: the simulated screens, app windows, the widget itself and the context menu. The sticky nav gains a hairline and soft shadow only after scrolling.

### Shadow Vocabulary
- **Screen bezel** (`0 30px 60px -30px rgba(0,0,0,0.9), 0 0 0 6px #111110, 0 0 0 7px #232321`): the simulated monitors only.
- **Window lift** (`0 24px 40px -18px rgba(0,0,0,0.85)`): fake app windows on the desktops.
- **Widget drop** (`filter: drop-shadow(0 18px 24px rgba(0,0,0,0.6))`, 0 22px 30px 0.7 on the stage): the live widget canvas.
- **Menu** (`0 18px 40px -12px rgba(0,0,0,0.9)`): the context menu.
- **Nav scrolled** (`0 1px 0 #303030, 0 10px 24px -12px rgba(0,0,0,0.8)`): sticky header after 8px of scroll.

### Named Rules
**The Desktop-Objects-Only Rule.** Only things that would float on a real desktop (screens, windows, the widget, menus) cast shadows. Content cards, lists and buttons stay flat.

**The Scanline Rule.** Every dark surface carries 1px lines every 3px: 1.8% Phosphor White over the whole page (fixed, non-interactive), 2% inside the widget.

## Shapes

Square pixels inside softly rounded containers. Every mark (glyph dot, bar segment, sparkline column, core meter step, week bar, live pip) is a hard-edged rectangle drawn with `crispEdges`; no circles, no anti-aliased curves in data. Containers round in proportion to their size: 2px on chips and the focus ring, 3px on toggle segments and step boxes, 4px on buttons and menu items, 6px on controls and command wells, 8px on menus and code, 10px on the Mini widget, 12px on screens and the stage, 14px on the widget and the Claude board (continuous corners in SwiftUI). Tiles inside the widget are square-cornered boxes with a 1px Rule Grey border.

Dividers come in two forms: solid 1px Rule Grey hairlines between page groups, and the dotted rule (2px on, 2px off, 1px tall) inside the widget, echoed on the page by 1px dotted borders above gestures.

## Components

### Buttons
Solid and certain, the only filled shapes on the page besides lit pixels.
- **Shape:** gently rounded (4px), 52px tall, 1px border always present.
- **Primary:** Phosphor White fill, Panel Black text, 600 15px, 22px side padding, 12px gap to a 14px pixel icon (a 7×7 SVG drawn in the same square-pixel grammar).
- **Ghost / Star:** transparent with a Strong Edge border and Phosphor White text; hover brightens the border to Phosphor White and adds a 6% white wash.
- **Small:** 40px tall, 14px padding, 14px text (nav Star, Options).
- **Hover / Active:** 180ms colour transitions on the house ease; active presses down 1px.
- **Star count:** a mono 12px chip inside the button, tabular numerals, 2px radius, shown only when the live count loads.

### Segmented control (OS toggle, size picker, phone desktop tabs)
- **Style:** 1px Rule Grey outline, 6px radius, 3px inner padding and gap; segments are 40px (44px on the phone tabs), Steel Grey 600 14px.
- **Active:** Phosphor White fill with Panel Black text, 3px radius. Uses `aria-pressed` (or `aria-selected` for the phone tabs, with arrow-key roving).
- **Size icons:** outline rectangles at 16, 9 and 5px tall stand for Full, Compact and Mini.

### Ruled metric list
- Rows separated by 1px Rule Grey, key column of pixel labels at 55% opacity.
- **Lit state** (hover or focus): a left-to-right 5% white wash, the key goes to full opacity, the description brightens from Caption Grey to Steel Grey, and the widget dims everything except that metric's region (66% black veil with 6px corner brackets). Rows are focusable.

### Claude board
- **Corner Style:** 14px. **Background:** Raised Black with a 1px edge. **Padding:** 24px to 40px.
- Pixel number at dot 9px, stats at dot 3px with captions below in Caption Grey, then a canvas week chart. Sticky on wide screens.

### Command well and code figure
- Well Black, 1px edge, 6px (commands) or 8px (code) radius. Commands wrap anywhere; the Copy button sits in a divided right cell and inverts to Phosphor White on success.
- JSON is greyscale-highlighted: keys Steel Grey, strings a lighter grey, the highlighted `usage` span Phosphor White.

### Context menu
- Near-black at 98%, 1px Dotted Edge border, 8px radius, 6px padding, menu shadow. Items 34px, 500 14px, 30px left inset; a checked item shows a solid 8px square. Hover and focus invert to Phosphor White. Disabled items stay Caption Grey. Arrow keys move, Escape closes and returns focus.

### Navigation
- Sticky 68px bar on the ground colour; brand is the app icon plus the pixel wordmark at dot 2.5px. Section links are Steel Grey 500 15px with 44px hit targets, turning Phosphor White on hover. Links hide below 760px.

### Numbered steps and disclosure
- Steps use a 28px square counter box (3px radius, Strong Edge border, mono 600 13px). The source disclosure uses a 22px box showing a mono plus or minus.

### The Widget (signature component)
The product itself, drawn identically in SwiftUI, WPF and canvas.
- **Panel:** Panel Black, 14px radius (10px in Mini), 1px border of Phosphor White at 16%, scanlines over the top.
- **Header:** PULSE at scale 2, the 8-dot scanner, clock at scale 1.5 in Steel Grey, and a minus/plus at scale 1.5 in Ash. Clicking the header cycles Full, Compact, Mini.
- **Segmented bar:** 28 segments (16 in tiles, 8 in Compact), 2px gaps, 8px tall (5px in tiles, 4px in Compact). Lit segments Phosphor White, unlit Unlit, a leading segment more than 15% filled shows in Ash. Hot temperature blinks the last lit segment off once per tick.
- **Sparkline:** 18 columns, 2px wide with 1px gaps, 18px tall, stacked 2px cells. The top cell of each column fades from 35% to 100% white by age; the body cells use Ash at 12% to 42%. A row of Unlit baseline dots underneath.
- **Core grid:** one 5-step vertical meter per core, 4px gaps, 2px cells with 1px gaps, 15px tall.
- **Week chart:** 7 columns of 8 steps; today Phosphor White, past days Steel Grey at 75%, future days Unlit at 50%; M T W T F S S labels at scale 1 with today lit.
- **Tile:** label at scale 1 in Ash, value at scale 2, sub-line at scale 1 in Steel Grey; 10px padding, 1px Rule Grey square border.
- **Live pip:** a 4px square breathing between 30% and 100% opacity.
- **Sizes:** Full (header, CPU/MEM/TMP/DSK hero rows, 2×2 tiles, Claude section, thermal and uptime footer), Compact (header and four columns of label, number and 8-segment bar, plus a one-line Claude tally), Mini (one quiet line of CPU, MEM, TMP with a static 4px pip, no scanner and no sweep).

### Motion
- **House ease:** cubic-bezier(0.16, 1, 0.3, 1) for every site transition; durations 120ms (press), 160 to 200ms (hover, colour), 260ms (quit fade with 6px blur).
- **Headline assembly:** the hero headline only, once per load: each dot fades and drops 2px over 420ms with a randomised stagger of up to about 0.6s.
- **Widget loops:** scanner step 0.16s (0.07s when hot) with a 3-dot trail at 90/50/25%; live pip 1.3s breathe; CRT band 80px tall at 4% white sweeping every 9s; bars tween 0.45s ease-out and only animate when a segment changes; the weekly total counts up over 1.2s. The site drives ambient loops at 12fps and pauses widgets that are off screen.
- **Terminal caret:** 1.1s stepped blink.

## Do's and Don'ts

### Do:
- **Do** draw every display word and every data mark from the 5×7 glyph table and square cells; keep the 6-column advance and 3-dot line gap.
- **Do** pair each pixel heading with a visually hidden real-text twin and mark the pixels `aria-hidden`.
- **Do** express state through brightness steps (on, mid, dim, off) and the blink-to-off for hot.
- **Do** keep real text in Schibsted Grotesk at Steel Grey for body and Caption Grey for small text; reserve Phosphor White for headings, links, emphasis and lit pixels.
- **Do** lay faint 3px scanlines over dark surfaces and use dotted rules between widget groups.
- **Do** honour reduced motion everywhere: smooth scroll off, no headline assembly, no caret blink, widget loops frozen (scanner parked, pip held at 85%, no sweep).
- **Do** keep focus visible as a 2px Phosphor White outline at 3px offset, hit targets at 40px or more (44px for nav links and phone tabs), and keyboard paths for tabs (arrows) and menus (arrows, Escape).
- **Do** label any simulated widget or chart as synthetic data.

### Don't:
- **Don't** introduce a hue. No accent colour, no red for hot, no green for good.
- **Don't** use Ash (pixel-dim) for real text; it is pixel ink only.
- **Don't** render prose, descriptions or instructions in the pixel font, and don't uppercase the grotesk.
- **Don't** put shadows on content cards, lists or buttons; shadows belong to desktop objects only.
- **Don't** add motion to the Mini size or loops that run under reduced motion.
- **Don't** draw data with anti-aliased curves, gradients or rounded marks; bars, sparklines and meters are square cells.
