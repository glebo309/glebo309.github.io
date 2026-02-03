#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Scholar PDF extraction.

Searches Google Scholar for papers and extracts PDF links from:
- University repositories (.edu, .ac.uk, .ac.cn, etc.)
- Institutional repositories
- Author homepages
- ResearchGate, Academia.edu
"""

import re
import time
import random
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _is_university_domain(url: str) -> bool:
    """Check if URL is from a university or institutional repository"""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # University domains
    university_tlds = [
        '.edu', '.ac.uk', '.ac.cn', '.edu.cn', '.ac.jp', '.edu.au',
        '.ac.in', '.edu.br', '.ac.za', '.edu.sg', '.ac.kr', '.edu.tw',
        '.ac.nz', '.edu.hk', '.ac.il', '.edu.mx', '.ac.at', '.edu.ar'
    ]
    
    for tld in university_tlds:
        if tld in url_lower:
            return True
    
    # Known institutional repositories
    repo_domains = [
        'arxiv.org', 'biorxiv.org', 'medrxiv.org', 'ssrn.com',
        'researchgate.net', 'academia.edu', 'philpapers.org',
        'hal.archives-ouvertes.fr', 'zenodo.org', 'figshare.com',
        'osf.io', 'europepmc.org', 'ncbi.nlm.nih.gov/pmc'
    ]
    
    for domain in repo_domains:
        if domain in url_lower:
            return True
    
    return False


def _is_pdf_link(url: str, link_text: str = "") -> bool:
    """Check if URL likely points to a PDF"""
    if not url:
        return False
    
    url_lower = url.lower()
    text_lower = link_text.lower()
    
    # Direct PDF URL
    if url_lower.endswith('.pdf'):
        return True
    
    # PDF in URL path
    if '/pdf' in url_lower or 'pdf/' in url_lower:
        return True
    
    # Link text indicates PDF
    if any(word in text_lower for word in ['pdf', 'download', 'full text', 'view pdf']):
        return True
    
    return False


def search_google_scholar(title: str, author: str = None, year: str = None) -> List[Tuple[str, str, str]]:
    """
    Search Google Scholar and extract PDF links.
    
    Returns list of (source_type, url, description) tuples.
    """
    if not title:
        return []
    
    results = []
    
    # Build search query
    query = f'"{title}"'
    if author:
        query += f' author:"{author}"'
    if year:
        query += f' {year}'
    
    # Google Scholar search URL
    base_url = "https://scholar.google.com/scholar"
    params = {
        'q': query,
        'hl': 'en',
        'as_sdt': '0,5'
    }
    
    headers = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://scholar.google.com/',
    }
    
    try:
        # Add random delay to avoid rate limiting
        time.sleep(random.uniform(2, 4))
        
        session = requests.Session()
        response = session.get(base_url, params=params, headers=headers, timeout=15)
        
        if response.status_code == 429:
            print("    ⚠ Google Scholar rate limit hit")
            return []
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all search results
        for result in soup.find_all('div', class_='gs_r gs_or gs_scl'):
            # Look for PDF links in the result
            
            # Check for [PDF] links (direct PDF)
            pdf_link = result.find('div', class_='gs_or_ggsm')
            if pdf_link:
                link = pdf_link.find('a')
                if link and link.get('href'):
                    url = link['href']
                    if _is_pdf_link(url, link.get_text()):
                        results.append(('google_scholar_pdf', url, 'Direct PDF link'))
            
            # Check main title link
            title_link = result.find('h3', class_='gs_rt')
            if title_link:
                link = title_link.find('a')
                if link and link.get('href'):
                    url = link['href']
                    # Only include if from university/repository
                    if _is_university_domain(url):
                        results.append(('university_repo', url, 'University repository'))
            
            # Check for "All X versions" link
            versions_link = result.find('a', string=re.compile(r'All \d+ versions'))
            if versions_link and versions_link.get('href'):
                # This could lead to more sources, but skip for now to avoid complexity
                pass
        
    except Exception as e:
        print(f"    Google Scholar search failed: {e}")
    
    return results


def extract_pdf_from_page(page_url: str, expected_title: str = None) -> Optional[str]:
    """
    Visit a page and try to extract PDF link.
    
    Common patterns:
    - Direct PDF link in page
    - Download button
    - View PDF button
    """
    if not page_url:
        return None
    
    try:
        headers = {'User-Agent': UA}
        response = requests.get(page_url, headers=headers, timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
        
        # Check if response is already a PDF
        if response.headers.get('content-type', '').lower().startswith('application/pdf'):
            return page_url
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for PDF links
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text().strip()
            
            if _is_pdf_link(href, text):
                # Make absolute URL
                pdf_url = urljoin(page_url, href)
                return pdf_url
        
        # Look for meta tags with PDF URLs
        for meta in soup.find_all('meta'):
            if meta.get('name') == 'citation_pdf_url' or meta.get('property') == 'citation_pdf_url':
                pdf_url = meta.get('content')
                if pdf_url:
                    return urljoin(page_url, pdf_url)
        
    except Exception as e:
        pass
    
    return None


def try_fetch_from_google_scholar(
    title: str,
    doi: str,
    outpath: Path,
    author: str = None,
    year: str = None,
    validate_title: bool = True
) -> Optional[str]:
    """
    Try to fetch PDF via Google Scholar.
    
    Returns source type if successful, None otherwise.
    """
    if not title:
        return None
    
    print("  Searching Google Scholar...")
    
    # Search Google Scholar
    candidates = search_google_scholar(title, author, year)
    
    if not candidates:
        print("    No Google Scholar results found")
        return None
    
    print(f"  Found {len(candidates)} Google Scholar candidates")
    
    session = requests.Session()
    session.headers.update({'User-Agent': UA})
    
    # Try each candidate
    for source_type, url, description in candidates:
        try:
            print(f"  Trying {source_type}: {url[:80]}...")
            
            # If it's a direct PDF link, download it
            if source_type == 'google_scholar_pdf' or url.lower().endswith('.pdf'):
                response = session.get(url, timeout=30, allow_redirects=True)
                
                # Check if it's actually a PDF
                if not (response.headers.get('content-type', '').lower().startswith('application/pdf') or
                        response.content[:4] == b'%PDF'):
                    print(f"    ✗ Not a valid PDF")
                    continue
                
                # Check file size
                if len(response.content) < 50 * 1024:
                    print(f"    ✗ File too small")
                    continue
                
                # Save
                with outpath.open('wb') as f:
                    f.write(response.content)
                
                print(f"  ✓ Downloaded from {source_type}")
                return source_type
            
            # If it's a university repository page, try to extract PDF
            elif source_type == 'university_repo':
                pdf_url = extract_pdf_from_page(url, title)
                
                if not pdf_url:
                    print(f"    ✗ No PDF found on page")
                    continue
                
                # Download the PDF
                response = session.get(pdf_url, timeout=30, allow_redirects=True)
                
                # Validate
                if not (response.headers.get('content-type', '').lower().startswith('application/pdf') or
                        response.content[:4] == b'%PDF'):
                    print(f"    ✗ Not a valid PDF")
                    continue
                
                if len(response.content) < 50 * 1024:
                    print(f"    ✗ File too small")
                    continue
                
                # Save
                with outpath.open('wb') as f:
                    f.write(response.content)
                
                print(f"  ✓ Downloaded from university repository")
                return 'university_repo'
            
            # Small delay between attempts
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"    ✗ Failed: {type(e).__name__}")
            continue
    
    return None


# ============================================================================
# RESEARCHGATE
# ============================================================================

def search_researchgate(title: str, author: str = None) -> List[str]:
    """
    Search ResearchGate for PDFs.
    
    Note: ResearchGate requires login for most PDFs, so this has limited success.
    """
    if not title:
        return []
    
    candidates = []
    
    try:
        base_url = "https://www.researchgate.net/search/publication"
        params = {'q': title}
        
        headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        time.sleep(random.uniform(2, 3))
        
        response = requests.get(base_url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for publication links
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/publication/' in href and 'researchgate.net' in href:
                candidates.append(href)
        
    except Exception as e:
        pass
    
    return candidates[:5]  # Return top 5


# ============================================================================
# ACADEMIA.EDU
# ============================================================================

def search_academia_edu(title: str, author: str = None) -> List[str]:
    """
    Search Academia.edu for PDFs.
    
    Note: Academia.edu also requires login for most PDFs.
    """
    if not title:
        return []
    
    candidates = []
    
    try:
        # Academia.edu search
        base_url = "https://www.academia.edu/search"
        params = {'q': title}
        
        headers = {'User-Agent': UA}
        
        time.sleep(random.uniform(2, 3))
        
        response = requests.get(base_url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for paper links
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'academia.edu' in href and '/attachments/' not in href:
                candidates.append(href)
        
    except Exception as e:
        pass
    
    return candidates[:5]


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test Google Scholar search
    test_title = "Attention Is All You Need"
    
    print("=" * 80)
    print(f"Testing Google Scholar search for: {test_title}")
    print("=" * 80)
    print()
    
    results = search_google_scholar(test_title)
    
    print(f"Found {len(results)} results:")
    for source_type, url, desc in results:
        print(f"  {source_type}: {url[:80]}...")
        print(f"    Description: {desc}")
        print()
