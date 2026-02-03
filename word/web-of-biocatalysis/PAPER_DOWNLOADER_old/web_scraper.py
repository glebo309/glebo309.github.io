#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic web scraper for finding PDFs on academic pages.

Crawls common academic platforms and author homepages for PDF links.
"""

import re
import time
from pathlib import Path
from typing import Optional, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def find_pdfs_on_page(url: str, title_keywords: List[str] = None) -> List[str]:
    """
    Scrape a page for PDF links.
    
    Args:
        url: Page URL to scrape
        title_keywords: Keywords from paper title to filter results
    
    Returns:
        List of PDF URLs found
    """
    if not url:
        return []
    
    pdf_urls = []
    
    try:
        headers = {'User-Agent': UA}
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text().strip().lower()
            
            # Check if it's a PDF link
            if href.lower().endswith('.pdf') or '/pdf' in href.lower() or 'pdf' in text:
                # Make absolute URL
                pdf_url = urljoin(url, href)
                
                # If we have title keywords, check if link text matches
                if title_keywords:
                    if any(keyword.lower() in text for keyword in title_keywords):
                        pdf_urls.append(pdf_url)
                else:
                    pdf_urls.append(pdf_url)
        
        # Check meta tags
        for meta in soup.find_all('meta'):
            if meta.get('name') == 'citation_pdf_url' or meta.get('property') == 'citation_pdf_url':
                pdf_url = meta.get('content')
                if pdf_url:
                    pdf_urls.append(urljoin(url, pdf_url))
        
    except Exception as e:
        pass
    
    return pdf_urls


def search_author_homepage(author_name: str, paper_title: str) -> List[str]:
    """
    Try to find author's homepage and look for PDF.
    
    Many professors post their papers on personal/university pages.
    """
    if not author_name:
        return []
    
    pdf_urls = []
    
    try:
        # Search for author's homepage using Google
        query = f'"{author_name}" homepage'
        search_url = f"https://www.google.com/search?q={quote(query)}"
        
        headers = {'User-Agent': UA}
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract first few search results (likely homepages)
        for result in soup.find_all('a', href=True)[:5]:
            href = result['href']
            
            # Filter for university domains
            if any(domain in href for domain in ['.edu', '.ac.uk', '.ac.cn']):
                # Visit the page and look for PDFs
                title_keywords = paper_title.split()[:3]  # First 3 words
                pdfs = find_pdfs_on_page(href, title_keywords)
                pdf_urls.extend(pdfs)
        
    except Exception as e:
        pass
    
    return pdf_urls[:5]  # Return top 5


def try_common_repositories(title: str, doi: str = None) -> List[str]:
    """
    Try common open access repositories.
    
    These are repositories not covered by other modules.
    """
    pdf_urls = []
    
    # PubMed Central
    if doi:
        try:
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/pmid/{doi}/"
            pdfs = find_pdfs_on_page(pmc_url)
            pdf_urls.extend(pdfs)
        except Exception:
            pass
    
    # Europe PMC
    if doi:
        try:
            epmc_url = f"https://europepmc.org/article/MED/{doi}"
            pdfs = find_pdfs_on_page(epmc_url)
            pdf_urls.extend(pdfs)
        except Exception:
            pass
    
    # bioRxiv/medRxiv (if DOI matches)
    if doi and ('biorxiv' in doi.lower() or 'medrxiv' in doi.lower()):
        try:
            if 'biorxiv' in doi.lower():
                base = "https://www.biorxiv.org"
            else:
                base = "https://www.medrxiv.org"
            
            pdf_url = f"{base}/content/{doi}v1.full.pdf"
            pdf_urls.append(pdf_url)
        except Exception:
            pass
    
    return pdf_urls


if __name__ == "__main__":
    # Test
    test_url = "https://arxiv.org/abs/1706.03762"
    
    print(f"Testing PDF extraction from: {test_url}")
    pdfs = find_pdfs_on_page(test_url)
    
    print(f"Found {len(pdfs)} PDFs:")
    for pdf in pdfs:
        print(f"  {pdf}")
