import { useEffect, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { X } from "lucide-react";
import gsap from "gsap";
import type { TagInfo } from "@/lib/types";

interface TagCloudProps {
  tags: TagInfo[];
  selectedTags: string[];
  onTagToggle: (tag: string) => void;
}

export function TagCloud({ tags, selectedTags, onTagToggle }: TagCloudProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Animate tags
    const tagElements = containerRef.current.querySelectorAll('[data-tag]');
    
    tagElements.forEach((el) => {
      const tagName = el.getAttribute('data-tag');
      if (!tagName) return;
      
      const tag = tags.find(t => t.name === tagName);
      const isSelected = selectedTags.includes(tagName);
      const isAvailable = tag?.available ?? true;
      
      // Reduced motion check
      const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      
      if (prefersReducedMotion) {
        gsap.set(el, {
          opacity: isAvailable ? 1 : 0.3,
          scale: isSelected ? 1.05 : 1,
        });
      } else {
        gsap.to(el, {
          opacity: isAvailable ? 1 : 0.3,
          scale: isSelected ? 1.05 : 1,
          duration: 0.4,
          ease: "power2.out",
        });
      }
    });
  }, [tags, selectedTags]);

  // Sort tags: selected first, then by count
  const sortedTags = [...tags].sort((a, b) => {
    const aSelected = selectedTags.includes(a.name);
    const bSelected = selectedTags.includes(b.name);
    
    if (aSelected && !bSelected) return -1;
    if (!aSelected && bSelected) return 1;
    
    return b.count - a.count;
  });

  const handleTagClick = (tagName: string, available: boolean) => {
    // Don't allow clicking disabled tags (unless already selected)
    const isSelected = selectedTags.includes(tagName);
    if (!available && !isSelected) return;
    onTagToggle(tagName);
  };

  if (tags.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        No tags found in documents
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex gap-2 flex-wrap">
      {sortedTags.map((tag) => {
        const isSelected = selectedTags.includes(tag.name);
        const isAvailable = tag.available;
        
        return (
          <Badge
            key={tag.name}
            data-tag={tag.name}
            variant={isSelected ? "default" : "outline"}
            className={`transition-all flex items-center gap-1 ${
              isAvailable || isSelected
                ? "cursor-pointer hover:scale-105" 
                : "cursor-not-allowed"
            }`}
            style={{
              opacity: isAvailable || isSelected ? 1 : 0.3,
              pointerEvents: isAvailable || isSelected ? 'auto' : 'none'
            }}
            onClick={() => handleTagClick(tag.name, isAvailable)}
          >
            {tag.name}
            <span className="text-xs opacity-70">({tag.count})</span>
            {isSelected && (
              <X className="h-3 w-3 ml-1" />
            )}
          </Badge>
        );
      })}
    </div>
  );
}
