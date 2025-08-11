# This Might Hurt tarot image and description scraper

Gets the images and descriptions of the very wonderful [This Might Hurt tarot deck](https://www.thismighthurttarot.com/). This script:

- Crawls all five “Card Descriptions” pages (Major Arcana, Wands, Cups, Swords, Pentacles)
- Extracts: Card, Suit/Arcana, Subtitle (if any), Description text, and Image URL
- Saves a Notion-ready CSV and an optional images/ folder of downloaded card art

Big thanks to [Isabella Rotman](https://www.isabellarotman.com/) for making such a beautiful deck. All text and images are © Isabella Rotman / This Might Hurt Tarot.

Buy the deck. I have three copies. It's wonderful.

## How to use

1. Make sure you have Python 3.9+
1. `pip install requests beautifulsoup4 lxml pandas tqdm`
1. Save the script below as tmh_tarot_scraper.py
1. Run: `python tmh_tarot_scraper.py`

Outputs:

`this_might_hurt_tarot.csv` — descriptions which you can import into a spreadsheet or into a database tool like Notion)
`images/`
