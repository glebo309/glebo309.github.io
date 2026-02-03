#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick test script for international sources module.
"""

from international_sources import search_international_sources

# Test cases
test_papers = [
    {
        "title": "Emergent Properties of Networks of Biological Signaling Pathways",
        "doi": "10.1126/science.283.5400.381",
        "description": "Classic STEM paper"
    },
    {
        "title": "The Structure of Scientific Revolutions",
        "doi": "10.7208/chicago/9780226458106.001.0001",
        "description": "Philosophy classic"
    },
    {
        "title": "Deep Learning",
        "doi": "10.1038/nature14539",
        "description": "Recent AI paper"
    }
]

print("=" * 80)
print("Testing International Sources Module")
print("=" * 80)
print()

for i, paper in enumerate(test_papers, 1):
    print(f"\n{i}. Testing: {paper['description']}")
    print(f"   Title: {paper['title'][:60]}...")
    print(f"   DOI: {paper['doi']}")
    print()
    
    results = search_international_sources(
        title=paper['title'],
        doi=paper['doi'],
        countries=['CN', 'RU', 'FR', 'ES']  # Test subset for speed
    )
    
    if results:
        print(f"   ✓ Found {len(results)} candidates:")
        for source, url in results[:3]:  # Show first 3
            print(f"     - {source}: {url[:70]}...")
    else:
        print("   ✗ No candidates found")
    
    print()

print("=" * 80)
print("Test complete!")
print("=" * 80)
