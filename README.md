# Bluefeed

# What is this?
- This is a dockerized python script.
- It polls a Bluesky feed, like [this feed of article gift links](https://bsky.app/profile/davidsacerdote.bsky.social/feed/aaaixbb5liqbu), and persists title, link, description, and pubDate to a sqllite database.
- It generates _two RSS feeds:
  - [`all.rss`](https://nealshyam.com/rss/all.rss) (self explanatory)
  - [`filtered.rss`](https://nealshyam.com/rss/filtered.rss) (reads from `blacklist.txt` to exclude specific keywords / phrases)
- Feeds are saved to an s3 bucket.
- Script runs every 20 minutes.
- Bluesky & AWS credentials are stored in `.env`.
- You'll need to create a Bluesky app password -- because 2fa.

## Why did you make this?

- 🤷🏽‍♂️ I'm in between jobs and I get bored easily.
- Bluesky added RSS feeds recently, but only for _profiles_. 
- I wanted to test drive Copilot and check how much Python I remembered.
- FWIW, Copilot did help me with things I wasn't sure of & didn't want to spend tons of time figuring out. I guess that's the whole point.
- Yes, my code is a bit sloppy, but it gets the job done.

## Todo
- figure out why the stylesheet isn't working, because RSS is ugly

&copy; [Neal Shyam](https://nealshyam.com) &middot; @nealrs