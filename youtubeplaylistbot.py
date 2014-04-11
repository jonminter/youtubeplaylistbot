# YouTube Playlist Bot
# Maintains a YouTube playlist that contains all submissions to a set of sub-reddits that are YouTube links


"""YouTube Playlist Reddit Bot
Usage:
  $ python youtubeplaylistbot.py

You can also get help on all the command-line flags the program understands
by running:

  $ python youtubeplaylistbot.py --help

"""

__author__ = 'Jon Minter (jdiminter@gmail.com)'
__version__ = '1.0a'

import time
import datetime
import sqlite3
import praw
import logging
import settings
import urllib
from pprint import pprint
import re
import httplib

import argparse
import httplib2
import os
import sys
import requests.exceptions

import apiclient.errors
from apiclient import discovery
from oauth2client import file
from oauth2client import client
from oauth2client import tools

SCRIPT_NAME = os.path.basename(__file__)
SQLITE_FILENAME = 'youtubeplaylistbot.db'
SQLITE_CREATE_SCHEMA_TEST = "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='reddit_submissions_processed'"
REDDIT_USER_AGENT = 'YoutubePlaylistBot by /u/codeninja84 v 1.0a https://github.com/jonminter/youtubeplaylistbot'
REDDIT_PLAY_CATCHUP = False
REDDIT_SUBMISSION_CATCHUP_LIMIT = 1000
REDDIT_SUBMISSION_LIMIT = 100
REDDIT_SUBMISSION_GET_TRY_LIMIT = 10
REDDIT_SLEEP_INTERVAL = 120
REDDIT_SLEEP_MAX_INTERVAL = 3600
GOOGLE_USER_AGENT = 'Reddit YoutubePlaylistBot'
GOOGLE_OAUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_OAUTH_REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'
GOOGLE_OAUTH_SCOPE = 'https://www.googleapis.com/auth/youtube'
GOOGLE_OAUTH_TOKEN_VARIABLE = 'gdata_oauth2_token'
YOUTUBE_VIDEO_ID_REGEX_LIST = [
	re.compile(r'youtube(?:-nocookie)?\.com/watch[#\?].*?v=(?P<video_id>[^"\& ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/embed/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/v/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/\?v=(?P<video_id>[^"\& ]+)'),
	re.compile(r'youtu\.be/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'gdata\.youtube\.com/feeds/api/videos/(?P<video_id>[^"\&\? ]+)')
]

# Opens the connection to the SQLite3 database and tests to see if the schema needs to be
# created or updated and performs queries to update the schema if neccessary
def get_db_connection():
	db_connection = sqlite3.connect(SQLITE_FILENAME)
	
	#test to see if we need to run schema.sql
	result = db_connection.execute(SQLITE_CREATE_SCHEMA_TEST)
	if result.fetchone() is None:
		sql_schema = open('schema.sql').read()
		db_cursor = db_connection.cursor()
		db_cursor.executescript(sql_schema)
	return db_connection

# Adds the specified video to the playlist using the YouTube Data API object
def add_video_to_playlist(yt_service, playlist_id, video_id):
	try:
		add_video_request=yt_service.playlistItems().insert(
			part="snippet",
			body={
				'snippet': {
					'playlistId': playlist_id, 
					'resourceId': {
						'kind': 'youtube#video',
						'videoId': video_id
					}
					#'position': 0
				}
			}
		).execute()
		return add_video_request
	except (IOError,httplib.HTTPException,apiclient.errors.HttpError) as e:
		logging.warning("Http error occurred when trying to add video '" + video_id + "' to playlist '" + playlist_id + "'. Message: " + str(e))
		return False

# Parses a YouTube URL and retrieves the Video ID from that URL.
# Uses a set of regular expressions to parse many different forms of YouTube video URLs.
def get_youtube_video_id_from_url(url):
	for regex in YOUTUBE_VIDEO_ID_REGEX_LIST:
		match = regex.search(url)
		if match:
			return match.group('video_id')

# Method to run the logic for the bot. Connects to the Reddit API and periodically polls the API to get the latest submissions to the subreddits
# that the bot is watching. It loops through those submissions and for the ones that have not been processed yet if they are links to youtube
# it adds the videos to a playlist.
def run_bot(yt_service):
	db_connection = get_db_connection()
	db_cursor = db_connection.cursor()
	r = praw.Reddit(REDDIT_USER_AGENT)
	r.login(settings.reddit['username'], settings.reddit['password'])
	first_pass = True
	play_catchup = REDDIT_PLAY_CATCHUP
	current_sleep_interval = REDDIT_SLEEP_INTERVAL
	while True:
		pass_start_time = time.time()
		multireddit = '+'.join(settings.reddit['subreddits'])
		subreddit = r.get_subreddit(multireddit)
		current_pull_limit = REDDIT_SUBMISSION_CATCHUP_LIMIT if first_pass and play_catchup else REDDIT_SUBMISSION_LIMIT
		first_pass = False

		try:
			for submission in subreddit.get_new(limit=current_pull_limit):
				# make sure the sleep interval is reset since we have a successful request
				current_sleep_interval = REDDIT_SLEEP_INTERVAL

				logging.debug('Submission -> ID: ' + submission.id + ', URL: ' + submission.url)
				sql_result = db_cursor.execute('SELECT COUNT(submission_id) FROM reddit_submissions_processed WHERE submission_id = ?', [submission.id])
				submission_processed = db_cursor.fetchone()
				
				if submission_processed[0] == 0:
					logging.debug('Submission not processed yet')
					is_youtube_link = False
					youtube_video_id = get_youtube_video_id_from_url(submission.url)
					add_video_success = False
					if youtube_video_id:
						is_youtube_link = True
						logging.debug('YouTube Video ID: ' + youtube_video_id)
						add_video_result = add_video_to_playlist(yt_service, settings.google['youtube']['playlist_id'], youtube_video_id)
						logging.debug('Add video result = ' + str(add_video_result));
						if add_video_result != False:
							add_video_success = True
					else:
						logging.debug('Not a YouTube link')
					if is_youtube_link == False or add_video_success == True:
						db_cursor.execute("INSERT INTO reddit_submissions_processed (submission_id, url) values (?,?)", (submission.id, submission.url))
					db_connection.commit()
				else:
					logging.debug('Submission already processed')
		except requests.exceptions.HTTPError as e:
			logging.error('HTTP error occurred trying to load reddit submissions: ' + str(e))
			# double the wait time every time we get an HTTP error until we hit the max wait interval
			# to prevent from continuing to hit the server frequently if it's down or busy
			# sleep interval will reset with a successful query
			if current_sleep_interval < REDDIT_SLEEP_MAX_INTERVAL:
				current_sleep_interval += current_sleep_interval
			logging.debug('Waiting ' + str(datetime.timedelta(seconds=current_sleep_interval)) + ' to try next request')

		pass_total_time = time.time() - pass_start_time
		logging.debug('Pass through last ' + str(current_pull_limit) + ' submissions took ' + str(datetime.timedelta(seconds=pass_total_time)))
		time.sleep(current_sleep_interval)


# Setup logging
logging.basicConfig(filename=SCRIPT_NAME + '.log',level=settings.logging['level'])
logger = logging.getLogger()
logger.disabled = settings.logging['disabled']

# Parser for command-line arguments.
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[tools.argparser])


# CLIENT_SECRETS is name of a file containing the OAuth 2.0 information for this
# application, including client_id and client_secret. You can see the Client ID
# and Client secret on the APIs page in the Cloud Console:
# <https://cloud.google.com/console#/project/233647656699/apiui>
CLIENT_SECRETS = os.path.join(os.path.dirname(__file__), 'client_secrets.json')

# Set up a Flow object to be used for authentication.
# Add one or more of the following scopes. PLEASE ONLY ADD THE SCOPES YOU
# NEED. For more information on using scopes please see
# <https://developers.google.com/+/best-practices>.
FLOW = client.flow_from_clientsecrets(CLIENT_SECRETS,
  scope=[
      'https://www.googleapis.com/auth/youtube',
      'https://www.googleapis.com/auth/youtube.readonly',
      'https://www.googleapis.com/auth/youtube.upload',
      'https://www.googleapis.com/auth/youtubepartner',
      'https://www.googleapis.com/auth/youtubepartner-channel-audit',
    ],
    message=tools.message_if_missing(CLIENT_SECRETS))


def main(argv):
  # Parse the command-line flags.
  flags = parser.parse_args(argv[1:])

  # If the credentials don't exist or are invalid run through the native client
  # flow. The Storage object will ensure that if successful the good
  # credentials will get written back to the file.
  storage = file.Storage('youtubeplaylistbot_credentials.dat')
  credentials = storage.get()
  if credentials is None or credentials.invalid:
    credentials = tools.run_flow(FLOW, storage, flags)

  # Create an httplib2.Http object to handle our HTTP requests and authorize it
  # with our good Credentials.
  http = httplib2.Http()
  http = credentials.authorize(http)

  # Construct the service object for the interacting with the YouTube Data API.
  service = discovery.build('youtube', 'v3', http=http)

  try:
    run_bot(service)

  except client.AccessTokenRefreshError:
    print ("The credentials have been revoked or expired, please re-run"
      "the application to re-authorize")


# For more information on the YouTube Data API you can visit:
#
#   https://developers.google.com/youtube/v3
#
# For more information on the YouTube Data API Python library surface you
# can visit:
#
#   https://developers.google.com/resources/api-libraries/documentation/youtube/v3/python/latest/
#
# For information on the Python Client Library visit:
#
#   https://developers.google.com/api-client-library/python/start/get_started
if __name__ == '__main__':
  main(sys.argv)