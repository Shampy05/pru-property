from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
import json
import os
from datetime import datetime
from scrapper import PropertyScanner

app = Flask(__name__)
app.secret_key = 'property_scraper_secret_key'

# Add context processor for common template variables
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Load favorites from file
def load_favorites():
    if os.path.exists('favorites.json'):
        with open('favorites.json', 'r') as f:
            return json.load(f)
    return {}

# Save favorites to file
def save_favorites(favorites):
    with open('favorites.json', 'w') as f:
        json.dump(favorites, f)

# Homepage - show all current listings
@app.route('/')
def index():
    # Initialize the property scanner
    scanner = PropertyScanner('config.json')
    
    # Get URL parameters for filtering
    min_price = request.args.get('min_price', type=int)
    max_price = request.args.get('max_price', type=int)
    min_beds = request.args.get('min_beds', type=int)
    max_beds = request.args.get('max_beds', type=int)
    
    # Get all listings
    try:
        all_listings = scanner.fetch_listings()
        
        # Apply web interface filters if provided
        filtered_listings = []
        
        for listing in all_listings:
            # Apply price filters
            if min_price is not None and int(listing.get('price', 0)) < min_price:
                continue
            if max_price is not None and int(listing.get('price', 0)) > max_price:
                continue
                
            # Apply bedroom filters
            if min_beds is not None and int(listing.get('bedrooms', 0)) < min_beds:
                continue
            if max_beds is not None and int(listing.get('bedrooms', 0)) > max_beds:
                continue
                
            # All filters passed
            filtered_listings.append(listing)
            
        # Apply server-side filters (keywords, etc.)
        filtered_listings = scanner.filter_listings(filtered_listings)
    except Exception as e:
        flash(f"Error fetching listings: {str(e)}")
        filtered_listings = []
    
    # Load favorites
    favorites = load_favorites()
    
    # Mark listings that are favorites
    for listing in filtered_listings:
        listing['is_favorite'] = listing['id'] in favorites
    
    return render_template('index.html', 
                          listings=filtered_listings,
                          favorites_count=len(favorites))

# View favorites page
@app.route('/favorites')
def favorites():
    favorites = load_favorites()
    favorite_listings = []
    
    # For each favorite, we need to reconstruct the listing information
    # In a real app, you'd store the full listing data
    for listing_id, listing_data in favorites.items():
        favorite_listings.append(listing_data)
    
    return render_template('favorites.html', 
                           listings=favorite_listings,
                           favorites_count=len(favorites))

# Add to favorites
@app.route('/add_favorite', methods=['POST'])
def add_favorite():
    listing_id = request.form.get('listing_id')
    title = request.form.get('title')
    price = request.form.get('price')
    address = request.form.get('address')
    link = request.form.get('link')
    bedrooms = request.form.get('bedrooms')
    images = request.form.getlist('images')
    
    if not listing_id:
        flash('Error: No listing ID provided')
        return redirect(url_for('index'))
    
    # Load current favorites
    favorites = load_favorites()
    
    # Add this listing to favorites
    favorites[listing_id] = {
        'id': listing_id,
        'title': title,
        'price_text': price,
        'address': address,
        'link': link,
        'bedrooms': bedrooms,
        'images': images,
        'added_on': datetime.now().isoformat()
    }
    
    # Save updated favorites
    save_favorites(favorites)
    
    flash('Listing added to favorites')
    return redirect(url_for('index'))

# Remove from favorites
@app.route('/remove_favorite', methods=['POST'])
def remove_favorite():
    listing_id = request.form.get('listing_id')
    
    if not listing_id:
        flash('Error: No listing ID provided')
        return redirect(url_for('favorites'))
    
    # Load current favorites
    favorites = load_favorites()
    
    # Remove this listing from favorites
    if listing_id in favorites:
        del favorites[listing_id]
    
    # Save updated favorites
    save_favorites(favorites)
    
    flash('Listing removed from favorites')
    
    # Determine where to redirect based on the referer
    referer = request.headers.get('Referer', '')
    if 'favorites' in referer:
        return redirect(url_for('favorites'))
    else:
        return redirect(url_for('index'))

# Run scrapers manually
@app.route('/run_scraper', methods=['POST'])
def run_scraper():
    scanner = PropertyScanner('config.json')
    try:
        scanner.run_scraper()
        flash('Scraper run successfully! Check your email for new listings.')
    except Exception as e:
        flash(f'Error running scraper: {str(e)}')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True) 