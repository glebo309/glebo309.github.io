#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI wrapper for the DOI-to-PDF fetcher.

This provides a simple graphical interface for downloading PDFs by DOI.
"""

import sys
import threading
from pathlib import Path
from tkinter import Tk, Label, Entry, Button, Text, Scrollbar, Frame, filedialog, StringVar
from tkinter import ttk
import tkinter.font as tkFont

# Ensure we can import the local fetcher module from this folder
CURRENT_DIR = Path(__file__).parent
sys.path.insert(0, str(CURRENT_DIR))

from fetch_pdf_by_doi import (
    download_pdf_with_fallbacks,
    normalize_doi,
    DEFAULT_OUTPUT_DIR,
    looks_like_doi,
    resolve_query_to_doi,
    clean_input,
    extract_doi_from_text,
)


class TextRedirector:
    """Redirects stdout/stderr to a Tkinter Text widget"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        
    def write(self, string):
        self.text_widget.insert('end', string)
        self.text_widget.see('end')
        self.text_widget.update_idletasks()
        
    def flush(self):
        pass


class PDFDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PaperDownloader")
        self.root.geometry("700x600")

        # Colors for dark theme
        bg_main = "#222222"
        bg_frame = "#2b2b2b"
        bg_entry = "#333333"
        bg_button = "#4CAF50"
        bg_button_disabled = "#555555"
        fg_text = "#f5f5f5"
        fg_muted = "#cccccc"
        
        # Status colors
        self.status_success = "#4CAF50"
        self.status_warning = "#FFA726"
        self.status_error = "#EF5350"

        # Apply window background
        self.root.configure(bg=bg_main)
        
        # Output directory
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure ttk styles
        style = ttk.Style()
        # Use a theme that respects custom styles more consistently across platforms
        try:
            style.theme_use('clam')
        except Exception:
            style.theme_use(style.theme_use())

        # Custom button styles to ensure readable colors on macOS
        # Use black text to avoid white-on-white issues with system button backgrounds
        style.configure("Green.TButton",
                        background=bg_button,
                        foreground="black",
                        font=("Helvetica", 12, "bold"))
        style.map("Green.TButton",
                   foreground=[('active', 'black'), ('disabled', '#555555')],
                   background=[('active', '#45a049'), ('disabled', bg_button_disabled)])
        style.configure("Grey.TButton",
                        background="#666666",
                        foreground="black",
                        font=("Helvetica", 10))
        style.map("Grey.TButton",
                   foreground=[('active', 'black')],
                   background=[('active', '#808080')])
        
        # Main container
        main_frame = Frame(root, padx=20, pady=20, bg=bg_main)
        main_frame.pack(fill='both', expand=True)
        
        # Title
        title_font = tkFont.Font(family="Helvetica", size=16, weight="bold")
        title_label = Label(main_frame, text="PaperDownloader", font=title_font,
                            bg=bg_main, fg=fg_text)
        title_label.pack(pady=(0, 20))
        
        # DOI input section
        input_frame = Frame(main_frame, bg=bg_main)
        input_frame.pack(fill='x', pady=(0, 10))
        
        doi_label = Label(input_frame, text="Enter DOI or citation:", font=("Helvetica", 11),
                          bg=bg_main, fg=fg_text)
        doi_label.pack(side='left', padx=(0, 10))
        
        self.doi_entry = Entry(input_frame, font=("Helvetica", 11), width=50,
                               bg=bg_entry, fg=fg_text, insertbackground=fg_text,
                               relief='flat')
        self.doi_entry.pack(side='left', fill='x', expand=True)
        self.doi_entry.bind('<Return>', lambda e: self.start_download())
        
        # Output directory section
        dir_frame = Frame(main_frame, bg=bg_main)
        dir_frame.pack(fill='x', pady=(0, 10))
        
        dir_label = Label(dir_frame, text="Save to:", font=("Helvetica", 11),
                          bg=bg_main, fg=fg_text)
        dir_label.pack(side='left', padx=(0, 10))
        
        self.dir_var = StringVar(value=str(self.output_dir))
        dir_entry = Entry(dir_frame, textvariable=self.dir_var, font=("Helvetica", 10),
                          width=40, bg=bg_entry, fg=fg_muted, insertbackground=fg_muted,
                          relief='flat')
        dir_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        dir_button = ttk.Button(dir_frame, text="Browse...",
                                command=self.browse_directory,
                                style="Grey.TButton")
        dir_button.pack(side='left')
        
        # Download button
        self.download_button = ttk.Button(main_frame, text="Download PDF", 
                                          command=self.start_download,
                                          style="Green.TButton")
        self.download_button.pack(pady=(10, 10))
        
        # Status banner
        self.status_frame = Frame(main_frame, bg=bg_main, height=30)
        self.status_frame.pack(fill='x', pady=(0, 10))
        self.status_label = Label(self.status_frame, text="", font=("Helvetica", 10),
                                  bg=bg_main, fg=fg_text, anchor='w')
        self.status_label.pack(fill='x', padx=5)
        
        # Output text area
        output_label = Label(main_frame, text="Output:", font=("Helvetica", 11),
                             bg=bg_main, fg=fg_text)
        output_label.pack(anchor='w', pady=(0, 5))
        
        text_frame = Frame(main_frame, bg=bg_frame)
        text_frame.pack(fill='both', expand=True)
        
        scrollbar = Scrollbar(text_frame, bg=bg_frame, troughcolor=bg_frame)
        scrollbar.pack(side='right', fill='y')
        
        self.output_text = Text(text_frame, wrap='word', 
                               yscrollcommand=scrollbar.set,
                               font=("Courier", 10),
                               bg="#111111", fg=fg_text,
                               insertbackground=fg_text,
                               relief='flat')
        self.output_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.output_text.yview)
        
        # Initial message
        self.output_text.insert('1.0', 
            "Enter a DOI or a full citation/title and click 'Download PDF' to start.\n"
            "Examples:\n"
            "  10.1038/nature12373\n"
            "  Bhalla, U. S.; Iyengar, R. Emergent Properties of Networks of Biological Signaling Pathways. "
            "Science 1999, 283, 381-387.\n\n"
            "The tool will first resolve citations to a DOI, then try multiple sources to find the PDF.\n"
        )
        
        # Status
        self.is_downloading = False

        # Store colors for later use
        self._bg_button = bg_button
        self._bg_button_disabled = bg_button_disabled
        
    def browse_directory(self):
        """Open directory browser"""
        directory = filedialog.askdirectory(
            initialdir=self.output_dir,
            title="Select output directory"
        )
        if directory:
            self.output_dir = Path(directory)
            self.dir_var.set(str(self.output_dir))
    
    def set_status(self, message: str, status_type: str = "info"):
        """Update status banner with color coding.
        
        status_type: 'success', 'warning', 'error', 'info'
        """
        color_map = {
            "success": self.status_success,
            "warning": self.status_warning,
            "error": self.status_error,
            "info": "#f5f5f5"
        }
        self.status_label.config(text=message, fg=color_map.get(status_type, "#f5f5f5"))
    
    def start_download(self):
        """Start the download in a background thread"""
        if self.is_downloading:
            self.output_text.insert('end', "\nDownload already in progress...\n")
            return
        
        user_input = self.doi_entry.get().strip()
        if not user_input:
            self.output_text.insert('end', "\nPlease enter a DOI or citation.\n")
            self.set_status("Please enter a DOI or citation.", "warning")
            return
        
        # Clear previous output and status
        self.output_text.delete('1.0', 'end')
        self.set_status("Starting...", "info")
        
        # Pre-flight checks
        thread = threading.Thread(target=self.preflight_and_download, args=(user_input,), daemon=True)
        thread.start()
    
    def preflight_and_download(self, user_input: str):
        """Run pre-flight checks then start download worker."""
        try:
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = TextRedirector(self.output_text)
            sys.stderr = TextRedirector(self.output_text)
            
            print("Running pre-flight checks...\n")
            
            # Check output directory writable
            try:
                test_file = self.output_dir / ".write_test"
                test_file.touch()
                test_file.unlink()
                print("Output directory is writable.")
            except Exception as e:
                print(f"Output directory is not writable: {e}")
                self.set_status("Cannot write to output folder. Choose another directory.", "error")
                return
            
            # Check network connectivity (quick Crossref ping)
            try:
                import requests
                r = requests.head("https://api.crossref.org/works", timeout=5)
                if r.status_code < 500:
                    print("Network connectivity OK.")
                else:
                    print("Warning: Crossref returned an error. Downloads may fail.")
                    self.set_status("Network issue detected. Downloads may fail.", "warning")
            except Exception as e:
                print(f"Network connectivity check failed: {e}")
                self.set_status("Cannot reach external services. Check your internet or VPN.", "error")
                return
            
            print("Pre-flight checks passed.\n")
            print("-" * 60)
            print()
            
            # Mark as busy
            self.is_downloading = True
            self.set_status("Processing...", "info")
            
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            # Start actual download
            self.download_worker(user_input)
            
        except Exception as e:
            print(f"\nPre-flight error: {e}")
            import traceback
            traceback.print_exc()
            self.set_status("Pre-flight checks failed.", "error")
            self.is_downloading = False
    
    def download_worker(self, user_input: str):
        """Worker thread that performs the download"""
        try:
            # Redirect stdout to the text widget
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = TextRedirector(self.output_text)
            sys.stderr = TextRedirector(self.output_text)
            
            # Clean input
            user_input = clean_input(user_input)
            print("Input:", user_input, "\n")
            
            # Try to extract DOI from text first
            extracted_doi = extract_doi_from_text(user_input)
            if extracted_doi:
                doi = normalize_doi(extracted_doi)
                print(f"Extracted DOI from input: {doi}\n")
                self.set_status(f"Found DOI: {doi}", "info")
            elif looks_like_doi(user_input):
                doi = normalize_doi(user_input)
                print(f"Interpreted input as DOI: {doi}\n")
                self.set_status(f"Processing DOI: {doi}", "info")
            else:
                print("Input does not look like a DOI. Trying to resolve it as a citation or title...\n")
                self.set_status("Resolving citation...", "info")
                candidates = resolve_query_to_doi(user_input, top_n=5)
                if not candidates:
                    print("Could not resolve the input to a unique DOI.\n"
                          "Please paste or type the DOI directly and try again.")
                    self.set_status("Could not resolve citation. Please paste DOI.", "warning")
                    return
                
                # Auto-pick if top score is high and much better than second
                if len(candidates) == 1 or (candidates[0]["score"] > 50 and len(candidates) > 1 and candidates[0]["score"] > candidates[1]["score"] * 1.5):
                    doi = normalize_doi(candidates[0]["doi"])
                    print(f"Resolved to DOI: {doi}")
                    print(f"  Title: {candidates[0]['title']}")
                    print(f"  Year: {candidates[0]['year']}\n")
                    self.set_status(f"Resolved to: {candidates[0]['title'][:50]}...", "info")
                else:
                    # Multiple candidates: show in GUI and ask user to pick
                    print("Multiple possible matches found:\n")
                    for i, cand in enumerate(candidates, 1):
                        print(f"  {i}. {cand['title']} ({cand['year']}) - {cand['journal']}")
                    print("\nPlease select the correct paper using the dialog...\n")
                    self.set_status("Multiple matches found. Please select one.", "warning")
                    
                    # Show selection dialog
                    selected_doi = self.show_candidate_dialog(candidates)
                    if not selected_doi:
                        print("Selection cancelled.")
                        self.set_status("Cancelled.", "warning")
                        return
                    doi = normalize_doi(selected_doi)
                    print(f"Selected DOI: {doi}\n")
                    self.set_status(f"Selected DOI: {doi}", "info")
            
            # Generate output filename
            safe_doi = doi.replace("/", "_").replace(".", "_")
            output_path = self.output_dir / f"{safe_doi}.pdf"
            
            print(f"Output will be saved to: {output_path}\n")
            print("-" * 60)
            print()
            
            # Perform the download
            success = download_pdf_with_fallbacks(doi, output_path)
            
            print()
            print("-" * 60)
            
            if success:
                print("\nDownload completed successfully.")
                print(f"PDF saved to: {output_path}")
                print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
                self.set_status("Downloaded successfully!", "success")
            else:
                print("\nFailed to download PDF from any source.")
                print("This could be because:")
                print("  • The paper is behind a paywall")
                print("  • The DOI is invalid or not found")
                print("  • Network connectivity issues")
                print("  • The paper is not available in digital format")
                self.set_status("Download failed. See log for details.", "error")
            
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
            self.set_status(f"Error: {str(e)[:50]}", "error")
        finally:
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            # Clear busy flag
            self.is_downloading = False
            # ttk style handles colors; no need to reset explicitly
    
    def show_candidate_dialog(self, candidates: list) -> str:
        """Show a dialog to select from multiple candidate DOIs.
        
        Returns the selected DOI or empty string if cancelled.
        """
        from tkinter import Toplevel, Listbox, SINGLE, END
        
        result = [""]
        
        def on_select():
            selection = listbox.curselection()
            if selection:
                idx = selection[0]
                result[0] = candidates[idx]["doi"]
                dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        dialog = Toplevel(self.root)
        dialog.title("Select Paper")
        dialog.geometry("600x300")
        dialog.configure(bg="#222222")
        
        Label(dialog, text="Multiple papers found. Select the correct one:",
              font=("Helvetica", 11), bg="#222222", fg="#f5f5f5").pack(pady=10)
        
        listbox = Listbox(dialog, font=("Courier", 10), bg="#333333", fg="#f5f5f5",
                         selectmode=SINGLE, height=10)
        listbox.pack(fill='both', expand=True, padx=10, pady=5)
        
        for i, cand in enumerate(candidates, 1):
            display = f"{i}. {cand['title'][:60]}... ({cand['year']}) - {cand['journal'][:30]}"
            listbox.insert(END, display)
        
        button_frame = Frame(dialog, bg="#222222")
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="Select", command=on_select,
                  style="Green.TButton").pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel,
                  style="Grey.TButton").pack(side='left', padx=5)
        
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)
        
        return result[0]


def main():
    root = Tk()
    app = PDFDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
