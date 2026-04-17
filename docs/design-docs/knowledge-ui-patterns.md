# Knowledge Base UI Patterns - Visual Reference

## Current State (Table View)
```
┌─────────────────────────────────────────────────────────────┐
│ Knowledge Base                                              │
│ Agent-written documentation...                              │
├─────────────────────────────────────────────────────────────┤
│ [Local ▼] [Search...] [All][ADR][Contract][Schema]...      │
├─────────────────────────────────────────────────────────────┤
│ Documents (178) — ~/.claude/knowledge                       │
│ ┌───────┬──────────────────────┬─────────┬──────────┐      │
│ │ Type  │ Title                │ Version │ Created  │      │
│ ├───────┼──────────────────────┼─────────┼──────────┤      │
│ │ raw   │ 100% code coverage...│ v1      │ 1/21/70  │      │
│ │ raw   │ Enforce invariants...│ v1      │ 1/21/70  │      │
│ │ ...   │ ...                  │ ...     │ ...      │      │
│ └───────┴──────────────────────┴─────────┴──────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Proposed State (Card Grid + Sidebar)
```
┌──────────────────────────────────────────────────┬──────────────────────┐
│ Knowledge Base                    [Grid][List]   │                      │
│ Agent-written documentation...                   │                      │
├──────────────────────────────────────────────────┤                      │
│ [Local ▼] [Search...] [All][ADR][Contract]...   │                      │
├──────────────────────────────────────────────────┤  Related Sidebar     │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  (slides in when     │
│ │ [raw]    │ │ [context]│ │ [raw]    │          │   doc selected)      │
│ │ 100% code│ │ Enforce  │ │ Agent dev│          │                      │
│ │ coverage │ │ invarian │ │ environm │          │  ┌────────────────┐  │
│ │ creates..│ │ ts mecha │ │ ents must│          │  │ Selected Doc   │  │
│ │          │ │ nically..│ │ be fast..│          │  │ Title          │  │
│ │ First 100│ │          │ │          │          │  │ [type badge]   │  │
│ │ chars... │ │ First 100│ │ First 100│          │  ├────────────────┤  │
│ │          │ │ chars... │ │ chars... │          │  │ Links to (3)   │  │
│ │ [tag1]   │ │          │ │          │          │  │ ┌────────────┐ │  │
│ │ [tag2]   │ │ [tag1]   │ │ [tag1]   │          │  │ │ Doc A      │ │  │
│ │          │ │ [tag2]   │ │ [tag2]   │          │  │ │ Preview... │ │  │
│ │ → 3 links│ │          │ │          │          │  │ └────────────┘ │  │
│ │ ← 2 back │ │ → 1 link │ │ → 5 links│          │  │ ┌────────────┐ │  │
│ └──────────┘ └──────────┘ └──────────┘          │  │ │ Doc B      │ │  │
│                                                  │  │ │ Preview... │ │  │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │ └────────────┘ │  │
│ │ [raw]    │ │ [raw]    │ │ [adr]    │          │  ├────────────────┤  │
│ │ Parse at │ │ Structure│ │ ADR 001: │          │  │ Referenced by  │  │
│ │ boundari │ │ docs as  │ │ Use Fast │          │  │ (2)            │  │
│ │ es...    │ │ progress │ │ API...   │          │  │ ┌────────────┐ │  │
│ │ ...      │ │ ive...   │ │ ...      │          │  │ │ Doc C      │ │  │
│ └──────────┘ └──────────┘ └──────────┘          │  │ │ Preview... │ │  │
│                                                  │  │ └────────────┘ │  │
│ [Load more...]                                   │  ├────────────────┤  │
│                                                  │  │ Related topics │  │
│                                                  │  │ (5)            │  │
│                                                  │  │ ┌────────────┐ │  │
│                                                  │  │ │ Doc D      │ │  │
│                                                  │  │ │ [tag][tag] │ │  │
│                                                  │  │ └────────────┘ │  │
└──────────────────────────────────────────────────┴──────────────────────┘
```

## Interaction Patterns

### 1. Card Hover Animation (GSAP)
```
Normal State:
┌──────────┐
│ [badge]  │
│ Title    │
│ Excerpt  │
│ [tags]   │
│ → links  │
└──────────┘

Hover State (animated):
┌──────────┐  ← scale(1.02) + shadow
│ [badge]  │
│ Title    │
│ Excerpt  │
│ [tags]   │
│ → links  │
├──────────┤  ← border appears
│ Extended │  ← height: auto
│ preview  │  ← opacity: 0 → 1
│ text...  │  ← 300ms ease-out
└──────────┘
```

### 2. Sidebar Slide Animation
```
Closed:                    Open (animated):
                          ┌──────────────┐
                          │ Related Docs │ ← translateX(100% → 0)
                          │              │   400ms power3.out
                          │ Links to     │
                          │ ┌──────────┐ │
                          │ │ Doc A    │ │
                          │ └──────────┘ │
                          │              │
                          │ Backlinks    │
                          │ ┌──────────┐ │
                          │ │ Doc B    │ │
                          │ └──────────┘ │
                          └──────────────┘
```

### 3. Navigation Flow
```
User Journey:

1. Browse cards in grid
   ↓
2. Hover over card → see extended preview
   ↓
3. Click card → sidebar slides in with related docs
   ↓
4. Click related doc in sidebar → update main view + sidebar
   ↓
5. Traverse knowledge graph via connections
```

## Key UI Components

### Card Component Structure
```tsx
<Card> (hover: scale + shadow)
  <Badge>doc_type</Badge>
  <Title>document title</Title>
  <Excerpt>first 100 chars...</Excerpt>
  <Tags>[tag1] [tag2] [tag3]</Tags>
  <Preview> (hidden, expands on hover)
    next 200 chars...
  </Preview>
  <Connections>
    → 3 links  ← 2 backlinks
  </Connections>
</Card>
```

### Sidebar Component Structure
```tsx
<Sidebar> (slide-in animation)
  <Header>
    <SelectedDocTitle />
    <Badge>type</Badge>
  </Header>
  
  <Section title="Links to">
    <RelatedCard onClick={navigate} />
    <RelatedCard onClick={navigate} />
  </Section>
  
  <Section title="Referenced by">
    <RelatedCard onClick={navigate} />
  </Section>
  
  <Section title="Related topics">
    <RelatedCard onClick={navigate} />
  </Section>
</Sidebar>
```

## Responsive Behavior

### Desktop (>1024px)
- Grid: 3 columns
- Sidebar: fixed 320px width on right
- Main content: adjusts width when sidebar open

### Tablet (768px - 1024px)
- Grid: 2 columns
- Sidebar: overlay with backdrop blur
- Main content: full width

### Mobile (<768px)
- Grid: 1 column
- Sidebar: bottom sheet (slides up from bottom)
- Full-screen modal on card click

## Color & Visual Hierarchy

### Card States
- **Default**: border-gray-200, shadow-sm
- **Hover**: border-gray-300, shadow-lg, scale(1.02)
- **Selected**: ring-2 ring-primary, shadow-xl

### Sidebar
- **Background**: bg-background (matches theme)
- **Border**: border-l (left border only)
- **Shadow**: shadow-2xl (prominent)

### Connection Indicators
- **Outgoing links**: text-blue-600 with → arrow
- **Backlinks**: text-green-600 with ← arrow
- **Similar**: text-purple-600 with ≈ symbol

## Accessibility

### Keyboard Navigation
- **Tab**: move between cards
- **Enter**: select card / open sidebar
- **Escape**: close sidebar
- **Arrow keys**: navigate within sidebar

### Screen Readers
- Card: "Document card, {title}, {type}, {connection count}"
- Sidebar: "Related documents panel, {count} items"
- Navigation: "Navigate to {title}"

### Motion Preferences
```tsx
// Respect prefers-reduced-motion
const shouldAnimate = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (shouldAnimate) {
  gsap.to(element, { /* animation */ });
} else {
  // Instant state change
  element.style.transform = 'scale(1.02)';
}
```

## Performance Optimizations

1. **Virtual scrolling** for large lists (>100 items)
2. **Lazy load** card previews on hover
3. **Debounce** search input (300ms)
4. **Cache** related docs API responses
5. **GSAP quickTo** for high-frequency hover events
6. **Intersection Observer** for card animations on scroll

## Implementation Priority

### P0 (Must Have)
- Card grid layout
- Basic hover animation
- Sidebar with wikilinks/backlinks
- Click navigation

### P1 (Should Have)
- Extended preview on hover
- Tag filtering
- Similar docs by tags
- Smooth transitions

### P2 (Nice to Have)
- Graph visualization
- Breadcrumb trails
- Export functionality
- Advanced search with highlighting
