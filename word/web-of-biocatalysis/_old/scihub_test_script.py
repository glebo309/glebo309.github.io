#!/usr/bin/env python3
"""
Test script to verify SciHub access using SciDownl
"""

import subprocess
import sys
import tempfile
from pathlib import Path
import requests

def install_scidownl():
    """Install SciDownl if not available"""
    try:
        import scidownl
        print("✅ SciDownl already installed")
        return True
    except ImportError:
        print("📦 Installing SciDownl...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-U", "scidownl"], 
                         check=True, capture_output=True)
            print("✅ SciDownl installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install SciDownl: {e}")
            return False

def test_scidownl_download(doi: str, output_path: Path = None):
    """Test downloading a paper using SciDownl"""
    
    if not output_path:
        output_path = Path(f"test_paper_{doi.replace('/', '_').replace('.', '_')}.pdf")
    
    print(f"🔬 Testing SciDownl download for DOI: {doi}")
    print(f"📁 Output path: {output_path}")
    
    try:
        # Method 1: Using scidownl command line
        cmd = [
            sys.executable, "-m", "scidownl", "download",
            "--doi", doi,
            "--out", str(output_path)
        ]
        
        print(f"🚀 Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        print(f"📤 Return code: {result.returncode}")
        print(f"📤 STDOUT: {result.stdout}")
        if result.stderr:
            print(f"📤 STDERR: {result.stderr}")
        
        if result.returncode == 0 and output_path.exists():
            file_size = output_path.stat().st_size
            print(f"✅ Download successful! File size: {file_size:,} bytes")
            return True
        else:
            print(f"❌ Download failed")
            return False
            
    except Exception as e:
        print(f"❌ SciDownl test failed: {e}")
        return False

def test_scidownl_programmatic(doi: str, output_path: Path = None):
    """Test using SciDownl programmatically (if possible)"""
    
    if not output_path:
        output_path = Path(f"test_paper_prog_{doi.replace('/', '_').replace('.', '_')}.pdf")
    
    print(f"\n🔬 Testing SciDownl programmatic access for DOI: {doi}")
    
    try:
        import scidownl
        
        # Try to use SciDownl programmatically
        # Note: The exact API might vary, this is based on common patterns
        
        # Method 1: Try direct download
        try:
            scidownl.download(doi, output=str(output_path))
            
            if output_path.exists():
                file_size = output_path.stat().st_size
                print(f"✅ Programmatic download successful! File size: {file_size:,} bytes")
                return True
            else:
                print(f"❌ Programmatic download failed - no file created")
                return False
                
        except Exception as e:
            print(f"❌ Programmatic method failed: {e}")
            return False
            
    except ImportError:
        print(f"⚠️ SciDownl not available for programmatic access")
        return False
    except Exception as e:
        print(f"❌ Programmatic test failed: {e}")
        return False

def test_manual_scihub_access(doi: str, output_path: Path = None):
    """Test manual SciHub access using requests"""
    
    if not output_path:
        output_path = Path(f"test_paper_manual_{doi.replace('/', '_').replace('.', '_')}.pdf")
    
    print(f"\n🔬 Testing manual SciHub access for DOI: {doi}")
    
    # Common SciHub domains to try
    scihub_domains = [
        "https://sci-hub.se",
        "https://sci-hub.st", 
        "https://sci-hub.ru",
        "https://sci-hub.ren"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for domain in scihub_domains:
        try:
            print(f"🌐 Trying {domain}...")
            
            # Try DOI URL
            scihub_url = f"{domain}/{doi}"
            
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(scihub_url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            print(f"✅ Successfully accessed {domain}")
            print(f"📄 Response length: {len(response.content):,} bytes")
            
            # Look for PDF download link in the response
            if response.headers.get('content-type', '').startswith('application/pdf'):
                # Direct PDF response
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                print(f"✅ PDF downloaded directly from {domain}")
                return True
            else:
                # HTML response - need to parse for PDF link
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for PDF links
                pdf_links = []
                for link in soup.find_all(['a', 'iframe', 'embed']):
                    href = link.get('href') or link.get('src')
                    if href and ('.pdf' in href.lower() or 'download' in href.lower()):
                        if not href.startswith('http'):
                            href = f"{domain}{href}" if href.startswith('/') else f"{domain}/{href}"
                        pdf_links.append(href)
                
                print(f"🔗 Found {len(pdf_links)} potential PDF links")
                
                # Try downloading from PDF links
                for pdf_url in pdf_links[:3]:  # Try first 3 links
                    try:
                        print(f"⬇️ Trying PDF URL: {pdf_url}")
                        pdf_response = session.get(pdf_url, timeout=60, allow_redirects=True)
                        pdf_response.raise_for_status()
                        
                        if pdf_response.headers.get('content-type', '').startswith('application/pdf'):
                            with open(output_path, 'wb') as f:
                                f.write(pdf_response.content)
                            
                            file_size = output_path.stat().st_size
                            print(f"✅ PDF downloaded from {pdf_url}! Size: {file_size:,} bytes")
                            return True
                    except Exception as e:
                        print(f"❌ PDF download failed from {pdf_url}: {e}")
                        continue
            
        except Exception as e:
            print(f"❌ Failed to access {domain}: {e}")
            continue
    
    print(f"❌ Manual SciHub access failed for all domains")
    return False

def test_grobid_server():
    """Test if GROBID server is working properly"""
    print(f"\n🔬 Testing GROBID server...")
    
    try:
        # Test isalive endpoint
        response = requests.get("http://localhost:8070/api/isalive", timeout=10)
        if response.status_code == 200 and response.text.strip().lower() == "true":
            print(f"✅ GROBID server is alive")
        else:
            print(f"⚠️ GROBID server responded but may have issues: {response.text}")
        
        # Test version endpoint
        try:
            version_response = requests.get("http://localhost:8070/api/version", timeout=10)
            if version_response.status_code == 200:
                print(f"✅ GROBID version: {version_response.text}")
            else:
                print(f"⚠️ GROBID version check failed: {version_response.status_code}")
        except:
            print(f"⚠️ Could not get GROBID version")
        
        return True
        
    except Exception as e:
        print(f"❌ GROBID server test failed: {e}")
        print(f"💡 Make sure GROBID is running on http://localhost:8070")
        return False

def main():
    print("🧪 SciHub Access Test Suite")
    print("=" * 50)
    
    # Test DOIs
    test_dois = [
        "10.1021/cr0503097",  # Your failing DOI
        "10.1038/nature06032",  # The discovered DOI
        "10.1093/nar/gkh793"   # Another from your list
    ]
    
    # Install SciDownl
    if not install_scidownl():
        print("❌ Cannot proceed without SciDownl")
        return
    
    # Test GROBID server
    grobid_ok = test_grobid_server()
    
    print(f"\n" + "=" * 50)
    print(f"🧪 Testing PDF Download Methods")
    print(f"=" * 50)
    
    results = {}
    
    for doi in test_dois:
        print(f"\n📄 Testing DOI: {doi}")
        print("-" * 30)
        
        results[doi] = {
            'scidownl_cli': False,
            'scidownl_prog': False,
            'manual_scihub': False
        }
        
        # Clean up any existing test files
        for pattern in [f"test_paper_*{doi.replace('/', '_').replace('.', '_')}*.pdf"]:
            for file in Path('.').glob(pattern):
                try:
                    file.unlink()
                except:
                    pass
        
        # Test 1: SciDownl CLI
        results[doi]['scidownl_cli'] = test_scidownl_download(doi)
        
        # Test 2: SciDownl Programmatic
        results[doi]['scidownl_prog'] = test_scidownl_programmatic(doi)
        
        # Test 3: Manual SciHub
        try:
            from bs4 import BeautifulSoup
            results[doi]['manual_scihub'] = test_manual_scihub_access(doi)
        except ImportError:
            print("⚠️ BeautifulSoup not available for manual SciHub test")
            print("   Install with: pip install beautifulsoup4")
    
    # Summary
    print(f"\n" + "=" * 50)
    print(f"📊 TEST RESULTS SUMMARY")
    print(f"=" * 50)
    
    print(f"GROBID Server: {'✅ Working' if grobid_ok else '❌ Issues'}")
    print()
    
    for doi, tests in results.items():
        print(f"DOI: {doi}")
        print(f"  SciDownl CLI:        {'✅' if tests['scidownl_cli'] else '❌'}")
        print(f"  SciDownl Programmatic: {'✅' if tests['scidownl_prog'] else '❌'}")
        print(f"  Manual SciHub:       {'✅' if tests['manual_scihub'] else '❌'}")
        print()
    
    # Recommendations
    working_methods = []
    if any(tests['scidownl_cli'] for tests in results.values()):
        working_methods.append("SciDownl CLI")
    if any(tests['scidownl_prog'] for tests in results.values()):
        working_methods.append("SciDownl Programmatic")
    if any(tests['manual_scihub'] for tests in results.values()):
        working_methods.append("Manual SciHub")
    
    print(f"💡 RECOMMENDATIONS:")
    if working_methods:
        print(f"✅ Working methods: {', '.join(working_methods)}")
        print(f"🔧 Consider integrating the working method(s) into your pipeline")
    else:
        print(f"❌ No methods worked reliably")
        print(f"🔧 Check internet connection and try different SciHub domains")
    
    if not grobid_ok:
        print(f"🔧 Fix GROBID server issues first - this is blocking PDF processing")

if __name__ == "__main__":
    main()
