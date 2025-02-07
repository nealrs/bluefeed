from atproto import Client
from pprint import pprint
from dotenv import load_dotenv
import os
import sqlite3
import shortuuid
import datetime
import boto3
import pytz
from botocore.exceptions import ClientError
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree

def bsClient(login, password):
  client = Client()
  client.login(login, password)
  #print(client)
  return client

def bsFeed(client, feedId):
  data = client.app.bsky.feed.get_feed({
    'feed': feedId, #https://bsky.app/profile/davidsacerdote.bsky.social/feed/aaaixbb5liqbu
    'limit': 100,
  }, headers={'Accept-Language': 'en'})

  feed = data.feed
  return feed

def bsItems(feed):
  #gifts = []
  for item in feed:
    social = (item.post.like_count + item.post.repost_count)
    description = ''
    p = item.post.record
    #print(p.created_at)
    #print(p)
    try:
      # Extract and print links and article titles from embed
      if p.embed is not None and p.embed.external:
        try:
          #print("Title:", p.embed.external.title)
          #print("URL:", p.embed.external.uri)
          #print("Description:", p.embed.external.description)
          title = p.embed.external.title.replace("(Gift Article)", "").strip()
          title = title.replace('â€™', "'").replace('â€œ', '"').replace('â€�', '"').replace('â€˜', "'").replace('â€”', '—')
          
          if title == "":
            title = shortuuid.uuid()
            #gifts.append({"title": title, "url": p.embed.external.uri, "date": p.created_at})
          
          if p.embed.external.description:
            description = p.embed.external.description
            description = description.replace('â€™', "'").replace('â€œ', '"').replace('â€�', '"').replace('â€˜', "'").replace('â€”', '—')
          
          dbAdd(title, description, p.embed.external.uri, p.created_at, social)
        except AttributeError:
          pass
        except sqlite3.IntegrityError as e:
          print(e)
          
    except Exception as e:
      #print(f"Error processing embed: {e}")
      pass
    try:
      # Extract and print links from facets
      if p.facets is not None:
        for facet in p.facets:
          try:
            #print (facet.features)
            if facet.features and hasattr(facet.features, 'uri'):
              title = shortuuid.uuid()
              #print(title) 
              #gifts.append({"title": title, "url": facet.features.uri, "date": p.created_at})
              dbAdd(title, description, p.embed.external.uri, p.created_at, social)
          except AttributeError:
            pass
          except sqlite3.IntegrityError as e:
            print(e)
    except Exception as e:
      #print(f"Error processing facets: {e}")
      pass
  #unique_gifts = {gift['title']: gift for gift in gifts}.values()
  #gifts = list(unique_gifts)
  #gifts.sort(key=lambda x: x['date'], reverse=True)
  #return gifts

def dbInit():
  try:
    with sqlite3.connect(dbFile) as conn:
      conn.execute("""
        CREATE TABLE feed (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL UNIQUE,
          description TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE,
          date DATE NOT NULL,
          social int NOT NULL
        )
      """)
  except sqlite3.OperationalError as e:
    print("-",e)

def dbAdd(title, description, url, date, social):
  try:
    with sqlite3.connect(dbFile) as conn:
      conn.execute("INSERT INTO feed (title, description, url, date, social) VALUES (?, ?, ?, ?, ?)", (title, description, url, date, social))
      print("* Added: ", title, description, social)
  except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
    #print("Failed to insert item:", e)
    pass

def buildRSS(dbFile, blacklist=[]):
  try:
    with sqlite3.connect(dbFile) as conn:
      name = "all"
      cursor = conn.cursor()
      
      if blacklist != []:
        name = "filtered"
        query = "SELECT * FROM feed WHERE " + " AND ".join(["title NOT LIKE ?"] * len(blacklist)) + " ORDER BY social DESC, date DESC"
        cursor.execute(query, ['%' + term + '%' for term in blacklist])
      else:
        query = "SELECT * FROM feed ORDER BY social DESC, date DESC"
        cursor.execute(query)      
      #query = "SELECT * FROM feed ORDER BY date DESC"
      rows = cursor.fetchall()
      
      rss = Element('rss')
      rss.set('version', '2.0')
      rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
      
      channel = SubElement(rss, 'channel')
      
      atom = SubElement(channel, 'atom:link')
      atom.set('href', 'http://nealshyam.com/rss/'+name+'.rss')
      atom.set('rel', 'self')
      atom.set('type', 'application/rss+xml')

      title = SubElement(channel, 'title')
      title.text = "Gift Articles"

      link = SubElement(channel, 'link')
      link.text = 'http://nealshyam.com/rss/'+name+'.rss'

      description = SubElement(channel, 'description')
      description.text = "A RSS feed of free article links from BlueSky. Updated every 15 minutes. "

      for row in rows:
        item = SubElement(channel, 'item')
        
        item_guid = SubElement(item, 'guid')
        item_guid.text = row[3]
        
        item_title = SubElement(item, 'title')
        item_title.text = row[1]
        
        item_description = SubElement(item, 'description')
        item_description.text = row[2]
        
        item_link = SubElement(item, 'link')
        item_link.text = row[3]
        
        item_pubDate = SubElement(item, 'pubDate')
        try:
          item_pubDate.text = datetime.datetime.strptime(row[4], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%a, %d %b %Y %H:%M:%S GMT')
        except ValueError:
          item_pubDate.text = datetime.datetime.strptime(row[4], '%Y-%m-%dT%H:%M:%S%z').strftime('%a, %d %b %Y %H:%M:%S GMT')

      rss_str = tostring(rss, encoding='utf-8').decode('utf-8')
      xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>'
      xml_stylesheet = '<?xml-stylesheet type="text/xsl" href="http://nealshyam.com/rss/rss.xsl"?>' ##  this is probably the worst way to do this...
      return f"{xml_declaration}\n{xml_stylesheet}\n{rss_str}"
  except sqlite3.OperationalError as e:
    print("Failed to fetch items:", e)
    return []

def writeRSS(rss, filename):
  try:
    #s3 = boto3.resource("s3")
    s3 = boto3.client('s3', aws_access_key_id=aws_key, aws_secret_access_key=aws_secret)
    #print("Connected to s3!!")
    
    s3.put_object(
      Bucket=bucket,
      Key="rss/" + filename,
      Body=rss,
      ACL="public-read",
      ContentType="application/rss+xml"
    )
    print("- wrote " + filename + " to s3")
    return True
  except Exception as e:
      print("^error writing "+filename+ " to s3")
      raise
      return

def updateHTML(blacklist):
  html = """
    <html>
    <head>
        <title>RSS feeds of Gift links from Bluesky</title>
        <meta name="robots" content="noindex, nofollow">
        <meta name="description" content="Gift links to popular news articles">
        <meta property="og:title" content="Gift links to popular news articles">
        <meta property="og:description" content="I converted a Blusky feed into an RSS feed.">
        <meta property="og:type" content="website">
        <meta name="author" content="Neal Shyam | @nealrs">
        <link rel="canonical" href="https://nealshyam.com/rss/">
        <meta property="og:url" content="https://nealshyam.com/rss/">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!--<meta property="og:image" content="https://nealshyam.com/img/">-->
        <styles>
        <style>
          body {
            max-width: 80%;
            margin: 0 auto;
            text-align: left;
            font-size: 1.3rem;
            color: 111111;
            background-color: #fffdf5;
          }
          h1, h3{
            color: #38220f;
          }

          a {color: #38220f;}
          a:active, a:hover {color: #967259;}
          table {
            max-width: 70%;
            border-collapse: collapse;
          }
          th, td {
            border: 1px solid #ddd;
            padding: 8px;
            font-size: 1rem;
          }
          th {
            background-color: #f2f2f2;
            text-align: left;
          }
        </style>
    </head>
    <body>
      <div>
        <h2>RSS Feed of gift links</h2>
        <p>I converted <a href="https://bsky.app/profile/davidsacerdote.bsky.social" target="_blank">David Sacerdot's</a> Bluesky feed of <a href="https://bsky.app/profile/davidsacerdote.bsky.social/feed/aaaixbb5liqbu" target="_blank">Gift Links / Articles</a> into an RSS feed.</p>
        
        <p>More info & code at <a href="https://github.com/nealrs/bluefeed">github.com/nealrs/bluefeed</a>.</p>
        
        <p>There are two feeds, which are updated every 20 minutes:</p>

        <p>&bull; <a href="./all.rss" target="_blank">All articles</a></p>
        <p>&bull; <a href="./filtered.rss" target="_blank">Filtered feed</a> &mdash; excludes headlines with these keywords:</p>
        <table id="blacklist"></table>
        <hr>
        <p>&copy; <a href="https://nealshyam.com" target="_blank">Neal Shyam</a></p>      
      </div>
    </body>
    </html>
  """
  if blacklist != []:
    blacklist = sorted(blacklist)
    rows = [blacklist[i:i+3] for i in range(0, len(blacklist), 3)]
    table_rows = ''.join('<tr>' + ''.join(f'<td>{item}</td>' for item in row) + '</tr>' for row in rows)
    html = html.replace('<table id="blacklist"></table>', f'<table id="blacklist">{table_rows}</table>')
  
  try:
    s3 = boto3.client('s3', aws_access_key_id=aws_key, aws_secret_access_key=aws_secret)
    #print("Connected to s3!!")
    s3.put_object(
      Bucket=bucket,
      Key="rss/index.html",
      Body=html,
      ACL="public-read",
      ContentType="text/html"
    )
    print("- wrote index to s3")
    return True
  except Exception as e:
      print("^error writing index to s3")
      raise
      return
    

# OK LET'S DO THIS
print('\n*****************')
print(datetime.datetime.now().astimezone(pytz.timezone('US/Eastern')).strftime('%A, %d-%m-%Y, %I:%M %p %Z'))

## load env vars &setup
load_dotenv()
feedId = os.getenv('feedId')
login = os.getenv('login')
password = os.getenv('password')
dbFile = os.getenv('dbFile')
aws_key = os.getenv('aws_access_key_id')
aws_secret = os.getenv('aws_secret_access_key')
bucket = os.getenv('bucket')
folder='rss/'

# load blacklist
blacklist = []
with open('blacklist.txt', 'r') as file:
  for line in file:
    blacklist.append(line.strip())
#print(blacklist)

## create db & update it with new items
dbInit() # initialize the database & table if it doesen't e  print (blacklist)st    
client = bsClient(login, password) # login to bluesky
feed = bsFeed(client, feedId) # get all feed items
bsItems(feed) # process & insert feed items.

## build feeds from db & save it to s3
rssAll = buildRSS(dbFile) # build the RSS feed
rssFiltered = buildRSS(dbFile, blacklist) # build _filtered_ feed
#print(rssAll)
#print(rssFiltered)

writeRSS(rssAll, 'all.rss')
writeRSS(rssFiltered, 'filtered.rss')
updateHTML(blacklist)

print('*****************\n')