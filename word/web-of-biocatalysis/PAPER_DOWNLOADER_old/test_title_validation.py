#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test title validation for international sources.
"""

from international_sources import _titles_match

print("=" * 80)
print("Testing Title Validation")
print("=" * 80)
print()

# Test cases
test_cases = [
    {
        "title1": "Being-in-the-World as a Concept in Phenomenology",
        "title2": "Being-in-the-World as a Concept in Phenomenology",
        "expected": True,
        "description": "Exact match"
    },
    {
        "title1": "Being-in-the-World as a Concept in Phenomenology",
        "title2": "Phenomenology and Aristotle's concept of being-at-work",
        "expected": False,
        "description": "Different papers (your bug case)"
    },
    {
        "title1": "Deep Learning in Neural Networks",
        "title2": "Deep Learning in Neural Networks: An Overview",
        "expected": True,
        "description": "Shortened title (minor difference)"
    },
    {
        "title1": "The Structure of Scientific Revolutions",
        "title2": "Structure of Scientific Revolutions",
        "expected": True,
        "description": "Minor difference (missing 'The')"
    },
    {
        "title1": "Attention Is All You Need",
        "title2": "Attention Mechanisms in Neural Networks",
        "expected": False,
        "description": "Different papers about same topic"
    },
]

print("Testing with threshold=0.5 (international sources default):\n")

passed = 0
failed = 0

for i, test in enumerate(test_cases, 1):
    result = _titles_match(test["title1"], test["title2"], threshold=0.5)
    status = "✓ PASS" if result == test["expected"] else "✗ FAIL"
    
    if result == test["expected"]:
        passed += 1
    else:
        failed += 1
    
    print(f"{i}. {test['description']}")
    print(f"   Title 1: {test['title1'][:60]}...")
    print(f"   Title 2: {test['title2'][:60]}...")
    print(f"   Expected: {test['expected']}, Got: {result} → {status}")
    print()

print("=" * 80)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 80)

if failed == 0:
    print("\n✓ All tests passed! Title validation is working correctly.")
else:
    print(f"\n✗ {failed} test(s) failed. Check the implementation.")
