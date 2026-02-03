#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deep web crawler for exhaustive PDF search.

Crawls author pages, institutional repositories, and follows citation chains.
"""

import re
import time
import random
from pathlib import Path
from typing import Optional, List, Dict, Set
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def extract_author_info(metadata: Dict) -> List[Dict]:
    """Extract author names and affiliations from metadata"""
    authors = []
    
    author_list = metadata.get('author', [])
    for author in author_list:
        if isinstance(author, dict):
            name = f"{author.get('given', '')} {author.get('family', '')}".strip()
            affiliation = author.get('affiliation', [])
            
            if affiliation and len(affiliation) > 0:
                aff_name = affiliation[0].get('name', '')
            else:
                aff_name = ''
            
            authors.append({
                'name': name,
                'affiliation': aff_name
            })
    
    return authors


def find_author_homepage(author_name: str, affiliation: str = None) -> Optional[str]:
    """
    Find author's homepage using Google search.
    
    Many professors post PDFs on their university pages.
    """
    if not author_name:
        return None
    
    try:
        # Build search query
        query = f'"{author_name}"'
        if affiliation:
            query += f' {affiliation}'
        query += ' homepage'
        
        url = f"https://www.google.com/search?q={quote(query)}"
        headers = {'User-Agent': UA}
        
        time.sleep(random.uniform(2, 3))
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find first university link
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            
            # Check if it's a university domain
            if any(domain in href for domain in ['.edu', '.ac.uk', '.ac.cn', '.edu.cn']):
                # Extract actual URL from Google redirect
                if '/url?q=' in href:
                    actual_url = href.split('/url?q=')[1].split('&')[0]
                    return actual_url
                elif href.startswith('http'):
                    return href
        
    except Exception as e:
        pass
    
    return None


def crawl_author_page(page_url: str, paper_title: str) -> List[str]:
    """
    Crawl author's homepage for PDF links.
    
    Returns list of PDF URLs found.
    """
    if not page_url:
        return []
    
    pdf_urls = []
    
    try:
        headers = {'User-Agent': UA}
        response = requests.get(page_url, headers=headers, timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract title keywords for matching
        title_words = set(paper_title.lower().split())
        title_words = {w for w in title_words if len(w) > 3}  # Only meaningful words
        
        # Find all PDF links
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text().strip().lower()
            
            # Check if it's a PDF
            if href.lower().endswith('.pdf') or '/pdf' in href.lower():
                # Make absolute URL
                pdf_url = urljoin(page_url, href)
                
                # Check if link text matches paper title
                link_words = set(text.split())
                overlap = len(title_words & link_words)
                
                if overlap >= 2:  # At least 2 words match
                    pdf_urls.append(pdf_url)
                elif not pdf_urls:  # If no matches yet, keep all PDFs
                    pdf_urls.append(pdf_url)
        
        # Also check for "publications" or "papers" pages
        for link in soup.find_all('a', href=True):
            text = link.get_text().strip().lower()
            href = link['href']
            
            if any(word in text for word in ['publication', 'paper', 'research', 'cv']):
                # Follow this link
                pub_url = urljoin(page_url, href)
                if pub_url != page_url:  # Avoid infinite loop
                    sub_pdfs = _crawl_publications_page(pub_url, paper_title)
                    pdf_urls.extend(sub_pdfs[:5])  # Limit to 5 from subpage
        
    except Exception as e:
        pass
    
    return pdf_urls[:10]  # Return top 10


def _crawl_publications_page(page_url: str, paper_title: str) -> List[str]:
    """Crawl a publications subpage"""
    pdf_urls = []
    
    try:
        headers = {'User-Agent': UA}
        response = requests.get(page_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_words = set(paper_title.lower().split())
        title_words = {w for w in title_words if len(w) > 3}
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text().strip().lower()
            
            if href.lower().endswith('.pdf'):
                pdf_url = urljoin(page_url, href)
                
                link_words = set(text.split())
                overlap = len(title_words & link_words)
                
                if overlap >= 2:
                    pdf_urls.append(pdf_url)
        
    except Exception as e:
        pass
    
    return pdf_urls


def search_institutional_repositories(title: str, affiliation: str = None) -> List[str]:
    """
    Search institutional repositories.
    
    Many universities have their own repositories (DSpace, EPrints, etc.)
    """
    pdf_urls = []
    
    # Common repository platforms
    repo_domains = [
        'dspace',
        'eprints',
        'repository',
        'digital.library',
        'scholarworks',
        'research.repository'
    ]
    
    try:
        # Build search query
        query = f'"{title}"'
        if affiliation:
            query += f' {affiliation}'
        query += ' repository'
        
        url = f"https://www.google.com/search?q={quote(query)}"
        headers = {'User-Agent': UA}
        
        time.sleep(random.uniform(2, 3))
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find repository links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            
            # Check if it's a repository
            if any(repo in href.lower() for repo in repo_domains):
                # Extract actual URL
                if '/url?q=' in href:
                    actual_url = href.split('/url?q=')[1].split('&')[0]
                    pdf_urls.append(actual_url)
                elif href.startswith('http'):
                    pdf_urls.append(href)
        
    except Exception as e:
        pass
    
    return pdf_urls[:10]


def try_fetch_deep_crawl(
    title: str,
    doi: str,
    outpath: Path,
    metadata: Dict = None
) -> Optional[str]:
    """
    Deep crawl for PDF using author pages and repositories.
    
    Returns source type if successful, None otherwise.
    """
    if not title:
        return None
    
    print("  Deep crawling author pages and repositories...")
    
    session = requests.Session()
    session.headers.update({'User-Agent': UA})
    
    # Extract author info
    authors = []
    if metadata:
        authors = extract_author_info(metadata)
    
    if not authors:
        print("    No author information available")
        return None
    
    print(f"    Found {len(authors)} authors")
    
    # Try first 2 authors (corresponding and first author usually)
    for i, author in enumerate(authors[:2]):
        author_name = author['name']
        affiliation = author['affiliation']
        
        if not author_name:
            continue
        
        print(f"    Searching for {author_name}...")
        
        # Find author homepage
        homepage = find_author_homepage(author_name, affiliation)
        
        if not homepage:
            print(f"      No homepage found")
            continue
        
        print(f"      Found homepage: {homepage[:60]}...")
        
        # Crawl author page
        pdf_urls = crawl_author_page(homepage, title)
        
        if not pdf_urls:
            print(f"      No PDFs found on homepage")
            continue
        
        print(f"      Found {len(pdf_urls)} PDF candidates")
        
        # Try each PDF
        for pdf_url in pdf_urls:
            try:
                print(f"      Trying: {pdf_url[:60]}...")
                
                response = session.get(pdf_url, timeout=30, allow_redirects=True)
                
                # Validate PDF
                if response.content[:4] != b'%PDF':
                    print(f"        ✗ Not a valid PDF")
                    continue
                
                if len(response.content) < 50 * 1024:
                    print(f"        ✗ File too small")
                    continue
                
                # Save
                with outpath.open('wb') as f:
                    f.write(response.content)
                
                print(f"  ✓ Downloaded from author homepage")
                return 'author_homepage'
                
            except Exception as e:
                print(f"        ✗ Failed: {type(e).__name__}")
                continue
        
        time.sleep(random.uniform(1, 2))
    
    # Try institutional repositories
    print("    Searching institutional repositories...")
    
    first_affiliation = authors[0]['affiliation'] if authors else None
    repo_urls = search_institutional_repositories(title, first_affiliation)
    
    if repo_urls:
        print(f"    Found {len(repo_urls)} repository candidates")
        
        for repo_url in repo_urls[:5]:
            try:
                # Visit repository page
                response = session.get(repo_url, timeout=15)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for PDF links
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    if href.lower().endswith('.pdf') or '/bitstream/' in href:
                        pdf_url = urljoin(repo_url, href)
                        
                        # Try to download
                        pdf_response = session.get(pdf_url, timeout=30)
                        
                        if pdf_response.content[:4] == b'%PDF' and len(pdf_response.content) > 50 * 1024:
                            with outpath.open('wb') as f:
                                f.write(pdf_response.content)
                            
                            print(f"  ✓ Downloaded from institutional repository")
                            return 'institutional_repo'
                
            except Exception as e:
                continue
    
    return None


if __name__ == "__main__":
    # Test
    test_author = "Geoffrey Hinton"
    test_affiliation = "University of Toronto"
    
    print(f"Testing author homepage search for: {test_author}")
    homepage = find_author_homepage(test_author, test_affiliation)
    
    if homepage:
        print(f"Found: {homepage}")
    else:
        print("Not found")
