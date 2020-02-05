# ==================
# PODCAST RSS MIRROR
# ==================
#
# The purpose of this program is to create a mirror podcast RSS feed 
# in the case of a horrible work proxy or something like that.
#
# Usage:
# Set up config file (.ini) and run the program
#
# Requirements
# wget
#
# How it works:
# The program will parse all feeds in the config file, download MP3s,
# host locally and make a nice new feed file (showing only downloaded
# files)
#
# Schedule this with cron or something to make it run daily (or whenever you want)
#
# By a cold-infected Christoffer Rudeklint 2018-01-10
# Changes by Abel 2020-02-05 (config file, date parsing etc)

import os
import sys
import argparse
import configparser
import hashlib

from datetime import datetime, timezone, timedelta
from subprocess import call
from xml.etree import ElementTree as ET

config = configparser.ConfigParser()
try:
  config.read(sys.argv[1])
except IndexError:
  print("Config ini file must be given, as first argument",file=sys.stderr)
  sys.exit(1)

# Simple log function
def logger( message ) :
  with open( config['DEFAULT']['logfile'],'a') as log_file:
    print( 
      datetime.now().replace(microsecond=0).isoformat(" ")  + " " + message , 
      file=log_file
    )
  

# Function to download files. You need wget.
def download_file( input, output ) :
  call( [config['DEFAULT']['wget_binary'] , input, "-qO", output] )

# Main function.
def create_pod_mirror( rss_href, podcast_name, new_base_href, oldest_download_days, min_wait_between_downloads_sec, max_download_episodes, base_directory_save ) :

  # This list contains the episodes which will be removed from
  # the main feed.
  delete_list = []

  logger( "Start mirroring of " + rss_href )
  
  local_pod_dir = os.path.join( base_directory_save , podcast_name )
  local_pod_rss = os.path.join( base_directory_save , podcast_name + ".rss" )
  tmp_podcast_rss = os.path.join( local_pod_dir,podcast_name+".orig")
  
  # Check if the podcast-folder exists. If not, create it.
  if( not os.path.exists( local_pod_dir ) ) :
    os.mkdir( local_pod_dir )

  # If there is a previous file, check if we may download
  try:
    last_download_time = datetime.fromtimestamp(os.path.getmtime(local_pod_rss))

    if( datetime.now() - last_download_time < timedelta(seconds=int(min_wait_between_downloads_sec)) ):
      logger( "Download timeout has not been reached! Exiting" )
      return 0

  except FileNotFoundError:
    logger("No previous file found, continuing")
  
  # Register the namespaces so the resulting XML-file is correct ...
  ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd" )
  ET.register_namespace("atom", "http://www.w3.org/2005/Atom" )
  ET.register_namespace("sr", "http://www.sverigesradio.se/podrss" )
  
  # Download the real RSS to the temporary path. Parse it using ElementTree
  download_file( rss_href, tmp_podcast_rss )
  if os.stat(tmp_podcast_rss).st_size == 0:
    os.unlink(tmp_podcast_rss)
    logger('Empty podcast!')
    return 0
  rss_tree = ET.parse( tmp_podcast_rss )

  root_elem = rss_tree.getroot()
  data_node = root_elem.findall( 'channel' )
  
  # This counter is used if the test-flag is set.
  i=0
  
  for child in data_node[0]:
    # Only "items" in the feed are interesting.
    if( child.tag != "item" ) :
      continue
    
    i+=1
    
    # Max downloads
    if( i > int(max_download_episodes) ) :
      delete_list.append( child )
      continue

    # Get the publication date.
    pub_date = child.findall( "pubDate" )[0]
    datestring = pub_date.text
    
    # Parse the time string to a time-object and calculate the time delta.
    date_obj=None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
      try:
        date_obj=datetime.strptime(datestring, fmt)
      except ValueError:
        pass
    if not date_obj:
      print("FATAL Date fail: "+datestring)
      sys.exit(1)
      raise ValueError('no valid date format found')

    # Get the enclosure node which contains the mp3-link.
    mp3link = child.findall( "enclosure" )[0]
    oldlink = mp3link.get( "url" )
    
    # Get the filename for the mp3-file (used for rewriting the links in the feed).
    link_basename = date_obj.strftime("%Y%m%d-%H%M")+hashlib.md5(oldlink.encode()).hexdigest()+".mp3"
    
    # If the time delta is too large, add this episode to the remove-list.
    try:
      time_delta = datetime.now(tz=date_obj.tzinfo) - date_obj
    except TypeError:
      print("ERROR")
      print(date_obj)
      sys.exit(1)
      return 0

    if( time_delta.days > int(oldest_download_days) ):
      logger("Will not remove too old ep")
      delete_list.append( child )
      continue

    # Create the new web address and the os path for the mp3-files.
    newlink = os.path.join( new_base_href, podcast_name, link_basename )
    local_path = os.path.join( local_pod_dir, link_basename )
    
    # Update the mp3-parameter to the new web address.
    mp3link.set( "url", newlink )
  
    # Check if the file already exists. If it does, skip this episode.
    if( not os.path.isfile( local_path ) ) :
      download_file( oldlink, local_path )  
      logger( "downloading " + link_basename)

  # Remove the unwanted episodes from the feed.
  for deletechild in delete_list:
    data_node[0].remove( deletechild )
  
  # Write the new RSS-feed
  rss_tree.write( local_pod_rss, encoding="UTF-8", xml_declaration=True )

  logger( "Skipped " + str( len( delete_list ) ) + " episodes" )
  logger( "Finished mirroring " + rss_href)


# MAIN ENTRY  
logger("==START==")
for podcast_name in config.sections():
  podcast=config[podcast_name]
  logger("Process "+podcast_name)
  create_pod_mirror( 
          podcast['href'], 
          podcast_name, 
          podcast['new_location_base'],
          podcast['oldest_download_days'],
          podcast['min_wait_between_downloads_sec'],
          podcast['max_download_episodes'],
          podcast['base_directory_save'],
  )
logger("==END==\n")
