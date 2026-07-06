# Sprint 9.2 - Professional Widget UX Audit

## Status

Steps 2.0, 2.1, 2.2, and 2.3 are complete.

Sprint 9.2 is focused on product experience only. The architecture from Sprint 9.1 should remain intact.

Primary rule:

```text
No architectural changes.
```

The widget should consume the existing SDK, configuration, state, event, theme, API, session, analytics, and build layers. UX work should improve the visual and interaction quality without moving responsibilities back into components.

## Product Experience Goal

ASK Vera should feel like a polished commercial assistant:

- trustworthy
- calm
- branded without feeling heavy
- fast
- readable
- accessible
- mobile friendly
- easy to embed in enterprise websites

The target experience should be closer to enterprise chat products such as ChatGPT, Copilot, Intercom, Zendesk AI, Drift, HubSpot Chat, and Salesforce Einstein Copilot. The goal is not to copy any one product. The goal is to adopt familiar interaction patterns users already understand.

## Current UX Summary

The current widget is functional and structurally strong, but visually it still feels like an early product implementation.

Strengths:

- Clear floating launcher.
- Strong brand header.
- Working region and language selector.
- Consent-first flow.
- Dynamic legal documents.
- Message rendering supports basic markdown.
- API errors and loading states exist.
- Theme tokens and CSS variables are already in place.

Main gaps:

- Visual density is uneven.
- Header lacks assistant identity and online state.
- Chat messages need stronger hierarchy, spacing, timestamps, and actions.
- Input needs a more modern composer experience.
- Loading state is basic.
- Empty state is not yet a strong guided onboarding moment.
- Mobile sizing and keyboard behavior need more attention.
- Error state needs clearer recovery actions.
- Icons and actions are currently text/symbol based rather than a polished control system.

## Screen Audit

### Launcher

Current:

- Circular launcher with first brand letter.
- Good fixed position.
- Simple hover lift.

Friction:

- Does not communicate "AI assistant" clearly enough.
- No unread/status indicator.
- No tooltip or expanded label.
- Brand mark is generic.

Target:

- Branded assistant launcher.
- Optional label on hover or desktop.
- Online/available dot.
- Smooth open animation.
- Configurable launcher icon or logo.

Keep:

- Floating bottom-right default.
- Circular control.
- Configurable aria label.

### Widget Shell

Current:

- Fixed panel.
- Strong shadow.
- Rounded corners.
- Header/body/footer structure exists.

Friction:

- Panel height is rigid.
- Body padding is large in some areas and tight in others.
- Success banner can visually crowd the top area.
- Mobile panel is usable but not yet refined for safe areas or keyboard behavior.

Target:

- More intentional shell sizing.
- Softer professional elevation.
- Clear internal layout rhythm.
- Better separation between header, conversation, and composer.
- Mobile full-height mode with safe-area handling.

Keep:

- Floating panel behavior.
- Theme-driven panel dimensions.
- Existing component structure.

### Header

Current:

- Brand name centered.
- Menu and close controls.
- Selected country subtitle is hidden by CSS.

Friction:

- No assistant identity.
- No availability indicator.
- Actions are visually minimal.
- Brand title is elegant but not enough for an assistant product.
- Menu/close symbols have encoding artifacts in source and should become proper icons.

Target:

```text
Logo / Brand
AI Assistant label
Online indicator
Menu
Minimize
Close
```

Keep:

- Brand presence.
- Menu action.
- Close action.

### Region And Language Selector

Current:

- Two select controls in a bordered panel.
- Works with dynamic backend config.

Friction:

- Looks like a form block rather than part of a conversational setup.
- Select dropdowns are plain.
- No short helper text explaining why locale matters.
- Long country lists are hard to scan in native select.

Target:

- Compact locale row in setup state.
- Clear labels.
- Better select visual polish.
- Optional future searchable selector if country list remains large.

Keep:

- Dynamic countries and languages.
- Backend-driven options.
- Accessibility through labels.

### Consent Screen

Current:

- Clear consent card.
- Legal links listed one per line.
- Required acknowledgement checkbox.
- Accept disabled until acknowledged.

Friction:

- Card is functional but not yet premium.
- The card competes visually with the region selector.
- Text hierarchy could be clearer.
- Error and saving states could feel more polished.

Target:

- Calm legal onboarding card.
- Strong title, short explanation, legal document list, acknowledgement, actions.
- Inline success/error feedback.
- Better spacing and button hierarchy.

Keep:

- One required checkbox.
- Legal documents loaded dynamically.
- Accept disabled until checked.
- "Not Now" path that does not allow chat.

### Legal Documents

Current:

- Links open legal content.
- Backend provides HTML through `/api/privacy`.

Friction:

- Legal document reading experience should feel more like a controlled modal or focused legal page.
- Long documents need readable width and typography.

Target:

- Dedicated legal viewer layout.
- Clear title.
- Readable typography.
- Sticky close/back action.
- No raw HTML/JSON display.

Keep:

- Backend-owned legal content.
- Frontend should not hardcode legal copy.

### Welcome And Empty State

Current:

- Welcome text appears as a system message.
- Suggested topics are shown as pills.

Friction:

- The opening moment feels more like content than an intentional onboarding screen.
- Suggested topics are useful but not yet grouped or prioritized.
- No visual assistant identity.

Target:

```text
Welcome
Short assistant promise
Suggested questions
Recent/helpful topics
Start conversation
```

Keep:

- Config-driven welcome text.
- Config-driven topics.

### Chat Screen

Current:

- User bubbles are visible.
- Assistant messages are mostly plain text with basic markdown.
- No avatars, timestamps, or message actions.

Friction:

- Assistant content can feel like a long paragraph wall.
- No copy action.
- No feedback controls.
- No citation expansion.
- No retry path on failed assistant response.
- Message roles are not visually rich.

Target:

- Assistant avatar or identity label.
- User and assistant bubble rhythm.
- Timestamps or subtle metadata.
- Better markdown rendering.
- Copy button.
- Like/dislike feedback.
- Retry action.
- Citation area when sources exist.

Keep:

- Existing `MessageFeed` component boundary.
- Optional custom `renderMessages`.

### Composer

Current:

- Single-line input.
- Send button displayed as an up arrow through CSS.
- Disabled while loading or before consent.

Friction:

- Single-line input limits longer questions.
- Send control is functional but not polished.
- No keyboard shortcut hints.
- No attachment or microphone placeholders.
- Disabled state could explain why input is disabled.

Target:

- Auto-resizing textarea.
- Clear send button.
- Enter to send, Shift+Enter for newline.
- Optional attachment and microphone placeholders.
- Better focus state.
- Smooth send animation.

Keep:

- Consent-aware disabled behavior.
- Existing `onSendMessage` contract.

### Loading And Typing

Current:

- Spinner with loading text.

Friction:

- Feels generic.
- Does not communicate assistant typing well.

Target:

- Typing dots.
- Skeleton or progressive response placeholder.
- Reduced-motion fallback.
- Loading copy controlled by config.

Keep:

- Config-driven loading text.

### Error State

Current:

- Backend demo can append warning/error messages.
- Consent errors show inside consent panel.

Friction:

- Errors can blend into chat history.
- Recovery actions are not always obvious.
- Repeated warnings can clutter history.

Target:

```text
We're having trouble connecting.
Retry
Contact support
```

Use contextual, non-alarming language. Errors should provide next action.

Keep:

- Existing API error classification.
- Existing event/audit flow.

### Menu

Current:

- Settings/history/new chat style menu exists.

Friction:

- Menu is simple and visually light.
- No icons.
- No active states.
- Needs clearer separation between safe and destructive actions.

Target:

- Compact action menu.
- Icons.
- Clear labels.
- Divider groups.
- Future room for feedback/export/debug actions.

Keep:

- Config-driven labels.
- Existing callbacks.

### Mobile View

Current:

- Panel width adjusts below 520px.
- Region selector becomes single column.

Friction:

- Needs full mobile interaction pass.
- Composer and keyboard overlap should be considered.
- Safe areas are not explicit.
- Scrolling could become awkward with long legal documents.

Target:

- Nearly full-screen mobile panel.
- Safe-area-aware bottom composer.
- Touch-friendly controls.
- Stable scrolling.
- No layout jumps when keyboard opens.

Keep:

- Responsive breakpoints.

### Accessibility

Current:

- Several aria labels exist.
- Message feed uses `role="log"` and `aria-live`.
- Focus states exist.

Friction:

- Icon-only controls need stronger accessible labels and visible tooltips.
- Reduced motion is not yet formalized.
- Color contrast should be checked after visual updates.
- Keyboard flow should be audited across open, selector, consent, chat, menu, and close.

Target:

- Full keyboard path.
- Visible focus ring.
- Reduced motion support.
- Clear landmarks.
- Screen-reader-friendly state updates.
- No contrast regressions.

## Benchmark Pattern Summary

Common enterprise assistant patterns worth adopting:

- Clear assistant identity in the header.
- Availability/online indicator.
- Guided empty state.
- Suggested prompts.
- Conversation-first message hierarchy.
- Message actions on assistant responses.
- Copy and feedback controls.
- Friendly recoverable errors.
- Smooth but restrained motion.
- Strong keyboard accessibility.
- Mobile-first composer behavior.
- Build/version diagnostics for support teams.

Patterns to avoid:

- Overly decorative visuals that reduce readability.
- Large marketing-style hero text inside the widget.
- Animations that slow the user down.
- Hardcoded brand content.
- Excessive cards inside cards.
- Chat history cluttered with repeated system warnings.

## Sprint 9.2 UX Principles

1. Preserve architecture.
2. Use existing theme tokens and config.
3. Keep all content config/backend-driven.
4. Improve hierarchy before adding decoration.
5. Prefer restrained enterprise polish.
6. Make every state recoverable.
7. Keep mobile and accessibility in every step.
8. Avoid new dependencies unless clearly justified.

## Recommended Implementation Order

### Step 2.1 - Visual Design System

Create consistent visual primitives:

- 8px spacing system
- typography scale
- icon sizes
- radius scale
- elevation scale
- motion timings
- button styles
- input styles
- card styles

Expected files:

```text
src/styles/
src/themes/
```

Status: complete.

Implementation files:

```text
src/styles/
  animations.css
  buttons.css
  cards.css
  forms.css
  index.css
  layout.css
  spacing.css
  tokens.css
  typography.css
  utilities.css
```

The design system now defines:

- 4/8/12/16/20/24/32/40/48/64 spacing scale
- typography roles for display, title, heading, body, caption, and label
- icon sizes
- radius scale
- elevation scale
- motion timings
- control heights
- focus outline
- button foundations
- card foundations
- form foundations
- reduced-motion behavior
- screen-reader utility

`generic-widget.css` now imports `src/styles/index.css` and consumes these design tokens for key widget surfaces.

No component behavior changed.

### Step 2.2 - Widget Shell

Polish:

- panel sizing
- shadows
- border radius
- body spacing
- footer/composer placement
- mobile shell behavior

Status: complete.

Implementation file:

```text
src/generic-widget/generic-widget.css
```

Shell improvements:

- intentional panel height with min/max viewport constraints
- softer bordered enterprise panel edge
- standardized panel radius and elevation
- header separated from body with a subtle boundary
- content area uses the design-system spacing scale
- composer separated from conversation with a border and soft top shadow
- composer padding accounts for mobile safe-area inset
- success banner is smaller, softer, and less visually dominant
- mobile panel uses more available viewport space
- very small screens can use a full-height, edge-to-edge panel

No component behavior changed.

### Step 2.3 - Header

Add:

- assistant label
- online indicator
- better action buttons
- optional minimize control
- cleaner icon handling

Status: complete.

Implementation files:

```text
src/generic-widget/Header.tsx
src/generic-widget/GenericWidgetWrapper.tsx
src/generic-widget/generic-widget.css
src/generic-widget/types.ts
src/generic-widget/examples/foreverDemoConfig.tsx
```

Header improvements:

- assistant identity is now separate from brand identity
- optional `assistantName`, `assistantSubtitle`, `logoUrl`, and `statusLabels` config fields
- existing connection state drives the visible online/reconnecting/offline status
- header includes a brand/assistant mark area
- title, subtitle, and status have clearer hierarchy
- menu and close controls use SVG icon buttons instead of text symbols
- icon controls retain accessible labels and keyboard focus states
- mobile header hides lower-priority metadata to avoid cramped layout

No new state layer was introduced.

### Step 2.4 - Message Experience

Improve:

- assistant message layout
- user bubble style
- avatars/identity
- timestamps
- copy action
- feedback placeholders

### Step 2.5 - Composer

Improve:

- textarea behavior
- send state
- keyboard shortcuts
- disabled explanations
- attachment/microphone placeholders

### Step 2.6 - Loading And Typing

Replace generic spinner with:

- typing dots
- skeleton
- progressive loading state
- reduced-motion support

### Step 2.7 - Empty State

Create a guided welcome state:

- assistant intro
- suggested topics
- starter prompts
- config-driven content

### Step 2.8 - Mobile

Refine:

- safe areas
- full-screen panel behavior
- touch targets
- scrolling
- composer stability

### Step 2.9 - Accessibility

Audit and improve:

- keyboard navigation
- ARIA
- focus
- contrast
- reduced motion

### Step 2.10 - Error Experience

Create recoverable error UI:

- connection issue
- retry action
- support action
- no repeated warning clutter

### Step 2.11 - Message Actions

Add:

- copy
- thumbs up/down
- retry
- future share placeholder

### Step 2.12 - Rich Rendering

Add:

- improved markdown
- tables
- links
- code blocks
- citation areas

### Step 2.13 - Animations

Add restrained motion:

- panel open/close
- hover
- send
- receive
- typing

### Step 2.14 - Branding

Ensure:

- logo support
- font support
- color support
- launcher support
- brand name support

### Step 2.15 - Final Polish

Remove:

- spacing inconsistencies
- misaligned icons
- overflow
- layout shift
- abrupt transitions

## Definition Of Done For Sprint 9.2

Sprint 9.2 is complete when:

- The widget looks professional on desktop and mobile.
- The welcome, consent, chat, loading, error, and legal states are polished.
- Message rendering supports common enterprise formatting.
- The composer feels modern and smooth.
- Keyboard and screen-reader basics are verified.
- No architecture boundaries are broken.
- `npm run typecheck` passes.
- `npm run build` passes.

## Architecture Boundaries To Preserve

- No direct `fetch()` outside `src/api`.
- No direct browser storage outside `src/storage`.
- No analytics logic inside visual components.
- No hardcoded legal, country, language, or product content.
- No backend calls from the wrapper shell except through API services.
- No brand-specific assumptions inside generic components.
- No new global state outside the state layer.

## Step 2.0 Conclusion

The current widget has the right foundation. Sprint 9.2 should not rebuild it.

The next move is Step 2.1: define and apply a visual design system that makes every subsequent UI change consistent.
