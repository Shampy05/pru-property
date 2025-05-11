# Property Scraper & Web Interface

A flexible property listing scraper and web application that monitors multiple property sites (Rightmove, Spareroom, OnTheMarket, OpenRent) for new listings matching your criteria. It includes a Flask web interface to view listings, manage favorites, and trigger the scraper.

## Features

**Scraper (`scrapper.py`):**
- Scrapes property listings from multiple configurable property sites.
- Filters results based on criteria defined in `config.json` (keywords, price, beds).
- Supports sorting of listings (e.g., by price, date).
- Notifies users via email (configurable) about new properties.
- Keeps track of seen listings in `seen_listings.csv` to avoid duplicates.
- Highly configurable via `config.json`.

**Web Interface (`app.py`):**
- Displays scraped listings in a user-friendly web page.
- Allows filtering of displayed listings by price and number of bedrooms.
- Feature to add/remove listings from a 'Favorites' list (stored in `favorites.json`).
- Separate page to view favorited listings.
- Button to manually trigger the scraper script.
- Built with Flask and Bootstrap.

## Setup

1.  **Clone Repository:**
    ```bash
    git clone <repository_url>
    cd property_scraper
    ```
2.  **Install Dependencies:**
    Ensure you have Python 3 installed.
    ```bash
    pip install requests beautifulsoup4 Flask
    ```
3.  **Configuration:**
    *   Copy `config_sample.json` (if one exists) or create `config.json`.
    *   Adjust settings in `config.json` to your preferences. See the "Configuration (`config.json`)" section below for details.
    *   Ensure `favorites.json` exists (it can be an empty JSON object `{}` initially).

## Running the Application

There are two main components: the scraper and the web application.

### 1. Running the Scraper (Command Line)

The scraper can be run independently to fetch and process listings according to `config.json`.
```bash
python3 scrapper.py
```
You can optionally provide a path to a different config file:
```bash
python3 scrapper.py path/to/your/config.json
```
The scraper will log its activities to the console and send email notifications if configured.

### 2. Running the Web Application

The web application provides a UI to view listings and interact with the scraper.
```bash
python3 app.py
```
Open your web browser and go to `http://127.0.0.1:5000/` (or the address shown in the console).

## Configuration (`config.json`)

The `config.json` file is central to customizing the scraper's behavior.

```json
{
  "sort_type": "newest_first", // Global sort preference
  "sites": {
    "rightmove": {
      "enabled": true,
      "params": {
        "location_identifier": "REGION^219", // Example: Bristol
        "radius": 0.0,
        "min_price": 0,
        "max_price": 1200,
        "min_beds": 0,
        "max_beds": 1,
        "include_let_agreed": false,
        "dont_show": "houseShare,student,retirement", // Comma-separated types to exclude
        "let_type": "shortTerm" // e.g., shortTerm, longTerm
        // ... other site-specific params
      }
    },
    "spareroom": {
      "enabled": true,
      "search_url": "https://www.spareroom.co.uk/flatshare/?search_id=YOUR_SEARCH_ID&mode=list", // IMPORTANT: Use your own search URL
      "params": {}
    },
    "onthemarket": {
      "enabled": true,
      "params": {
        "location": "bristol",
        // ... other params
      }
    },
    "openrent": {
      "enabled": true,
      "params": {
        "location": "bristol",
        // ... other params
      }
    },
    "zoopla": {
      "enabled": false, // Example of a disabled site
      "params": {}
    }
    // ... other sites like gumtree (if configured)
  },
  "filters": { // Global filters applied after fetching
    "keywords": [], // e.g., ["garden", "balcony"]
    "exclude_keywords": ["student"],
    "min_price": null, // Overrides site-specific if set
    "max_price": 1200,
    "min_beds": 0,
    "max_beds": 1
  },
  "notifications": {
    "method": "email",
    "email": {
      "smtp_server": "smtp.gmail.com",
      "smtp_port": 465,
      "username": "your_email@gmail.com",
      "password": "your_app_password",
      "sender": "your_email@gmail.com",
      "recipient": "your_email@gmail.com"
    }
  },
  "debug": {
    "bypass_seen_check": false,
    "log_level": "info" // "debug" for more verbose output
  },
  "schedule": { // (Currently informational, not implemented for auto-runs)
    "frequency": "hourly"
  }
}
```

**Key Configuration Sections:**

*   **`sort_type`**: Defines the default sorting for listings across all sites.
    *   `"price_high_to_low"`: Most expensive first.
    *   `"price_low_to_high"`: Cheapest first.
    *   `"newest_first"`: Newest listings first (default for Rightmove and SpareRoom if not specified).
    *   `"oldest_first"`: Oldest listings first (Rightmove only).
    *   `"last_updated"`: Most recently updated (SpareRoom only).
    *   `"default"`: Site-specific default (e.g., recommended for OnTheMarket).
*   **`sites`**: Configure each property site.
    *   Set `"enabled": true` to scrape a site, `false` to disable.
    *   `"params"`: Site-specific search parameters. Consult each site's URL structure to find relevant parameters.
        *   **Rightmove specific**: `dont_show` (e.g., "houseShare,student") and `let_type` (e.g., "shortTerm").
        *   **SpareRoom specific**: It's often best to perform a search on SpareRoom with your desired filters, then copy the full search URL into `search_url`.
*   **`filters`**: Global filters applied *after* listings are fetched. These can further refine results from all enabled sites.
*   **`notifications`**: Setup email alerts. For Gmail, you might need to use an "App Password".
*   **`debug`**:
    *   `bypass_seen_check`: Set to `true` to re-process all listings, ignoring `seen_listings.csv`.
    *   `log_level`: Set to `"debug"` for detailed logs.

## Web Interface Features

The web interface (`app.py`) provides:

*   **Homepage (`/`)**:
    *   Displays listings fetched by the scraper.
    *   Filter controls for Min/Max Price and Min/Max Bedrooms (these filters apply to the currently displayed set of listings).
*   **Favorites (`/favorites`)**:
    *   View listings you've marked as favorites.
    *   Remove listings from favorites.
*   **Add to Favorites**: Button on each listing card on the homepage.
*   **Run Scraper**: A button in the navigation bar to manually trigger `scanner.run_scraper()`. Results (new listings) will typically be sent via email if configured.

## Adapters

The scraper uses site-specific adapter classes (e.g., `RightmoveAdapter`, `SpareroomAdapter`) found in `scrapper.py` to handle the nuances of each property website. Currently supported and configured adapters include:
- `RightmoveAdapter`
- `SpareroomAdapter`
- `OnTheMarketAdapter`
- `OpenRentAdapter`
- `ZooplaAdapter` (can be enabled in `config.json`)

## File Structure

```
/
|-- scrapper.py             # Main scraper script
|-- app.py                  # Flask web application
|-- config.json             # Configuration for the scraper and sites
|-- seen_listings.csv       # Stores IDs of listings already processed
|-- favorites.json          # Stores favorited listings from the web UI
|-- README.md               # This file
|-- requirements.txt        # (Recommended) For project dependencies
|-- static/                 # Static files for web app (CSS, JS, images)
|   |-- css/
|       |-- style.css
|-- templates/              # HTML templates for Flask app
|   |-- base.html           # Base template
|   |-- index.html          # Homepage listings
|   |-- favorites.html      # Favorites page
|-- config_sample.json      # (Recommended) Example configuration file
```

## Testing (Legacy)

The `README.md` previously mentioned a `test_scraper.py`. If this script is still in use or relevant, its documentation can be re-integrated here. Otherwise, testing is primarily done by running the main `scrapper.py` or interacting with the web UI.

## Troubleshooting

*   **AttributeError during startup**: Ensure `self.sort_type` is initialized before `self.adapters` in `PropertyScanner.__init__` (this was a recent fix).
*   **No listings found**:
    *   Check `config.json` for correct site parameters and ensure the site is enabled.
    *   Set `log_level: "debug"` in `config.json` and observe `scrapper.py` output for errors or empty results from sites.
    *   The `dont_show` and `let_type` parameters for Rightmove might be too restrictive.
*   **Email notifications not working**: Verify SMTP settings in `config.json`. For Gmail, ensure "Less secure app access" is enabled or use an App Password.
*   **Web interface issues**: Check the Flask console output for errors when running `app.py`.

## License

This project is open source and available for personal use. 