# Knowledge Graph UI Enhancement

## Goal
Transform flat knowledge base table into interactive graph-aware interface showing related entries, backlinks, and semantic connections using GSAP animations and shadcn/ui components.

## Inspiration Sources
- **Obsidian backlinks panel** - shows bidirectional links in sidebar
- **Roam Research** - block-level references and graph view
- **Skill graphs pattern** - wikilinks in prose create traversable knowledge network
- **Card hover patterns** - preview content without navigation

## Core Features

### 1. Enhanced Document Card View
Replace table with card grid showing:
- **Title** with doc type badge
- **Excerpt** (first 100 chars)
- **Tag pills** extracted from content
- **Connection count** indicator
- **Hover preview** - GSAP animated expansion showing more content

### 2. Related Entries Sidebar
When document selected:
- **Outgoing links** - documents this one references
- **Backlinks** - documents that reference this one
- **Similar by tags** - shared topic clustering
- **Recently viewed** - session history

### 3. Interactive Animations (GSAP)
- **Card hover** - scale(1.02) + shadow expansion
- **Sidebar slide-in** - translateX animation when document selected
- **Connection lines** - animated paths between related cards (optional)
- **Smooth transitions** - between list/grid/graph views

### 4. View Modes
- **Grid view** (default) - responsive card grid
- **List view** - compact table (current)
- **Graph view** - force-directed network visualization (future)

## Technical Design

### Data Model Extensions

```typescript
interface KBDocument {
  id: string;
  title: string;
  content: string;
  doc_type: KBDocType;
  
  // NEW: Graph metadata
  wikilinks?: string[];        // [[link]] references in content
  backlinks?: string[];        // docs that link to this
  tags?: string[];             // extracted from frontmatter or content
  related_score?: Record<string, number>; // similarity scores
}

interface KBGraphData {
  nodes: { id: string; title: string; type: string; }[];
  edges: { source: string; target: string; type: 'wikilink' | 'backlink' | 'similar'; }[];
}
```

### Backend Changes

**New API endpoint**: `GET /api/kb/{doc_id}/related`
```python
@router.get("/kb/{doc_id}/related")
async def get_related_docs(doc_id: str, scope: KBScope = "local"):
    """Get related documents via wikilinks, backlinks, and similarity."""
    doc = await get_kb_doc(doc_id, scope)
    
    # Extract wikilinks from content: [[filename]] or [[title]]
    wikilinks = extract_wikilinks(doc.content)
    
    # Find backlinks: scan all docs for references to this doc
    backlinks = find_backlinks(doc_id, scope)
    
    # Find similar by tags/content
    similar = find_similar_docs(doc, scope, limit=5)
    
    return {
        "wikilinks": wikilinks,
        "backlinks": backlinks,
        "similar": similar
    }
```

**Wikilink extraction**:
```python
import re

def extract_wikilinks(content: str) -> list[str]:
    """Extract [[wikilink]] references from markdown content."""
    pattern = r'\[\[([^\]]+)\]\]'
    matches = re.findall(pattern, content)
    return [m.strip() for m in matches]

def find_backlinks(doc_id: str, scope: KBScope) -> list[dict]:
    """Find all docs that link to this doc."""
    kb_path = _get_kb_path(scope)
    backlinks = []
    
    for file_path in kb_path.rglob("*.md"):
        content = file_path.read_text(encoding="utf-8")
        links = extract_wikilinks(content)
        
        # Check if any link matches this doc's id or title
        if any(link in doc_id or doc_id in link for link in links):
            backlinks.append({
                "id": str(file_path.relative_to(kb_path)),
                "title": extract_title(content)
            })
    
    return backlinks
```

### Frontend Components

#### 1. KnowledgeCardGrid Component
```tsx
// frontend/src/components/KnowledgeCardGrid.tsx
import { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface KnowledgeCardProps {
  doc: KBDocument;
  onSelect: (id: string) => void;
  isSelected: boolean;
}

export function KnowledgeCard({ doc, onSelect, isSelected }: KnowledgeCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  
  useGSAP(() => {
    const card = cardRef.current;
    if (!card) return;
    
    // Hover animation
    const onEnter = () => {
      gsap.to(card, {
        scale: 1.02,
        boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)',
        duration: 0.3,
        ease: 'power2.out'
      });
      
      // Expand preview
      gsap.to(previewRef.current, {
        height: 'auto',
        opacity: 1,
        duration: 0.3,
        ease: 'power2.out'
      });
    };
    
    const onLeave = () => {
      gsap.to(card, {
        scale: 1,
        boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1)',
        duration: 0.3,
        ease: 'power2.out'
      });
      
      gsap.to(previewRef.current, {
        height: 0,
        opacity: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    };
    
    card.addEventListener('mouseenter', onEnter);
    card.addEventListener('mouseleave', onLeave);
    
    return () => {
      card.removeEventListener('mouseenter', onEnter);
      card.removeEventListener('mouseleave', onLeave);
    };
  }, []);
  
  return (
    <Card
      ref={cardRef}
      className={`cursor-pointer transition-colors ${isSelected ? 'ring-2 ring-primary' : ''}`}
      onClick={() => onSelect(doc.id)}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium line-clamp-2">{doc.title}</h3>
          <Badge variant="secondary">{doc.doc_type}</Badge>
        </div>
        
        <p className="mt-2 text-sm text-muted-foreground line-clamp-2">
          {doc.content.substring(0, 100)}...
        </p>
        
        {doc.tags && doc.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {doc.tags.slice(0, 3).map(tag => (
              <Badge key={tag} variant="outline" className="text-xs">
                {tag}
              </Badge>
            ))}
          </div>
        )}
        
        {/* Hover preview - hidden by default */}
        <div
          ref={previewRef}
          className="overflow-hidden opacity-0"
          style={{ height: 0 }}
        >
          <div className="mt-3 pt-3 border-t">
            <p className="text-xs text-muted-foreground line-clamp-4">
              {doc.content.substring(100, 300)}...
            </p>
          </div>
        </div>
        
        {/* Connection indicator */}
        {(doc.wikilinks?.length || doc.backlinks?.length) && (
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            {doc.wikilinks && doc.wikilinks.length > 0 && (
              <span>→ {doc.wikilinks.length} links</span>
            )}
            {doc.backlinks && doc.backlinks.length > 0 && (
              <span>← {doc.backlinks.length} backlinks</span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
```

#### 2. RelatedSidebar Component
```tsx
// frontend/src/components/RelatedSidebar.tsx
import { useRef, useEffect } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';

interface RelatedSidebarProps {
  doc: KBDocument | null;
  relatedDocs: {
    wikilinks: KBDocument[];
    backlinks: KBDocument[];
    similar: KBDocument[];
  };
  onSelectDoc: (id: string) => void;
  isOpen: boolean;
}

export function RelatedSidebar({ doc, relatedDocs, onSelectDoc, isOpen }: RelatedSidebarProps) {
  const sidebarRef = useRef<HTMLDivElement>(null);
  
  useGSAP(() => {
    if (!sidebarRef.current) return;
    
    gsap.to(sidebarRef.current, {
      x: isOpen ? 0 : '100%',
      duration: 0.4,
      ease: 'power3.out'
    });
  }, [isOpen]);
  
  if (!doc) return null;
  
  return (
    <div
      ref={sidebarRef}
      className="fixed right-0 top-0 h-full w-80 bg-background border-l shadow-lg overflow-y-auto"
      style={{ transform: 'translateX(100%)' }}
    >
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold">{doc.title}</h2>
          <Badge variant="secondary" className="mt-2">{doc.doc_type}</Badge>
        </div>
        
        <Separator />
        
        {/* Outgoing Links */}
        {relatedDocs.wikilinks.length > 0 && (
          <div>
            <h3 className="text-sm font-medium mb-3">Links to</h3>
            <div className="space-y-2">
              {relatedDocs.wikilinks.map(link => (
                <Card
                  key={link.id}
                  className="cursor-pointer hover:bg-accent/50 transition-colors"
                  onClick={() => onSelectDoc(link.id)}
                >
                  <CardContent className="p-3">
                    <p className="text-sm font-medium">{link.title}</p>
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                      {link.content.substring(0, 80)}...
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
        
        {/* Backlinks */}
        {relatedDocs.backlinks.length > 0 && (
          <div>
            <h3 className="text-sm font-medium mb-3">Referenced by</h3>
            <div className="space-y-2">
              {relatedDocs.backlinks.map(backlink => (
                <Card
                  key={backlink.id}
                  className="cursor-pointer hover:bg-accent/50 transition-colors"
                  onClick={() => onSelectDoc(backlink.id)}
                >
                  <CardContent className="p-3">
                    <p className="text-sm font-medium">{backlink.title}</p>
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                      {backlink.content.substring(0, 80)}...
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
        
        {/* Similar Documents */}
        {relatedDocs.similar.length > 0 && (
          <div>
            <h3 className="text-sm font-medium mb-3">Related topics</h3>
            <div className="space-y-2">
              {relatedDocs.similar.map(similar => (
                <Card
                  key={similar.id}
                  className="cursor-pointer hover:bg-accent/50 transition-colors"
                  onClick={() => onSelectDoc(similar.id)}
                >
                  <CardContent className="p-3">
                    <p className="text-sm font-medium">{similar.title}</p>
                    {similar.tags && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {similar.tags.slice(0, 3).map(tag => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

#### 3. Updated KnowledgePage
```tsx
// frontend/src/pages/KnowledgePage.tsx (enhanced)
import { useState, useEffect } from 'react';
import { KnowledgeCard } from '@/components/KnowledgeCardGrid';
import { RelatedSidebar } from '@/components/RelatedSidebar';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function KnowledgePage() {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [selectedDoc, setSelectedDoc] = useState<KBDocument | null>(null);
  const [relatedDocs, setRelatedDocs] = useState(null);
  
  const handleSelectDoc = async (id: string) => {
    const doc = await getKBDoc(id, scope);
    setSelectedDoc(doc);
    
    // Fetch related documents
    const related = await fetch(`/api/kb/${id}/related?scope=${scope}`).then(r => r.json());
    setRelatedDocs(related);
  };
  
  return (
    <div className="relative">
      <div className={`transition-all ${selectedDoc ? 'mr-80' : 'mr-0'}`}>
        {/* Header with view mode toggle */}
        <div className="flex items-center justify-between mb-6">
          <h1>Knowledge Base</h1>
          <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)}>
            <TabsList>
              <TabsTrigger value="grid">Grid</TabsTrigger>
              <TabsTrigger value="list">List</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        
        {/* Filters */}
        {/* ... existing filters ... */}
        
        {/* Content */}
        {viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {docs.map(doc => (
              <KnowledgeCard
                key={doc.id}
                doc={doc}
                onSelect={handleSelectDoc}
                isSelected={selectedDoc?.id === doc.id}
              />
            ))}
          </div>
        ) : (
          /* ... existing table view ... */
        )}
      </div>
      
      {/* Related sidebar */}
      <RelatedSidebar
        doc={selectedDoc}
        relatedDocs={relatedDocs}
        onSelectDoc={handleSelectDoc}
        isOpen={!!selectedDoc}
      />
    </div>
  );
}
```

## Implementation Phases

### Phase 1: Backend Graph Support
1. Add wikilink extraction to KB route
2. Implement backlink scanning
3. Create `/api/kb/{id}/related` endpoint
4. Add tags extraction from frontmatter

### Phase 2: Card Grid View
1. Create KnowledgeCard component
2. Add GSAP hover animations
3. Implement grid layout with responsive design
4. Add view mode toggle (grid/list)

### Phase 3: Related Sidebar
1. Create RelatedSidebar component
2. Add slide-in animation with GSAP
3. Implement three sections: wikilinks, backlinks, similar
4. Add click navigation between related docs

### Phase 4: Polish
1. Add loading states with skeleton cards
2. Implement smooth transitions between selections
3. Add keyboard navigation (arrow keys, escape)
4. Optimize performance for large knowledge bases

## Design Principles

1. **Progressive disclosure** - show summary, reveal details on interaction
2. **Semantic connections** - wikilinks carry meaning through prose context
3. **Performance first** - animate transform/opacity only, use GSAP for 60fps
4. **Accessibility** - honor prefers-reduced-motion, keyboard navigation
5. **Mobile responsive** - sidebar becomes bottom sheet on mobile

## Future Enhancements

- **Graph visualization** - force-directed network using D3.js or vis.js
- **Breadcrumb trails** - show navigation path through knowledge graph
- **Tag clustering** - visual grouping of related topics
- **Search highlighting** - show search terms in context
- **Export graph** - generate GraphML or JSON for external analysis
