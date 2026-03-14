# chef-recs

Restaurant recommendations extracted from food-focused Substack newsletters, displayed on a filterable list + map.

**Live site:** [jcubb.github.io/chef-recs](https://jcubb.github.io/chef-recs)

## Setup

```bash
git clone https://github.com/jcubb/chef-recs.git
cd chef-recs
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Usage

```bash
python run.py              # full pipeline: scrape → extract → geocode → build site
python run.py --build-only # rebuild site from existing data
python run.py --status     # show stats
```

Then push to GitHub — Pages serves from `/docs` automatically.
