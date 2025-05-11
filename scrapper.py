# import pandas as pd
# import numpy as np
import json
import os
import requests
import re
from datetime import datetime
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("property_scraper")

class PropertyScanner:
    def __init__(self, config_path):
        self.config = self._load_config(config_path)
        self.seen_listings = self._load_seen_listings()
        self.sort_type = self.config.get("sort_type", "default")
        self.adapters = self._initialize_adapters()
        logger.info(f"Using sort type: {self.sort_type}")

    def _load_config(self, config_path):
        try:
            logger.info(f"Loading config from: {config_path}")
            with open(config_path) as f:
                config = json.load(f)
                logger.info(f"Loaded config: {config}")
                return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def _initialize_adapters(self):
        return {
            "rightmove": RightmoveAdapter(self.config, self.sort_type),
            "zoopla": ZooplaAdapter(self.config, self.sort_type),
            "spareroom": SpareroomAdapter(self.config, self.sort_type),
            "onthemarket": OnTheMarketAdapter(self.config, self.sort_type),
            "openrent": OpenRentAdapter(self.config, self.sort_type)
        }

    def _load_seen_listings(self):
        if os.path.exists("seen_listings.csv"):
            try:
                with open("seen_listings.csv", "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load seen listings: {e}")
        return {}

    def _save_seen_listings(self):
        try:
            with open("seen_listings.csv", "w") as f:
                json.dump(self.seen_listings, f)
        except Exception as e:
            logger.error(f"Failed to save seen listings: {e}")

    def run_scraper(self):
        """Main method to run the scraper process"""
        try:
            logger.info("Fetching listings...")
            listings = self.fetch_listings()
            logger.info(f"Found {len(listings)} listings")

            logger.info("Filtering listings...")
            filtered_listings = self.filter_listings(listings)
            logger.info(f"Filtered to {len(filtered_listings)} listings")

            if filtered_listings:
                logger.info("Notifying user...")
                # self.notify_user(filtered_listings)
                logger.info("User notified")

            self._save_seen_listings()
            logger.info("Seen listings saved")
            
        except Exception as e:
            logger.error(f"Error running scraper: {e}", exc_info=True)

    def fetch_listings(self):
        """Fetch listings from all enabled sites"""
        all_listings = []
        sites = self._get_enabled_sites()
        
        for site_name in sites:
            try:
                adapter = self.adapters.get(site_name.lower())
                if not adapter:
                    logger.warning(f"No adapter available for {site_name}")
                    continue
                    
                logger.info(f"Fetching from {site_name} with sort type: {self.sort_type}...")
                url = adapter.build_url()
                raw_data = adapter.fetch_listings(url)
                site_listings = adapter.parse_listings(raw_data)
                logger.info(f"Found {len(site_listings)} listings from {site_name}")
                all_listings.extend(site_listings)
                
            except Exception as e:
                logger.error(f"Failed to fetch listings from {site_name}: {e}")
                
        return all_listings

    def _get_enabled_sites(self):
        """Get list of enabled sites from config"""
        sites = self.config.get("sites", {})
        enabled_sites = []
        
        logger.info(f"Sites from config: {sites}")
        
        for site, site_config in sites.items():
            logger.info(f"Checking site {site}: {site_config}")
            if site_config.get("enabled", True):
                enabled_sites.append(site)
                logger.info(f"Added {site} to enabled sites")
        
        # Default to rightmove if no sites specified
        if not enabled_sites:
            enabled_sites = ["rightmove"]
            logger.info("No enabled sites found, defaulting to rightmove")
            
        logger.info(f"Enabled sites: {enabled_sites}")
        return enabled_sites

    def filter_listings(self, listings):
        """Filter listings based on criteria and previously seen status"""
        filtered_listings = []
        logger.info(f"Starting filtering with {len(listings)} listings")
        
        bypass_seen_check = self.config.get("debug", {}).get("bypass_seen_check", False)
        
        for listing in listings:
            # Skip if we've seen this listing before
            if listing['id'] in self.seen_listings and not bypass_seen_check:
                continue
                
            # Apply filtering criteria
            if self._meets_criteria(listing):
                filtered_listings.append(listing)
                self.seen_listings[listing['id']] = datetime.now().isoformat()
        
        return filtered_listings

    def _meets_criteria(self, listing):
        """Check if listing meets the search criteria"""
        if not listing:
            return False
            
        # Get filters from config
        filters = self.config.get("filters", {})
        keywords = filters.get("keywords", [])
        exclude_keywords = filters.get("exclude_keywords", [])
        min_price = filters.get("min_price")
        max_price = filters.get("max_price")
        min_beds = filters.get("min_beds")
        max_beds = filters.get("max_beds")
        
        # Extract text to check
        listing_text = f"{listing.get('title', '')} {listing.get('address', '')} {listing.get('description', '')}".lower()
        
        # Check for excluded keywords
        for keyword in exclude_keywords:
            if keyword.lower() in listing_text:
                return False
        
        # Check for required keywords
        if keywords:
            matches_keyword = any(keyword.lower() in listing_text for keyword in keywords)
            if not matches_keyword:
                return False
        
        # Price check
        if min_price is not None or max_price is not None:
            try:
                price = int(listing.get('price', 0))
                if min_price is not None and price < min_price:
                    return False
                if max_price is not None and price > max_price:
                    return False
            except (ValueError, TypeError):
                pass
        
        # Bedrooms check
        if min_beds is not None or max_beds is not None:
            try:
                beds = int(listing.get('bedrooms', 0))
                if min_beds is not None and beds < min_beds:
                    return False
                if max_beds is not None and beds > max_beds:
                    return False
            except (ValueError, TypeError):
                pass
        
        return True

    def notify_user(self, listings):
        """Send notification to user about new listings"""
        try:
            self._send_email(listings)
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            self._print_listings(listings)

    def _send_email(self, listings):
        """Send email notification with listings"""
        email_config = self.config.get("notifications", {}).get("email", {})
        if not email_config:
            logger.warning("No email configuration found")
            return

        try:
            message = MIMEMultipart()
            message["From"] = email_config.get("sender")
            message["To"] = email_config.get("recipient")
            message["Subject"] = f"New Properties Found: {len(listings)} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            body = "New properties found:\n\n"
            for listing in listings:
                body += f"{listing.get('title', 'Property')} - {listing.get('price_text', '')} - {listing.get('address', '')} - [{listing.get('source', 'unknown')}]\n"
                body += f"Link: {listing.get('link', '')}\n\n"

            message.attach(MIMEText(body, "plain"))

            with smtplib.SMTP_SSL(email_config.get("smtp_server"), email_config.get("smtp_port", 465)) as server:
                server.login(email_config.get("username"), email_config.get("password"))
                server.send_message(message)

            logger.info("Email notification sent successfully!")
        except Exception as e:
            raise Exception(f"Failed to send email: {e}")

    def _print_listings(self, listings):
        """Fallback method to print listings if email fails"""
        logger.info("Printing listings:")
        for i, listing in enumerate(listings[:5]):
            print(f"{listing.get('title', 'Property')} - {listing.get('price_text', '')} - {listing.get('address', '')}")
            print(f"Link: {listing.get('link', '')}")
            print("")
            
        if len(listings) > 5:
            print(f"... and {len(listings) - 5} more listings")


class BaseAdapter:
    """Base class for all property site adapters"""
    def __init__(self, config, sort_type="default"):
        self.config = config
        self.sort_type = sort_type
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }
        logger.info(f"Initializing adapter with sort type: {sort_type}")

    def build_url(self):
        """Build search URL based on config parameters"""
        raise NotImplementedError("Subclasses must implement build_url")
    
    def fetch_listings(self, url):
        """Fetch raw data from the property site"""
        logger.info(f"Fetching from URL: {url}")
        response = requests.get(url, headers=self.headers)
        logger.info(f"Response status: {response.status_code}")
        return response.text
    
    def parse_listings(self, raw_data):
        """Parse raw data into standardized listing format"""
        raise NotImplementedError("Subclasses must implement parse_listings")
        
    def get_sort_parameter(self, site_specific=False):
        """Get the sorting parameter based on the sort type.
        Returns a string to be added to the URL or None if no sorting is needed."""
        return None


class RightmoveAdapter(BaseAdapter):
    def __init__(self, config, sort_type="default"):
        super().__init__(config, sort_type)
        self.config = config.get("rightmove", {})
        self.base_url = self.config.get("base_url", "https://www.rightmove.co.uk")
        self.search_url = self.config.get("search_url", "https://www.rightmove.co.uk/property-to-rent/find.html")
        self.params = self.config.get("params", {})

    def get_sort_parameter(self, site_specific=False):
        """Get Rightmove-specific sort parameter
        sortType=2 (for highest price first)
        sortType=1 (for lowest price first)
        sortType=6 (for newest first)
        sortType=10 (for oldest first)
        """
        if site_specific and self.sort_type != "default":
            return self.sort_type
            
        sort_mapping = {
            "price_high_to_low": "sortType=2",
            "price_low_to_high": "sortType=1",
            "newest_first": "sortType=6", 
            "oldest_first": "sortType=10",
            "default": "sortType=6"  # Default to newest first
        }
        
        return sort_mapping.get(self.sort_type, sort_mapping["default"])

    def build_url(self):
        """Build Rightmove search URL"""
        location_identifier = self.params.get("location_identifier", "REGION^219")
        radius = self.params.get("radius", 0.0)
        include_let_agreed = self.params.get("include_let_agreed", False)
        min_price = self.params.get("min_price", 0)
        max_price = self.params.get("max_price", 1200)
        min_beds = self.params.get("min_beds", 1)
        max_beds = self.params.get("max_beds", 1)
        dont_show = self.params.get("dont_show", "houseShare,student,retirement")
        let_type = self.params.get("let_type", "shortTerm")

        url = f"{self.search_url}?" + \
              f"locationIdentifier={location_identifier}" + \
              f"&minPrice={min_price}" + \
              f"&maxPrice={max_price}" + \
              f"&minBedrooms={min_beds}" + \
              f"&maxBedrooms={max_beds}" + \
              f"&radius={radius}" + \
              f"&includeLetAgreed={str(include_let_agreed).lower()}" + \
              f"&dontShow={dont_show}" + \
              f"&letType={let_type}" + \
              f"&propertyTypes=&mustHave=&dontShow=&furnishTypes=&keywords="
        
        # Add sorting parameter
        sort_param = self.get_sort_parameter()
        if sort_param:
            url += f"&{sort_param}"
             
        return url
    
    def fetch_listings(self, url):
        """Fetch raw data with enhanced browser-like behavior"""
        logger.info(f"Fetching from URL: {url}")
        
        # Add delay to mimic human behavior
        import time
        import random
        time.sleep(random.uniform(1, 3))
        
        try:
            # Create a session to maintain cookies
            session = requests.Session()
            
            # First visit the homepage to get cookies
            logger.info("Visiting Rightmove homepage to get cookies...")
            session.get("https://www.rightmove.co.uk/", headers=self.headers)
            
            # Then visit the search page
            logger.info("Visiting search page...")
            response = session.get(url, headers=self.headers)
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 403:
                logger.error("Received 403 Forbidden - Rightmove may be blocking scrapers")
                logger.info("Trying alternative approach...")
                
                # Try with different user agent
                alt_headers = self.headers.copy()
                alt_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                response = session.get(url, headers=alt_headers)
                logger.info(f"Alternative approach response status: {response.status_code}")
                
            return response.text
        except Exception as e:
            logger.error(f"Error fetching Rightmove listings: {e}")
            return ""
    
    def parse_listings(self, raw_data):
        """Parse Rightmove HTML into listings"""
        listings = []
        soup = BeautifulSoup(raw_data, 'html.parser')
            
        if not listings:
            listings = self._parse_from_json_data(soup, raw_data)
            
        logger.info(f"Found {len(listings)} Rightmove listings")
        return listings
    
    def _parse_from_json_data(self, soup, raw_data):
        """Parse listings from JSON data in the page"""
        listings = []
        
        try:
            # Try to find the JSON data in the __NEXT_DATA__ script tag
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script:
                json_data = json.loads(next_data_script.string)
                
                # Navigate to the property data in the JSON structure
                property_data = None
                if 'props' in json_data and 'pageProps' in json_data['props']:
                    page_props = json_data['props']['pageProps']
                    
                    if 'propertyData' in page_props:
                        property_data = page_props['propertyData'].get('properties', [])
                    elif 'searchResults' in page_props:
                        property_data = page_props['searchResults'].get('properties', [])
                
                # Check if we got property data
                if property_data:
                    for prop in property_data:
                        try:
                            # Extract the necessary information
                            prop_id = prop.get('id')
                            summary = prop.get('summary', '')
                            bedrooms = prop.get('bedrooms', 1)
                            address = prop.get('displayAddress', '')
                            
                            # Extract price
                            price_data = prop.get('price', {})
                            amount = price_data.get('amount', 0)
                            display_prices = price_data.get('displayPrices', [])
                            price_text = display_prices[0].get('displayPrice', f"£{amount}") if display_prices else f"£{amount}"
                            
                            # Extract URL
                            property_url = prop.get('propertyUrl', '')
                            
                            # Create listing
                            listing = {
                                "id": str(prop_id),
                                "title": summary[:100] if summary else "Property",
                                "price": amount,
                                "price_text": price_text,
                                "address": address,
                                "bedrooms": bedrooms,
                                "link": f"https://www.rightmove.co.uk{property_url}" if property_url else "",
                                "source": "rightmove"
                            }
                            
                            # Extract images
                            if 'propertyImages' in prop and 'images' in prop['propertyImages']:
                                listing['images'] = [img.get('srcUrl') for img in prop['propertyImages']['images'] if 'srcUrl' in img]
                            
                            listings.append(listing)
                        except Exception as e:
                            logger.error(f"Error parsing property from JSON: {e}")
        except Exception as e:
            logger.error(f"Error extracting JSON data: {e}")
            
        return listings


class ZooplaAdapter(BaseAdapter):
    """Adapter for Zoopla property site"""
    def __init__(self, config, sort_type="default"):
        super().__init__(config, sort_type)
        # Enhanced headers to mimic a real browser
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.zoopla.co.uk/",
            "sec-ch-ua": "\"Google Chrome\";v=\"120\", \"Chromium\";v=\"120\", \"Not=A?Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "Connection": "keep-alive",
            "Cookie": "",  # Add any necessary cookies
            "Upgrade-Insecure-Requests": "1"
        }
        
        self.config = config.get("zoopla", {})
        self.base_url = self.config.get("base_url", "https://www.zoopla.co.uk")
        self.search_url = self.config.get("search_url", "https://www.zoopla.co.uk/to-rent/property/")
        self.params = self.config.get("params", {})
    
    def get_sort_parameter(self, site_specific=False):
        """Get Zoopla-specific sort parameter 
        (Not fully implemented since Zoopla is under construction)
        """
        # Since Zoopla is under construction, we're just adding this method for consistency
        return ""

    def build_url(self):
        """Build Zoopla search URL"""
        location = self.params.get("location", "bristol")
        q = self.params.get("q", "property bristol bristol")
        beds_min = self.params.get("beds_min", 0)
        beds_max = self.params.get("beds_max", 1)
        radius = self.params.get("radius", 0.0)
        price_max = self.params.get("price_max", 1500)
        price_min = self.params.get("price_min", 0)
        price_frequency = self.params.get("price_frequency", "per_month")
        is_retirement_home = self.params.get("is_retirement_home", False)
        is_shared_accommodation = self.params.get("is_shared_accommodation", False)
        is_student_accommodation = self.params.get("is_student_accommodation", False)
        search_source = self.params.get("search_source", "to-rent")
        furnished_state = self.params.get("furnished_state", "any")
        available_from = self.params.get("available_from", "1month")

        # More parameters for a complete URL
        url = f"{self.search_url}{location}?" + \
              f"q={q}&" + \
              f"beds_min={beds_min}&" + \
              f"beds_max={beds_max}&" + \
              f"price_min={price_min}&" + \
              f"price_max={price_max}&" + \
              f"radius={radius}&" + \
              f"price_frequency={price_frequency}&" + \
              f"search_source={search_source}&" + \
              f"is_retirement_home={is_retirement_home}&" + \
              f"is_shared_accommodation={is_shared_accommodation}&" + \
              f"is_student_accommodation={is_student_accommodation}&" + \
              f"furnished_state={furnished_state}&" + \
              f"available_from={available_from}"
        
        logger.info(f"Zoopla URL: {url}")
        return url
    
    def fetch_listings(self, url):
        """Fetch raw data with enhanced browser-like behavior"""
        logger.info(f"Fetching from URL: {url}")
        
        # Add delay to mimic human behavior
        import time
        import random
        time.sleep(random.uniform(1, 3))
        
        try:
            # Create a session to maintain cookies
            session = requests.Session()
            
            # First visit the homepage to get cookies
            logger.info("Visiting Zoopla homepage to get cookies...")
            session.get("https://www.zoopla.co.uk/", headers=self.headers)
            
            # Then visit the search page
            logger.info("Visiting search page...")
            response = session.get(url, headers=self.headers)
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 403:
                logger.error("Received 403 Forbidden - Zoopla may be blocking scrapers")
                logger.info("Trying alternative approach...")
                
                # Try with different user agent
                alt_headers = self.headers.copy()
                alt_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                response = session.get(url, headers=alt_headers)
                logger.info(f"Alternative approach response status: {response.status_code}")
            
            return response.text
        except Exception as e:
            logger.error(f"Error fetching Zoopla listings: {e}")
            return ""
    
    def parse_listings(self, raw_data):
        """Parse Zoopla HTML into listings"""
        listings = []
        soup = BeautifulSoup(raw_data, 'html.parser')
        
        # Try to parse listings from the search results page
        property_cards = soup.select('.css-wfndrn-StyledSearchResult, .srp-result, .l-searchResult')
        
        if not property_cards:
            # Try alternative CSS selectors
            property_cards = soup.select('[data-testid="search-result"]') or soup.select('.e2uk8e18, .e2uk8e4')
        
        logger.info(f"Found {len(property_cards)} Zoopla property cards")
        
        for card in property_cards:
            try:
                # Extract property ID
                id_elem = card.get('id', '') or card.get('data-listing-id', '')
                
                if not id_elem:
                    # Try to extract from URL
                    link_elem = card.select_one('a[href*="/details/"]')
                    if link_elem and link_elem.get('href'):
                        id_match = re.search(r'/details/(\d+)', link_elem.get('href'))
                        if id_match:
                            id_elem = id_match.group(1)
                
                # Skip if we can't identify this property
                if not id_elem:
                    continue
                
                # Extract title/summary
                title_elem = card.select_one('.e2uk8e3, .css-vthwmi-DisplayStyle-Heading, .listing-title, h2')
                title = title_elem.text.strip() if title_elem else "Property"
                
                # Extract address
                address_elem = card.select_one('.e2uk8e15, .css-wxtc4h-DisplayStyle, .listing-address, [data-testid="address"]')
                address = address_elem.text.strip() if address_elem else ""
                
                # Extract price
                price_elem = card.select_one('.c-SrZLJz, .css-1h0liy1-DisplayStyle-PropertyPrice, .listing-price, [data-testid="price"]')
                price_text = price_elem.text.strip() if price_elem else "Price not specified"
                
                # Extract price value
                price = 0
                if price_elem:
                    price_match = re.search(r'£([\d,]+)', price_text) or re.search(r'([\d,]+)', price_text)
                    if price_match:
                        price_str = price_match.group(1).replace(',', '')
                        try:
                            price = int(price_str)
                            # Convert if not already monthly
                            if 'pw' in price_text.lower():
                                price = price * 4  # Approximate conversion
                        except (ValueError, TypeError):
                            pass
                
                # Extract link
                link_elem = card.select_one('a[href*="/details/"], a[href*="/to-rent/details/"]')
                link = link_elem.get('href') if link_elem else ""
                
                # Fix relative URLs
                if link and not link.startswith('http'):
                    link = f"https://www.zoopla.co.uk{link}"
                
                # Extract bedrooms
                beds_elem = card.select_one('.c-PJLV-cyFDVT, [data-testid="beds"], .icon-bed + span')
                bedrooms = 1  # Default
                if beds_elem:
                    beds_match = re.search(r'(\d+)', beds_elem.text)
                    if beds_match:
                        bedrooms = int(beds_match.group(1))
                
                # Extract images
                img_elems = card.select('img')
                images = []
                for img in img_elems:
                    src = img.get('src') or img.get('data-src')
                    if src and not src.endswith('svg') and 'placeholder' not in src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        images.append(src)
                
                # Create listing
                listing = {
                    "id": f"zoopla-{id_elem}",
                    "title": title,
                    "price": price,
                    "price_text": price_text,
                    "address": address,
                    "bedrooms": bedrooms,
                    "link": link,
                    "images": images,
                    "source": "zoopla"
                }
                
                listings.append(listing)
                
            except Exception as e:
                logger.error(f"Error parsing Zoopla property: {e}")
        
        # Try extracting from JSON data if HTML parsing didn't work
        if not listings:
            listings = self._parse_from_json_data(soup, raw_data)
        
        logger.info(f"Found {len(listings)} Zoopla listings")
        return listings
    
    def _parse_from_json_data(self, soup, raw_data):
        """Try to extract listings from JSON data in the page"""
        listings = []
        
        try:
            # Look for JSON data in script tags
            script_tags = soup.select('script[type="application/json"], script#__NEXT_DATA__')
            
            for script in script_tags:
                try:
                    json_data = json.loads(script.string)
                    
                    # Try to find property listings in various JSON structures
                    property_data = self._extract_property_data_from_json(json_data)
                    
                    if property_data:
                        for prop in property_data:
                            try:
                                # Extract basic property info
                                prop_id = prop.get('id', prop.get('listingId', ''))
                                
                                # Skip if no ID
                                if not prop_id:
                                    continue
                                
                                # Extract other details
                                title = prop.get('title', prop.get('displayAddress', 'Property'))
                                address = prop.get('displayAddress', prop.get('address', ''))
                                
                                # Extract price
                                price = 0
                                price_text = "Price not specified"
                                
                                price_data = prop.get('price', {})
                                if isinstance(price_data, dict):
                                    # Get the monthly price amount
                                    price = price_data.get('amount', 0)
                                    display_price = price_data.get('display', "")
                                    
                                    # If we have a display price, parse it to make sure we get the pcm value
                                    if display_price:
                                        pcm_match = re.search(r'£([\d,]+)\s*pcm', display_price)
                                        if pcm_match:
                                            try:
                                                price = int(pcm_match.group(1).replace(',', ''))
                                            except (ValueError, TypeError):
                                                pass
                                    
                                    price_text = display_price or f"£{price} pcm"
                                elif isinstance(price_data, (int, float)):
                                    price = price_data
                                    price_text = f"£{price} pcm"
                                
                                # Extract bedrooms
                                bedrooms = 1  # Default
                                if 'bedrooms' in prop:
                                    bedrooms = prop.get('bedrooms', 1)
                                elif 'features' in prop:
                                    for feature in prop.get('features', []):
                                        if 'bedroom' in feature.lower():
                                            beds_match = re.search(r'(\d+)', feature)
                                            if beds_match:
                                                bedrooms = int(beds_match.group(1))
                                
                                # Extract URL
                                link = prop.get('propertyUrl', prop.get('url', ''))
                                if link and not link.startswith('http'):
                                    link = f"https://www.zoopla.co.uk{link}"
                                
                                # Extract images
                                images = []
                                for img_key in ['images', 'propertyImages', 'photos']:
                                    img_data = prop.get(img_key, [])
                                    if img_data and isinstance(img_data, list):
                                        for img in img_data:
                                            if isinstance(img, dict):
                                                img_url = img.get('url', img.get('src', ''))
                                                if img_url:
                                                    if img_url.startswith('//'):
                                                        img_url = 'https:' + img_url
                                                    if not img_url.startswith('http'):
                                                        img_url = 'https://www.zoopla.co.uk' + img_url
                                                    images.append(img_url)
                                            elif isinstance(img, str):
                                                if img.startswith('//'):
                                                    img = 'https:' + img
                                                images.append(img)
                                
                                # Create listing
                                listing = {
                                    "id": f"zoopla-{prop_id}",
                                    "title": title,
                                    "price": price,
                                    "price_text": price_text,
                                    "address": address,
                                    "bedrooms": bedrooms,
                                    "link": link,
                                    "images": images,
                                    "source": "zoopla"
                                }
                                
                                listings.append(listing)
                            except Exception as e:
                                logger.error(f"Error parsing Zoopla property from JSON: {e}")
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"Error extracting Zoopla JSON data: {e}")
            
        return listings
    
    def _extract_property_data_from_json(self, json_data):
        """Extract property data from various JSON structures"""
        # Try common paths where property data might be found
        paths = [
            ['props', 'pageProps', 'initialResults', 'properties'],
            ['props', 'pageProps', 'initialResults', 'listings'],
            ['props', 'pageProps', 'searchResults', 'listings'],
            ['initialState', 'searchResults', 'properties'],
            ['initialState', 'searchResults', 'listings'],
            ['results', 'properties'],
            ['results', 'listings']
        ]
        
        for path in paths:
            try:
                # Navigate through the JSON structure
                data = json_data
                for key in path:
                    if key in data:
                        data = data[key]
                    else:
                        data = None
                        break
                
                if data and isinstance(data, list) and len(data) > 0:
                    return data
            except:
                pass
        
        return []

class OnTheMarketAdapter(BaseAdapter):
    """Adapter for OnTheMarket property site"""
    def __init__(self, config, sort_type="default"):
        super().__init__(config, sort_type)
        self.config = config.get("onthemarket", {})
        self.base_url = self.config.get("base_url", "https://www.onthemarket.com")
        self.search_url = self.config.get("search_url", "https://www.onthemarket.com/property-to-rent/bristol")
        self.params = self.config.get("params", {})
        
    def get_sort_parameter(self, site_specific=False):
        """Get OnTheMarket-specific sort parameter
        sort-field=price (for highest first)
        direction=asc&sort-field=price (for lowest first)
        sort-field=update_date (for newest first)
        no sort param for recommended listings
        """
        if site_specific and self.sort_type != "default":
            return self.sort_type
            
        sort_mapping = {
            "price_high_to_low": "sort-field=price",
            "price_low_to_high": "direction=asc&sort-field=price",
            "newest_first": "sort-field=update_date",
            "default": ""  # Default to recommended
        }
        
        return sort_mapping.get(self.sort_type, sort_mapping["default"])
        
    def build_url(self):
        """Build OnTheMarket search URL"""
        location = self.params.get("location", "bristol")
        max_bedrooms = self.params.get("max-bedrooms", 1)
        min_bedrooms = self.params.get("min-bedrooms", 0)
        max_price = self.params.get("max-price", 1500)
        min_price = self.params.get("min-price", 0)
        let_length = self.params.get("let-length", "short-term")
        furnished = self.params.get("furnished", "furnished")
        shared = self.params.get("shared", False)
        student = self.params.get("student", False)
        
        # Construct URL with search parameters
        url = f"{self.base_url}/to-rent/property/{location}/" + \
              f"?min-bedrooms={min_bedrooms}" + \
              f"&max-bedrooms={max_bedrooms}" + \
              f"&max-price={max_price}" + \
              f"&let-length={let_length}" + \
              f"&furnished={furnished}" + \
              f"&shared={shared}" + \
              f"&student={student}"
        
        # Add sorting parameter
        sort_param = self.get_sort_parameter()
        if sort_param:
            url += f"&{sort_param}"
            
        logger.info(f"OnTheMarket URL: {url}")
        return url

    def parse_listings(self, raw_data):
        """Parse OnTheMarket HTML into listings"""
        listings = []
        soup = BeautifulSoup(raw_data, 'html.parser')
        
        # Try to parse property cards
        property_cards = soup.select('.property-details, .property-result, li.otm-PropertyCard')
        
        if not property_cards:
            # Try alternative selectors
            property_cards = soup.select('[data-test="property-card"], [data-properties-link], .property')
        
        logger.info(f"Found {len(property_cards)} OnTheMarket property cards")
        
        for card in property_cards:
            try:
                # Extract property ID from URL or data attribute
                id_elem = card.get('id', '') or card.get('data-property-id', '')
                
                if not id_elem:
                    # Try to extract from link
                    link_elem = card.select_one('a[href*="/details/"]')
                    if link_elem and link_elem.get('href'):
                        id_match = re.search(r'/details/([^/]+)', link_elem.get('href'))
                        if id_match:
                            id_elem = id_match.group(1)
                
                # Skip if we can't identify this property
                if not id_elem:
                    continue
                
                # Extract title/summary
                title_elem = card.select_one('h2.title, h3.title, .otm-PropertyCardDetails-title, [data-test="property-title"]')
                address_elem = card.select_one('.address, .otm-PropertyCardAddress, [data-test="address"]')
                
                # Sometimes the title contains the address
                title = title_elem.text.strip() if title_elem else "Property"
                address = address_elem.text.strip() if address_elem else ""
                
                if not address and "," in title:
                    # Try to extract address from title if no separate address
                    address = title
                    title = f"{address.split(',')[0]} Property"
                
                # Extract price - simplified approach for OnTheMarket's structure
                price_text = "Price not specified"
                price = 0
                
                # Get the parent element that contains both carousel and price
                parent_card = card.find_parent('div', class_='property-row')
                if not parent_card:
                    parent_card = card.find_parent('div', class_='property-card')
                if not parent_card:
                    parent_card = card.find_parent('div', class_='listing-item')
                
                # Debug: Print the parent card HTML to see the actual structure
                print("DEBUG: Parent Card HTML structure:")
                print(parent_card.prettify() if parent_card else "No parent card found")
                
                # Find price element using the known structure
                price_elem = None
                if parent_card:
                    price_elem = parent_card.select_one('.pim h2, .price, [class*="price"]')
                print(f"DEBUG: Price Element: {price_elem}")
                
                if price_elem:
                    # Get the price text and remove any whitespace
                    price_text = price_elem.text.strip()
                    
                    # Extract the numeric value
                    price_match = re.search(r'£([\d,]+)', price_text)
                    if price_match:
                        try:
                            price = int(price_match.group(1).replace(',', ''))
                            # Add "per month" if not present
                            if "per month" not in price_text.lower():
                                price_text = f"£{price} per month"
                        except (ValueError, TypeError):
                            pass
                
                # Extract link
                link_elem = card.select_one('a[href*="/details/"]')
                link = link_elem.get('href', '') if link_elem else ""
                
                # Fix relative URLs
                if link and not link.startswith('http'):
                    link = f"https://www.onthemarket.com{link}"
                
                # Extract bedrooms
                beds_elem = card.select_one('.bed-icon + span, [data-test="beds"], .otm-IconBed + span')
                bedrooms = 1  # Default
                if beds_elem:
                    beds_match = re.search(r'(\d+)', beds_elem.text)
                    if beds_match:
                        bedrooms = int(beds_match.group(1))
                
                # Extract description (if available)
                description_elem = card.select_one('.description, .otm-PropertyCardDescription, [data-test="description"]')
                description = description_elem.text.strip() if description_elem else ""
                
                # Extract images
                img_elems = card.select('img.property-image, .otm-PropertyCardMedia img, [data-test="property-image"]')
                images = []
                
                for img in img_elems:
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src and 'placeholder' not in src.lower() and not src.endswith('svg'):
                        if src.startswith('//'):
                            src = 'https:' + src
                        images.append(src)
                
                # Create listing
                listing = {
                    "id": f"otm-{id_elem}",
                    "title": title,
                    "price": price,
                    "price_text": price_text,
                    "address": address,
                    "bedrooms": bedrooms,
                    "description": description,
                    "link": link,
                    "images": images,
                    "source": "onthemarket"
                }
                
                listings.append(listing)
                
            except Exception as e:
                logger.error(f"Error parsing OnTheMarket property: {e}")
        
        logger.info(f"Found {len(listings)} OnTheMarket listings")
        return listings

class SpareroomAdapter(BaseAdapter):
    def __init__(self, config, sort_type="default"):
        super().__init__(config, sort_type)
        self.config = config.get("spareroom", {})
        self.base_url = self.config.get("base_url", "https://www.spareroom.co.uk")
        self.search_url = self.config.get("search_url", "https://www.spareroom.co.uk/flatshare/?search_id=1361538853&mode=list")
        self.params = self.config.get("params", {})

    def get_sort_parameter(self, site_specific=False):
        """Get SpareRoom-specific sort parameter
        sort_by=days_since_placed (for newest adds)
        sort_by=last_updated (for last updated)
        sort_by=price_low_to_high (for price lowest first)
        sort_by=price_high_to_low (for prices highest first)
        """
        if site_specific and self.sort_type != "default":
            return self.sort_type
            
        sort_mapping = {
            "price_high_to_low": "sort_by=price_high_to_low",
            "price_low_to_high": "sort_by=price_low_to_high",
            "newest_first": "sort_by=days_since_placed", 
            "last_updated": "sort_by=last_updated",
            "default": "sort_by=days_since_placed"  # Default to newest
        }
        
        return sort_mapping.get(self.sort_type, sort_mapping["default"])

    def build_url(self):
        """Build SpareRoom search URL"""
        url = f"{self.search_url}"
        
        # Add sorting parameter
        sort_param = self.get_sort_parameter()
        if sort_param:
            # Check if URL already has parameters
            separator = "&" if "?" in url else "?"
            url += f"{separator}{sort_param}"
            
        return url
    
    def parse_listings(self, raw_data):
        """Parse SpareRoom HTML into listings"""
        listings = []
        soup = BeautifulSoup(raw_data, 'html.parser')
        
        # Try different selectors for property cards
        property_cards = soup.select('li.listing-result') or soup.select('article.listing-card')
        
        for card in property_cards:
            try:
                # Extract ID
                listing_id = card.get('data-listing-id', '')
                if not listing_id:
                    # Look for id in parent li if we're looking at an article
                    parent_li = card.find_parent('li')
                    if parent_li:
                        listing_id = parent_li.get('data-listing-id', '')
                
                # If still no ID, generate a random one
                if not listing_id:
                    listing_id = f"sr-{datetime.now().timestamp()}"
                
                # Extract price
                price_elem = card.select_one('.listingPrice, .listing-card__price, .listing-card__details strong')
                price_text = "Price not specified"
                price = 0
                
                if price_elem:
                    price_text = price_elem.text.strip()
                    price_match = re.search(r'£([\d,]+)', price_text) or re.search(r'([\d,]+)', price_text)
                    
                    if price_match:
                        price_str = price_match.group(1).replace(',', '')
                        price = int(price_str)
                        
                        # Convert weekly prices to monthly
                        if 'pw' in price_text.lower():
                            price = price * 4  # Approximate monthly price
                            price_text = f"£{price} pcm (calculated from {price_text})"
                
                # Extract title
                title_elem = card.select_one('h2.listing-result-title, h2.listing-card__title, .listing-card__title')
                title = "Room to rent"
                
                if not title_elem and card.get('data-listing-title'):
                    title = card.get('data-listing-title').replace('&#32;', ' ')
                elif title_elem:
                    title = title_elem.text.strip()
                
                # Extract address
                address_elem = card.select_one('.listingLocation, .listing-card__location')
                address = address_elem.text.strip() if address_elem else ""
                
                # Extract link
                link_elem = card.select_one('a.listing-result-title-link, a.listing-card__link')
                link = link_elem.get('href') if link_elem else ""
                
                # Fix relative URLs
                if link and not link.startswith('http'):
                    link = f"https://www.spareroom.co.uk{link}"
                
                # Extract image
                img_elem = card.select_one('.listing-card__main-image')
                image_url = img_elem.get('src') if img_elem else None

                if image_url and image_url.startswith('//'):
                    image_url = 'https:' + image_url
                    
                images = [image_url] if image_url else []
                
                # Add to listings
                listing = {
                    "id": f"spareroom-{listing_id}",
                    "title": title,
                    "price": price,
                    "price_text": price_text,
                    "address": address,
                    "bedrooms": 1,  # Default value for rooms
                    "link": link,
                    "images": images,
                    "source": "spareroom"
                }
                
                listings.append(listing)
                
            except Exception as e:
                logger.error(f"Error parsing SpareRoom property: {e}")
        
        return listings

class OpenRentAdapter(BaseAdapter):
    """Adapter for OpenRent property site"""
    def __init__(self, config, sort_type="default"):
        super().__init__(config, sort_type)
        self.config = config.get("openrent", {})
        self.base_url = self.config.get("base_url", "https://www.openrent.co.uk")
        self.search_url = self.config.get("search_url", "https://www.openrent.co.uk/properties-to-rent/bristol")
        self.params = self.config.get("params", {})
        
    def get_sort_parameter(self, site_specific=False):
        """Get OpenRent-specific sort parameter
        sortType=1 (price low to high)
        sortType=2 (price high to low)
        no sort type means it's default (distance)
        """
        if site_specific and self.sort_type != "default":
            return self.sort_type
            
        sort_mapping = {
            "price_high_to_low": "sortType=2",
            "price_low_to_high": "sortType=1",
            "default": ""  # Default to distance
        }
        
        return sort_mapping.get(self.sort_type, sort_mapping["default"])
    
    def build_url(self):
        """Build OpenRent search URL"""
        location = self.params.get("location", "bristol")
        min_beds = self.params.get("min_beds", 0)
        max_beds = self.params.get("max_beds", 1)
        min_price = self.params.get("min_price", 0)
        max_price = self.params.get("max_price", 1500)
        accept_non_students = self.params.get("accept-non-students", True)
        is_live = self.params.get("is-live", True)
        furnished_type = self.params.get("furnished-type", "1")
    
        # OpenRent uses a term parameter for location
        location_term = f"{location.capitalize()}, {location.capitalize()}"
        
        # Construct URL with search parameters
        url = f"{self.search_url}?" + \
              f"term={location_term}" + \
              (f"&prices_min={min_price}" if min_price else "") + \
              f"&prices_max={max_price}" + \
              f"&bedrooms_min={min_beds}" + \
              f"&bedrooms_max={max_beds}" + \
              f"&furnishedType={furnished_type}" + \
              (f"&acceptNonStudents={accept_non_students}" if accept_non_students else "") + \
              (f"&isLive={is_live}" if is_live else "")
        
        # Add sorting parameter
        sort_param = self.get_sort_parameter()
        if sort_param:
            url += f"&{sort_param}"
            
        logger.info(f"OpenRent URL: {url}")
        return url
    

    def parse_listings(self, raw_data):
        """Parse OpenRent HTML into listings"""
        listings = []
        soup = BeautifulSoup(raw_data, 'html.parser')
        
        # Try to parse property cards - look for the main container first
        property_cards = soup.select('.lpcc')  # This is the main container class for each property card
        print(f"DEBUG: Found {len(property_cards)} property cards")
        
        for card in property_cards:
            try:
                # Debug: Print the card HTML structure
                print("\nDEBUG: Card HTML structure:")
                print(card.prettify())
                
                # Extract property ID from the carousel
                carousel = card.select_one('.property-row-carousel')
                id_elem = carousel.get('data-listing-id') if carousel else ''
                
                if not id_elem:
                    continue
                
                # Extract price - using the specific structure we found
                price_text = "Price not specified"
                price = 0
                
                # Look for the price in the pim pl-title div
                price_elem = card.select_one('.pim.pl-title h2')
                if price_elem:
                    price_text = price_elem.text.strip()
                    # Extract the numeric value
                    price_match = re.search(r'£([\d,]+)', price_text)
                    if price_match:
                        try:
                            price = int(price_match.group(1).replace(',', ''))
                            # Add "per month" if not present
                            if "per month" not in price_text.lower():
                                price_text = f"£{price} per month"
                        except (ValueError, TypeError):
                            pass
                
                # Extract title
                title_elem = card.select_one('.banda.pt.listing-title')
                title = title_elem.text.strip() if title_elem else ""
                
                # Extract address from title if it contains location info
                address = ""
                if "in" in title.lower():
                    parts = title.split("in")
                    if len(parts) > 1:
                        address = parts[1].strip()
                
                # Extract bedrooms
                beds_elem = card.select_one('.lic li span')
                bedrooms = 1  # Default
                if beds_elem:
                    beds_match = re.search(r'(\d+)\s*Bed', beds_elem.text)
                    if beds_match:
                        bedrooms = int(beds_match.group(1))
                
                # Extract link
                link_elem = card.select_one('.btn.btn-success')
                link = ""
                if link_elem and link_elem.parent:
                    link = f"{self.base_url}/property-to-rent/{self.params.get('location', 'bristol')}/{title.replace(' ', '-').lower().replace(',', '')}/{id_elem}"
                
                # Extract images
                images = []
                img_elems = card.select('.propertyPic.or-lazy-image')
                for img in img_elems:
                    src = img.get('data-src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        images.append(src)
                
                # Create listing
                listing = {
                    "id": f"openrent-{id_elem}",
                    "title": title,
                    "price": price,
                    "price_text": price_text,
                    "address": address,
                    "bedrooms": bedrooms,
                    "link": link,
                    "images": images,
                    "source": "openrent"
                }
                
                listings.append(listing)
                
            except Exception as e:
                logger.error(f"Error parsing OpenRent property: {e}")
        
        logger.info(f"Found {len(listings)} OpenRent listings")
        return listings

if __name__ == "__main__":
    # Default config path
    config_path = "config.json"
    
    # If a config path is provided as a command line argument, use it
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        logger.info(f"Using config file from command line: {config_path}")
    
    # Print information about sorting options
    logger.info("Starting property scraper with the following sorting options available in config.json:")
    logger.info("  - price_high_to_low: Show most expensive properties first")
    logger.info("  - price_low_to_high: Show cheapest properties first")
    logger.info("  - newest_first: Show newest listings first")
    logger.info("  - oldest_first: Show oldest listings first (Rightmove only)")
    logger.info("  - last_updated: Show most recently updated listings first (SpareRoom only)")
    logger.info("  - default: Use site-specific default sorting")
    
    scraper = PropertyScanner(config_path)
    scraper.run_scraper()
    
    
    