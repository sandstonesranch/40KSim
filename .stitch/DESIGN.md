# Warscribe 40K — Adeptus Mechanicus Cogitator Design System

## Purpose and scope

This design system documents the grimdark, industrial interface used across Warscribe 40K, with particular focus on the Roster Builder. It is grounded in the shared styles in `client/src/App.css`, the base styles in `client/src/index.css`, and the React components in `client/src`.

The interface should resemble a field cogitator assembled from blackened steel, brass, and luminous telemetry. Keep the visual treatment functional and restrained: game information is dense, so typography, hierarchy, and status colors must remain legible.

## Design principles

1. **Industrial utility:** Treat controls as mechanical interfaces and content panels as armored data slates.
2. **Readable telemetry:** Use monospace for points, stats, and data-heavy readouts.
3. **Purposeful color:** Gold marks structure and command; toxic green marks active/valid telemetry; blood red marks destructive or critical states.
4. **Angular construction:** Use square geometry and clipped chamfers rather than rounded cards.
5. **Explicit status:** Pair state color with a label or icon; never rely on color alone.
6. **Responsive operation:** Preserve access to controls and data on narrow screens by wrapping and stacking rather than clipping.

## Color tokens

The primary tokens are defined in `client/src/App.css`:

| Token | Value | Role |
|---|---|---|
| `--bg-main` | `#0a0a0c` | Application void and primary canvas |
| `--bg-panel` | `#121216` | Main panels and sidebar surfaces |
| `--border-metal` | `#3a3a3f` | Neutral steel borders and dividers |
| `--border-gold` | `#c4a052` | Brass framing, headings, and command emphasis |
| `--accent-red` | `#8a0303` | Destructive, warning, or critical-action emphasis |
| `--accent-green` | `#4f9300` | Active controls and validated/healthy telemetry |
| `--text-main` | `#d4d4d8` | Primary readable text |
| `--surface-card` | `#18181d` | Card surfaces |
| `--surface-raised` | `#1d1d23` | Raised headers and active panels |
| `--surface-inset` | `#09090b` | Recessed controls and data slots |
| `--text-muted` | `#92929a` | Supporting labels |
| `--accent-green-bright` | `#64bc00` | High-visibility healthy telemetry |
| `--accent-red-bright` | `#b20a0a` | High-visibility critical state |

Use the main green and red sparingly. Gold and steel should frame the interface; large surfaces remain charcoal or near-black.

## Typography

- **Stencil display:** `Black Ops One`, sans-serif, through `--font-stencil`. Use for `h1`–`h4`, primary display titles, and command badges. Headings are uppercase with generous tracking.
- **Cogitator data:** `Share Tech Mono`, monospace, through `--font-mono`. Use for body copy, navigation controls, numerical readouts, points, stats, tables, and labels.
- Import both from Google Fonts in `client/index.html`; retain generic fallbacks so the interface remains usable if the font request fails.
- Use tabular numerals for points and stat readouts so changing values stay aligned.
- Preserve comfortable line height for long rules text.

## Geometry, borders, and texture

- Standard corners are square (`border-radius: 0`); use angled chamfers where a card or control should resemble an armored plate.
- Chamfers should be small (roughly 5–12px) and must not clip text or focus rings.
- Use thin gunmetal borders for secondary grouping and thicker brass borders for high-value frames, especially the Roster Builder top bar and Datacard modal.
- Use left-edge stripes for roster cards: blood red for standard units and brass/gold for a Warlord.
- Buttons should look like mechanical controls: compact, uppercase labels, clear borders, and a 4–6px corner notch.
- Use subtle scanline/repeating-linear gradients and low-opacity brass/red radial glows for texture. Texture must never reduce text contrast.
- Avoid rounded pills, glossy gradients, bright large-area fills, and decorative texture over rules text.

## Shared application navigation

- Use a dark, textured navigation plate with a fine metal divider.
- The Warscribe mark and wordmark sit to the left; navigation links form a row of compact mechanical buttons.
- Inactive links use muted telemetry text. Hover uses steel/brass emphasis.
- The current page is identified by an underline: green for general/navigation and red for Roster Builder or Simulator command surfaces.
- Keep keyboard focus distinct from the active underline.
- At narrow widths, stack the brand and navigation links and let links wrap.

## Home screen

- Present the product name as a large brass stencil heading, with a small monospace system eyebrow and a concise muted description.
- Arrange module cards in a responsive grid for Roster Builder, Codex, and Simulator.
- Each card uses a charcoal surface, metal border, restrained brass/green details, and a short action label.
- Cards are navigation affordances, so preserve clear hover, focus, and click feedback.

## Roster Builder

### Header

- The top bar is a dark, lightly textured armored strip with a **3px brass bottom border**.
- Keep faction/subfaction, detachment, points limit, current total, import, save, and print controls visually grouped.
- Use green monospace telemetry for a healthy points total. Use blood red for an over-limit state and retain the actual total and limit text.
- Inputs are recessed near-black controls with steel borders and visible focus.
- At small widths, stack the header sections and allow controls to wrap.

### Workspace and unit finder

- Desktop layout: a fixed-width left search pane, a flexible roster pane, and an optional advisor panel.
- Use `--bg-panel` for panes and thin steel borders to separate them from the workspace.
- The search input sits above independently scrolling grouped results.
- Group headers use raised charcoal surfaces and a green or brass structural accent.
- Unit rows show unit name and points; points use monospace. Hover lifts contrast without shifting layout.
- Keep expandable categories and their counts easy to scan.

### Current roster

- Place the current roster title and legality status at the top of the right pane.
- Use a quiet, helpful empty state when no units have been added.
- Each unit appears on a dark data-slate card with an angular profile, fine steel border, and left-side field stripe.
- Unit name and model count lead the card. Points, actions, attachment control, wargear, and enhancement are secondary.
- Show Warlord status in gold. Show quantities explicitly for selected wargear.
- Indicate attached leaders on the bodyguard card and provide only legal attachment options.
- Use green for valid roster state and red for violations, with explanatory text in addition to the color.

### Datacard modal

- Center the card over a dark overlay; use a charcoal body, a strong brass frame, angular corners, and an independent scroll region.
- Use a stencil title, compact monospace keywords, and a six-cell stats strip for M, T, SV, W, LD, and OC.
- Stats use Share Tech Mono and green telemetry emphasis; labels use muted gold.
- Keep ranged/melee weapon profiles in compact tables with aligned numeric columns.
- Separate loadout, abilities, attachment options, and wargear with consistent section labels and subtle borders.
- Use brass for section headings, green for interactive/active details, and red only for hazards or destructive actions.
- Keep modal actions at the bottom, with a clear primary action and neutral cancel action.
- On mobile, allow the weapon table to scroll horizontally and stack footer controls.

## Codex

- Preserve the book/archive metaphor while moving it into the cogitator material palette: dark plates, steel dividers, brass book edges, and green active telemetry.
- Faction books use clipped geometry and concise labels.
- Reader tabs use uppercase monospace labels; the active tab receives a green underline.
- Rules and reference panels use near-black or panel backgrounds, readable monochrome text, and brass section headings.
- Long rules remain naturally wrapped with comfortable line spacing.
- At narrow widths, stack reference columns and keep tabs horizontally scrollable.

## Interaction, accessibility, and status

- Buttons, links, inputs, and selects must retain keyboard access and a high-contrast visible focus outline.
- Use text labels and icons alongside green/red state coloring.
- Maintain adequate contrast for muted text; reserve muted color for secondary information, never essential values.
- Disabled controls should remain recognizable, with lower opacity and a disabled cursor.
- Use clear hover states without relying on motion or color alone.
- Chamfer clipping must not obscure labels, focus indicators, or control hit areas.

## Responsive behavior

- At 900px and below, stack the top bar and the main roster/search layout vertically; panes become full width.
- Keep the search pane tall enough to browse results before the roster begins.
- At 700px and below, stack the navigation brand and links and reduce header spacing.
- At 600px and below, tighten modal padding, retain readable stat values, and horizontally scroll wide weapon tables.
- Avoid fixed-width controls that cause horizontal page overflow.

## Implementation references

- Global theme, layout, and component styling: `client/src/App.css`
- Base document sizing and typography fallback: `client/src/index.css`
- Font loading and document metadata: `client/index.html`
- Mechanical navigation: `client/src/components/Navbar.tsx`
- Home module cards: `client/src/pages/Home.tsx`
- Roster builder and Datacard: `client/src/pages/RosterBuilder.tsx`
- Codex screens and reader content: `client/src/pages/codex.tsx`
