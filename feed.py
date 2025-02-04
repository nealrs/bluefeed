from atproto import Client
from pprint import pprint
from dotenv import load_dotenv
import os
import sqlite3
import shortuuid
import datetime
import boto3
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
    p = item.post.record
    #print(p.created_at)
    #print(p)
    try:
      # Extract and print links and article titles from embed
      if p.embed is not None and p.embed.external:
        try:
          #print("Title:", p.embed.external.title)
          #print("URL:", p.embed.external.uri)
          title = p.embed.external.title.replace("(Gift Article)", "").strip()
          if title == "":
            title = shortuuid.uuid()
          #gifts.append({"title": title, "url": p.embed.external.uri, "date": p.created_at})
          dbAdd(title, p.embed.external.uri, p.created_at, social)
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
              dbAdd(title, p.embed.external.uri, p.created_at, social)
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
          url TEXT NOT NULL UNIQUE,
          date DATE NOT NULL,
          social int NOT NULL
        )
      """)
  except sqlite3.OperationalError as e:
    print("Failed to create table:", e)

def dbAdd(title, url, date, social):
  try:
    with sqlite3.connect(dbFile) as conn:
      conn.execute("INSERT INTO feed (title, url, date, social) VALUES (?, ?, ?, ?)", (title, url, date, social))
  except sqlite3.OperationalError as e:
    print("Failed to insert item:", e)
    #pass

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
      atom.set('href', 'http://www.nealshyam.com/rss/'+name+'.rss')
      atom.set('rel', 'self')
      atom.set('type', 'application/rss+xml')

      title = SubElement(channel, 'title')
      title.text = "Gift Articles"

      link = SubElement(channel, 'link')
      link.text = 'http://www.nealshyam.com/rss/'+name+'.rss'

      description = SubElement(channel, 'description')
      description.text = "A RSS feed of free article links from BlueSky"

      for row in rows:
        item = SubElement(channel, 'item')
        
        item_title = SubElement(item, 'guid')
        item_title.text = row[2]
        
        item_title = SubElement(item, 'title')
        item_title.text = row[1]
        
        item_link = SubElement(item, 'link')
        item_link.text = row[2]
        
        item_pubDate = SubElement(item, 'pubDate')
        try:
          item_pubDate.text = datetime.datetime.strptime(row[3], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%a, %d %b %Y %H:%M:%S GMT')
        except ValueError:
          item_pubDate.text = datetime.datetime.strptime(row[3], '%Y-%m-%dT%H:%M:%S%z').strftime('%a, %d %b %Y %H:%M:%S GMT')

      rss_str = tostring(rss, encoding='utf-8').decode('utf-8')
      xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>'
      xml_stylesheet = '<?xml-stylesheet type="text/xsl" href="rss.xsl"?>' ##  this is probably the worst way to do this...
      return f"{xml_declaration}\n{xml_stylesheet}\n{rss_str}"
  except sqlite3.OperationalError as e:
    print("Failed to fetch items:", e)
    return []

def writeRSS(rss, filename):
  try:
    #s3 = boto3.resource("s3")
    s3 = boto3.client('s3', aws_access_key_id=aws_key, aws_secret_access_key=aws_secret)
    print("Connected to s3!!")
    
    s3.put_object(
      Bucket=bucket,
      Key="rss/" + filename,
      Body=rss,
      ACL="public-read",
      ContentType="application/rss+xml"
    )
    print("uploaded " + filename + " to s3")
    return True
  except Exception as e:
      print("Error saving "+filename+ " to s3")
      raise
      return

# OK LET'S DO THIS
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