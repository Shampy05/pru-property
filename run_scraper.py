#!/usr/bin/env python3
"""
Property Scraper - Run Script
This script runs the property scraper and can be scheduled as a recurring task.
"""
import os
import sys
import time
import json
import argparse
from datetime import datetime
from scrapper import PropertyScanner

def load_config(config_path):
    """Load configuration from file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        sys.exit(1)

def setup_logger(log_dir="logs"):
    """Set up basic logging to file."""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    # Redirect stdout and stderr to the log file
    sys.stdout = open(log_file, 'w')
    sys.stderr = sys.stdout
    
    print(f"=== Property Scraper Run - {datetime.now()} ===")
    return log_file

def main():
    """Main function to run the scraper."""
    parser = argparse.ArgumentParser(description="Run the property scraper")
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--log', action='store_true', help='Enable logging to file')
    args = parser.parse_args()
    
    log_file = None
    if args.log:
        log_file = setup_logger()
        print(f"Logging to: {log_file}")
    
    start_time = time.time()
    print(f"Starting scraper at {datetime.now()}")
    
    # Load configuration
    config = load_config(args.config)
    
    # Initialize and run scraper
    scraper = PropertyScanner(args.config)
    scraper.run_scraper()
    
    # Print summary
    end_time = time.time()
    print(f"Scraper completed in {end_time - start_time:.2f} seconds")
    print(f"Run completed at {datetime.now()}")
    
    # Reset stdout/stderr if logging was enabled
    if args.log:
        sys.stdout.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        print(f"Scraper run complete. Log saved to {log_file}")

if __name__ == "__main__":
    main() 